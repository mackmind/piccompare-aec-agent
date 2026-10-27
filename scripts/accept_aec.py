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
    parser.parse_args(argv)

    checks = [[sys.executable, "scripts/check_boundary.py"]]
    fixtures_verifier = ROOT / "scripts" / "verify_fixtures.py"
    fixtures_manifest = ROOT / "fixtures" / "manifest.json"
    if fixtures_verifier.is_file() and fixtures_manifest.is_file():
        checks.append(
            [
                sys.executable,
                "scripts/verify_fixtures.py",
                "--offline",
                "--geometry-only",
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
