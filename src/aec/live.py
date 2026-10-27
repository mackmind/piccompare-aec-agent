"""Live SAM 3.1 + Muse Spark pipeline plumbing.

The live response shape must be validated against the official API before a
real run. This module is fake-transport tested; no network call is made here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from aec.compare import candidate_findings, compare_measurements
from aec.correspondence import match_elements
from aec.critic import Critic
from aec.elements import build_elements
from aec.evidence import build_evidence
from aec.masks import mask_to_polygon
from aec.meta import MetaClient
from aec.models import PageGeometry, SamObject
from aec.pipeline import PairResult, _scale, plan_from_config
from aec.report import build_report, write_report
from aec.sam import SamClient, SamResult
from aec.sam_adapter import object_from_payload


def _raw_with_polygon(raw: dict[str, Any]) -> dict[str, Any]:
    if raw.get("polygon") or raw.get("bbox"):
        return raw
    mask = raw.get("mask")
    if mask is None:
        raise ValueError("live SAM object has neither polygon, bbox nor mask")
    polygon = mask_to_polygon(np.asarray(mask, dtype=np.uint8))
    return {**raw, "polygon": [list(point) for point in polygon]}


def live_objects(
    result: SamResult,
    page: PageGeometry,
    fixture: str,
    side: str,
) -> list[SamObject]:
    return [
        object_from_payload(
            _raw_with_polygon(raw), page, fixture, index, side
        )
        for index, raw in enumerate(result.objects)
    ]


def run_pair_live(
    fixture_dir: str | Path,
    sam_client: SamClient,
    meta_client: MetaClient,
    out_dir: str | Path | None = None,
    prompt: str = "room",
) -> PairResult:
    directory = Path(fixture_dir)
    config = json.loads((directory / "config.json").read_text(encoding="utf-8"))
    plan = plan_from_config(config)
    page_config = config["page"]
    page = PageGeometry(
        page=int(page_config["page"]),
        width=int(page_config["width"]),
        height=int(page_config["height"]),
    )
    scale = _scale(config)
    a_result = sam_client.segment((directory / "a.png").read_bytes(), prompt, page.page)
    b_result = sam_client.segment((directory / "b.png").read_bytes(), prompt, page.page)
    meta_calls_start = meta_client.calls
    meta_result_before = meta_client.last_result
    elements_a = build_elements(
        live_objects(a_result, page, plan.pair_id, "a"), scale, plan.pair_id
    )
    elements_b = build_elements(
        live_objects(b_result, page, plan.pair_id, "b"), scale, plan.pair_id
    )
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
            "sam": {
                "model": a_result.model,
                "calls": a_result.calls + b_result.calls,
                "usage": {"a": a_result.usage, "b": b_result.usage},
            },
            "meta": {
                "model": meta_client.model_id,
                "calls": meta_client.calls,
                "usage": (
                    meta_client.last_result.usage
                    if meta_client.last_result
                    else None
                ),
            },
        },
    )
    findings = Critic(meta_client).verify(
        candidates, measurements, matches, evidence, plan
    )
    meta_calls = meta_client.calls - meta_calls_start
    latest_result = (
        meta_client.last_result
        if meta_client.last_result is not meta_result_before
        else None
    )
    latest_usage = latest_result.usage if latest_result else {}
    evidence["receipts"]["meta"] = {
        "model": meta_client.model_id,
        "calls": meta_calls,
        "usage": latest_usage or None,
    }
    verified = [finding for finding in findings if finding.status == "verified"]
    rejected = [finding for finding in findings if finding.status == "rejected"]
    not_compared = [
        finding for finding in findings if finding.status == "not_compared"
    ]
    report = build_report(
        engine={"name": "external", "mode": "live_meta"},
        inputs={"a": "a.png", "b": "b.png"},
        settings={"variant": config.get("variant"), "mode": "live_meta"},
        plan=plan,
        pages=[page],
        elements_a=elements_a,
        elements_b=elements_b,
        matches=matches,
        measurements=measurements,
        findings=verified,
        rejected=rejected,
        not_compared=not_compared,
        evidence=evidence,
        usage={
            "provider": "live_meta",
            "sam_model": a_result.model,
            "meta_model": meta_client.model_id,
            "model": meta_client.model_id,
            "network": True,
            "meta_api_calls": meta_calls,
            "sam_calls": a_result.calls + b_result.calls,
            "sam_usage": {"a": a_result.usage, "b": b_result.usage},
            "meta_usage": latest_usage,
            "fallback_used": False,
            "note": "Live run; receipts are recorded from the clients.",
        },
        limitations=[
            "Live SAM response shape must be validated against the official API.",
            "Synthetic fixture used for this live-path test only; no real-world claim.",
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
