"""Workspace containment: run ids, traversal, file names, fixtures and body size.

Every case here asserts a status and, where a file exists that a traversal
would reach, that none of its bytes came back. The workspace snapshot before a
refused request must equal the snapshot after it.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from urllib.parse import quote, urlencode

import pytest
from webapp_harness import (
    FIXTURES,
    client,
    measure,
    post_raw,
    request,
    running_app,
)


def _json_error(body: bytes) -> str:
    payload = json.loads(body)
    assert set(payload) == {"error"}
    return str(payload["error"])


def test_a_run_id_must_be_thirty_two_lowercase_hex_digits(tmp_path: Path) -> None:
    with running_app(tmp_path) as server, client(server) as connection:
        for run_id in ("../demo", "A" * 32, "0" * 31, "0" * 33, "0" * 32 + "g"):
            status, headers, body = request(connection, "GET", f"/run/{run_id}")
            assert status in {400, 404}, (run_id, status)
            assert headers["Content-Type"] == "application/json"
            assert _json_error(body) in {"no such run", "refused request path"}


def test_a_dot_segment_is_refused_before_any_file_is_looked_up(
    tmp_path: Path,
) -> None:
    with running_app(tmp_path) as server, client(server) as connection:
        status, headers, body = request(
            connection, "GET", "/run/../demo/live-report.json"
        )
    assert status == 400
    assert headers["Content-Type"] == "application/json"
    assert b"live_meta" not in body


def test_an_encoded_traversal_is_refused(tmp_path: Path) -> None:
    with running_app(tmp_path) as server, client(server) as connection:
        status, _, body = request(
            connection, "GET", "/run/%2e%2e%2fdemo/live-report.json"
        )
    assert status == 400
    assert b"live_meta" not in body


def test_a_backslash_in_a_path_is_refused(tmp_path: Path) -> None:
    with running_app(tmp_path) as server, client(server) as connection:
        run_id, _ = measure(connection, server.token)
        status, _, body = request(
            connection, "GET", f"/run/{run_id}/card/a\\b.png"
        )
    assert status == 400
    assert _json_error(body) == "refused request path"


def test_an_absolute_path_is_never_served(tmp_path: Path) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("SECRET-MARKER", encoding="utf-8")
    with running_app(tmp_path) as server, client(server) as connection:
        run_id, _ = measure(connection, server.token)
        paths = (
            f"/run/{run_id}/card/{quote(str(outside), safe='')}",
            f"/run/{run_id}/card/C:/Windows/win.ini",
            f"/run/{run_id}/card/..%2f..%2fconfig.json",
        )
        for path in paths:
            status, _, body = request(connection, "GET", path)
            assert status in {400, 404}, (path, status)
            assert b"SECRET-MARKER" not in body
            assert b"for 16-bit app support" not in body


def test_the_report_is_not_served_through_the_card_route(tmp_path: Path) -> None:
    with running_app(tmp_path) as server, client(server) as connection:
        run_id, _ = measure(connection, server.token)
        status, _, body = request(
            connection, "GET", f"/run/{run_id}/card/report.json"
        )
    assert status == 404
    assert b"digest" not in body


def test_a_card_symlink_outside_the_run_is_not_served(tmp_path: Path) -> None:
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"\x89PNG\r\n\x1a\nSECRET-MARKER")
    with running_app(tmp_path) as server, client(server) as connection:
        run_id, _ = measure(connection, server.token)
        link = server.workspace / run_id / "cards" / "evil.png"
        try:
            os.symlink(outside, link)
        except (OSError, NotImplementedError):
            pytest.skip("this platform does not permit a test symlink")
        status, _, body = request(
            connection, "GET", f"/run/{run_id}/card/evil.png"
        )
    assert status == 404
    assert b"SECRET-MARKER" not in body


def test_a_body_above_the_cap_is_refused(tmp_path: Path) -> None:
    with running_app(tmp_path) as server, client(server) as connection:
        before = sorted(path.name for path in server.workspace.iterdir())
        payload = urlencode(
            {
                "pair": "resize-01",
                "token": server.token,
                "padding": "x" * (64 * 1024),
            }
        )
        status, headers, body = post_raw(connection, "/measure", payload)
        assert status == 413
        assert headers["Content-Type"] == "application/json"
        assert _json_error(body) == "request body too large"
        after = sorted(path.name for path in server.workspace.iterdir())
    assert after == before


def test_a_pair_outside_the_fixtures_directory_is_refused(tmp_path: Path) -> None:
    outside = tmp_path / "pair-outside"
    shutil.copytree(FIXTURES / "resize-01", outside)
    with running_app(tmp_path) as server, client(server) as connection:
        before = sorted(path.name for path in server.workspace.iterdir())
        for pair in (str(outside), "../pair-outside", "../../pair-outside"):
            status, _, body = request(
                connection,
                "POST",
                "/measure",
                {"pair": pair, "token": server.token},
            )
            assert status == 400, pair
            assert _json_error(body) == "unknown fixture pair"
        after = sorted(path.name for path in server.workspace.iterdir())
    assert after == before


def test_a_fixture_pair_symlinked_outside_the_fixtures_is_refused(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "pair-outside"
    shutil.copytree(FIXTURES / "resize-01", outside)
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    try:
        os.symlink(outside, fixtures / "linked-01", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("this platform does not permit a test symlink")
    with running_app(tmp_path, fixtures=fixtures) as server, client(
        server
    ) as connection:
        status, _, body = request(
            connection,
            "POST",
            "/measure",
            {"pair": "linked-01", "token": server.token},
        )
    assert status == 400
    assert _json_error(body) == "unknown fixture pair"
