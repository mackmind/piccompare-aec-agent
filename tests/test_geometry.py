from __future__ import annotations

import pytest

from aec.geometry import (
    angles_deg,
    centroid_px,
    polygon_area_px,
    polygon_iou,
    polygon_perimeter_px,
    segments_px,
    simplify_polygon,
)


def test_square_geometry() -> None:
    square = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)]
    assert polygon_area_px(square) == pytest.approx(100)
    assert segments_px(square) == [10, 10, 10, 10]
    assert angles_deg(square) == [90, 90, 90, 90]
    assert centroid_px(square) == pytest.approx((5, 5))
    assert polygon_perimeter_px(square) == pytest.approx(40)


def test_iou_same_and_disjoint() -> None:
    square = [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]
    assert polygon_iou(square, square) == pytest.approx(1.0)
    other = [(20, 20), (30, 20), (30, 30), (20, 30), (20, 20)]
    assert polygon_iou(square, other) == pytest.approx(0.0)


def test_iou_half_overlap() -> None:
    first = [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]
    second = [(5, 0), (15, 0), (15, 10), (5, 10), (5, 0)]
    assert polygon_iou(first, second) == pytest.approx(50 / 150, abs=1e-6)


def test_simplify_keeps_square() -> None:
    square = [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]
    simplified = simplify_polygon(square, tolerance_px=0.1)
    assert len(simplified) >= 4
    assert simplified[0] == simplified[-1]


def test_centroid_of_triangle() -> None:
    triangle = [(0, 0), (6, 0), (0, 6), (0, 0)]
    assert centroid_px(triangle) == pytest.approx((2, 2))
    assert angles_deg(triangle) == [90, 45, 45]
