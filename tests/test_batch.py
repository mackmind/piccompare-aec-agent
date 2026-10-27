from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from factories import report

from aec.batch import triage
from aec.report import write_report

ROOT = Path(__file__).resolve().parent.parent


def test_batch_sorts_by_materiality() -> None:
    summary = triage(
        [
            report("p1", high=0, medium=1),
            report("p2", high=2),
            report("p3", high=1),
        ]
    )
    assert [pair.pair_id for pair in summary.pairs] == ["p2", "p3", "p1"]
    assert summary.totals["verified"] == 4
    assert summary.totals["high"] == 3


def test_run_batch_reads_reports(tmp_path) -> None:
    for pair_id, high in (("a", 0), ("b", 2)):
        write_report(report(pair_id, high=high), tmp_path / "reports" / pair_id)
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "run_batch.py"),
            "--reports",
            str(tmp_path / "reports"),
            "--out",
            str(tmp_path / "out"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    summary = json.loads((tmp_path / "out" / "summary.json").read_text())
    assert summary["pairs"][0]["pair_id"] == "b"
    assert summary["totals"]["pairs"] == 2
