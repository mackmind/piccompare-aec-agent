from __future__ import annotations

from factories import element, spec, square

from aec.correspondence import match_elements
from aec.elements import build_elements
from aec.models import SamObject
from aec.scale import ScaleCalibration


def test_identical_rooms_match() -> None:
    a = [element("a1", square(10))]
    b = [element("b1", square(10))]
    matches = match_elements(a, b, spec(iou=0.8, centroid=2))
    assert matches[0].status == "matched"
    assert matches[0].b_id == "b1"


def test_split_room_is_definition_mismatch() -> None:
    a = [element("a1", square(10))]
    b = [
        element("b1", [(0, 0), (5, 0), (5, 10), (0, 10), (0, 0)]),
        element("b2", [(5, 0), (10, 0), (10, 10), (5, 10), (5, 0)]),
    ]
    matches = match_elements(a, b, spec(iou=0.8, centroid=2))
    assert matches[0].status == "definition_mismatch"


def test_merged_room_is_definition_mismatch() -> None:
    a = [element("a1", square(10))]
    b = [element("b1", [(0, 0), (20, 0), (20, 10), (0, 10), (0, 0)])]
    matches = match_elements(a, b, spec(iou=0.8, centroid=2))
    assert matches[0].status == "definition_mismatch"


def test_ambiguous_duplicate_candidates() -> None:
    a = [element("a1", square(10))]
    b = [element("b1", square(10)), element("b2", square(10))]
    matches = match_elements(a, b, spec(iou=0.5, centroid=2))
    assert matches[0].status == "ambiguous"


def test_far_room_is_unmatched() -> None:
    a = [element("a1", square(10))]
    b = [element("b1", square(10, x=100))]
    matches = match_elements(a, b, spec(iou=0.5, centroid=2))
    assert matches[0].status == "unmatched"


def test_build_elements_converts_area() -> None:
    scale = ScaleCalibration(px_per_unit=10, units="m", source="config")
    objects = [
        SamObject(
            object_id="o1",
            page=0,
            label="room",
            bbox_px=[0, 0, 10, 10],
            polygon_px=[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]],
            score=0.9,
            source="sam31",
        )
    ]
    elements = build_elements(objects, scale, "p1")
    assert elements[0].area_px2 == 100
    assert elements[0].area_m2 == 1.0
    assert elements[0].element_id == "p1:0:room:0"
