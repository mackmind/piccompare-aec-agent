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
from aec.models import PageGeometry, PlanSpec, SamObject
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


# A mask edge sits a few pixels off the drawn line, so segment/angle tolerances
# widen 5x. The material AREA floor comes from geometry instead: a 400 px room
# with a +-2 px boundary displaces about 0.3 m2 at 100 px/m.
MASK_PRECISION_MULTIPLIER = 5.0
MASK_AREA_NOISE_M2 = 0.3


def _live_plan(plan: PlanSpec) -> PlanSpec:
    """Adapt the comparison tolerances to live mask noise (disclosed).

    `area_tolerance_m2` is deliberately NOT touched: nothing in the comparison
    reads it (the material decision uses `material_area_delta_m2`), so scaling
    it would only advertise a number with no effect.
    """
    return plan.model_copy(update={
        "dimension_tolerance_px":
            plan.dimension_tolerance_px * MASK_PRECISION_MULTIPLIER,
        "angle_tolerance_deg":
            plan.angle_tolerance_deg * MASK_PRECISION_MULTIPLIER,
        "material_area_delta_m2":
            max(plan.material_area_delta_m2, MASK_AREA_NOISE_M2),
    })


def segment_proposed_regions(sam_client: SamClient, image: bytes,
                             min_area_ratio: float = 0.01) -> SamResult:
    """Propose plan regions geometrically, then let SAM produce each mask.

    SAM answers box prompts on line art but not concept prompts, so the caller
    supplies the candidate regions and the model supplies the segmentation.
    """
    import io
    import time as _time

    from PIL import Image

    from aec.propose import propose_boxes
    from aec.sam import SamError, box_prompt

    width, height = Image.open(io.BytesIO(image)).size
    boxes = propose_boxes(image, min_area_ratio=min_area_ratio)
    objects: list[dict[str, Any]] = []
    usage: dict[str, Any] = {}
    calls = 0
    model = sam_client.model_id
    started = _time.perf_counter()
    failures = 0
    for box in boxes:
        try:
            result = sam_client.segment(
                image, box_prompt(box[0], box[1], box[2], box[3], width, height),
                label="room")
        except SamError:
            # One bad region must not lose the other rooms of the side.
            failures += 1
            continue
        calls += result.calls
        model = result.model or model
        for key, value in (result.usage or {}).items():
            if isinstance(value, int):
                usage[key] = usage.get(key, 0) + value
        for obj in result.objects:
            objects.append({**obj, "object_id": str(len(objects) + 1),
                            "proposed_box": [int(v) for v in box]})
    if failures:
        usage["failed_boxes"] = failures
    return SamResult(objects=objects, usage=usage, model=model, calls=calls,
                     latency_ms=int((_time.perf_counter() - started) * 1000))


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


def _live_limitations(failures: int) -> list[str]:
    lines = [
        "Live SAM masks carry boundary noise; segment/angle tolerances are "
        f"{MASK_PRECISION_MULTIPLIER}x the plan's and the material area delta is "
        f"floored at {MASK_AREA_NOISE_M2} m2 (see the usage note).",
        "SAM supplies no room labels; the evaluator aligns live elements to "
        "ground-truth rooms by polygon IoU (scoring only).",
        "A proposed region that is not a room (title block, scale bar) is "
        "compared like any other element.",
        "Synthetic fixture used for this live-path test only; no real-world claim.",
    ]
    if failures:
        lines.append(f"{failures} proposed region(s) failed to segment and were skipped.")
    return lines


def run_pair_live(
    fixture_dir: str | Path,
    sam_client: SamClient,
    meta_client: MetaClient,
    out_dir: str | Path | None = None,
    prompt: str = "room",
    boxes_from_plan: bool = False,
) -> PairResult:
    directory = Path(fixture_dir)
    config = json.loads((directory / "config.json").read_text(encoding="utf-8"))
    plan = plan_from_config(config)
    if boxes_from_plan:
        plan = _live_plan(plan)
    page_config = config["page"]
    page = PageGeometry(
        page=int(page_config["page"]),
        width=int(page_config["width"]),
        height=int(page_config["height"]),
    )
    scale = _scale(config)
    image_a = (directory / "a.png").read_bytes()
    image_b = (directory / "b.png").read_bytes()
    if boxes_from_plan:
        a_result = segment_proposed_regions(sam_client, image_a)
        b_result = segment_proposed_regions(sam_client, image_b)
    else:
        a_result = sam_client.segment(image_a, prompt, page.page)
        b_result = sam_client.segment(image_b, prompt, page.page)
    failures = (int(a_result.usage.get("failed_boxes") or 0)
                + int(b_result.usage.get("failed_boxes") or 0))
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
            "note": (f"Live run; receipts are recorded from the clients. "
                     f"Live mask precision: segment {plan.dimension_tolerance_px:.1f} px "
                     f"and angle {plan.angle_tolerance_deg:.1f} deg "
                     f"({MASK_PRECISION_MULTIPLIER}x the plan's); material area delta "
                     f"{plan.material_area_delta_m2:.2f} m2 "
                     f"(floor {MASK_AREA_NOISE_M2} m2). "
                     f"area_tolerance_m2 is not consulted by the comparison."),
        },
        limitations=_live_limitations(failures),
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
