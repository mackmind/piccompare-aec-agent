"""Offline and live AEC evaluation over verified synthetic ground truth.

Moved out of ``scripts/run_eval.py`` (W3-2) so an installed ``aec`` package can
import it: ``scripts/`` is not a package. ``scripts/run_eval.py`` is now a thin
``main()`` wrapper around :func:`run_eval`.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from aec.live import run_pair_live
from aec.meta import MetaClient
from aec.models import Element, Finding
from aec.pipeline import PairResult, run_pair
from aec.sam import SamClient


class LiveCredentialsMissing(RuntimeError):
    """The live run was asked for without the credentials it needs."""


def _room_ids(finding: Finding, elements: dict[str, Element]) -> set[str]:
    result: set[str] = set()
    for element_id in finding.element_ids:
        element = elements.get(element_id)
        result.add(element.room_id if element and element.room_id else element_id)
    return result


def _match_expected(
    expected: dict[str, Any],
    pool: list[Finding],
    elements: dict[str, Element],
) -> list[Finding]:
    target = set(expected.get("room_ids", []))
    same_type = [
        finding
        for finding in pool
        if finding.change_type == expected["change_type"]
    ]
    for finding in same_type:
        if target <= _room_ids(finding, elements):
            return [finding]
    covered: set[str] = set()
    selected: list[Finding] = []
    for finding in same_type:
        selected.append(finding)
        covered |= _room_ids(finding, elements)
        if target <= covered:
            return selected
    return []


def _assign_gt_room_ids(result: PairResult, truth: dict[str, Any]) -> dict[str, str]:
    """Map live elements to ground-truth room ids by polygon IoU (scoring only).

    SAM supplies no room labels, so the live report cannot name R1/R2. Scoring
    may use the ground truth, so align the element geometry to the GT room
    polygons here - never in generation.
    """
    from shapely.geometry import Polygon

    rooms = {"a": truth.get("rooms_a") or [], "b": truth.get("rooms_b") or []}
    assignment: dict[str, str] = {}
    for side, elements in (("a", result.elements_a), ("b", result.elements_b)):
        candidates: list[tuple[Any, Any]] = []
        for room in rooms[side]:
            polygon = Polygon(room["polygon_px"])
            if polygon.is_valid and polygon.area > 0:
                candidates.append((room["room_id"], polygon))
        for element in elements:
            try:
                element_polygon = Polygon(element.polygon_px)
            except Exception:  # noqa: BLE001 - a degenerate polygon maps to nothing
                continue
            if not element_polygon.is_valid or element_polygon.area <= 0:
                continue
            best_id: Any = None
            best_iou = 0.0
            for room_id, room_polygon in candidates:
                intersection = element_polygon.intersection(room_polygon).area
                union = element_polygon.union(room_polygon).area
                iou = intersection / union if union else 0.0
                if iou > best_iou:
                    best_id, best_iou = room_id, iou
            if best_id is not None and best_iou >= 0.5:
                assignment[element.element_id] = best_id
    return assignment


def _score_pair(result: PairResult, truth: dict[str, Any]) -> dict[str, Any]:
    alignment = _assign_gt_room_ids(result, truth)
    elements = {
        element.element_id: (
            element.model_copy(update={"room_id": alignment[element.element_id]})
            if element.element_id in alignment
            else element
        )
        for element in [*result.elements_a, *result.elements_b]
    }
    expected = truth.get("expected_findings", [])
    verified_pool = result.verified
    not_compared_pool = result.not_compared
    used: set[str] = set()
    matched = 0
    not_compared_matched = 0
    missing: list[dict[str, Any]] = []
    for item in expected:
        pool = (
            not_compared_pool
            if item.get("expected_status") == "not_compared"
            else verified_pool
        )
        selection = _match_expected(item, pool, elements)
        if not selection:
            missing.append(item)
            continue
        used.update(finding.finding_id for finding in selection)
        if item.get("expected_status") == "not_compared":
            not_compared_matched += 1
        else:
            matched += 1
    false_positives = [
        finding.finding_id
        for finding in verified_pool
        if finding.finding_id not in used
    ]
    unexpected_not_compared = [
        finding.finding_id
        for finding in not_compared_pool
        if finding.finding_id not in used
    ]
    expected_not_compared = [
        item for item in expected if item.get("expected_status") == "not_compared"
    ]
    return {
        "pair_id": result.pair_id,
        "expected": len(expected),
        "matched": matched,
        "not_compared_matched": not_compared_matched,
        "missing": missing,
        "false_positives": false_positives,
        "unexpected_not_compared": unexpected_not_compared,
        "baseline_flagged_changes": len(expected),
        "agent_refused_changes": len(expected_not_compared),
        "passed": not missing and not false_positives and not unexpected_not_compared,
        "room_alignment": alignment,
        "report": str(result.report_path) if result.report_path else None,
    }


def run_eval(
    fixtures: Path,
    out_dir: Path,
    pairs: list[str] | None = None,
    *,
    live: bool = False,
) -> dict[str, Any]:
    """Score every selected fixture pair and write ``metrics.json``.

    ``pairs`` is the manifest's name for the selection: the fixture pair ids to
    run, or ``None`` for all of them.
    """
    pair_dirs = sorted(
        path for path in (fixtures / "aec").iterdir() if path.is_dir()
    )
    if pairs:
        pair_dirs = [path for path in pair_dirs if path.name in pairs]
    sam_client: SamClient | None = None
    meta_client: MetaClient | None = None
    if live:
        api_key = os.environ.get("META_API_KEY", "")
        meta_model = os.environ.get("META_MODEL_ID", "")
        sam_model = os.environ.get("META_SAM_MODEL_ID", "sam-3.1")
        if not api_key or not meta_model:
            raise LiveCredentialsMissing(
                "META_API_KEY and META_MODEL_ID are required for --live"
            )
        base = os.environ.get("META_API_BASE") or "https://api.meta.ai/v1"
        sam_client = SamClient(api_key=api_key, model_id=sam_model, base_url=base)
        meta_client = MetaClient(api_key=api_key, model_id=meta_model, base_url=base)
    records: list[dict[str, Any]] = []
    for pair_dir in pair_dirs:
        truth = json.loads(
            (pair_dir / "ground_truth.json").read_text(encoding="utf-8")
        )
        if live and sam_client is not None and meta_client is not None:
            # SAM answers box prompts on line art, not concept prompts, so the
            # live leg proposes regions from the plan geometry.
            result = run_pair_live(
                pair_dir, sam_client, meta_client, out_dir / pair_dir.name,
                boxes_from_plan=True,
            )
        else:
            result = run_pair(pair_dir, out_dir / pair_dir.name)
        records.append(_score_pair(result, truth))
    totals = {
        "pairs": len(records),
        "pairs_passed": sum(1 for record in records if record["passed"]),
        "expected": sum(record["expected"] for record in records),
        "matched": sum(record["matched"] for record in records),
        "not_compared_matched": sum(
            record["not_compared_matched"] for record in records
        ),
        "false_positives": sum(
            len(record["false_positives"]) for record in records
        ),
        "missing": sum(len(record["missing"]) for record in records),
        "baseline_flagged_changes": sum(
            record["baseline_flagged_changes"] for record in records
        ),
        "agent_refused_changes": sum(
            record["agent_refused_changes"] for record in records
        ),
        "unexpected_not_compared": sum(
            len(record["unexpected_not_compared"]) for record in records
        ),
    }
    metrics: dict[str, Any] = {
        "schema": "piccompare-aec-eval/1.0",
        "mode": "live_meta" if live else "offline_deterministic",
        "fixtures": str(fixtures),
        "provider": {
            "name": "live_meta" if live else "offline_deterministic",
            "model": (
                os.environ.get("META_MODEL_ID") if live else None
            ),
            "sam_model": (
                os.environ.get("META_SAM_MODEL_ID", "sam-3.1") if live else None
            ),
            "network": bool(live),
            "meta_api_calls": meta_client.calls if live and meta_client else 0,
            "fallback_used": False,
        },
        "pairs": records,
        "totals": totals,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=True) + "\n",
        encoding="ascii",
    )
    verified = [
        {
            "pair_id": record["pair_id"],
            "verified": record["passed"],
            "report": record["report"],
            "report_sha256": (
                hashlib.sha256(Path(record["report"]).read_bytes()).hexdigest()
                if record["report"]
                else None
            ),
        }
        for record in records
    ]
    (out_dir / "verified_manifest.json").write_text(
        json.dumps(
            {"schema": "piccompare-aec-verified/1.0", "pairs": verified},
            indent=2,
            ensure_ascii=True,
        )
        + "\n",
        encoding="ascii",
    )
    return metrics
