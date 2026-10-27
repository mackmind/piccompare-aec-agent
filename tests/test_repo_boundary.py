from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import check_boundary

ROOT = Path(__file__).resolve().parent.parent


def test_boundary_checker_passes_on_clean_repo() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_boundary.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_internal_record_names_are_refused() -> None:
    assert check_boundary.name_errors(Path("docs/LIVE-HANDOFF.md"))
    assert check_boundary.name_errors(Path("054-STATUS.md"))
    assert check_boundary.name_errors(Path("decision-log.md"))
    assert check_boundary.name_errors(Path("REVIEW.md"))
    assert not check_boundary.name_errors(Path("docs/LIVE-RUN.md"))
    assert not check_boundary.name_errors(Path("docs/preview.md"))


def test_pyproject_is_mit_and_python_311_plus() -> None:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'license = { text = "MIT" }' in text
    assert 'requires-python = ">=3.11"' in text
