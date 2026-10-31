#!/usr/bin/env python3
"""Offline AEC evaluation against verified synthetic ground truth.

The work lives in :mod:`aec.evaluation` so an installed package (and the tool
server) can call it; this script keeps the documented command and its flags.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from aec.evaluation import LiveCredentialsMissing, run_eval

REPO_ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", default=str(REPO_ROOT / "fixtures"))
    parser.add_argument("--out", default=str(REPO_ROOT / "runs" / "eval"))
    parser.add_argument("--pairs", nargs="*")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args(argv)
    try:
        metrics = run_eval(
            Path(args.fixtures), Path(args.out), args.pairs, live=args.live
        )
    except LiveCredentialsMissing as error:
        print(f"MISSING CREDENTIALS: {error}; no request made")
        return 2
    totals = metrics["totals"]
    print(
        f"{metrics['mode']}: {totals['pairs_passed']}/{totals['pairs']} pairs; "
        f"expected={totals['expected']} matched={totals['matched']} "
        f"not_compared={totals['not_compared_matched']} "
        f"false_positives={totals['false_positives']} missing={totals['missing']} "
        f"unexpected_not_compared={totals['unexpected_not_compared']}"
    )
    return 0 if totals["pairs_passed"] == totals["pairs"] else 1


if __name__ == "__main__":
    sys.exit(main())
