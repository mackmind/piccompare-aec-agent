"""The local web app: scaffold, routes and one end-to-end pass.

The server plumbing lives in :mod:`webapp_harness`: every server runs on an
ephemeral loopback port and is shut down in a ``finally`` block, and the
workspace is always ``tmp_path``.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import socket
import socketserver
from pathlib import Path

import pytest
from webapp_harness import CSP, FIXTURES, client, measure, request, running_app

from aec import ops, tool_registry
from aec.webapp import WebAppError, build_app


def test_build_app_binds_loopback_on_an_ephemeral_port(tmp_path: Path) -> None:
    with running_app(tmp_path) as server:
        host, port = server.server_address[:2]
        assert host == "127.0.0.1"
        assert isinstance(port, int) and port > 0
        assert server.daemon_threads is True
        assert len(server.token) >= 32


def test_the_harness_measures_from_a_copy_of_the_fixtures(tmp_path: Path) -> None:
    """The default tree is a copy under tmp_path, not the checkout.

    This is what makes the folder the server is given the folder the run is
    measured from, so the ``--fixtures`` path is exercised by every test here.
    """
    with running_app(tmp_path) as server:
        assert server.fixtures == tmp_path / "fixtures"
        assert server.fixtures != FIXTURES
        assert (server.fixtures / "resize-01" / "config.json").is_file()


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


def test_verify_uses_the_fixtures_folder_the_server_was_given(
    tmp_path: Path,
) -> None:
    """A sound run measured from another fixtures tree still verifies.

    The copy's pair id is renamed so it exists nowhere but this tree, which is
    the case a verify that fell back to the repository's own fixtures could
    not answer for: it would report a sound report as unverifiable.
    """
    fixtures = tmp_path / "other-fixtures"
    shutil.copytree(FIXTURES / "resize-01", fixtures / "resize-01-copy")
    config_path = fixtures / "resize-01-copy" / "config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["pair_id"] = "resize-01-copy"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    with running_app(tmp_path, fixtures=fixtures) as server, client(
        server
    ) as connection:
        run_id, _ = measure(connection, server.token, pair="resize-01-copy")
        status, headers, body = request(
            connection, "POST", f"/run/{run_id}/verify", {"token": server.token}
        )
    assert status == 200
    assert headers["Content-Type"] == "text/html; charset=utf-8"
    assert "Report verifies" in body.decode("utf-8")


def test_the_whole_flow_from_the_picker_to_the_svg(tmp_path: Path) -> None:
    """The acceptance pass: picker, measure, page, card, verify, export, tools."""
    workspace = tmp_path / "workspace"
    with running_app(tmp_path) as server, client(server) as connection:
        # 1. The picker, reached with the token in the query string.
        status, _, body = request(connection, "GET", f"/?token={server.token}")
        picker = body.decode("utf-8")
        assert status == 200
        assert "resize-01" in picker

        # 2. Measure with evidence cards; the answer is a redirect, followed here.
        run_id, location = measure(connection, server.token, cards=True)

        # 3. The run page carries the finding, two card images and the digest.
        status, _, body = request(connection, "GET", location)
        page = body.decode("utf-8")
        assert status == 200
        assert "room_resized" in page
        assert page.count("<img ") == 2
        assert f'src="/run/{run_id}/card/' in page
        report = json.loads(
            (workspace / run_id / "report.json").read_text(encoding="utf-8")
        )
        assert report["plan"]["pair_id"] == "resize-01"
        assert f"<code>{report['digest']}</code>" in page
        assert "C:" not in page

        # 4. One card image, hashed against the sha256 the page shows.
        card = report["evidence_cards"][0]
        name = card["path"].rpartition("/")[2]
        assert card["sha256"] in page
        status, headers, image = request(
            connection, "GET", f"/run/{run_id}/card/{name}"
        )
        assert status == 200
        assert headers["Content-Type"] == "image/png"
        assert hashlib.sha256(image).hexdigest() == card["sha256"]

        # 5. Verify says ok; export writes the SVG the page links.
        status, _, body = request(
            connection, "POST", f"/run/{run_id}/verify", {"token": server.token}
        )
        assert status == 200
        assert "Report verifies" in body.decode("utf-8")
        status, _, body = request(
            connection, "POST", f"/run/{run_id}/export", {"token": server.token}
        )
        assert status == 200
        assert (workspace / run_id / "export" / "resize-01.svg").is_file()
        assert f"/run/{run_id}/export/resize-01.svg" in body.decode("utf-8")

        # 6. The registry page and the health probe.
        status, _, body = request(connection, "GET", "/tools")
        tools = body.decode("utf-8")
        assert status == 200
        for tool in tool_registry.TOOLS:
            assert tools.count(tool.name) == 1, tool.name
        status, _, body = request(connection, "GET", "/healthz")
        assert status == 200
        assert json.loads(body) == {"ok": True}

        port = int(server.server_address[1])

    # The same fixture through the operation gives the same verified count, so
    # the page cannot disagree with the command line about what was found.
    assert len(report["findings"]) == ops.measure(FIXTURES / "resize-01")["verified"]

    # The context manager shut the server down; nothing is listening now.
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", port))
