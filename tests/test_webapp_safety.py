"""Refusals: containment, tokens, unknown routes, headers and body size.

Every case here asserts a status and, where a file exists that a traversal
would reach, that none of its bytes came back. A workspace snapshot taken
before a refused request must equal the snapshot after it, so a refusal can
never be a silent state change.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from urllib.parse import quote, urlencode

import pytest
from webapp_harness import (
    CSP,
    FIXTURES,
    client,
    measure,
    post_raw,
    request,
    running_app,
)

from aec.webapp import WebAppError, build_app


def _json_error(body: bytes) -> str:
    payload = json.loads(body)
    assert set(payload) == {"error"}
    return str(payload["error"])


def _snapshot(workspace: Path) -> list[tuple[str, int, int]]:
    """Every file under the workspace with its size and modification time."""
    return sorted(
        (
            path.relative_to(workspace).as_posix(),
            path.stat().st_size,
            path.stat().st_mtime_ns,
        )
        for path in workspace.rglob("*")
        if path.is_file()
    )


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


def test_a_cards_directory_symlinked_outside_the_run_is_not_served(
    tmp_path: Path,
) -> None:
    """The folder itself is resolved, not just the file inside it.

    The real cards folder is moved out of the run and a link to it is put in
    its place, so every name and every byte a card route would check still
    matches the report. Only the folder's resolved parent tells them apart.
    """
    with running_app(tmp_path) as server, client(server) as connection:
        run_id, _ = measure(connection, server.token)
        run_dir = server.workspace / run_id
        displaced = tmp_path / "displaced-cards"
        (run_dir / "cards").rename(displaced)
        try:
            os.symlink(displaced, run_dir / "cards", target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("this platform does not permit a test symlink")
        report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
        name = report["evidence_cards"][0]["path"].rpartition("/")[2]
        assert (displaced / name).is_file()
        status, _, body = request(
            connection, "GET", f"/run/{run_id}/card/{name}"
        )
    assert status == 404
    assert _json_error(body) == "no such file"


def test_a_report_symlinked_outside_the_run_is_not_served(tmp_path: Path) -> None:
    with running_app(tmp_path) as server, client(server) as connection:
        run_id, _ = measure(connection, server.token)
        run_dir = server.workspace / run_id
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        (run_dir / "report.json").rename(elsewhere / "report.json")
        try:
            os.symlink(elsewhere / "report.json", run_dir / "report.json")
        except (OSError, NotImplementedError):
            pytest.skip("this platform does not permit a test symlink")
        status, _, body = request(connection, "GET", f"/run/{run_id}")
    assert status == 404
    assert _json_error(body) == "no such run"
    assert b"room_resized" not in body


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


def test_every_post_refuses_a_missing_or_wrong_token(tmp_path: Path) -> None:
    with running_app(tmp_path) as server, client(server) as connection:
        run_id, _ = measure(connection, server.token)
        before = _snapshot(server.workspace)
        attempts: list[tuple[str, dict[str, str]]] = [
            ("/measure", {}),
            ("/measure", {"pair": "resize-01"}),
            ("/measure", {"pair": "resize-01", "token": "wrong"}),
            (f"/run/{run_id}/verify", {}),
            (f"/run/{run_id}/verify", {"token": server.token + "x"}),
            (f"/run/{run_id}/export", {}),
            (f"/run/{run_id}/export", {"token": "x" * 43}),
        ]
        for path, fields in attempts:
            status, headers, body = request(connection, "POST", path, fields)
            assert status == 403, (path, fields)
            assert headers["Content-Type"] == "application/json"
            assert _json_error(body) == "a valid session token is required"
            assert server.token not in body.decode("utf-8")
        after = _snapshot(server.workspace)
    assert after == before


def test_a_post_with_no_body_is_refused_like_a_missing_token(
    tmp_path: Path,
) -> None:
    with running_app(tmp_path) as server, client(server) as connection:
        status, _, body = post_raw(connection, "/measure", "")
    assert status == 403
    assert _json_error(body) == "a valid session token is required"


def test_a_post_without_a_form_content_type_is_refused_with_403(
    tmp_path: Path,
) -> None:
    # http.client sends a length but no content type: still no token, so the
    # answer is the token refusal rather than a body-format error.
    with running_app(tmp_path) as server, client(server) as connection:
        connection.request("POST", "/measure", body="pair=resize-01")
        response = connection.getresponse()
        status, body = response.status, response.read()
    assert status == 403
    assert _json_error(body) == "a valid session token is required"


def test_a_token_from_another_session_is_refused(tmp_path: Path) -> None:
    with running_app(tmp_path / "first") as first, running_app(
        tmp_path / "second"
    ) as second, client(first) as connection:
        assert first.token != second.token
        status, _, body = request(
            connection,
            "POST",
            "/measure",
            {"pair": "resize-01", "token": second.token},
        )
    assert status == 403
    assert _json_error(body) == "a valid session token is required"


def test_an_unknown_route_is_404(tmp_path: Path) -> None:
    with running_app(tmp_path) as server, client(server) as connection:
        for path in ("/nope", "/run", "/run/", "/card/x", "/tools/1", "/healthz/x"):
            status, headers, body = request(connection, "GET", path)
            assert status == 404, path
            assert headers["Content-Type"] == "application/json"
            assert _json_error(body) == "not found"


def test_a_request_for_another_host_name_is_refused(tmp_path: Path) -> None:
    """A page on another origin cannot read this server by rebinding its name.

    The request is addressed to the right port but names another host, which
    is what a DNS-rebinding page would send. It is refused before dispatch, so
    the token on ``/`` is never returned.
    """
    with running_app(tmp_path) as server, client(server) as connection:
        port = int(server.server_address[1])
        for host in (
            "evil.example",
            f"evil.example:{port}",
            f"127.0.0.1:{port + 1}",
            "127.0.0.1",
        ):
            connection.request(
                "GET", f"/?token={server.token}", headers={"Host": host}
            )
            response = connection.getresponse()
            status, headers, body = (
                response.status,
                response.headers,
                response.read(),
            )
            assert status == 403, host
            assert headers["Content-Type"] == "application/json"
            assert _json_error(body) == "request host is not allowed"
            assert server.token.encode("ascii") not in body


def test_the_three_loopback_names_are_accepted(tmp_path: Path) -> None:
    with running_app(tmp_path) as server, client(server) as connection:
        port = int(server.server_address[1])
        for host in (f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"):
            connection.request("GET", "/healthz", headers={"Host": host})
            response = connection.getresponse()
            assert response.status == 200, host
            assert json.loads(response.read()) == {"ok": True}


def test_a_normal_response_carries_the_security_headers(tmp_path: Path) -> None:
    with running_app(tmp_path) as server, client(server) as connection:
        status, headers, _ = request(connection, "GET", "/")
    assert status == 200
    assert headers["Content-Security-Policy"] == CSP
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Referrer-Policy"] == "no-referrer"
    assert headers["Cache-Control"] == "no-store"
    assert headers["X-Frame-Options"] == "DENY"


def test_an_unsupported_method_is_501_with_the_same_headers(tmp_path: Path) -> None:
    with running_app(tmp_path) as server, client(server) as connection:
        connection.request("DELETE", "/")
        response = connection.getresponse()
        status, headers, body = response.status, response.headers, response.read()
    assert status == 501
    assert headers["Content-Security-Policy"] == CSP
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert _json_error(body) == "not implemented"


def test_a_run_directory_without_a_report_is_404(tmp_path: Path) -> None:
    with running_app(tmp_path) as server, client(server) as connection:
        empty = server.workspace / ("0" * 32)
        empty.mkdir()
        status, _, body = request(connection, "GET", f"/run/{empty.name}")
    assert status == 404
    assert _json_error(body) == "no such run"


def test_a_tampered_report_does_not_verify_in_the_page(tmp_path: Path) -> None:
    with running_app(tmp_path) as server, client(server) as connection:
        run_id, _ = measure(connection, server.token)
        path = server.workspace / run_id / "report.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["findings"][0]["claim"] = "a claim that was never measured"
        path.write_text(json.dumps(data, ensure_ascii=True), encoding="ascii")
        status, headers, body = request(
            connection, "POST", f"/run/{run_id}/verify", {"token": server.token}
        )
    text = body.decode("utf-8")
    assert status == 200
    assert headers["Content-Type"] == "text/html; charset=utf-8"
    assert "Report does not verify" in text
    assert "report digest mismatch" in text
    assert "a claim that was never measured" not in text


def test_measure_without_cards_renders_no_card_images(tmp_path: Path) -> None:
    with running_app(tmp_path) as server, client(server) as connection:
        run_id, location = measure(connection, server.token, cards=False)
        status, _, body = request(connection, "GET", location)
        page = body.decode("utf-8")
        assert status == 200
        assert "<img " not in page
        assert "Evidence cards" not in page
        status, _, body = request(
            connection, "GET", f"/run/{run_id}/card/anything.png"
        )
    assert status == 404
    assert _json_error(body) == "no such file"


def test_a_card_whose_bytes_no_longer_match_the_report_is_not_served(
    tmp_path: Path,
) -> None:
    with running_app(tmp_path) as server, client(server) as connection:
        run_id, _ = measure(connection, server.token)
        path = server.workspace / run_id / "report.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        card = data["evidence_cards"][0]
        name = card["path"].rpartition("/")[2]
        image = server.workspace / run_id / "cards" / name
        image.write_bytes(image.read_bytes() + b"tampered")
        status, _, body = request(
            connection, "GET", f"/run/{run_id}/card/{name}"
        )
    assert status == 404
    assert _json_error(body) == "no such file"


def test_an_empty_fixtures_directory_renders_the_empty_state(tmp_path: Path) -> None:
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    with running_app(tmp_path, fixtures=fixtures) as server, client(
        server
    ) as connection:
        status, _, body = request(connection, "GET", "/")
    text = body.decode("utf-8")
    assert status == 200
    assert "No fixture pair was found" in text
    assert "<table>" not in text


def test_a_port_outside_the_range_is_refused(tmp_path: Path) -> None:
    with pytest.raises(WebAppError):
        build_app(workspace=tmp_path / "workspace", fixtures=FIXTURES, port=70000)
