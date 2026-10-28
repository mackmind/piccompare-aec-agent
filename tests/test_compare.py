from __future__ import annotations

from factories import compare_one, element, spec, split_pair, square

from aec.compare import candidate_findings, compare_measurements
from aec.correspondence import match_elements


def test_area_delta_is_reported() -> None:
    delta = compare_one(square(10), square(12), spec())
    assert delta.status == "comparable"
    assert delta.area_delta_m2 == 0.44


def test_definition_mismatch_is_not_compared() -> None:
    delta = compare_one(square(10), split_pair(), spec())
    assert delta.status == "not_compared"
    assert "definition" in " ".join(delta.reasons).lower()


def test_below_tolerance_is_no_material_change() -> None:
    delta = compare_one(square(10), square(10.01), spec())
    assert delta.status == "no_material_change"


def test_label_change_finding() -> None:
    first = [element("a1", square(10), label="ROOM A")]
    second = [element("b1", square(10), label="ROOM A REV")]
    matches = match_elements(first, second, spec())
    deltas = compare_measurements(matches, first, second, spec())
    findings = candidate_findings(deltas, matches, first, second, spec())
    assert findings[0].change_type == "label_changed"
    assert findings[0].materiality == "low"


def test_split_candidate_is_not_compared() -> None:
    first = [element("a1", square(10))]
    second = split_pair()
    matches = match_elements(first, second, spec(iou=0.8, centroid=2))
    deltas = compare_measurements(matches, first, second, spec())
    findings = candidate_findings(deltas, matches, first, second, spec())
    assert findings[0].status == "not_compared"
    assert findings[0].change_type == "room_split"


def test_vertex_count_mismatch_is_compared_on_a_common_sampling():
    from aec.compare import _comparable_geometry
    from aec.models import Element

    def element(polygon):
        return Element(element_id="e", element_type="room", label="room", page=0,
                       polygon_px=polygon, area_px2=160000.0, area_m2=16.0,
                       centroid_px=[300.0, 300.0], segments_px=[400.0] * 4,
                       angles_deg=[90.0] * 4, source_objects=["o"], confidence=1.0)

    square = [[100, 100], [500, 100], [500, 500], [100, 500], [100, 100]]
    chamfered = [[100, 100], [500, 100], [500, 480], [480, 500], [100, 500],
                 [100, 100]]
    first_segments, second_segments, _, _ = _comparable_geometry(
        element(square), element(chamfered))
    assert len(first_segments) == len(second_segments)
    deltas = [abs(a - b) for a, b in zip(first_segments, second_segments, strict=True)]
    assert max(deltas) < 20.0, deltas
