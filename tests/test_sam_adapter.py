from __future__ import annotations

from pathlib import Path

from aec.models import PageGeometry
from aec.sam_adapter import load_fixture_side, segment_payload

ROOT = Path(__file__).resolve().parent.parent


def test_sam_payload_bbox_becomes_polygon() -> None:
    payload = {
        "pages": [
            {
                "page": 0,
                "objects": [
                    {"label": "room", "bbox": [10, 10, 110, 110], "score": 0.9}
                ],
            }
        ]
    }
    objects = segment_payload(
        payload, [PageGeometry(page=0, width=200, height=200)], "p1"
    )
    assert objects[0].label == "room"
    assert objects[0].source == "sam31"
    assert objects[0].polygon_px[0] == objects[0].polygon_px[-1]
    assert len(objects[0].polygon_px) == 5


def test_sam_payload_polygon_is_preserved() -> None:
    payload = {
        "pages": [
            {
                "page": 0,
                "objects": [
                    {
                        "label": "space",
                        "polygon": [[0, 0], [10, 0], [10, 10], [0, 10]],
                        "score": 0.8,
                    }
                ],
            }
        ]
    }
    objects = segment_payload(
        payload, [PageGeometry(page=0, width=20, height=20)], "p2"
    )
    assert objects[0].label == "space"
    assert objects[0].polygon_px[-1] == [0, 0]


def test_fixture_payload_has_rooms_on_both_sides() -> None:
    pages = [PageGeometry(page=0, width=1600, height=1200)]
    a_objects = load_fixture_side(
        ROOT / "fixtures" / "aec" / "resize-01", "a", pages, "resize-01"
    )
    b_objects = load_fixture_side(
        ROOT / "fixtures" / "aec" / "resize-01", "b", pages, "resize-01"
    )
    assert len(a_objects) == 4
    assert len(b_objects) == 4
    assert all(obj.source == "sam31" for obj in a_objects + b_objects)
