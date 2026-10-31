"""Shared plumbing for the local web app tests.

One server per test, on an ephemeral loopback port, stopped in a ``finally``
block so a failing assertion cannot leave a listening socket behind. The
workspace is always ``tmp_path``: no test writes into the repository's
``runs/`` directory.
"""

from __future__ import annotations

import http.client
import re
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import cast
from urllib.parse import urlencode

from aec.webapp import WebServer, build_app

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures" / "aec"
CSP = (
    "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; "
    "form-action 'self'"
)
TIMEOUT = 10.0
FORM_TYPE = "application/x-www-form-urlencoded"


@contextmanager
def running_app(tmp_path: Path, fixtures: Path = FIXTURES) -> Iterator[WebServer]:
    """A server on an ephemeral loopback port, stopped even when a test fails."""
    server = cast(
        WebServer,
        build_app(workspace=tmp_path / "workspace", fixtures=fixtures),
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
    headers = {} if fields is None else {"Content-Type": FORM_TYPE}
    connection.request(method, path, body=body, headers=headers)
    response = connection.getresponse()
    return response.status, response.headers, response.read()


def post_raw(
    connection: http.client.HTTPConnection, path: str, body: str
) -> tuple[int, http.client.HTTPMessage, bytes]:
    """A form POST whose body the caller built, so it can exceed the cap."""
    connection.request(
        "POST", path, body=body, headers={"Content-Type": FORM_TYPE}
    )
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
