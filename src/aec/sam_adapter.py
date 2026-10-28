"""Normalise SAM 3.1-shaped payloads into public SAM objects."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aec.models import PageGeometry, SamObject

SUPPORTED_LABELS = {"room", "space", "wall", "column", "stair"}


class SamPayloadError(ValueError):
    pass


def _label(raw: dict[str, Any]) -> str:
    label = str(raw.get("label", "")).strip().lower()
    return label if label in SUPPORTED_LABELS else "unknown"


def _closed(points: list[list[float]]) -> list[list[float]]:
    if len(points) < 3:
        raise SamPayloadError("polygon needs at least three points")
    if points[0] != points[-1]:
        points = [*points, points[0]]
    return points


def _polygon(raw: dict[str, Any]) -> list[list[float]]:
    if raw.get("polygon"):
        return _closed(
            [[float(point[0]), float(point[1])] for point in raw["polygon"]]
        )
    bbox = raw.get("bbox")
    if not bbox or len(bbox) != 4:
        raise SamPayloadError("object needs a polygon or a four-value bbox")
    x0, y0, x1, y1 = (float(value) for value in bbox)
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]


def _bbox(raw: dict[str, Any], polygon: list[list[float]]) -> list[float]:
    if raw.get("bbox") and len(raw["bbox"]) == 4:
        return [float(value) for value in raw["bbox"]]
    xs = [point[0] for point in polygon]
    ys = [point[1] for point in polygon]
    return [min(xs), min(ys), max(xs), max(ys)]


def object_from_payload(
    raw: dict[str, Any],
    page: PageGeometry,
    fixture: str,
    index: int,
    side: str = "a",
) -> SamObject:
    label = _label(raw)
    polygon = _polygon(raw)
    score = float(raw.get("score") or 0.0)
    score = max(0.0, min(1.0, score))
    return SamObject(
        object_id=f"{fixture}:{side}:{page.page}:{label}:{index}",
        room_id=str(raw["room_id"]) if raw.get("room_id") else None,
        room_label=str(raw["room_label"]) if raw.get("room_label") else None,
        page=page.page,
        label=label,  # type: ignore[arg-type]
        bbox_px=_bbox(raw, polygon),
        polygon_px=polygon,
        score=score,
        source="sam31",
    )


def segment_payload(
    payload: dict[str, Any],
    pages: list[PageGeometry],
    fixture: str,
    side: str = "a",
) -> list[SamObject]:
    if "sides" in payload:
        side_payload = payload["sides"].get(side)
        if not isinstance(side_payload, dict):
            raise SamPayloadError(f"payload has no side {side!r}")
        payload = side_payload
    page_entries = payload.get("pages", [])
    page_map: dict[int, list[dict[str, Any]]] = {}
    for entry in page_entries:
        page_map[int(entry["page"])] = list(entry.get("objects", []))
    objects: list[SamObject] = []
    for page in pages:
        for index, raw in enumerate(page_map.get(page.page, [])):
            objects.append(object_from_payload(raw, page, fixture, index, side))
    return objects


def load_fixture_side(
    fixture_dir: str | Path,
    side: str,
    pages: list[PageGeometry],
    fixture: str,
) -> list[SamObject]:
    path = Path(fixture_dir) / "sam31.json"
    if not path.is_file():
        raise SamPayloadError(f"missing SAM payload: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return segment_payload(payload, pages, fixture, side)
