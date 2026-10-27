"""Offline end-to-end AEC pipeline over synthetic fixtures."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aec.compare import candidate_findings, compare_measurements
from aec.correspondence import match_elements
from aec.critic import DeterministicCritic
from aec.elements import build_elements
from aec.evidence import build_evidence
from aec.models import (
    Element,
    ElementMatch,
    Finding,
    MeasurementDelta,
    PageGeometry,
    PlanSpec,
    Report,
)
from aec.report import build_report, write_report
from aec.sam_adapter import load_fixture_side
from aec.scale import ScaleCalibration, Source, Units


@dataclass(frozen=True)
class PairResult:
    pair_id: str
    report: Report
    report_path: Path | None
    elements_a: list[Element]
    elements_b: list[Element]
    matches: list[ElementMatch]
    measurements: list[MeasurementDelta]
    verified: list[Finding]
    rejected: list[Finding]
    not_compared: list[Finding]


def plan_from_config(config: dict[str, Any]) -> PlanSpec:
    fields = (
        "pair_id",
        "units",
        "px_per_unit",
        "element_types",
        "area_tolerance_m2",
        "dimension_tolerance_px",
        "angle_tolerance_deg",
        "material_area_delta_m2",
        "match_iou_threshold",
        "match_centroid_tolerance_px",
        "match_area_ratio_tolerance",
        "scale_source",
    )
    return PlanSpec(**{key: config[key] for key in fields})


def _scale(config: dict[str, Any]) -> ScaleCalibration:
    units: Units = "m" if config.get("units") == "m" else "mm"
    raw_source = config.get("scale_source")
    source: Source = (
        "scale_bar"
        if raw_source == "scale_bar"
        else "known_dimension"
        if raw_source == "known_dimension"
        else "config"
    )
    return ScaleCalibration(
        px_per_unit=float(config["px_per_unit"]),
        units=units,
        source=source,
    )


def run_pair(fixture_dir: str | Path, out_dir: str | Path | None = None) -> PairResult:
    directory = Path(fixture_dir)
    config = json.loads((directory / "config.json").read_text(encoding="utf-8"))
    plan = plan_from_config(config)
    page = config["page"]
    pages = [
        PageGeometry(
            page=int(page["page"]),
            width=int(page["width"]),
            height=int(page["height"]),
        )
    ]
    scale = _scale(config)
    objects_a = load_fixture_side(directory, "a", pages, plan.pair_id)
    objects_b = load_fixture_side(directory, "b", pages, plan.pair_id)
    elements_a = build_elements(objects_a, scale, plan.pair_id)
    elements_b = build_elements(objects_b, scale, plan.pair_id)
    matches = match_elements(elements_a, elements_b, plan)
    measurements = compare_measurements(matches, elements_a, elements_b, plan)
    candidates = candidate_findings(
        measurements, matches, elements_a, elements_b, plan
    )
    evidence = build_evidence(
        inputs={"a.png": directory / "a.png", "b.png": directory / "b.png"},
        elements=[*elements_a, *elements_b],
        measurements=measurements,
        receipts={
            "provider": "offline_deterministic",
            "network": False,
            "meta_api_calls": 0,
        },
    )
    findings = DeterministicCritic().verify(
        candidates, measurements, matches, evidence, plan
    )
    verified = [finding for finding in findings if finding.status == "verified"]
    rejected = [finding for finding in findings if finding.status == "rejected"]
    not_compared = [
        finding for finding in findings if finding.status == "not_compared"
    ]
    report = build_report(
        engine={"name": "fixture", "mode": "offline_deterministic"},
        inputs={"a": "a.png", "b": "b.png"},
        settings={"variant": config.get("variant"), "mode": "offline_deterministic"},
        plan=plan,
        pages=pages,
        elements_a=elements_a,
        elements_b=elements_b,
        matches=matches,
        measurements=measurements,
        findings=verified,
        rejected=rejected,
        not_compared=not_compared,
        evidence=evidence,
        usage={
            "provider": "offline_deterministic",
            "model": None,
            "network": False,
            "meta_api_calls": 0,
            "fallback_used": False,
            "note": "Offline fixture evaluation; no Meta model called.",
        },
        limitations=[
            "Synthetic plans only; no real-world accuracy claim.",
            "Deterministic offline critic; no live Meta call in this run.",
        ],
    )
    report_path: Path | None = None
    if out_dir is not None:
        json_path, _ = write_report(report, out_dir)
        report_path = json_path
    return PairResult(
        pair_id=plan.pair_id,
        report=report,
        report_path=report_path,
        elements_a=elements_a,
        elements_b=elements_b,
        matches=matches,
        measurements=measurements,
        verified=verified,
        rejected=rejected,
        not_compared=not_compared,
    )
