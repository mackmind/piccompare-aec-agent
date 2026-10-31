"""The local web app: scaffold, routes and one end-to-end pass.

Every server here runs on an ephemeral loopback port and is shut down in a
``finally`` block, so a failing assertion cannot leave a listening socket
behind. The workspace is always ``tmp_path``: no test writes into the
repository's ``runs/`` directory.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import re
import socket
import socketserver
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import cast
from urllib.parse import urlencode

import pytest

from aec import tool_registry
from aec.webapp import WebAppError, WebServer, build_app

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures" / "aec"
CSP = (
    "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; "
    "form-action 'self'"
)
TIMEOUT = 10.0


@contextmanager
def running_app(tmp_path: Path) -> Iterator[WebServer]:
    """A server on an ephemeral loopback port, stopped even when a test fails."""
    server = cast(
        WebServer,
        build_app(workspace=tmp_path / "workspace", fixtures=FIXTURES),
    )
    thread = threading.Thread(
        target=server.serve_forever,
        kwargs={"poll_interval": 0.05},
        daemon=True,
    )
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)
        assert not thread.is_alive()


@contextmanager
def client(server: WebServer) -> Iterator[http.client.HTTPConnection]:
    connection = http.client.HTTPConnection(
        "127.0.0.1", int(server.server_address[1]), timeout=TIMEOUT
    )
    try:
        yield connection
    finally:
        connection.close()


def request(
    connection: http.client.HTTPConnection,
    method: str,
    path: str,
    fields: dict[str, str] | None = None,
) -> tuple[int, http.client.HTTPMessage, bytes]:
    """One request; ``fields`` makes it a form POST."""
    body = None if fields is None else urlencode(fields)
    headers = (
        {} if fields is None
        else {"Content-Type": "application/x-www-form-urlencoded"}
    )
    connection.request(method, path, body=body, headers=headers)
    response = connection.getresponse()
    return response.status, response.headers, response.read()


def measure(
    connection: http.client.HTTPConnection,
    token: str,
    *,
    pair: str = "resize-01",
    cards: bool = True,
) -> tuple[str, str]:
    """Measure one pair through the app; return the run id and the page path."""
    fields = {"pair": pair, "token": token}
    if cards:
        fields["cards"] = "on"
    status, headers, _ = request(connection, "POST", "/measure", fields)
    assert status == 303, status
    location = headers["Location"]
    match = re.fullmatch(r"/run/([0-9a-f]{32})\?token=([A-Za-z0-9_-]+)", location)
    assert match is not None, location
    return match.group(1), location


def test_build_app_binds_loopback_on_an_ephemeral_port(tmp_path: Path) -> None:
    with running_app(tmp_path) as server:
        host, port = server.server_address[:2]
        assert host == "127.0.0.1"
        assert isinstance(port, int) and port > 0
        assert server.daemon_threads is True
        assert len(server.token) >= 32


@pytest.mark.parametrize(
    "host", ["0.0.0.0", "192.168.1.10", "example.com", "", " localhost"]
)
def test_non_loopback_host_is_refused_before_any_socket(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, host: str
) -> None:
    binds: list[str] = []

    def refuse_bind(server: socketserver.BaseServer) -> None:
        binds.append(str(server))
        raise AssertionError("a socket was bound for a non-loopback host")

    monkeypatch.setattr(socketserver.TCPServer, "server_bind", refuse_bind)

    with pytest.raises(WebAppError):
        build_app(workspace=tmp_path / "ws", fixtures=FIXTURES, host=host)
    assert binds == []


def test_shutdown_releases_the_port(tmp_path: Path) -> None:
    with running_app(tmp_path) as server:
        port = int(server.server_address[1])
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", port))


def test_unknown_path_is_not_found_and_carries_the_security_headers(
    tmp_path: Path,
) -> None:
    with running_app(tmp_path) as server, client(server) as connection:
        connection.request("GET", "/no-such-page")
        response = connection.getresponse()
        body = response.read()
        assert response.status == 404
        assert response.getheader("Content-Type") == "application/json"
        assert response.getheader("Content-Security-Policy") == CSP
        assert response.getheader("X-Content-Type-Options") == "nosniff"
        assert response.getheader("Referrer-Policy") == "no-referrer"
        assert response.getheader("Cache-Control") == "no-store"
        assert json.loads(body) == {"error": "not found"}


def test_index_lists_the_fixture_pairs_with_a_measure_form(tmp_path: Path) -> None:
    with running_app(tmp_path) as server, client(server) as connection:
        status, headers, body = request(connection, "GET", "/")
    text = body.decode("utf-8")
    assert status == 200
    assert headers["Content-Type"] == "text/html; charset=utf-8"
    for name in ("identical-01", "resize-01", "split-01"):
        assert name in text
    assert 'action="/measure"' in text
    assert 'name="pair"' in text
    assert 'name="cards"' in text
    assert 'name="token"' in text
    assert server.token in text


def test_healthz_answers_ok(tmp_path: Path) -> None:
    with running_app(tmp_path) as server, client(server) as connection:
        status, headers, body = request(connection, "GET", "/healthz")
    assert status == 200
    assert headers["Content-Type"] == "application/json"
    assert json.loads(body) == {"ok": True}


def test_tools_page_lists_every_registry_tool(tmp_path: Path) -> None:
    with running_app(tmp_path) as server, client(server) as connection:
        status, headers, body = request(connection, "GET", "/tools")
    text = body.decode("utf-8")
    assert status == 200
    assert headers["Content-Type"] == "text/html; charset=utf-8"
    assert len(tool_registry.TOOLS) == 12
    for tool in tool_registry.TOOLS:
        assert text.count(tool.name) == 1, tool.name
    # The derived schema is shown as escaped text, never as live markup.
    assert "<pre>" in text
    assert "&quot;properties&quot;" in text


def test_a_get_on_a_post_route_is_method_not_allowed(tmp_path: Path) -> None:
    with running_app(tmp_path) as server, client(server) as connection:
        status, headers, body = request(connection, "GET", "/measure")
    assert status == 405
    assert headers["Allow"] == "POST"
    assert json.loads(body) == {"error": "method not allowed"}


def test_a_post_on_a_get_route_is_method_not_allowed(tmp_path: Path) -> None:
    with running_app(tmp_path) as server, client(server) as connection:
        status, headers, _ = request(
            connection, "POST", "/tools", {"token": server.token}
        )
    assert status == 405
    assert headers["Allow"] == "GET"


def test_every_route_answers(tmp_path: Path) -> None:
    """One measured pair drives the whole route table, as the video does."""
    workspace = tmp_path / "workspace"
    with running_app(tmp_path) as server, client(server) as connection:
        run_id, location = measure(connection, server.token)
        status, headers, body = request(connection, "GET", location)
        page = body.decode("utf-8")
        assert status == 200
        assert headers["Content-Type"] == "text/html; charset=utf-8"
        assert "room_resized" in page
        assert 'id="digest"' in page
        assert 'class="appbar"' in page
        assert "Verify report" in page
        assert "Export SVG" in page

        report = json.loads(
            (workspace / run_id / "report.json").read_text(encoding="utf-8")
        )
        assert len(report["evidence_cards"]) == 2
        card = report["evidence_cards"][0]
        name = card["path"].rpartition("/")[2]
        status, headers, body = request(
            connection, "GET", f"/run/{run_id}/card/{name}"
        )
        assert status == 200
        assert headers["Content-Type"] == "image/png"
        assert hashlib.sha256(body).hexdigest() == card["sha256"]

        status, headers, body = request(
            connection, "POST", f"/run/{run_id}/verify", {"token": server.token}
        )
        assert status == 200
        assert headers["Content-Type"] == "text/html; charset=utf-8"
        assert "Report verifies" in body.decode("utf-8")

        status, headers, body = request(
            connection, "POST", f"/run/{run_id}/export", {"token": server.token}
        )
        assert status == 200
        assert (workspace / run_id / "export" / "resize-01.svg").is_file()
        assert f"/run/{run_id}/export/resize-01.svg" in body.decode("utf-8")

        status, headers, body = request(
            connection, "GET", f"/run/{run_id}/export/resize-01.svg"
        )
        assert status == 200
        assert headers["Content-Type"] == "image/svg+xml"
        assert b"<svg" in body
