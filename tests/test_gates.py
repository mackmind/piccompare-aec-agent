from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _gate_ext():
    """Load scripts/gate_ext.py without running its main()."""
    spec = importlib.util.spec_from_file_location(
        "gate_ext_script", ROOT / "scripts" / "gate_ext.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_gate_runner_lists_seventeen_tasks() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/run_gates.py", "--list"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "T1" in result.stdout and "T17" in result.stdout


def test_the_default_gate_receipt_is_not_an_internal_evidence_path() -> None:
    assert _gate_ext().DEFAULT_OUT == "runs/gates/ext.json"


def test_an_explicit_out_still_reaches_a_runs_ext_receipt() -> None:
    args = _gate_ext().build_parser().parse_args(
        ["--out", "runs/ext/w0/gate.json"]
    )
    assert args.out == "runs/ext/w0/gate.json"
