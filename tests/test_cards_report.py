"""Report, Markdown and CLI wiring for evidence cards."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from factories import report, spec

from aec.cli import main
from aec.evidence import verify
from aec.models import EvidenceCard, Finding
from aec.pipeline import run_pair
from aec.report import build_report, render_markdown

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "fixtures" / "aec" / "resize-01"
CARD_SHA = "ab" * 32

OLD_REPORT_KEYS = {
    "schema_version",
    "demo_notice",
    "generated_at",
    "engine",
    "inputs",
    "settings",
    "plan",
    "pages",
    "elements_a",
    "elements_b",
    "matches",
    "measurements",
    "findings",
    "rejected",
    "not_compared",
    "evidence",
    "usage",
    "limitations",
    "digest",
}

EXPECTED_NO_CARDS_MARKDOWN = (
    "# PicCompare AEC evidence report\n"
    "\n"
    "**HACKATHON DEMO \u2014 NOT AN EVIDENCE RECORD**\n"
    "\n"
    "- Pair: `p1`\n"
    "- Generated: 2026-10-27T00:00:00+00:00\n"
    "- Findings: 1 verified, 0 rejected, 0 not compared\n"
    "- Report digest: "
    "`0000000000000000000000000000000000000000000000000000000000000000`\n"
    "\n"
    "## Findings\n"
    "\n"
    "| Type | Materiality | Evidence | Claim |\n"
    "|---|---|---|---|\n"
    "| room_resized | high | e | c |\n"
    "\n"
    "## Not compared\n"
    "\n"
    "None.\n"
    "\n"
    "## Limitations\n"
    "\n"
    "\n"
    "This is a hashed, replayable evidence report. It is not signed and is not "
    "an evidence record.\n"
)


def card(finding_id: str = "f1") -> EvidenceCard:
    return EvidenceCard(
        finding_id=finding_id,
        side="a",
        path="cards/example-a.png",
        sha256=CARD_SHA,
        bytes=1024,
        box_px=[92, 92, 508, 508],
        page=0,
        source="plan_raster",
    )


def finding(finding_id: str = "f1") -> Finding:
    return Finding(
        finding_id=finding_id,
        change_type="room_resized",
        element_ids=["e0"],
        materiality="high",
        status="verified",
        claim="c",
        evidence_refs=["e0"],
        measurement_refs=["m0"],
        reasons=[],
    )


def built(findings: list[Finding] | None = None, cards: list[EvidenceCard] | None = None):
    return build_report(
        engine={},
        inputs={},
        settings={},
        plan=spec(pair_id="p1"),
        pages=[],
        elements_a=[],
        elements_b=[],
        matches=[],
        measurements=[],
        findings=list(findings or []),
        rejected=[],
        not_compared=[],
        evidence={},
        usage={},
        limitations=[],
        generated_at="2026-10-27T00:00:00+00:00",
        evidence_cards=list(cards or []),
    )


def test_build_report_defaults_to_no_cards() -> None:
    assert built().evidence_cards == []


def test_build_report_carries_cards_into_the_json() -> None:
    result = built(findings=[finding()], cards=[card()])
    data = json.loads(result.model_dump_json())
    assert data["evidence_cards"][0]["path"] == "cards/example-a.png"
    assert result.evidence_cards[0].sha256 == CARD_SHA


def test_markdown_lists_cards_without_embedding_them() -> None:
    markdown = render_markdown(built(findings=[finding()], cards=[card()]))
    assert "## Evidence cards" in markdown
    assert "`cards/example-a.png`" in markdown
    assert CARD_SHA in markdown
    assert "| 1024 |" in markdown
    assert "room_resized" in markdown.split("## Evidence cards")[1]
    assert "![" not in markdown  # no image embedding
    assert markdown.index("## Evidence cards") < markdown.index("## Limitations")


def test_markdown_names_an_unknown_change_type_honestly() -> None:
    markdown = render_markdown(built(cards=[card("not-in-the-report")]))
    assert "| unknown |" in markdown


def test_markdown_without_cards_is_byte_identical_to_the_old_renderer() -> None:
    markdown = render_markdown(report("p1", high=1))
    assert "## Evidence cards" not in markdown
    assert markdown == EXPECTED_NO_CARDS_MARKDOWN


def test_run_pair_with_cards_writes_pngs_and_a_markdown_section(tmp_path) -> None:
    result = run_pair(FIXTURE, tmp_path, cards=True)
    assert len(result.report.evidence_cards) == 2
    for item in result.report.evidence_cards:
        assert (tmp_path / item.path).is_file()
    markdown = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "## Evidence cards" in markdown
    data = json.loads((tmp_path / "report.json").read_text(encoding="ascii"))
    assert len(data["evidence_cards"]) == 2
    assert data["evidence"]["cards_truncated"] is False
    assert data["evidence"]["cards_skipped"] == []
    assert result.report_path is not None
    assert verify(result.report_path, inputs_dir=FIXTURE).ok


def test_run_pair_without_cards_adds_only_the_one_key(tmp_path) -> None:
    result = run_pair(FIXTURE, tmp_path)
    assert result.report.evidence_cards == []
    data = json.loads((tmp_path / "report.json").read_text(encoding="ascii"))
    assert set(data) - OLD_REPORT_KEYS == {"evidence_cards"}
    assert data["evidence_cards"] == []
    assert "## Evidence cards" not in (tmp_path / "report.md").read_text(encoding="utf-8")
    assert not (tmp_path / "cards").exists()
    assert verify(result.report_path, inputs_dir=FIXTURE).ok


def test_run_pair_cards_need_an_output_directory() -> None:
    with pytest.raises(ValueError):
        run_pair(FIXTURE, cards=True)


def test_cli_measure_cards_writes_a_section(tmp_path) -> None:
    assert main(["measure", "--fixture", str(FIXTURE), "--out", str(tmp_path), "--cards"]) == 0
    assert (tmp_path / "cards").is_dir()
    assert "## Evidence cards" in (tmp_path / "report.md").read_text(encoding="utf-8")


def test_cli_measure_without_cards_writes_no_cards(tmp_path, capsys) -> None:
    assert main(["measure", "--fixture", str(FIXTURE), "--out", str(tmp_path)]) == 0
    assert not (tmp_path / "cards").exists()
    assert "cards=" not in capsys.readouterr().out


def test_cli_measure_cards_require_out(capsys) -> None:
    assert main(["measure", "--fixture", str(FIXTURE), "--cards"]) == 2
    assert "FAIL" in capsys.readouterr().out


CARD_LIMITATION = (
    "Evidence cards are raster crops of the plan at the measured element's box; "
    "they show what was measured, not that the measurement is correct."
)


def test_cards_add_the_honesty_limitation(tmp_path) -> None:
    result = run_pair(FIXTURE, tmp_path, cards=True)
    assert CARD_LIMITATION in result.report.limitations
    assert CARD_LIMITATION in (tmp_path / "report.md").read_text(encoding="utf-8")
    data = json.loads((tmp_path / "report.json").read_text(encoding="ascii"))
    assert CARD_LIMITATION in data["limitations"]


def test_a_no_cards_run_does_not_add_the_limitation(tmp_path) -> None:
    result = run_pair(FIXTURE, tmp_path)
    assert CARD_LIMITATION not in result.report.limitations
    assert CARD_LIMITATION not in (tmp_path / "report.md").read_text(encoding="utf-8")


def test_two_card_runs_produce_identical_card_hashes(tmp_path) -> None:
    first = run_pair(FIXTURE, tmp_path / "one", cards=True)
    second = run_pair(FIXTURE, tmp_path / "two", cards=True)
    first_cards = [
        (item.side, item.sha256, item.bytes, item.box_px)
        for item in first.report.evidence_cards
    ]
    second_cards = [
        (item.side, item.sha256, item.bytes, item.box_px)
        for item in second.report.evidence_cards
    ]
    assert first_cards == second_cards
    assert len(first_cards) == 2
