"""A loopback-only local web page in front of the AEC operations.

The page exists so a reviewer can pick a fixture pair, measure it, read the
report with its evidence cards, re-verify it and export it without a terminal.
It is not a hosted service and it has no accounts: the server binds loopback
only, mints one random token per process, and refuses every state change that
does not present that token.

Nothing here imports an engine module or runs a subprocess. Every measurement
is the same :mod:`aec.ops` call the command line and the assistant server make,
so the surfaces cannot disagree.

The security shape, in one list:

* the bind address is checked against a loopback allowlist before a socket is
  opened, and there is no switch that widens it;
* a request must address the server by one of its own loopback names on the
  bound port, so a page on another host name cannot reach it by DNS rebinding;
* a run id is 32 lowercase hex digits, a file name matches ``[A-Za-z0-9._-]+``,
  and every requested file, its folder and the run's report must resolve
  directly inside the run, which also catches a symlink pointing outside it;
* a card is served only while its bytes hash to the digest the report recorded,
  so a file edited after the run is refused;
* every error leaves through one redacted JSON answer and the detail goes to
  standard error;
* every response carries the same four security headers, including the 404 and
  the base class's own refusals;
* there is no JavaScript, no remote asset and no directory listing.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import secrets
import shutil
import socket
import sys
import threading
import traceback
import uuid
import webbrowser
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, NoReturn, cast
from urllib.parse import parse_qs, quote, urlsplit

from aec import ops, tool_registry
from aec.evidence import load_report
from aec.ops import OpsError
from aec.redact import redact
from aec.viewer import render_report_html

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
MAX_BODY_BYTES = 64 * 1024
# A body this module refuses is still read and dropped up to this many bytes:
# closing a socket with unread bytes in its receive buffer makes the operating
# system send a reset, which can destroy the refusal the client has not read.
MAX_DRAIN_BYTES = 1 << 20
RUN_ID = re.compile(r"^[0-9a-f]{32}$")
SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")
FORM_TYPE = "application/x-www-form-urlencoded"
CONTENT_SECURITY_POLICY = (
    "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; "
    "form-action 'self'"
)
SECURITY_HEADERS: tuple[tuple[str, str], ...] = (
    ("Content-Security-Policy", CONTENT_SECURITY_POLICY),
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "no-referrer"),
    ("Cache-Control", "no-store"),
    ("X-Frame-Options", "DENY"),
)
HTML_TYPE = "text/html; charset=utf-8"
JSON_TYPE = "application/json"

_RUN_PAGE = re.compile(r"/run/(?P<run_id>[^/]+)")
_CARD = re.compile(r"/run/(?P<run_id>[^/]+)/card/(?P<name>[^/]+)")
_EXPORT_FILE = re.compile(r"/run/(?P<run_id>[^/]+)/export/(?P<name>[^/]+)")
_VERIFY = re.compile(r"/run/(?P<run_id>[^/]+)/verify")
_EXPORT = re.compile(r"/run/(?P<run_id>[^/]+)/export")

PAGE_CSS = """
body { margin: 0; background: #f7f7f9; color: #16181d;
  font: 15px/1.5 "Segoe UI", system-ui, sans-serif; }
