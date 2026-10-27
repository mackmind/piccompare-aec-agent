"""Match the same elements across two plan revisions."""

from __future__ import annotations

import math
from typing import Literal

from aec.geometry import polygon_coverage, polygon_iou
from aec.models import Element, ElementMatch, PlanSpec

MatchStatus = Literal["matched", "ambiguous", "definition_mismatch", "unmatched"]


def _area_ratio(first: Element, second: Element) -> float:
    largest = max(first.area_px2, second.area_px2)
    if largest <= 0:
        return 0.0
    return min(first.area_px2, second.area_px2) / largest


def _centroid_delta(first: Element, second: Element) -> float:
    return math.dist(
        (first.centroid_px[0], first.centroid_px[1]),
        (second.centroid_px[0], second.centroid_px[1]),
    )


def _match(
    first: Element,
    second: Element | None,
    status: MatchStatus,
    iou: float | None,
    centroid_delta: float | None,
    area_ratio: float | None,
    reasons: list[str],
) -> ElementMatch:
    return ElementMatch(
        a_id=first.element_id,
        b_id=second.element_id if second else None,
        status=status,
        iou=iou,
        centroid_delta_px=centroid_delta,
        area_ratio=area_ratio,
        reasons=reasons,
    )


def match_elements(
    a_elements: list[Element],
    b_elements: list[Element],
    spec: PlanSpec,
) -> list[ElementMatch]:
    matches: list[ElementMatch] = []
    for first in a_elements:
        candidates = [
            second
            for second in b_elements
            if second.element_type == first.element_type
        ]
        scored = [
            (
                second,
                polygon_iou(first.polygon_px, second.polygon_px),
                _centroid_delta(first, second),
                _area_ratio(first, second),
            )
            for second in candidates
        ]
        strong = [
            item
            for item in scored
            if item[1] >= spec.match_iou_threshold
            and item[2] <= spec.match_centroid_tolerance_px
            and item[3] >= 1.0 - spec.match_area_ratio_tolerance
        ]
        if len(strong) == 1:
            second, iou, delta, ratio = strong[0]
            matches.append(
                _match(
                    first,
                    second,
                    "matched",
                    iou,
                    delta,
                    ratio,
                    ["iou and centroid within tolerance"],
                )
            )
            continue
        if len(strong) > 1:
            matches.append(
                _match(
                    first,
                    None,
                    "ambiguous",
                    max(item[1] for item in strong),
                    min(item[2] for item in strong),
                    max(item[3] for item in strong),
                    ["multiple candidates satisfy the match thresholds"],
                )
            )
            continue
        overlapping = [
            item for item in scored if item[1] > 0.0
        ]
        coverage = polygon_coverage(
            first.polygon_px, [item[0].polygon_px for item in overlapping]
        )
        if coverage >= 0.5 and len(overlapping) >= 2:
            matches.append(
                _match(
                    first,
                    None,
                    "definition_mismatch",
                    max(item[1] for item in overlapping),
                    None,
                    None,
                    ["room is split: multiple elements cover the original"],
                )
            )
            continue
        if coverage >= 0.5 and len(overlapping) == 1:
            matches.append(
                _match(
                    first,
                    None,
                    "definition_mismatch",
                    overlapping[0][1],
                    None,
                    None,
                    ["room is merged or the counterpart covers the original"],
                )
            )
            continue
        matches.append(
            _match(first, None, "unmatched", None, None, None, ["no overlapping candidate"])
        )
    return matches
