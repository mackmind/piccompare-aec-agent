#!/usr/bin/env python3
"""Read-only engine smoke: resolve a tree, call compare/regions, no Meta calls.

The engine admits raster work against free RAM minus a headroom of
``max(512 MiB, total/4)``. On a loaded dev box free RAM can fall below that,
which makes the allowance zero and refuses a job for reasons unrelated to the
integration under test. ``--pin-available-gib`` sets the engine's documented
``PICCOMPARE_AVAILABLE_BYTES`` seam for the child process only and records the
pinned value in the receipt; it is never set when the flag is omitted.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aec.client import EngineProtocolError, EngineToolError, PicCompareClient, ToolResult
from aec.engine import EngineNotFound, resolve_engine

REPO_ROOT = Path(__file__).resolve().parent.parent
GIB = 1024**3


def _iso_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _git_state(tree: Path) -> dict[str, object]:
    """Bind the receipt to the tree state; an absent repo is recorded as null."""
    try:
        head = subprocess.run(
            ["git", "-C", str(tree), "rev-parse", "--short=7", "HEAD"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        dirty = subprocess.run(
            ["git", "-C", str(tree), "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return {"head": None, "dirty": None}
    head_text = head.stdout.strip() if head.returncode == 0 else ""
    return {
        "head": head_text or None,
        "dirty": bool(dirty.stdout.strip()) if dirty.returncode == 0 else None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine-tree", required=True)
    parser.add_argument("--workspace-root", default=str(REPO_ROOT.parent))
    parser.add_argument("--fixture", default=str(REPO_ROOT / "fixtures" / "aec" / "resize-01"))
    parser.add_argument("--out", default=str(REPO_ROOT / "runs" / "engine-smoke"))
    parser.add_argument(
        "--pin-available-gib",
        type=float,
        default=0.0,
        help="pin the engine memory probe for this run (0 = probe the machine)",
    )
    args = parser.parse_args(argv)
    try:
        ref = resolve_engine(args.workspace_root, args.engine_tree)
    except EngineNotFound as error:
        print(f"ENGINE NOT FOUND: {error}")
        return 1

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    pinned_bytes = int(args.pin_available_gib * GIB)
    if pinned_bytes > 0:
        os.environ["PICCOMPARE_AVAILABLE_BYTES"] = str(pinned_bytes)
        print(f"memory pin: PICCOMPARE_AVAILABLE_BYTES={pinned_bytes}")

    steps: list[dict[str, Any]] = []
    receipt: dict[str, Any] = {
        "started_at": _iso_now(),
        "engine": {
            "tree": ref.tree.name,
            "version": ref.version,
            "python": str(ref.python),
            "cli": str(ref.cli),
            "source": ref.source,
            **_git_state(ref.tree),
        },
        "pinned_available_bytes": pinned_bytes or None,
        "fixture": str(Path(args.fixture)),
        "steps": steps,
        "result": "fail",
    }
    client = PicCompareClient(ref, profile_dir=out_dir / "profile")
    print(f"engine={ref.tree.name} version={ref.version} source={ref.source}")

    def run(command: str, call: Callable[[], ToolResult]) -> ToolResult | None:
        try:
            result = call()
        except (EngineToolError, EngineProtocolError) as error:
            steps.append(
                {
                    "command": command,
                    "exit_code": getattr(error, "exit_code", None),
                    "error": str(error),
                }
            )
            print(f"{command}: FAILED {error}")
            return None
        steps.append(
            {"command": command, "exit_code": result.exit_code, "duration_ms": result.duration_ms}
        )
        print(f"{command}: exit={result.exit_code}")
        return result

    if run("capabilities", client.capabilities) is None:
        return _finish(receipt, out_dir)

    fixture = Path(args.fixture)
    comparison = run(
        "compare", lambda: client.compare(fixture / "a.png", fixture / "b.png", align="none")
    )
    if comparison is None:
        return _finish(receipt, out_dir)
    comparison_id = str(comparison.data["comparison_id"])
    steps[-1].update(
        {
            "comparison_id": comparison_id,
            "status": comparison.data.get("status"),
            "pages_a": comparison.data.get("pages_a"),
            "pages_b": comparison.data.get("pages_b"),
        }
    )
    print(
        f"  status={comparison.data.get('status')} "
        f"pages={comparison.data.get('pages_a')}/{comparison.data.get('pages_b')}"
    )

    regions = run("regions", lambda: client.regions(comparison_id))
    if regions is None:
        return _finish(receipt, out_dir)
    returned = len(regions.data.get("regions", []))
    steps[-1].update(
        {
            "total": regions.data.get("total"),
            "returned": returned,
            "geometry": regions.data.get("geometry"),
        }
    )
    print(f"  total={regions.data.get('total')} returned={returned}")
    if int(regions.data.get("total") or 0) < 1 or returned < 1:
        receipt["error"] = "regions returned no rows"
    else:
        receipt["result"] = "pass"
    return _finish(receipt, out_dir)


def _finish(receipt: dict[str, Any], out_dir: Path) -> int:
    receipt["finished_at"] = _iso_now()
    path = out_dir / "receipt.json"
    path.write_text(json.dumps(receipt, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(f"result={receipt['result']} receipt={path}")
    return 0 if receipt["result"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
