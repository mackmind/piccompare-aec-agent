from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from aec.evidence import verify
from aec.pipeline import run_pair

ROOT = Path(__file__).resolve().parent.parent


def test_offline_eval_passes_all_pairs(tmp_path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "run_eval.py"),
            "--fixtures",
            str(ROOT / "fixtures"),
            "--out",
            str(tmp_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    metrics = json.loads((tmp_path / "metrics.json").read_text(encoding="utf-8"))
    totals = metrics["totals"]
    assert totals["pairs"] == 12
    assert totals["pairs_passed"] == 12
    assert totals["false_positives"] == 0
    assert totals["missing"] == 0
    assert totals["not_compared_matched"] == 4
    assert totals["agent_refused_changes"] == 4
    assert totals["baseline_flagged_changes"] > 0


def test_pair_report_verifies_with_inputs(tmp_path) -> None:
    fixture = ROOT / "fixtures" / "aec" / "resize-01"
    result = run_pair(fixture, tmp_path)
    assert result.report_path is not None
    assert verify(result.report_path, inputs_dir=fixture).ok
    assert not result.not_compared
    assert result.verified


def test_live_eval_fails_closed_without_credentials(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("META_API_KEY", raising=False)
    monkeypatch.delenv("META_MODEL_ID", raising=False)
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "run_eval.py"),
            "--fixtures",
            str(ROOT / "fixtures"),
            "--out",
            str(tmp_path / "should-not-exist"),
            "--live",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "MISSING CREDENTIALS" in result.stdout
    assert not (tmp_path / "should-not-exist").exists()
