"""Propose candidate regions from a plan image (no model, no ground truth).

Line-art plans enclose rooms with walls, so the free (paper) areas bounded by
dark strokes are the room candidates. SAM 3.1 does not answer concept prompts
on line art, so the live pipeline proposes boxes here and asks SAM to segment
each one; the mask, not the box, is what the comparison then uses.
"""
from __future__ import annotations

import cv2
import numpy as np

MIN_SIDE_PX = 30


def _iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    if x2 <= x1 or y2 <= y1:
        return 0.0
    inter = (x2 - x1) * (y2 - y1)
    union = ((a[2] - a[0]) * (a[3] - a[1])
             + (b[2] - b[0]) * (b[3] - b[1]) - inter)
    return inter / union if union else 0.0


def _contains(outer: tuple[int, int, int, int],
              inner: tuple[int, int, int, int]) -> bool:
    return (outer[0] <= inner[0] and outer[1] <= inner[1]
            and inner[2] <= outer[2] and inner[3] <= outer[3])


def _drop_parent_boxes(
    boxes: list[tuple[int, int, int, int]],
) -> list[tuple[int, int, int, int]]:
    """Keep the FINER partition: drop a box two or more children TILE.

    A split room is proposed twice - as the outer free-space region and as the
    two halves - because the new wall leaves a gap. Segmenting the parent hides
    the split, so the children win - but only when their union fills the parent
    AND they are disjoint pieces. A bbox-area sum is not enough: a room that
    merely contains furniture (two tables) would otherwise be deleted, which is
    the opposite of what this rule is for.
    """
    from shapely.geometry import box as _shp_box
    from shapely.ops import unary_union

    kept: list[tuple[int, int, int, int]] = []
    for box in boxes:
        children = [other for other in boxes
                    if other != box and _contains(box, other)]
        if len(children) >= 2:
            parent = _shp_box(*box)
            pieces = unary_union([_shp_box(*child) for child in children])
            covered = parent.intersection(pieces).area
            if (parent.area and covered >= 0.8 * parent.area
                    and pieces.area <= 1.05 * covered):
                continue
        kept.append(box)
    return kept


def propose_boxes(image_bytes: bytes, min_area_ratio: float = 0.01,
                  max_area_ratio: float = 0.4) -> list[tuple[int, int, int, int]]:
    """Enclosed paper regions as (x1, y1, x2, y2), largest first."""
    data = np.frombuffer(image_bytes, dtype=np.uint8)
    gray = cv2.imdecode(data, cv2.IMREAD_GRAYSCALE)
    if gray is None:
        return []
    height, width = gray.shape[:2]
    _, dark = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    kernel = np.ones((5, 5), np.uint8)
    walls = cv2.dilate(dark, kernel, iterations=1)
    free = cv2.bitwise_not(walls)
    contours, _ = cv2.findContours(free, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    page_area = width * height
    minimum = max(MIN_SIDE_PX, int(min_area_ratio * page_area))
    maximum = int(max_area_ratio * page_area)
    boxes: list[tuple[int, int, int, int]] = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w < MIN_SIDE_PX or h < MIN_SIDE_PX:
            continue
        if w * h < minimum or w * h > maximum:
            continue
        # The page background and its margin are page-sized regions, not rooms.
        if x <= 2 or y <= 2 or x + w >= width - 2 or y + h >= height - 2:
            continue
        box = (x, y, x + w, y + h)
        if box not in boxes:
            boxes.append(box)
    boxes.sort(key=lambda box: (box[2] - box[0]) * (box[3] - box[1]), reverse=True)
    # A room's wall produces an inner and an outer contour; keep the larger of
    # any near-identical pair so a room is proposed once.
    kept: list[tuple[int, int, int, int]] = []
    for box in boxes:
        if all(_iou(box, other) < 0.8 for other in kept):
            kept.append(box)
    return _drop_parent_boxes(kept)
