#!/usr/bin/env python3
"""Generate deterministic synthetic floor-plan pairs with exact ground truth."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parent.parent
PAGE_W = 1600
PAGE_H = 1200
PX_PER_M = 100.0
UNITS = "m"
BLACK = (0, 0, 0)
ROOM_FILL = (235, 235, 235)
ROOM_LINE = 6
FILES = ("a.png", "b.png", "config.json", "ground_truth.json", "sam31.json")
VARIANTS: list[tuple[str, str]] = [
    ("identical-01", "identical"),
    ("resize-01", "resize"),
    ("resize-02", "resize-02"),
    ("wall_move-01", "wall_move"),
    ("wall_move-02", "wall_move-02"),
    ("split-01", "split"),
    ("split-02", "split-02"),
    ("merge-01", "merge"),
    ("merge-02", "merge-02"),
    ("label_change-01", "label_change"),
    ("noise-01", "noise"),
    ("mixed-01", "mixed"),
]


@dataclass(frozen=True)
class PairSpec:
    pair_id: str
    variant: str
    directory: Path
    a: Path
    b: Path
    config: Path
    ground_truth: Path
    sam31: Path


def _rect(x0: int, y0: int, x1: int, y1: int) -> list[tuple[int, int]]:
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]


def _base_rooms() -> list[dict[str, Any]]:
    return [
        {"room_id": "R1", "label": "ROOM A", "polygon": _rect(100, 100, 500, 500)},
        {"room_id": "R2", "label": "ROOM B", "polygon": _rect(600, 100, 1000, 500)},
        {"room_id": "R3", "label": "ROOM C", "polygon": _rect(100, 600, 500, 900)},
        {"room_id": "R4", "label": "ROOM D", "polygon": _rect(600, 600, 1000, 900)},
    ]


def _find(rooms: list[dict[str, Any]], room_id: str) -> dict[str, Any]:
    for room in rooms:
        if room["room_id"] == room_id:
            return room
    raise KeyError(room_id)


def _rooms_for_variant(variant: str) -> list[dict[str, Any]]:
    rooms = _base_rooms()
    if variant == "resize":
        _find(rooms, "R1")["polygon"] = _rect(100, 100, 550, 500)
    elif variant == "resize-02":
        _find(rooms, "R2")["polygon"] = _rect(600, 100, 1050, 500)
    elif variant == "wall_move":
        _find(rooms, "R1")["polygon"] = _rect(100, 100, 520, 500)
    elif variant == "wall_move-02":
        _find(rooms, "R2")["polygon"] = _rect(600, 100, 1020, 500)
    elif variant == "split":
        rooms = [room for room in rooms if room["room_id"] != "R1"]
        rooms.extend(
            [
                {"room_id": "R1a", "label": "ROOM A-1", "polygon": _rect(100, 100, 300, 500)},
                {"room_id": "R1b", "label": "ROOM A-2", "polygon": _rect(300, 100, 500, 500)},
            ]
        )
    elif variant == "split-02":
        rooms = [room for room in rooms if room["room_id"] != "R2"]
        rooms.extend(
            [
                {"room_id": "R2a", "label": "ROOM B-1", "polygon": _rect(600, 100, 800, 500)},
                {"room_id": "R2b", "label": "ROOM B-2", "polygon": _rect(800, 100, 1000, 500)},
            ]
        )
    elif variant == "merge":
        rooms = [room for room in rooms if room["room_id"] not in {"R1", "R2"}]
        rooms.append({"room_id": "M1", "label": "ROOM A+B", "polygon": _rect(100, 100, 1000, 500)})
    elif variant == "merge-02":
        rooms = [room for room in rooms if room["room_id"] not in {"R3", "R4"}]
        rooms.append({"room_id": "M2", "label": "ROOM C+D", "polygon": _rect(100, 600, 1000, 900)})
    elif variant == "label_change":
        _find(rooms, "R4")["label"] = "ROOM D REV"
    elif variant == "mixed":
        _find(rooms, "R1")["polygon"] = _rect(100, 100, 550, 500)
        _find(rooms, "R4")["label"] = "ROOM D REV"
    return rooms


def _changes_for_variant(variant: str) -> list[dict[str, Any]]:
    if variant in {"identical", "noise"}:
        return []
    if variant in {"resize", "resize-02"}:
        room_id = "R1" if variant == "resize" else "R2"
        return [
            {
                "type": "room_resized",
                "room_ids": [room_id],
                "area_delta_m2": 2.0,
                "expected": "verified",
                "materiality": "high",
            }
        ]
    if variant in {"wall_move", "wall_move-02"}:
        room_id = "R1" if variant == "wall_move" else "R2"
        return [
            {
                "type": "room_resized",
                "room_ids": [room_id],
                "area_delta_m2": 0.8,
                "expected": "verified",
                "materiality": "high",
            }
        ]
    if variant in {"split", "split-02"}:
        room_id = "R1" if variant == "split" else "R2"
        return [
            {
                "type": "room_split",
                "room_ids": [room_id],
                "area_delta_m2": 0.0,
                "expected": "not_compared",
                "materiality": "high",
            }
        ]
    if variant in {"merge", "merge-02"}:
        room_ids = ["R1", "R2"] if variant == "merge" else ["R3", "R4"]
        return [
            {
                "type": "room_merged",
                "room_ids": room_ids,
                "area_delta_m2": 0.0,
                "expected": "not_compared",
                "materiality": "high",
            }
        ]
    if variant == "label_change":
        return [
            {
                "type": "label_changed",
                "room_ids": ["R4"],
                "area_delta_m2": 0.0,
                "expected": "verified",
                "materiality": "low",
            }
        ]
    if variant == "mixed":
        return [
            {
                "type": "room_resized",
                "room_ids": ["R1"],
                "area_delta_m2": 2.0,
                "expected": "verified",
                "materiality": "high",
            },
            {
                "type": "label_changed",
                "room_ids": ["R4"],
                "area_delta_m2": 0.0,
                "expected": "verified",
                "materiality": "low",
            },
        ]
    raise ValueError(f"unknown variant: {variant}")


def _shoelace(polygon: list[tuple[float, float]] | list[list[float]]) -> float:
    points = [(float(x), float(y)) for x, y in polygon]
    return abs(
        sum(
            points[index][0] * points[(index + 1) % len(points)][1]
            - points[(index + 1) % len(points)][0] * points[index][1]
            for index in range(len(points))
        )
    ) / 2.0


def _room_record(room: dict[str, Any]) -> dict[str, Any]:
    polygon = room["polygon"]
    area_px = _shoelace(polygon)
    open_points = polygon[:-1] if polygon[0] == polygon[-1] else polygon
    cx = sum(float(x) for x, _ in open_points) / len(open_points)
    cy = sum(float(y) for _, y in open_points) / len(open_points)
    return {
        "room_id": room["room_id"],
        "label": room["label"],
        "polygon_px": [[float(x), float(y)] for x, y in polygon],
        "area_px2": round(area_px, 6),
        "area_m2": round(area_px / (PX_PER_M * PX_PER_M), 6),
        "centroid_px": [round(cx, 6), round(cy, 6)],
    }


def _sam_object(room: dict[str, Any]) -> dict[str, Any]:
    xs = [float(x) for x, _ in room["polygon"]]
    ys = [float(y) for _, y in room["polygon"]]
    return {
        "label": "room",
        "bbox": [min(xs), min(ys), max(xs), max(ys)],
        "polygon": [[float(x), float(y)] for x, y in room["polygon"]],
        "score": 0.95,
    }


def _draw_plan(
    rooms: list[dict[str, Any]],
    pair_id: str,
    variant: str,
    seed: int,
    path: Path,
) -> None:
    image = Image.new("RGB", (PAGE_W, PAGE_H), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((40, 40, PAGE_W - 40, PAGE_H - 40), outline=BLACK, width=8)
    for room in rooms:
        polygon = room["polygon"]
        draw.polygon(polygon, fill=ROOM_FILL)
        draw.line(polygon, fill=BLACK, width=ROOM_LINE, joint="curve")
        cx = sum(x for x, _ in polygon[:-1]) / (len(polygon) - 1)
        cy = sum(y for _, y in polygon[:-1]) / (len(polygon) - 1)
        draw.text((cx - 30, cy - 8), str(room["label"]), fill=BLACK)
    draw.line((100, 1080, 600, 1080), fill=BLACK, width=6)
    for x in (100, 200, 300, 400, 500, 600):
        draw.line((x, 1068, x, 1092), fill=BLACK, width=4)
    draw.text((100, 1100), "0", fill=BLACK)
    draw.text((560, 1100), "5 m", fill=BLACK)
    draw.text((300, 1040), "100 px = 1 m", fill=BLACK)
    draw.rectangle((1050, 1000, 1500, 1130), outline=BLACK, width=4)
    draw.text((1070, 1020), f"{pair_id}", fill=BLACK)
    draw.text((1070, 1050), f"variant: {variant}", fill=BLACK)
    draw.text((1070, 1080), "SYNTHETIC - NO CUSTOMER DATA", fill=BLACK)
    if variant == "noise":
        rng = random.Random(seed)
        for _ in range(250):
            x = rng.randint(60, PAGE_W - 60)
            y = rng.randint(60, PAGE_H - 60)
            draw.point((x, y), fill=(120, 120, 120))
    image.save(path)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
        encoding="ascii",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def make_plan_pair(
    fixtures_root: Path,
    pair_id: str,
    variant: str,
    seed: int = 7,
) -> PairSpec:
    directory = fixtures_root / "aec" / pair_id
    directory.mkdir(parents=True, exist_ok=True)
    rooms_a = _base_rooms()
    rooms_b = _rooms_for_variant(variant)
    a_path = directory / "a.png"
    b_path = directory / "b.png"
    _draw_plan(rooms_a, pair_id, "a", seed, a_path)
    _draw_plan(rooms_b, pair_id, variant, seed, b_path)
    records_a = [_room_record(room) for room in rooms_a]
    records_b = [_room_record(room) for room in rooms_b]
    config = {
        "pair_id": pair_id,
        "units": UNITS,
        "px_per_unit": PX_PER_M,
        "scale_source": "scale_bar",
        "page": {"page": 0, "width": PAGE_W, "height": PAGE_H},
        "element_types": ["room"],
        "area_tolerance_m2": 0.05,
        "dimension_tolerance_px": 2.0,
        "angle_tolerance_deg": 1.0,
        "material_area_delta_m2": 0.1,
        "match_iou_threshold": 0.5,
        "match_centroid_tolerance_px": 8.0,
        "match_area_ratio_tolerance": 0.25,
        "variant": variant,
    }
    changes = _changes_for_variant(variant)
    ground_truth = {
        "schema": "piccompare-aec-groundtruth/1.0",
        "pair_id": pair_id,
        "units": UNITS,
        "scale": {"px_per_unit": PX_PER_M, "units": UNITS, "source": "scale_bar"},
        "page": {"page": 0, "width": PAGE_W, "height": PAGE_H},
        "rooms_a": records_a,
        "rooms_b": records_b,
        "changes": changes,
        "expected_findings": [
            {
                "change_type": change["type"],
                "room_ids": change["room_ids"],
                "materiality": change["materiality"],
                "expected_status": change["expected"],
            }
            for change in changes
        ],
    }
    sam31 = {
        "schema": "piccompare-aec-sam/1.0",
        "pair_id": pair_id,
        "sides": {
            "a": {
                "pages": [
                    {"page": 0, "objects": [_sam_object(room) for room in rooms_a]}
                ]
            },
            "b": {
                "pages": [
                    {"page": 0, "objects": [_sam_object(room) for room in rooms_b]}
                ]
            },
        },
    }
    config_path = directory / "config.json"
    truth_path = directory / "ground_truth.json"
    sam_path = directory / "sam31.json"
    _write_json(config_path, config)
    _write_json(truth_path, ground_truth)
    _write_json(sam_path, sam31)
    return PairSpec(
        pair_id=pair_id,
        variant=variant,
        directory=directory,
        a=a_path,
        b=b_path,
        config=config_path,
        ground_truth=truth_path,
        sam31=sam_path,
    )


def make_all(fixtures_root: Path, count: int = 12, seed: int = 7) -> list[PairSpec]:
    pairs: list[PairSpec] = []
    for pair_id, variant in VARIANTS[:count]:
        pairs.append(make_plan_pair(fixtures_root, pair_id, variant, seed))
    manifest = {
        "schema": "piccompare-aec-fixtures/1.0",
        "seed": seed,
        "pairs": [
            {
                "pair_id": pair.pair_id,
                "variant": pair.variant,
                "files": {
                    name: _sha256(pair.directory / name) for name in FILES
                },
            }
            for pair in pairs
        ],
    }
    _write_json(fixtures_root / "manifest.json", manifest)
    return pairs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(REPO_ROOT / "fixtures"))
    parser.add_argument("--count", type=int, default=12)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args(argv)
    if not 10 <= args.count <= 12:
        parser.error("--count must be between 10 and 12")
    pairs = make_all(Path(args.out), count=args.count, seed=args.seed)
    print(f"generated {len(pairs)} pairs in {Path(args.out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
