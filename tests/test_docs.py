from __future__ import annotations

from pathlib import Path

from aec.evidence import sha256_file, verify
from aec.models import Report

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
    # Round 14: live evidence exists, so "not yet exercised" became false.
    # Pin the limits that must always be stated instead.
    assert "not signed" in text
    assert "no real-world accuracy claim" in text


def test_submission_checklist_has_no_placeholders() -> None:
    text = (ROOT / "docs" / "SUBMISSION.md").read_text(encoding="utf-8")
    assert "TODO" not in text
    assert "TBD" not in text
    assert "not yet recorded" in text


def test_limitations_are_explicit() -> None:
    text = (ROOT / "docs" / "LIMITATIONS.md").read_text(encoding="utf-8")
    # Round 13: live evidence now exists, so the pinned phrase became false.
    # Keep the test on the limits that must always be stated.
    for phrase in ["Synthetic data only", "No real-world accuracy claim",
                   "No full CAD", "No OCR", "No signed evidence"]:
        assert phrase in text


def test_limitations_doc_states_the_card_limit() -> None:
    flat = " ".join(
        (ROOT / "docs" / "LIMITATIONS.md").read_text(encoding="utf-8").split()
    )
    assert (
        "Evidence cards are raster crops of the plan at the measured element's "
        "box; they show what was measured, not that the measurement is correct."
    ) in flat


def test_sample_report_is_valid_and_verifies() -> None:
    path = ROOT / "demo" / "sample-report.json"
    report = Report.model_validate_json(path.read_text(encoding="utf-8"))
    assert report.findings
    assert report.demo_notice == "HACKATHON DEMO \u2014 NOT AN EVIDENCE RECORD"
    assert verify(path, inputs_dir=ROOT / "fixtures" / "aec" / "resize-01").ok


def test_committed_sample_report_carries_verifiable_cards() -> None:
    path = ROOT / "demo" / "sample-report.json"
    report = Report.model_validate_json(path.read_text(encoding="utf-8"))
    assert len(report.evidence_cards) == 2
    assert {card.side for card in report.evidence_cards} == {"a", "b"}
    total = 0
    for card in report.evidence_cards:
        png = ROOT / "demo" / card.path
        assert png.is_file()
        assert card.sha256 == sha256_file(png)
        assert card.bytes == png.stat().st_size
        total += card.bytes
    assert total < 200 * 1024
    markdown = (ROOT / "demo" / "sample-report.md").read_text(encoding="utf-8")
    assert "## Evidence cards" in markdown
    for card in report.evidence_cards:
        assert card.path in markdown


def test_committed_live_report_verifies_and_names_the_live_provider() -> None:
    path = ROOT / "demo" / "live-report.json"
    report = Report.model_validate_json(path.read_text(encoding="utf-8"))
    assert report.findings
    assert report.usage["provider"] == "live_meta"
    assert report.usage["sam_calls"] > 0
    assert report.usage["sam_model"] and report.usage["meta_model"]
    assert verify(path, inputs_dir=ROOT / "fixtures" / "aec" / "resize-01").ok
