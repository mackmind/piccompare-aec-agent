from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_gate_runner_lists_seventeen_tasks() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/run_gates.py", "--list"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "T1" in result.stdout and "T17" in result.stdout
