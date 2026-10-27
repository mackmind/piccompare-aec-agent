#!/usr/bin/env python3
"""Offline SAM payload preflight.

The live SAM 3.1 gate needs the Task 4 HTTP client and an API key; this script
validates the deterministic fixture payloads and prints object counts now.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from aec.models import PageGeometry
from aec.sam_adapter import load_fixture_side


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--side", choices=["a", "b"], default="a")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args(argv)
    if args.live:
        print("live SAM gate requires Task 4 client + credentials; not run")
        return 2
    fixture_dir = Path(args.fixture)
    config = json.loads((fixture_dir / "config.json").read_text(encoding="utf-8"))
    page = config["page"]
    pages = [PageGeometry(page=page["page"], width=page["width"], height=page["height"])]
    objects = load_fixture_side(fixture_dir, args.side, pages, fixture_dir.name)
    print(
        f"{fixture_dir.name}/{args.side}: {len(objects)} objects, "
        f"labels={sorted({obj.label for obj in objects})}"
    )
    return 0 if objects else 1


if __name__ == "__main__":
    raise SystemExit(main())
