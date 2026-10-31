"""``aec serve``: one printed URL, a live page, and a clean stop.

The subprocess test is the acceptance for W2-5: start with ``--port 0
--no-open``, read the URL the command prints, fetch ``/healthz``, close standard
input and expect exit 0. The reader thread bounds every wait, so a server that
never prints or never stops fails the test instead of hanging the suite.
"""

from __future__ import annotations

import io
import json
import queue
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path
from typing import IO
from urllib.parse import urlsplit

import pytest
from webapp_harness import FIXTURES

from aec import webapp
from aec.cli import main

ROOT = Path(__file__).resolve().parent.parent


def read_line(stream: IO[str], timeout: float = 30.0) -> str:
    """One line from a pipe, with a bound: a silent child must not hang us."""
    lines: queue.Queue[str] = queue.Queue()

    def reader() -> None:
        lines.put(stream.readline())

    threading.Thread(target=reader, daemon=True).start()
    try:
        return lines.get(timeout=timeout)
    except queue.Empty:
        raise AssertionError("the command printed no URL") from None


def test_serve_prints_the_token_url_and_stops_when_input_closes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    opened: list[str] = []
    monkeypatch.setattr(webapp.webbrowser, "open", opened.append)

    code = webapp.serve(
        workspace=tmp_path / "workspace",
        fixtures=FIXTURES,
        port=0,
    )

    printed = capsys.readouterr().out.strip()
    assert code == 0
    assert printed.startswith("http://127.0.0.1:")
    assert "?token=" in printed
    assert opened == [printed]


def test_aec_serve_answers_healthz_and_exits_on_stdin_close(tmp_path: Path) -> None:
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "aec",
            "serve",
            "--port",
            "0",
            "--no-open",
            "--fixtures",
            str(FIXTURES),
            "--workspace",
            str(tmp_path / "workspace"),
        ],
        cwd=ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout is not None
        url = read_line(process.stdout).strip()
        assert url.startswith("http://127.0.0.1:")
        assert "?token=" in url
        parsed = urlsplit(url)
        health = f"http://{parsed.netloc}/healthz"
        with urllib.request.urlopen(health, timeout=10) as response:
            assert response.status == 200
            assert json.loads(response.read()) == {"ok": True}
        assert process.stdin is not None
        process.stdin.close()
        assert process.wait(timeout=20) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)


def test_serve_refuses_a_missing_fixtures_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(
        [
            "serve",
            "--no-open",
            "--fixtures",
            str(tmp_path / "no-such-fixtures"),
            "--workspace",
            str(tmp_path / "workspace"),
        ]
    )
    assert code == 2
    assert "FAIL" in capsys.readouterr().out
