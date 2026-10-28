"""Compare measurements only for elements whose definitions are comparable."""

from __future__ import annotations

from typing import Literal

from aec.geometry import angles_deg, resample_polygon, segments_px
from aec.models import Element, ElementMatch, Finding, MeasurementDelta, PlanSpec


def _deltas(first: list[float], second: list[float]) -> list[float]:
    return [abs(a - b) for a, b in zip(first, second, strict=False)]


def _comparable_geometry(first: Element, second: Element) -> tuple[
        list[float], list[float], list[float], list[float]]:
    """Segment/angle lists for a matched pair on a common sampling.

    A mask may simplify to one more vertex than its counterpart (a chamfered
    corner), and zipping the raw lists then reports a large delta at every later
    index. When the counts differ, resample both polygons onto the same
    arc-length grid so the comparison stays shape-based.
    """
    if len(first.segments_px) == len(second.segments_px):
        return (first.segments_px, second.segments_px,
                first.angles_deg, second.angles_deg)
    count = max(12, min(64, 2 * max(len(first.segments_px),
                                   len(second.segments_px))))
    first_polygon = resample_polygon(first.polygon_px, count)
    second_polygon = resample_polygon(second.polygon_px, count)
    return (segments_px(first_polygon), segments_px(second_polygon),
            angles_deg(first_polygon), angles_deg(second_polygon))


def compare_measurements(
    matches: list[ElementMatch],
    a_elements: list[Element],
    b_elements: list[Element],
    spec: PlanSpec,
) -> list[MeasurementDelta]:
    a_by_id = {element.element_id: element for element in a_elements}
    b_by_id = {element.element_id: element for element in b_elements}
    deltas: list[MeasurementDelta] = []
    for match in matches:
        first = a_by_id.get(match.a_id) if match.a_id else None
        second = b_by_id.get(match.b_id) if match.b_id else None
        if match.status != "matched" or first is None or second is None:
            deltas.append(
                MeasurementDelta(
                    element_id=match.a_id or "unknown",
                    status="not_compared",
                    area_delta_m2=None,
                    segment_deltas_px=[],
                    angle_deltas_deg=[],
                    reasons=match.reasons + [f"match:{match.status}"],
                )
            )
            continue
        area_delta = second.area_m2 - first.area_m2
        first_segments, second_segments, first_angles, second_angles = (
            _comparable_geometry(first, second))
        segment_deltas = _deltas(first_segments, second_segments)
        angle_deltas = _deltas(first_angles, second_angles)
        reasons: list[str] = []
        if abs(area_delta) > spec.material_area_delta_m2:
            reasons.append("area_delta")
        if any(delta > spec.dimension_tolerance_px for delta in segment_deltas):
            reasons.append("segment_delta")
        if any(delta > spec.angle_tolerance_deg for delta in angle_deltas):
            reasons.append("angle_delta")
        if first.label != second.label:
            reasons.append("label_changed")
        material = bool(reasons)
        deltas.append(
            MeasurementDelta(
                element_id=first.element_id,
                status="comparable" if material else "no_material_change",
                area_delta_m2=round(area_delta, 6),
                segment_deltas_px=[round(value, 6) for value in segment_deltas],
                angle_deltas_deg=[round(value, 6) for value in angle_deltas],
                reasons=reasons,
            )
        )
    return deltas


ChangeType = Literal[
    "room_resized",
    "wall_moved",
    "room_split",
    "room_merged",
    "room_added",
    "room_removed",
    "label_changed",
    "no_material_change",
]
Materiality = Literal["high", "medium", "low"]


def _change_type(delta: MeasurementDelta) -> tuple[ChangeType, Materiality]:
    reasons = set(delta.reasons)
    if "split" in " ".join(delta.reasons).lower():
        return ("room_split", "high")
    if "merged" in " ".join(delta.reasons).lower():
        return ("room_merged", "high")
    if "label_changed" in reasons:
        return ("label_changed", "low")
    if "area_delta" in reasons or "segment_delta" in reasons:
        return ("room_resized", "high")
    return ("no_material_change", "low")


def candidate_findings(
    deltas: list[MeasurementDelta],
    matches: list[ElementMatch],
    a_elements: list[Element],
    b_elements: list[Element],
    spec: PlanSpec,
) -> list[Finding]:
    a_by_id = {element.element_id: element for element in a_elements}
    b_by_id = {element.element_id: element for element in b_elements}
    match_by_a = {match.a_id: match for match in matches if match.a_id}
    findings: list[Finding] = []
    for delta in deltas:
        match = match_by_a.get(delta.element_id)
        change_type, materiality = _change_type(delta)
        if delta.status == "no_material_change":
            continue
        first = a_by_id.get(delta.element_id)
        second = b_by_id.get(match.b_id) if match and match.b_id else None
        evidence_refs = [
            element_id
            for element_id in (delta.element_id, match.b_id if match else None)
            if element_id
        ]
        claim = "; ".join(delta.reasons) or "measurement change"
        if first is not None and second is not None:
            claim = (
                f"{claim}; area {first.area_m2:.3f} -> {second.area_m2:.3f} m2 "
                f"(delta {delta.area_delta_m2:+.3f})"
            )
        findings.append(
            Finding(
                finding_id=f"{change_type}:{delta.element_id}",
                change_type=change_type,
                element_ids=evidence_refs,
                materiality=materiality,
                status="not_compared" if delta.status == "not_compared" else "verified",
                claim=claim,
                evidence_refs=evidence_refs,
                measurement_refs=[f"measurement:{delta.element_id}"],
                reasons=delta.reasons,
            )
        )
    return findings
