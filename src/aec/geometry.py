"""Deterministic polygon geometry for AEC measurements."""

from __future__ import annotations

import math
from collections.abc import Sequence

from shapely.geometry import Polygon
from shapely.ops import unary_union

Point = tuple[float, float]
PolygonLike = Sequence[Sequence[float]]


def _points(polygon: PolygonLike) -> list[Point]:
    return [(float(point[0]), float(point[1])) for point in polygon]


def _open_points(polygon: PolygonLike) -> list[Point]:
    points = _points(polygon)
    if len(points) > 1 and points[0] == points[-1]:
        return points[:-1]
    return points


def polygon_area_px(polygon: PolygonLike) -> float:
    points = _points(polygon)
    if len(points) < 3:
        return 0.0
    return abs(
        sum(
            points[index][0] * points[(index + 1) % len(points)][1]
            - points[(index + 1) % len(points)][0] * points[index][1]
            for index in range(len(points))
        )
    ) / 2.0


def segments_px(polygon: PolygonLike) -> list[float]:
    points = _open_points(polygon)
    if len(points) < 2:
        return []
    return [
        math.dist(points[index], points[(index + 1) % len(points)])
        for index in range(len(points))
    ]


def polygon_perimeter_px(polygon: PolygonLike) -> float:
    return sum(segments_px(polygon))


def angles_deg(polygon: PolygonLike) -> list[float]:
    points = _open_points(polygon)
    if len(points) < 3:
        return []
    result: list[float] = []
    for index, current in enumerate(points):
        previous = points[index - 1]
        following = points[(index + 1) % len(points)]
        first = (previous[0] - current[0], previous[1] - current[1])
        second = (following[0] - current[0], following[1] - current[1])
        first_norm = math.hypot(*first)
        second_norm = math.hypot(*second)
        if first_norm == 0 or second_norm == 0:
            result.append(0.0)
            continue
        cosine = (first[0] * second[0] + first[1] * second[1]) / (
            first_norm * second_norm
        )
        cosine = max(-1.0, min(1.0, cosine))
        result.append(round(math.degrees(math.acos(cosine)), 6))
    return result


def centroid_px(polygon: PolygonLike) -> Point:
    points = _points(polygon)
    if len(points) < 3:
        return (0.0, 0.0)
    signed_area = 0.0
    cx = 0.0
    cy = 0.0
    for index in range(len(points)):
        x0, y0 = points[index]
        x1, y1 = points[(index + 1) % len(points)]
        cross = x0 * y1 - x1 * y0
        signed_area += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    signed_area *= 0.5
    if abs(signed_area) < 1e-12:
        open_points = _open_points(polygon)
        return (
            sum(point[0] for point in open_points) / len(open_points),
            sum(point[1] for point in open_points) / len(open_points),
        )
    return (cx / (6.0 * signed_area), cy / (6.0 * signed_area))


def _shape(polygon: PolygonLike) -> Polygon:
    return Polygon(_points(polygon)).buffer(0)


def simplify_polygon(polygon: PolygonLike, tolerance_px: float) -> list[Point]:
    shape = _shape(polygon)
    if shape.is_empty:
        return []
    simplified = shape.simplify(tolerance_px, preserve_topology=True)
    coordinates = list(simplified.exterior.coords)
    if len(coordinates) < 4:
        return []
    return [(float(x), float(y)) for x, y in coordinates]


def polygon_iou(first: PolygonLike, second: PolygonLike) -> float:
    a = _shape(first)
    b = _shape(second)
    if a.is_empty or b.is_empty:
        return 0.0
    union = a.union(b)
    if union.area == 0:
        return 0.0
    return float(a.intersection(b).area / union.area)


def polygon_coverage(polygon: PolygonLike, candidates: Sequence[PolygonLike]) -> float:
    """Fraction of ``polygon`` covered by the union of candidate polygons."""
    target = _shape(polygon)
    if target.is_empty or target.area == 0:
        return 0.0
    shapes = [_shape(candidate) for candidate in candidates]
    shapes = [shape for shape in shapes if not shape.is_empty]
    if not shapes:
        return 0.0
    union = unary_union(shapes)
    return float(target.intersection(union).area / target.area)
