from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from aec.models import (
    DEMO_NOTICE,
    Element,
    Finding,
    PlanSpec,
    Report,
    dump_ascii_json,
    load_json_model,
)


def test_plan_spec_requires_positive_scale() -> None:
    with pytest.raises(ValidationError):
        PlanSpec(
            pair_id="p1",
            units="m",
            px_per_unit=0,
            element_types=["room"],
            area_tolerance_m2=0.05,
            dimension_tolerance_px=2,
            angle_tolerance_deg=1,
            material_area_delta_m2=0.1,
            scale_source="config",
        )


def test_plan_spec_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        PlanSpec(
            pair_id="p1",
            units="m",
            px_per_unit=10,
            element_types=["room"],
            area_tolerance_m2=0.05,
            dimension_tolerance_px=2,
            angle_tolerance_deg=1,
            material_area_delta_m2=0.1,
            scale_source="config",
            unknown=True,
        )


def test_element_rejects_negative_area() -> None:
    with pytest.raises(ValidationError):
        Element(
            element_id="e1",
            page=0,
            element_type="room",
            label="A",
            polygon_px=[[0, 0], [1, 0], [1, 1]],
            area_px2=-1,
            area_m2=1,
            centroid_px=[0, 0],
            segments_px=[],
            angles_deg=[],
            source_objects=[],
            confidence=0.9,
        )


def test_demo_notice_is_exact_u2014() -> None:
    assert DEMO_NOTICE == "HACKATHON DEMO \u2014 NOT AN EVIDENCE RECORD"


def test_report_roundtrip_is_ascii(tmp_path) -> None:
    report = Report(
        schema_version="piccompare-aec-report/1.0",
        demo_notice=DEMO_NOTICE,
        generated_at="2026-10-27T00:00:00+00:00",
        engine={},
        inputs={},
        settings={},
        plan=PlanSpec(
            pair_id="p1",
            units="m",
            px_per_unit=10,
            element_types=["room"],
            area_tolerance_m2=0.05,
            dimension_tolerance_px=2,
            angle_tolerance_deg=1,
            material_area_delta_m2=0.1,
            scale_source="config",
        ),
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
        limitations=[],
        digest="0" * 64,
    )
    path = tmp_path / "report.json"
    dump_ascii_json(report, path)
    raw = path.read_bytes()
    assert all(byte < 128 for byte in raw)
    loaded = load_json_model(path, Report)
    assert loaded.demo_notice == DEMO_NOTICE
    assert json.loads(path.read_text(encoding="ascii"))["plan"]["pair_id"] == "p1"


def test_finding_requires_known_status() -> None:
    with pytest.raises(ValidationError):
        Finding(
            finding_id="f1",
            change_type="room_resized",
            element_ids=["e1"],
            materiality="high",
            status="maybe",
            claim="c",
            evidence_refs=["e"],
            measurement_refs=["m"],
            reasons=[],
        )
