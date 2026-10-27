from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_boundary_checker_passes_on_clean_repo() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_boundary.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_pyproject_is_mit_and_python_311_plus() -> None:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'license = { text = "MIT" }' in text
    assert 'requires-python = ">=3.11"' in text
