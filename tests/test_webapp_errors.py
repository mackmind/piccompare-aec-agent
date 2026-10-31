"""Error answers: a refusal is JSON, redacted, and never carries a traceback.

The handler answers an :class:`aec.ops.OpsError` with 400 and any other
exception with 500. Both bodies pass through :func:`aec.redact.redact`, so an
absolute path in a library message becomes ``<path>`` and a message that quotes
the session token becomes ``<redacted>``. The traceback goes to standard error
only, which is what these tests read.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest
from webapp_harness import client, request, running_app

from aec import webapp
from aec.ops import OpsError


def _refuse_factory(message: str):
    def refuse(*args: object, **kwargs: object) -> None:
        raise OpsError(message)

    return refuse


def _explode_factory(message: str):
    def explode(*args: object, **kwargs: object) -> None:
        raise RuntimeError(message)

    return explode


def test_an_ops_error_becomes_a_redacted_400(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with running_app(tmp_path) as server, client(server) as connection:
        before = sorted(path.name for path in server.workspace.iterdir())
        monkeypatch.setattr(
            webapp.ops,
            "measure",
            _refuse_factory(r"cannot read C:\Users\owner\fixtures\a.png"),
        )
        status, headers, body = request(
            connection,
            "POST",
            "/measure",
            {"pair": "resize-01", "token": server.token},
        )
        after = sorted(path.name for path in server.workspace.iterdir())
    text = body.decode("utf-8")
    assert status == 400
    assert headers["Content-Type"] == "application/json"
    error = json.loads(text)["error"]
    assert error == "cannot read <path>"
    assert "C:" not in text
    assert "\\" not in text
    assert after == before


def test_an_unexpected_error_becomes_a_redacted_500(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured = io.StringIO()
    with running_app(tmp_path) as server, client(server) as connection:
        monkeypatch.setattr(
            webapp.ops,
            "measure",
            _explode_factory(r"boom while reading C:\private\plan.png"),
        )
        monkeypatch.setattr(sys, "stderr", captured)
        status, headers, body = request(
            connection,
            "POST",
            "/measure",
            {"pair": "resize-01", "token": server.token},
        )
    text = body.decode("utf-8")
    assert status == 500
    assert headers["Content-Type"] == "application/json"
    assert json.loads(text)["error"] == "boom while reading <path>"
    assert "C:" not in text
    assert "\\" not in text
    assert "Traceback" not in text
    detail = captured.getvalue()
    assert "Traceback" in detail
    assert "RuntimeError" in detail


def test_a_message_that_quotes_the_token_is_redacted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with running_app(tmp_path) as server, client(server) as connection:
        monkeypatch.setattr(
            webapp.ops,
            "measure",
            _explode_factory(f"bad session token {server.token}"),
        )
        status, _, body = request(
            connection,
            "POST",
            "/measure",
            {"pair": "resize-01", "token": server.token},
        )
    text = body.decode("utf-8")
    assert status == 500
    assert server.token not in text
    assert json.loads(text)["error"] == "bad session token <redacted>"
