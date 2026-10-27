#!/usr/bin/env python3
"""Verify an AEC report's hashes and replay digest."""

from __future__ import annotations

import argparse
from pathlib import Path

from aec.evidence import verify


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report")
    parser.add_argument("--inputs-dir")
    args = parser.parse_args(argv)
    result = verify(
        Path(args.report), Path(args.inputs_dir) if args.inputs_dir else None
    )
    if result.ok:
        print("PASS report verifies")
        return 0
    for reason in result.reasons:
        print(f"FAIL {reason}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
