#!/usr/bin/env python3
"""Offline SAM payload preflight.

The live SAM 3.1 gate needs the Task 4 HTTP client and an API key; this script
validates the deterministic fixture payloads and prints object counts now.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from aec.models import PageGeometry
from aec.sam import SamClient, box_prompt
from aec.sam_adapter import load_fixture_side


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--side", choices=["a", "b"], default="a")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--image")
    parser.add_argument("--prompt", default="room")
    parser.add_argument("--box", help="x1,y1,x2,y2 in image pixels; overrides a "
                                     "concept prompt with an object prompt")
    parser.add_argument("--model", default=os.environ.get("META_SAM_MODEL_ID", "sam-3.1"))
    args = parser.parse_args(argv)
    if args.live:
        if not args.image:
            parser.error("--live requires --image")
        api_key = os.environ.get("META_API_KEY", "")
        if not api_key:
            print("MISSING META_API_KEY; no request made")
            return 2
        prompt = args.prompt
        if args.box:
            from PIL import Image
            image_width, image_height = Image.open(args.image).size
            x1, y1, x2, y2 = (int(value) for value in args.box.split(","))
            prompt = box_prompt(x1, y1, x2, y2, image_width, image_height)
        base = os.environ.get("META_API_BASE") or "https://api.meta.ai/v1"
        result = SamClient(api_key=api_key, model_id=args.model,
                           base_url=base).segment(
            Path(args.image).read_bytes(), prompt
        )
        print(
            f"{args.image}: {len(result.objects)} objects; model={result.model}; "
            f"calls={result.calls}; latency_ms={result.latency_ms}"
        )
        for obj in result.objects:
            polygon = obj.get("polygon") or []
            print(f"  object={obj.get('object_id')} bbox={obj.get('bbox')} "
                  f"points={len(polygon)} mask={obj.get('mask_available')}")
        return 0 if result.objects else 1
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
