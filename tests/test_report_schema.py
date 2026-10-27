from __future__ import annotations

import json

import pytest
from factories import report

from aec.report import build_report, write_report


def test_report_requires_exact_demo_notice(tmp_path) -> None:
    payload = report("p1", high=1)
    payload = payload.model_copy(
        update={"demo_notice": "HACKATHON DEMO - NOT AN EVIDENCE RECORD"}
    )
    with pytest.raises(ValueError):
        write_report(payload, tmp_path)


def test_clean_report_writes_ascii_json_and_markdown(tmp_path) -> None:
    json_path, md_path = write_report(report("p1", high=1), tmp_path)
    raw = json_path.read_bytes()
    assert all(byte < 128 for byte in raw)
    data = json.loads(json_path.read_text(encoding="ascii"))
    assert data["demo_notice"] == "HACKATHON DEMO \u2014 NOT AN EVIDENCE RECORD"
    assert data["digest"]
    assert "PASS" not in md_path.read_text(encoding="utf-8")  # no fake verification claim


def test_build_report_sets_digest() -> None:
    built = build_report(
        engine={},
        inputs={},
        settings={},
        plan=report("p1").plan,
        pages=[],
        elements_a=[],
        elements_b=[],
        matches=[],
        measurements=[],
        findings=[],
        rejected=[],
        not_compared=[],
        evidence={},
        usage={},
        limitations=["synthetic only"],
    )
    assert len(built.digest) == 64
    assert built.demo_notice == "HACKATHON DEMO \u2014 NOT AN EVIDENCE RECORD"
