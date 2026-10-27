#!/usr/bin/env python3
"""Geometry-only fixture verifier for Task 5.

Task 12 extends this with the generator/verifier pipeline and metrics.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _area(polygon: list[list[float]]) -> float:
    points = [(float(x), float(y)) for x, y in polygon]
    return abs(
        sum(
            points[index][0] * points[(index + 1) % len(points)][1]
            - points[(index + 1) % len(points)][0] * points[index][1]
            for index in range(len(points))
        )
    ) / 2.0


def _check_rooms(rooms: list[dict], px_per_unit: float, label: str) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for room in rooms:
        room_id = str(room.get("room_id"))
        if room_id in seen:
            errors.append(f"{label}: duplicate room_id {room_id}")
        seen.add(room_id)
        polygon = room.get("polygon_px") or []
        if len(polygon) < 4 or polygon[0] != polygon[-1]:
            errors.append(f"{label}: {room_id} polygon is not closed")
            continue
        area = _area(polygon)
        if abs(area - float(room["area_px2"])) > 1e-5:
            errors.append(f"{label}: {room_id} area_px2 mismatch")
        expected_m2 = area / (px_per_unit * px_per_unit)
        if abs(expected_m2 - float(room["area_m2"])) > 1e-5:
            errors.append(f"{label}: {room_id} area_m2 mismatch")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", default=str(REPO_ROOT / "fixtures"))
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--geometry-only", action="store_true")
    args = parser.parse_args(argv)
    fixtures = Path(args.fixtures)
    manifest_path = fixtures / "manifest.json"
    if not manifest_path.is_file():
        print(f"FAIL missing {manifest_path}")
        return 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    pairs = manifest.get("pairs", [])
    if not 10 <= len(pairs) <= 12:
        print(f"FAIL expected 10-12 pairs, got {len(pairs)}")
        return 1
    errors: list[str] = []
    for pair in pairs:
        pair_id = str(pair["pair_id"])
        directory = fixtures / "aec" / pair_id
        for name, expected in pair.get("files", {}).items():
            path = directory / name
            if not path.is_file():
                errors.append(f"{pair_id}: missing {name}")
                continue
            if _sha256(path) != expected:
                errors.append(f"{pair_id}: hash mismatch {name}")
        config_path = directory / "config.json"
        truth_path = directory / "ground_truth.json"
        if not config_path.is_file() or not truth_path.is_file():
            continue
        config = json.loads(config_path.read_text(encoding="utf-8"))
        truth = json.loads(truth_path.read_text(encoding="utf-8"))
        px_per_unit = float(config["px_per_unit"])
        if px_per_unit <= 0:
            errors.append(f"{pair_id}: px_per_unit must be positive")
            continue
        if float(truth["scale"]["px_per_unit"]) != px_per_unit:
            errors.append(f"{pair_id}: scale mismatch")
        errors.extend(_check_rooms(truth["rooms_a"], px_per_unit, f"{pair_id}/a"))
        errors.extend(_check_rooms(truth["rooms_b"], px_per_unit, f"{pair_id}/b"))
        for change in truth.get("changes", []):
            for room_id in change.get("room_ids", []):
                if room_id not in {
                    room["room_id"] for room in truth["rooms_a"] + truth["rooms_b"]
                }:
                    errors.append(f"{pair_id}: change references unknown {room_id}")
    if errors:
        for error in errors:
            print(f"FAIL {error}")
        return 1
    print(f"geometry PASS ({len(pairs)} pairs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
