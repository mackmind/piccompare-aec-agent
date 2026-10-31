#!/usr/bin/env python3
"""Read per-pair AEC reports and write a materiality-sorted batch summary.

The work lives in :mod:`aec.batch` so an installed package (and the tool
server) can call it; this script keeps the documented command and its flags.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from aec.batch import run_batch

REPO_ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reports", default=str(REPO_ROOT / "runs" / "eval"))
    parser.add_argument("--out", default=str(REPO_ROOT / "runs" / "batch"))
    args = parser.parse_args(argv)
    payload = run_batch(Path(args.reports), Path(args.out))
    print(
        f"batch: {payload['totals']['pairs']} pairs, "
        f"{payload['totals']['high']} high, "
        f"{payload['totals']['not_compared']} refused"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
