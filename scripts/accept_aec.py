#!/usr/bin/env python3
"""Bootstrap acceptance runner.

Task 1 runs the boundary check. Later tasks append schema, fixture, report and
replay checks here.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--task")
    parser.add_argument(
        "--engine-tree",
        action="append",
        default=[],
        help="also smoke this local PicCompare tree (repeatable; needs the app on disk)",
    )
    parser.add_argument("--pin-available-gib", type=float, default=0.0)
    args = parser.parse_args(argv)

    checks = [[sys.executable, "scripts/check_boundary.py"]]
    fixtures_verifier = ROOT / "scripts" / "verify_fixtures.py"
    fixtures_manifest = ROOT / "fixtures" / "manifest.json"
    if fixtures_verifier.is_file() and fixtures_manifest.is_file():
        checks.extend(
            [
                [
                    sys.executable,
                    "scripts/verify_fixtures.py",
                    "--offline",
                    "--geometry-only",
                ],
                [
                    sys.executable,
                    "scripts/run_eval.py",
                    "--fixtures",
                    "fixtures",
                    "--out",
                    "runs/accept-eval",
                ],
                [
                    sys.executable,
                    "-m",
                    "aec",
                    "verify",
                    "--report",
                    "runs/accept-eval/resize-01/report.json",
                    "--inputs-dir",
                    "fixtures/aec/resize-01",
                ],
            ]
        )
    for tree in args.engine_tree:
        checks.append(
            [
                sys.executable,
                "scripts/engine_smoke.py",
                "--engine-tree",
                tree,
                "--out",
                str(ROOT / "runs" / f"engine-smoke-{Path(tree).name}"),
                "--pin-available-gib",
                str(args.pin_available_gib),
            ]
        )
    for command in checks:
        completed = subprocess.run(command, cwd=ROOT)
        if completed.returncode != 0:
            return completed.returncode
    print("accept_aec bootstrap PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
