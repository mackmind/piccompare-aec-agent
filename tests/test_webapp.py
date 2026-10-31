"""The local web app: scaffold, routes and one end-to-end pass.

Every server here runs on an ephemeral loopback port and is shut down in a
``finally`` block, so a failing assertion cannot leave a listening socket
behind. The workspace is always ``tmp_path``: no test writes into the
repository's ``runs/`` directory.
"""

from __future__ import annotations

import http.client
import json
import socket
import socketserver
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import cast

import pytest

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
