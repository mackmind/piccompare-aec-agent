from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_readme_has_required_sections_and_repo_link() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    for section in [
        "## What it is",
        "## Quick start",
        "## Evidence",
        "## Limitations",
        "## Licence",
    ]:
        assert section in text
    assert "https://github.com/mackmind/piccompare-aec-agent" in text
    assert "not yet exercised" in text


def test_submission_checklist_has_no_placeholders() -> None:
    text = (ROOT / "docs" / "SUBMISSION.md").read_text(encoding="utf-8")
    assert "TODO" not in text
    assert "TBD" not in text
    assert "not yet recorded" in text


def test_limitations_are_explicit() -> None:
    text = (ROOT / "docs" / "LIMITATIONS.md").read_text(encoding="utf-8")
    for phrase in ["Synthetic data only", "No live model evidence", "No full CAD"]:
        assert phrase in text
