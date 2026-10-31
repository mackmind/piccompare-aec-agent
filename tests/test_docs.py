from __future__ import annotations

from pathlib import Path

from aec import tool_registry
from aec.evidence import sha256_file, verify
from aec.models import Report
from aec.report import render_markdown

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
    # The card limit is 12 = 6 findings x 2 sides; "each verified finding"
    # overstated it as soon as a pair had more than six findings or any skip.
    assert "up to 12 PNG crops" in text


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


def test_committed_markdown_matches_the_renderer() -> None:
    for name in ("sample", "live"):
        report = Report.model_validate_json(
            (ROOT / "demo" / f"{name}-report.json").read_text(encoding="utf-8")
        )
        committed = (ROOT / "demo" / f"{name}-report.md").read_text(encoding="utf-8")
        assert committed == render_markdown(report)


def test_committed_live_report_verifies_and_names_the_live_provider() -> None:
    path = ROOT / "demo" / "live-report.json"
    report = Report.model_validate_json(path.read_text(encoding="utf-8"))
    assert report.findings
    assert report.usage["provider"] == "live_meta"
    assert report.usage["sam_calls"] > 0
    assert report.usage["sam_model"] and report.usage["meta_model"]
    assert verify(path, inputs_dir=ROOT / "fixtures" / "aec" / "resize-01").ok


def test_mcp_doc_is_linked_and_covers_every_published_tool() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    events = (ROOT / "docs" / "EVENT-INTEGRATION.md").read_text(encoding="utf-8")
    doc = (ROOT / "docs" / "MCP.md").read_text(encoding="utf-8")
    assert "docs/MCP.md" in readme
    assert "MCP.md" in events
    # The snippets must name the command that actually starts the server.
    assert '"command": "python"' in doc
    assert '"args": ["-m", "aec.mcp_server"]' in doc
    # A published tool with no row in the table is the drift this catches.
    for tool in tool_registry.TOOLS:
        assert f"`{tool.name}`" in doc, tool.name


def _flat_doc(name: str) -> str:
    return " ".join((ROOT / "docs" / name).read_text(encoding="utf-8").split()).lower()


def test_every_aec_module_is_listed_in_the_architecture_components() -> None:
    # The W4 sweep that checked this used to be a gitignored script; the test
    # makes a new module without a components row fail the suite instead.
    text = (ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
    start = text.index("## Components")
    end = text.index("\n## ", start + 1)
    table = text[start:end]
    modules = sorted(
        path.name
        for path in (ROOT / "src" / "aec").glob("*.py")
        if path.name != "__init__.py"
    )
    assert modules
    missing = [name for name in modules if name not in table]
    assert not missing, missing


def test_public_docs_credit_the_proposer_and_never_the_model_with_rooms() -> None:
    architecture = _flat_doc("ARCHITECTURE.md")
    limitations = _flat_doc("LIMITATIONS.md")
    # Both pages must credit the proposer, not SAM, with the region boxes.
    assert "region proposal" in architecture
    assert "proposed region" in limitations
    # Only affirmative phrasings are forbidden. The compliant negation
    # "not independent room discovery" is deliberate, so the bare substring
    # "room discovery" must never be banned by this guard.
    assert "room discovery" in limitations
    for text in (architecture, limitations):
        for phrase in (
            "sam finds rooms",
            "sam discovers rooms",
            "the model identifies the rooms",
        ):
            assert phrase not in text, phrase
