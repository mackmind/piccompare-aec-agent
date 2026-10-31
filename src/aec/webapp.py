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
* a run id is 32 lowercase hex digits, a file name matches ``[A-Za-z0-9._-]+``,
  and every requested file must sit directly inside the directory it belongs
  to, which also catches a symlink pointing outside it;
* every error leaves through one redacted JSON answer and the detail goes to
  standard error;
* every response carries the same four security headers, including the 404 and
  the base class's own refusals;
* there is no JavaScript, no remote asset and no directory listing.
"""

from __future__ import annotations

import html
import json
import re
import secrets
import socket
import sys
import threading
import traceback
import webbrowser
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, NoReturn, cast
from urllib.parse import quote, urlsplit

from aec.ops import OpsError
from aec.redact import redact

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
MAX_BODY_BYTES = 64 * 1024
RUN_ID = re.compile(r"^[0-9a-f]{32}$")
SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")
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


class WebAppError(ValueError):
    """The app refuses to start with this configuration."""


class _HttpError(Exception):
    """A refusal that becomes a JSON answer carrying this status."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass(frozen=True)
class _State:
    """What one server process needs to answer a request."""

    workspace: Path
    fixtures: Path
    token: str


class WebServer(ThreadingHTTPServer):
    """The threaded server, carrying the session state the handler reads."""

    daemon_threads = True
    allow_reuse_address = True

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

    @property
    def state(self) -> _State:
        return cast(WebServer, self.server).state

    def do_GET(self) -> None:
        self._guard("GET")

    def do_POST(self) -> None:
        self._guard("POST")

    def send_error(
        self, code: int, message: str | None = None, explain: str | None = None
    ) -> None:
        """Answer a base-class refusal with the same headers and a JSON body."""
        self.close_connection = True
        self._json(code, {"error": _status_text(code)})

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
            self._json(error.status, {"error": error.message}, close=True)
        except OpsError as error:
            sys.stderr.write(self._clean(str(error)) + "\n")
            self._json(400, {"error": self._clean(str(error))}, close=True)
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True
        except Exception as error:
            detail = traceback.format_exc()
            sys.stderr.write(detail)
            sys.stderr.flush()
            message = self._clean(str(error)) or "internal error"
            self._json(500, {"error": message}, close=True)

    def _dispatch(self, method: str) -> None:
        path = urlsplit(self.path).path
        if method == "GET":
            self._get(path)
        else:
            self._post(path)

    def _get(self, path: str) -> None:
        raise _HttpError(404, "not found")

    def _post(self, path: str) -> None:
        raise _HttpError(404, "not found")

    def _refuse_unknown(self, path: str) -> NoReturn:
        """405 for a known path with the wrong method, 404 for anything else."""
        if path == "/measure" or _VERIFY.fullmatch(path) or _EXPORT.fullmatch(path):
            raise _HttpError(405, "method not allowed")
        raise _HttpError(404, "not found")

    def _page(self, status: int, page: str) -> None:
        self._answer(status, HTML_TYPE, page.encode("utf-8"))

    def _json(
        self, status: int, payload: dict[str, Any], *, close: bool = False
    ) -> None:
        body = json.dumps(payload, ensure_ascii=True).encode("ascii")
        self._answer(status, JSON_TYPE, body, close=close)

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
            self.close_connection = True
        self.end_headers()
        if body:
            self.wfile.write(body)


def _status_text(code: int) -> str:
    try:
        return HTTPStatus(code).phrase.lower()
    except ValueError:
        return "request refused"


def _text(value: object) -> str:
    """Escape one value for text and attribute contexts alike."""
    return html.escape(str(value), quote=True)


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
