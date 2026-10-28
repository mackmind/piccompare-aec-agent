"""Region proposals from plan geometry, and the merged live segmentation."""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from aec.live import segment_proposed_regions
from aec.propose import _iou, propose_boxes
from aec.sam import SamResult

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "aec" / "resize-01"
PAGE_AREA = 1600 * 1200


def _gt_boxes(side: str = "a") -> list[tuple[int, int, int, int]]:
    payload = json.loads((FIXTURE / "sam31.json").read_text(encoding="utf-8"))
    objects = payload["sides"][side]["pages"][0]["objects"]
    return [tuple(int(value) for value in obj["bbox"]) for obj in objects]


def test_proposals_recover_every_room():
    boxes = propose_boxes((FIXTURE / "a.png").read_bytes())
    expected = _gt_boxes()
    assert expected
    for room in expected:
        assert any(_iou(box, room) >= 0.5 for box in boxes), (room, boxes)
    # No page-sized region: the border and its margin are not rooms.
    assert all((box[2] - box[0]) * (box[3] - box[1]) < 0.4 * PAGE_AREA
               for box in boxes)


def test_proposals_are_deduplicated():
    boxes = propose_boxes((FIXTURE / "a.png").read_bytes())
    for index, box in enumerate(boxes):
        for other in boxes[index + 1:]:
            assert _iou(box, other) < 0.8


def test_blank_page_proposes_nothing():
    blank = np.full((240, 320, 3), 255, dtype=np.uint8)
    encoded = cv2.imencode(".png", blank)[1].tobytes()
    assert propose_boxes(encoded) == []


def test_segment_proposed_regions_merges_one_call_per_box():
    prompts: list[str] = []

    class FakeClient:
        model_id = "sam-3.1"

        def segment(self, image: bytes, prompt: str, page: int = 0) -> SamResult:
            prompts.append(prompt)
            return SamResult(
                objects=[{"bbox": [0, 0, 10, 10], "label": "room",
                          "polygon": [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]],
                          "score": None, "mask_available": False}],
                usage={"images_processed": 1},
                model="sam-3.1", calls=1, latency_ms=5,
            )

    image = (FIXTURE / "a.png").read_bytes()
    boxes = propose_boxes(image)
    result = segment_proposed_regions(FakeClient(), image)  # type: ignore[arg-type]
    assert len(prompts) == len(boxes) == len(result.objects)
    assert result.calls == len(boxes)
    assert result.usage == {"images_processed": len(boxes)}
    assert all(prompt.startswith("<0f>1<|box;") for prompt in prompts)
    assert [obj["object_id"] for obj in result.objects] == [
        str(index) for index in range(1, len(boxes) + 1)]
