"""Shared model/test factories.

The geometry-dependent helpers are imported lazily by later tasks; Task 2 tests
only use the model constructors.
"""

from __future__ import annotations

import json

from aec.models import (
    DEMO_NOTICE,
    Element,
    Finding,
    PageGeometry,
    PlanSpec,
    Report,
)


def spec(
    iou: float = 0.5,
    centroid: float = 8.0,
    px_per_unit: float = 10.0,
    **overrides,
) -> PlanSpec:
    values = {
        "pair_id": "p1",
        "units": "m",
        "px_per_unit": px_per_unit,
        "element_types": ["room"],
        "area_tolerance_m2": 0.05,
        "dimension_tolerance_px": 2.0,
        "angle_tolerance_deg": 1.0,
        "material_area_delta_m2": 0.1,
        "scale_source": "config",
        "match_iou_threshold": iou,
        "match_centroid_tolerance_px": centroid,
        "match_area_ratio_tolerance": 0.4,
    }
    values.update(overrides)
    return PlanSpec(**values)


def square(size_px: float, x: float = 0.0, y: float = 0.0) -> list[tuple[float, float]]:
    return [
        (x, y),
        (x + size_px, y),
        (x + size_px, y + size_px),
        (x, y + size_px),
        (x, y),
    ]


def element(
    element_id: str,
    polygon: list[tuple[float, float]],
    page: int = 0,
    label: str = "room",
    scale: float = 10.0,
) -> Element:
    from aec import geometry

    area_px = geometry.polygon_area_px(polygon)
    return Element(
        element_id=element_id,
        page=page,
        element_type="room",
        label=label,
        polygon_px=polygon,
        area_px2=area_px,
        area_m2=area_px / (scale * scale),
        centroid_px=list(geometry.centroid_px(polygon)),
        segments_px=geometry.segments_px(polygon),
        angles_deg=geometry.angles_deg(polygon),
        source_objects=[f"src:{element_id}"],
        confidence=0.9,
    )


def candidate(
    change_type: str = "room_resized",
    evidence_refs: list[str] | None = None,
) -> Finding:
    return Finding(
        finding_id="f1",
        change_type=change_type,
        element_ids=["e1"],
        materiality="high",
        status="verified",
        claim="candidate",
        evidence_refs=list(evidence_refs or []),
        measurement_refs=["m1"],
        reasons=[],
    )


def sample_report(rooms: int = 3) -> Report:
    elements = [element(f"e{i}", square(10, x=i * 20)) for i in range(rooms)]
    return Report(
        schema_version="piccompare-aec-report/1.0",
        demo_notice=DEMO_NOTICE,
        generated_at="2026-10-27T00:00:00+00:00",
        engine={},
        inputs={},
        settings={},
        plan=spec(),
        pages=[PageGeometry(page=0, width=1600, height=1200)],
        elements_a=elements,
        elements_b=elements,
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


def report(pair_id: str, high: int = 0, medium: int = 0) -> Report:
    findings = [
        Finding(
            finding_id=f"{pair_id}-{i}",
            change_type="room_resized",
            element_ids=[f"e{i}"],
            materiality=("high" if i < high else "medium"),
            status="verified",
            claim="c",
            evidence_refs=["e"],
            measurement_refs=["m"],
            reasons=[],
        )
        for i in range(high + medium)
    ]
    return sample_report(rooms=1).model_copy(
        update={"plan": spec(pair_id=pair_id), "findings": findings}
    )


def split_pair() -> list[Element]:
    return [element("b1", square(5, x=0)), element("b2", square(5, x=5))]


def compare_one(a_polygon, b, plan: PlanSpec):
    from aec.compare import compare_measurements
    from aec.correspondence import match_elements

    a_elements = [element("a1", a_polygon)]
    if b and isinstance(b[0], (tuple, list)) and len(b[0]) == 2:
        b_elements = [element("b1", b)]
    else:
        b_elements = list(b)
    matches = match_elements(a_elements, b_elements, plan)
    return compare_measurements(matches, a_elements, b_elements, plan)[0]


def defaults() -> PlanSpec:
    return spec()


class _OneShotTransport:
    def __init__(self, response: dict) -> None:
        self.response = response

    def __call__(self, url, headers, payload, timeout):
        return self.response


def fake_meta_client(payload: dict):
    from aec.meta import MetaClient

    content = json.dumps(payload)
    transport = _OneShotTransport(
        {"choices": [{"message": {"content": content}}]}
    )
    return MetaClient(
        api_key="test-key",
        model_id="test-model",
        base_url="https://example.invalid/v1",
        transport=transport,
    )