main { max-width: 1080px; margin: 0 auto; padding: 32px 20px 64px; }
h1 { font-size: 24px; margin: 0 0 8px; }
h2 { font-size: 18px; margin: 0 0 10px; }
section { margin-top: 28px; }
.lede, .note { color: #545a66; margin: 0 0 12px; }
table { width: 100%; border-collapse: collapse; background: #ffffff; }
th, td { border: 1px solid #d7dbe3; padding: 8px; text-align: left;
  vertical-align: top; }
th { background: #eceff4; font-weight: 600; white-space: nowrap; }
code { font: 13px/1.4 Consolas, ui-monospace, monospace; }
pre { margin: 0; font: 12px/1.4 Consolas, ui-monospace, monospace;
  white-space: pre-wrap; word-break: break-word; }
form { margin: 0; }
label { margin-right: 10px; }
button { padding: 6px 14px; border: 1px solid #16181d; border-radius: 4px;
  background: #16181d; color: #f7f7f9; font: inherit; cursor: pointer; }
a { color: #12467a; }
.ok { color: #1b5e20; font-weight: 600; }
.reasons { color: #8a1f11; }
"""

# Added to the viewer's own document, not to the pages this module builds, so
# the viewer's look is untouched and only the bar is new.
APP_CSS = """
.appbar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center;
  margin: 0; padding: 10px 20px; background: #16181d; color: #f7f7f9;
  font: 14px/1.4 "Segoe UI", system-ui, sans-serif; }
.appbar a { color: #f7f7f9; text-decoration: none; font-weight: 600; }
.appbar .pair { color: #b9c0cc; }
.appbar form { margin: 0 0 0 auto; }
.appbar form + form { margin-left: 8px; }
.appbar button { padding: 5px 12px; border: 1px solid #b9c0cc; border-radius: 4px;
  background: #f7f7f9; color: #16181d; font: inherit; cursor: pointer; }
"""


class WebAppError(ValueError):
    """The app refuses to start with this configuration."""


class _HttpError(Exception):
    """A refusal that becomes a JSON answer carrying this status."""

    def __init__(
        self, status: int, message: str, *, allow: str | None = None
    ) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.allow = allow


@dataclass(frozen=True)
class _State:
    """What one server process needs to answer a request."""

    workspace: Path
    fixtures: Path
    token: str


class WebServer(ThreadingHTTPServer):
    """The threaded server, carrying the session state the handler reads."""

    daemon_threads = True
    # On Windows SO_REUSEADDR lets a second local socket bind a port that is
    # already listening, and which one receives a connection is undefined. The
    # page defaults to an ephemeral port, so nothing is gained by sharing one.
    allow_reuse_address = False

    def __init__(self, address: tuple[str, int], state: _State) -> None:
        self.state = state
        # A "::1" bind needs the IPv6 family; the default is IPv4 only.
        if ":" in address[0]:
            self.address_family = socket.AF_INET6
        super().__init__(address, _Handler)

    @property
    def token(self) -> str:
        """The per-process session token every state change must present."""
        return self.state.token

    @property
    def workspace(self) -> Path:
        return self.state.workspace

    @property
    def fixtures(self) -> Path:
        return self.state.fixtures


class _Handler(BaseHTTPRequestHandler):
    """One request: dispatch, guard, and answer with the same headers each time."""

    server_version = "aec-webapp"
    sys_version = ""
    protocol_version = "HTTP/1.1"
    # A local client that stalls mid-request must not hold a handler thread.
    timeout = 5
    # Whether this request's body has been read or dropped. Reset per request.
    body_consumed: bool = False

    @property
    def state(self) -> _State:
        return cast(WebServer, self.server).state

    def handle_one_request(self) -> None:
        # One handler instance serves every request on a kept-alive connection,
        # so the "is this request's body consumed" flag starts each one fresh.
        self.body_consumed = False
        super().handle_one_request()

    def do_GET(self) -> None:
        self._guard("GET")

    def do_POST(self) -> None:
        self._guard("POST")

    def send_error(
        self, code: int, message: str | None = None, explain: str | None = None
    ) -> None:
        """Answer a base-class refusal with the same headers and a JSON body."""
        self._drain_unread()
        self._json(code, {"error": _status_text(code)}, close=True)

    def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
        """One line per request, with the query string dropped.

        The token travels in the query string of the redirect, so logging
        ``self.path`` unchanged would write the session secret to stderr.
        """
        path = self.path.split("?", 1)[0]
        sys.stderr.write(f"{self.address_string()} {self.command} {path} {code}\n")

    def log_error(self, format: str, *args: Any) -> None:
        sys.stderr.write(self._clean(format % args) + "\n")

    def _clean(self, text: str) -> str:
        """Redact absolute paths and this session's token from a message."""
        return redact(text, secrets=(self.state.token,))

    def _guard(self, method: str) -> None:
        try:
            self._dispatch(method)
        except _HttpError as error:
            self._drain_unread()
            extra = () if error.allow is None else (("Allow", error.allow),)
            self._json(error.status, {"error": error.message}, extra=extra, close=True)
        except OpsError as error:
            self._drain_unread()
            sys.stderr.write(self._clean(str(error)) + "\n")
            self._json(400, {"error": self._clean(str(error))}, close=True)
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True
        except TimeoutError:
            # The client stalled; the connection, not the app, is the problem.
            self.close_connection = True
        except Exception as error:
            self._drain_unread()
            sys.stderr.write(traceback.format_exc())
            sys.stderr.flush()
            message = self._clean(str(error)) or "internal error"
            self._json(500, {"error": message}, close=True)

    def _dispatch(self, method: str) -> None:
        self._require_host()
        path = urlsplit(self.path).path
        if _unsafe_path(path):
            raise _HttpError(400, "refused request path")
        if method == "GET":
            self._get(path)
        else:
            self._post(path)

    def _require_host(self) -> None:
        """Refuse a request that did not address this server by its own name.

        A browser sends the name it used. A page on another origin that has
        rebound its own name to this loopback address sends *that* name, and
        could otherwise read the token off ``/`` and drive the POST actions
        with it. Only the three loopback names on the port this socket is
        bound to are accepted, so the rebinding page is refused before
        dispatch.
        """
        port = cast(WebServer, self.server).server_port
        allowed = {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}
        if self.headers.get("Host", "").lower() not in allowed:
            raise _HttpError(403, "request host is not allowed")

    def _get(self, path: str) -> None:
        if path == "/":
            self._page(200, _index_page(self.state))
            return
        if path == "/tools":
            self._page(200, _tools_page())
            return
        if path == "/healthz":
            self._json(200, {"ok": True})
            return
        match = _RUN_PAGE.fullmatch(path)
        if match is not None:
            self._run_page(match.group("run_id"))
            return
        match = _CARD.fullmatch(path)
        if match is not None:
            self._card(match.group("run_id"), match.group("name"))
            return
        match = _EXPORT_FILE.fullmatch(path)
        if match is not None:
            self._export_file(match.group("run_id"), match.group("name"))
            return
        self._refuse(path, method="GET")

    def _post(self, path: str) -> None:
        action = self._post_action(path)
        form = self._form()
        self._require_token(form.get("token", ""))
        action(form)

    def _post_action(self, path: str) -> Callable[[dict[str, str]], None]:
        """The action a POST path names, resolved before its body is read."""
        if path == "/measure":
            return self._measure
        match = _VERIFY.fullmatch(path)
        if match is not None:
            run_id = match.group("run_id")
            return lambda form: self._verify(run_id)
        match = _EXPORT.fullmatch(path)
        if match is not None:
            run_id = match.group("run_id")
            return lambda form: self._export(run_id)
        self._refuse(path, method="POST")

    def _refuse(self, path: str, *, method: str) -> NoReturn:
        """405 for a known path with the other method, 404 for anything else."""
        if method == "GET" and _is_post_path(path):
            raise _HttpError(405, "method not allowed", allow="POST")
        if method == "POST" and _is_get_path(path):
            raise _HttpError(405, "method not allowed", allow="GET")
        raise _HttpError(404, "not found")

    def _form(self) -> dict[str, str]:
        """The submitted fields, or an empty mapping when there is no form.

        A body is only read when its declared size and type are the ones this
        app accepts; anything else yields no fields, and a request without
        fields has no token, which the caller refuses with 403. The one answer
        given before the token check is a body above the cap, because that is a
        resource limit rather than an identity one.
        """
        # Every path here either reads the body, drops it, or establishes that
        # there is none, so the body is accounted for from this point on.
        self.body_consumed = True
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            return {}
        try:
            length = int(raw_length)
        except ValueError:
            return {}
        if length < 0:
            return {}
        if length > MAX_BODY_BYTES:
            self._drain(length)
            raise _HttpError(413, "request body too large")
        kind = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if kind != FORM_TYPE:
            self._drain(length)
            return {}
        raw = self.rfile.read(length)
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return {}
        parsed = parse_qs(text, keep_blank_values=True)
        return {name: values[-1] for name, values in parsed.items() if values}

    def _drain(self, length: int) -> None:
        """Read and drop a body that is being refused, within a fixed bound.

        Reading the bytes before answering keeps the refusal readable; the
        bound means an enormous body costs a fixed amount and then the socket
        is reset rather than buffered.
        """
        remaining = min(length, MAX_DRAIN_BYTES)
        while remaining > 0:
            chunk = self.rfile.read(min(remaining, 64 * 1024))
            if not chunk:
                return
            remaining -= len(chunk)

    def _drain_unread(self) -> None:
        """Drop a request body nobody read, before an error answer closes.

        A server that closes with unread bytes in its receive buffer makes the
        operating system send a reset, and that reset can destroy the answer the
        client has not read yet: a refused POST whose body was never consumed
        would otherwise reach the caller as a dropped connection.
        """
        if self.body_consumed or self.command != "POST":
            return
        self.body_consumed = True
        raw = self.headers.get("Content-Length")
        if raw is None:
            return
        try:
            length = int(raw)
        except ValueError:
            return
        if length > 0:
            self._drain(length)

    def _require_token(self, provided: str) -> None:
        token = self.state.token
        if (
            not provided
            or not provided.isascii()
            or not secrets.compare_digest(provided, token)
        ):
            raise _HttpError(403, "a valid session token is required")

    def _measure(self, form: dict[str, str]) -> None:
        directory = self._pair_directory(form.get("pair", ""))
        run_id = uuid.uuid4().hex
        run_dir = self.state.workspace / run_id
        run_dir.mkdir(parents=True)
        try:
            ops.measure(directory, run_dir, cards=form.get("cards") == "on")
        except Exception:
            # A run that produced no report must not leave a directory behind
            # that would answer 404 with a path the reader cannot explain.
            shutil.rmtree(run_dir, ignore_errors=True)
            raise
        location = f"/run/{run_id}?token={quote(self.state.token, safe='')}"
        self._answer(
            303,
            "text/plain; charset=utf-8",
            b"",
            extra=(("Location", location),),
        )

    def _pair_directory(self, pair: str) -> Path:
        fixtures = self.state.fixtures
        if not SAFE_NAME.fullmatch(pair) or pair in {".", ".."}:
            raise _HttpError(400, "unknown fixture pair")
        candidate = (fixtures / pair).resolve()
        if candidate.parent != fixtures or not (candidate / "config.json").is_file():
            raise _HttpError(400, "unknown fixture pair")
        return candidate

    def _run_page(self, run_id: str) -> None:
        run_dir = self._run_directory(run_id)
        report = load_report(_report_file(run_dir))
        page = render_report_html(
            report,
            card_url_prefix=f"/run/{run_id}/card",
            cards_dir=run_dir,
        )
        self._page(
            200,
            _with_run_bar(
                page,
                run_id=run_id,
                pair_id=report.plan.pair_id,
                token=self.state.token,
            ),
        )

    def _run_directory(self, run_id: str) -> Path:
        if not RUN_ID.fullmatch(run_id):
            raise _HttpError(404, "no such run")
        workspace = self.state.workspace
        candidate = (workspace / run_id).resolve()
        if candidate.parent != workspace or not candidate.is_dir():
            raise _HttpError(404, "no such run")
        return candidate

    def _card(self, run_id: str, name: str) -> None:
        """One card image, served only while its bytes match the report.

        The report records the sha256 of every card it wrote, so a file edited
        after the run is refused rather than shown beside a claim it no longer
        illustrates. A name the report does not record is refused the same way.
        """
        run_dir = self._run_directory(run_id)
        path = _child_file(run_dir, "cards", name)
        report = load_report(_report_file(run_dir))
        expected = next(
            (
                card.sha256
                for card in report.evidence_cards
                if card.path.rpartition("/")[2] == name
            ),
            None,
        )
        if expected is None:
            raise _HttpError(404, "no such file")
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise _HttpError(404, "no such file")
        self._bytes(data, "image/png")

    def _export_file(self, run_id: str, name: str) -> None:
        run_dir = self._run_directory(run_id)
        path = _child_file(run_dir, "export", name)
        media = (
            "image/svg+xml"
            if path.suffix.lower() == ".svg"
            else "application/octet-stream"
        )
        self._bytes(path.read_bytes(), media)

    def _verify(self, run_id: str) -> None:
        run_dir = self._run_directory(run_id)
        report_path = _report_file(run_dir)
        report = load_report(report_path)
        result = ops.verify(
            report_path, self._inputs_directory(report.plan.pair_id)
        )
        self._page(
            200,
            _verify_page(
                run_id=run_id,
                token=self.state.token,
                ok=bool(result["ok"]),
                reasons=[str(reason) for reason in result["reasons"]],
            ),
        )

    def _inputs_directory(self, pair_id: str) -> Path:
        """The fixtures folder this server was given, for one pair.

        ``ops.verify`` defaults to the repository's own fixture tree, which
        would report a sound run measured from any other tree as unverified.
        The pair name is resolved and must stay directly inside the fixtures
        root; a report naming anything else is checked against the root
        itself, where its inputs are absent, so the check fails closed
        instead of reading a folder the server was not given.
        """
        fixtures = self.state.fixtures
        candidate = (fixtures / pair_id).resolve()
        if (
            SAFE_NAME.fullmatch(pair_id) is None
            or pair_id in {".", ".."}
            or candidate.parent != fixtures
        ):
            return fixtures
        return candidate

    def _export(self, run_id: str) -> None:
        run_dir = self._run_directory(run_id)
        result = ops.export(_report_file(run_dir), out=run_dir / "export")
        self._page(
            200,
            _export_page(
                run_id=run_id,
                token=self.state.token,
                files=[Path(str(path)).name for path in result["files"]],
            ),
        )

    def _page(self, status: int, page: str) -> None:
        self._answer(status, HTML_TYPE, page.encode("utf-8"))

    def _bytes(self, body: bytes, content_type: str) -> None:
        self._answer(200, content_type, body)

    def _json(
        self,
        status: int,
        payload: dict[str, Any],
        *,
        extra: tuple[tuple[str, str], ...] = (),
        close: bool = False,
    ) -> None:
        body = json.dumps(payload, ensure_ascii=True).encode("ascii")
        self._answer(status, JSON_TYPE, body, extra=extra, close=close)

    def _answer(
        self,
        status: int,
        content_type: str,
        body: bytes,
        *,
        extra: tuple[tuple[str, str], ...] = (),
        close: bool = False,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for name, value in SECURITY_HEADERS:
            self.send_header(name, value)
        for name, value in extra:
            self.send_header(name, value)
        if close:
            # Announce the close: a client that keeps the socket would reuse a
            # connection this server is about to drop.
            self.send_header("Connection", "close")
            self.close_connection = True
        self.end_headers()
        if body:
            self.wfile.write(body)


def _status_text(code: int) -> str:
    try:
        return HTTPStatus(code).phrase.lower()
    except ValueError:
        return "request refused"


def _is_post_path(path: str) -> bool:
    return path == "/measure" or bool(
        _VERIFY.fullmatch(path) or _EXPORT.fullmatch(path)
    )


def _is_get_path(path: str) -> bool:
    if path in {"/", "/tools", "/healthz"}:
        return True
    return any(
        pattern.fullmatch(path) for pattern in (_RUN_PAGE, _CARD, _EXPORT_FILE)
    )


def _unsafe_path(path: str) -> bool:
    """Whether a request path carries anything that could name a location.

    No route takes a percent-encoded segment, so a ``%`` is refused rather than
    decoded: a decoder is exactly where a traversal slips through. A backslash
    is refused because Windows reads it as a separator, a ``.`` or ``..``
    segment and a drive-letter prefix are refused because they name a place
    rather than a resource, and a leading ``//`` is refused because a
    request-target in that form can be read as another host.
    """
    if not path.startswith("/") or path.startswith("//"):
        return True
    if "%" in path or "\\" in path:
        return True
    for segment in path.split("/"):
        if segment in {".", ".."}:
            return True
        if len(segment) > 1 and segment[1] == ":":
            return True
        if any(ord(character) < 32 or ord(character) == 127 for character in segment):
            return True
    return False


def _text(value: object) -> str:
    """Escape one value for text and attribute contexts alike."""
    return html.escape(str(value), quote=True)


def _report_file(run_dir: Path) -> Path:
    """The run's report, refusing one that resolves outside the run.

    ``run_dir`` is already resolved, so a ``report.json`` that is a symlink to
    another location has a parent that is not this run and is refused. The app
    wrote the report itself, so a link here means the folder was altered after
    the run.
    """
    try:
        path = (run_dir / "report.json").resolve(strict=True)
    except OSError:
        raise _HttpError(404, "no such run") from None
    if path.parent != run_dir or not path.is_file():
        raise _HttpError(404, "no such run")
    return path


def _child_file(run_dir: Path, folder: str, name: str) -> Path:
    """The one file ``name`` inside ``run_dir/folder``; anything else is a 404.

    The name is checked before the filesystem is touched, so no request can
    name a path: no separator, no drive letter and no ``.`` or ``..``. The
    folder and the candidate are then resolved, and each must keep its own
    resolved parent - the run directory for the folder, the folder for the
    file - which is what stops a symlinked ``cards`` or ``export`` folder, or a
    symlink inside one, from reaching outside the run.
    """
    if not SAFE_NAME.fullmatch(name) or name in {".", ".."}:
        raise _HttpError(404, "no such file")
    try:
        base = (run_dir / folder).resolve(strict=True)
    except OSError:
        raise _HttpError(404, "no such file") from None
    if base.parent != run_dir or not base.is_dir():
        raise _HttpError(404, "no such file")
    candidate = (base / name).resolve()
    if candidate.parent != base or not candidate.is_file():
        raise _HttpError(404, "no such file")
    return candidate


def _schema_text(tool: tool_registry.Tool) -> str:
    """One tool's derived input schema as readable JSON."""
    return json.dumps(tool.json_schema, ensure_ascii=True, sort_keys=True, indent=2)


def _document(title: str, body: str) -> str:
    return "\n".join(
        [
            "<!DOCTYPE html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            f"<title>{_text(title)}</title>",
            f"<style>{PAGE_CSS}</style>",
            "</head>",
            "<body>",
            "<main>",
            body,
            "</main>",
            "</body>",
            "</html>",
            "",
        ]
    )


def _fixture_names(fixtures: Path) -> list[str]:
    """The pairs a Measure form can name: directories holding a config."""
    try:
        return sorted(
            path.name
            for path in fixtures.iterdir()
            if path.is_dir() and (path / "config.json").is_file()
        )
    except OSError:
        return []


def _index_page(state: _State) -> str:
    names = _fixture_names(state.fixtures)
    rows = [
        "<tr>"
        f"<td><code>{_text(name)}</code></td>"
        "<td>"
        '<form method="post" action="/measure">'
        f'<input type="hidden" name="pair" value="{_text(name)}">'
        f'<input type="hidden" name="token" value="{_text(state.token)}">'
        '<label><input type="checkbox" name="cards" value="on" checked>'
        " evidence cards</label>"
        '<button type="submit">Measure</button>'
        "</form>"
        "</td>"
        "</tr>"
        for name in names
    ]
    if rows:
        table = (
            "<table><thead><tr><th>Pair</th><th>Measure</th></tr></thead><tbody>"
            + "".join(rows)
            + "</tbody></table>"
        )
    else:
        table = '<p class="note">No fixture pair was found under the fixtures folder.</p>'
    body = "\n".join(
        [
            "<h1>PicCompare AEC</h1>",
            '<p class="lede">Measure a prepared floor-plan pair, then read the report, '
            "re-check it and export it. This page is served from this machine only, "
            "and every action carries the token minted when the server started.</p>",
            "<section>",
            "<h2>Fixture pairs</h2>",
            f'<p class="note">{len(names)} pairs available.</p>',
            table,
            "</section>",
            "<section>",
            "<h2>Elsewhere</h2>",
            f'<p><a href="/tools">Tool registry</a> - the {len(tool_registry.TOOLS)} '
            "tools this repository publishes to an AI assistant.</p>",
            "</section>",
        ]
    )
    return _document("PicCompare AEC - local web app", body)


def _tools_page() -> str:
    rows = [
        "<tr>"
        f"<td><code>{_text(tool.name)}</code></td>"
        f"<td>{_text(tool.status)}</td>"
        f"<td>{_text(tool.description)}</td>"
        f"<td><pre>{_text(_schema_text(tool))}</pre></td>"
        "</tr>"
        for tool in tool_registry.TOOLS
    ]
    body = "\n".join(
        [
            "<h1>Tool registry</h1>",
            f'<p class="lede">{len(tool_registry.TOOLS)} tools this repository '
            "publishes to an AI assistant. Each input schema is derived from its "
            "registry entry, which is the single source of the protocol schema. "
            "Nothing on this page runs a tool.</p>",
            "<section>",
            "<table><thead><tr><th>Name</th><th>Status</th><th>Description</th>"
            "<th>Input schema</th></tr></thead><tbody>",
            *rows,
            "</tbody></table>",
            "</section>",
        ]
    )
    return _document("Tool registry - PicCompare AEC", body)


def _back_link(run_id: str, token: str) -> str:
    return (
        f'<p><a href="/run/{_text(run_id)}?token={_text(quote(token, safe=""))}">'
        "Back to the report</a></p>"
    )


def _verify_page(
    *, run_id: str, token: str, ok: bool, reasons: Sequence[str]
) -> str:
    if ok:
        result = (
            "<h1>Report verifies</h1>"
            '<p class="ok">Every recorded fingerprint matched: the report digest, '
            "both input images, the elements and the measurements.</p>"
        )
    else:
        items = "".join(f"<li>{_text(reason)}</li>" for reason in reasons)
        if not items:
            items = "<li>no reason was recorded</li>"
        result = (
            "<h1>Report does not verify</h1>"
            f'<ul class="reasons">{items}</ul>'
        )
    return _document("Verify - PicCompare AEC", result + _back_link(run_id, token))


def _export_page(*, run_id: str, token: str, files: Sequence[str]) -> str:
    items = "".join(
        f'<li><a href="/run/{_text(run_id)}/export/{_text(name)}">{_text(name)}</a></li>'
        for name in files
    )
    result = (
        "<h1>Exported</h1>"
        f'<p class="lede">{len(files)} files were written under this run\'s '
        "export folder.</p>"
        f"<ul>{items}</ul>"
    )
    return _document("Export - PicCompare AEC", result + _back_link(run_id, token))


def _run_bar(*, run_id: str, pair_id: str, token: str) -> str:
    hidden = f'<input type="hidden" name="token" value="{_text(token)}">'
    return "\n".join(
        [
            '<nav class="appbar">',
            '<a href="/">PicCompare AEC</a>',
            f'<span class="pair">{_text(pair_id)}</span>',
            f'<form method="post" action="/run/{_text(run_id)}/verify">{hidden}'
            '<button type="submit">Verify report</button></form>',
            f'<form method="post" action="/run/{_text(run_id)}/export">{hidden}'
            '<button type="submit">Export SVG</button></form>',
            "</nav>",
        ]
    )


def _with_run_bar(page: str, *, run_id: str, pair_id: str, token: str) -> str:
    """Add the app bar and its CSS to the viewer's own document.

    The viewer is a complete document and is not edited here, so its two stable
    anchors - ``</head>`` and ``<body>`` - are where the style and the bar go;
    the bar sits above ``<main>`` so it spans the page. A viewer that loses
    either anchor raises instead of silently dropping the buttons.
    """
    if "</head>" not in page or "<body>" not in page:
        raise RuntimeError(
            "the viewer page has no head or body to attach the run bar to"
        )
    styled = page.replace("</head>", f"<style>{APP_CSS}</style>\n</head>", 1)
    bar = _run_bar(run_id=run_id, pair_id=pair_id, token=token)
    return styled.replace("<body>", "<body>\n" + bar, 1)


def build_app(
    *,
    workspace: Path,
    fixtures: Path,
    host: str = "127.0.0.1",
    port: int = 0,
) -> ThreadingHTTPServer:
    """Create the threaded server, bound to a loopback address.

    A host outside :data:`LOOPBACK_HOSTS` raises :class:`WebAppError` before a
    socket exists, so there is no window in which the page is reachable from
    another machine.
    """
    if host not in LOOPBACK_HOSTS:
        raise WebAppError(
            "the app binds loopback only; "
            f"{host!r} is not one of {', '.join(sorted(LOOPBACK_HOSTS))}"
        )
    if not 0 <= port <= 65535:
        raise WebAppError("port must be between 0 and 65535")
    fixture_root = Path(fixtures).resolve()
    if not fixture_root.is_dir():
        raise WebAppError(f"fixtures directory not found: {Path(fixtures)}")
    workspace_root = Path(workspace).resolve()
    workspace_root.mkdir(parents=True, exist_ok=True)
    state = _State(
        workspace=workspace_root,
        fixtures=fixture_root,
        token=secrets.token_urlsafe(24),
    )
    return WebServer((host, port), state)


def serve(
    *,
    workspace: Path,
    fixtures: Path,
    host: str = "127.0.0.1",
    port: int = 0,
    open_browser: bool = True,
) -> int:
    """Run the app until Ctrl-C or standard input closes, then release the port."""
    server = cast(
        WebServer,
        build_app(workspace=workspace, fixtures=fixtures, host=host, port=port),
    )
    url = (
        f"http://{_url_host(host)}:{server.server_port}/"
        f"?token={quote(server.token, safe='')}"
    )
    print(url, flush=True)
    if open_browser:
        webbrowser.open(url)
    _watch_stdin(server)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def _url_host(host: str) -> str:
    """Bracket an IPv6 literal so the printed URL is well formed."""
    return f"[{host}]" if ":" in host else host


def _watch_stdin(server: ThreadingHTTPServer) -> None:
    """Stop the server when standard input reaches end of file.

    A terminal keeps this blocked, so Ctrl-C stays the normal way to stop. A
    script that redirects standard input from an empty file stops the server at
    once, which is deliberate: a closed input is read as "stop".
    """
    stream = sys.stdin
    if stream is None:
        return

    def stop_at_eof() -> None:
        try:
            while stream.read(1) != "":
                pass
        except (OSError, ValueError):
            pass
        server.shutdown()

    threading.Thread(target=stop_at_eof, name="aec-serve-stdin", daemon=True).start()
