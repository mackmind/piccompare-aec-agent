from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from make_plans import make_all, make_plan_pair

from aec.evidence import sha256_content

ROOT = Path(__file__).resolve().parent.parent


def _sha256(path: Path) -> str:
    return sha256_content(path)


def test_generator_creates_twelve_pairs(tmp_path) -> None:
    fixtures = tmp_path / "fixtures"
    make_all(fixtures, count=12, seed=7)
    manifest = json.loads((fixtures / "manifest.json").read_text())
    assert len(manifest["pairs"]) == 12
    for pair in manifest["pairs"]:
        assert (fixtures / "aec" / pair["pair_id"] / "ground_truth.json").is_file()


def test_resize_variant_has_expected_area_delta(tmp_path) -> None:
    pair = make_plan_pair(tmp_path / "fixtures", "resize-01", "resize", seed=1)
    truth = json.loads(pair.ground_truth.read_text())
    assert truth["changes"][0]["type"] == "room_resized"
    assert abs(truth["changes"][0]["area_delta_m2"] - 2.0) < 1e-6


def test_split_variant_has_two_replacement_rooms(tmp_path) -> None:
    pair = make_plan_pair(tmp_path / "fixtures", "split-01", "split", seed=1)
    truth = json.loads(pair.ground_truth.read_text())
    assert {room["room_id"] for room in truth["rooms_b"]} >= {"R1a", "R1b"}
    assert truth["expected_findings"][0]["expected_status"] == "not_compared"


def test_manifest_hashes_match_files(tmp_path) -> None:
    fixtures = tmp_path / "fixtures"
    make_all(fixtures, count=12, seed=7)
    manifest = json.loads((fixtures / "manifest.json").read_text())
    for pair in manifest["pairs"]:
        directory = fixtures / "aec" / pair["pair_id"]
        for name, expected in pair["files"].items():
            assert _sha256(directory / name) == expected


def test_geometry_verifier_passes(tmp_path) -> None:
    fixtures = tmp_path / "fixtures"
    make_all(fixtures, count=12, seed=7)
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "verify_fixtures.py"),
            "--fixtures",
            str(fixtures),
            "--offline",
            "--geometry-only",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
