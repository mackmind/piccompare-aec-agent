from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from aec import evaluation
from aec.evaluation import LiveCredentialsMissing, run_eval
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


def test_run_eval_in_process_scores_one_pair(tmp_path) -> None:
    # The script leg above runs in a subprocess, which pytest-cov cannot see;
    # this is the measurable entry point the tool server calls.
    metrics = run_eval(ROOT / "fixtures", tmp_path, ["resize-01"])
    assert metrics["mode"] == "offline_deterministic"
    assert metrics["totals"]["pairs"] == 1
    assert metrics["totals"]["pairs_passed"] == 1
    assert metrics["totals"]["false_positives"] == 0
    assert (tmp_path / "metrics.json").is_file()
    manifest = json.loads(
        (tmp_path / "verified_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["schema"] == "piccompare-aec-verified/1.0"
    assert manifest["pairs"][0]["pair_id"] == "resize-01"
    assert manifest["pairs"][0]["verified"] is True
    assert len(manifest["pairs"][0]["report_sha256"]) == 64


def test_run_eval_live_without_credentials_raises(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("META_API_KEY", raising=False)
    monkeypatch.delenv("META_MODEL_ID", raising=False)
    with pytest.raises(LiveCredentialsMissing):
        run_eval(ROOT / "fixtures", tmp_path, ["resize-01"], live=True)
    assert not (tmp_path / "metrics.json").exists()


def test_run_eval_live_routes_each_pair_to_the_live_runner(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("META_API_KEY", "test-key")
    monkeypatch.setenv("META_MODEL_ID", "test-model")
    seeded = run_pair(ROOT / "fixtures" / "aec" / "resize-01", tmp_path / "seed")
    seen: list[str] = []

    def fake_run_pair_live(
        pair_dir, sam_client, meta_client, out_dir, *, boxes_from_plan=False
    ):
        seen.append(Path(pair_dir).name)
        return seeded

    monkeypatch.setattr(evaluation, "run_pair_live", fake_run_pair_live)
    metrics = evaluation.run_eval(
        ROOT / "fixtures", tmp_path / "out", ["resize-01"], live=True
    )
    assert seen == ["resize-01"]
    assert metrics["mode"] == "live_meta"
    assert metrics["provider"]["network"] is True
    assert metrics["provider"]["model"] == "test-model"


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
