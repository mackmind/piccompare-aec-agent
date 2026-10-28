#!/usr/bin/env python3
"""Run one live SAM 3.1 + Muse Spark pair; requires event credentials."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from aec.live import run_pair_live
from aec.meta import MetaClient
from aec.sam import SamClient


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--prompt", default="room")
    parser.add_argument("--boxes-from-plan", action="store_true",
                        help="propose regions from the plan geometry and ask SAM "
                             "to segment each box (concept prompts return nothing "
                             "on line-art plans)")
    args = parser.parse_args(argv)
    api_key = os.environ.get("META_API_KEY", "")
    meta_model = os.environ.get("META_MODEL_ID", "")
    sam_model = os.environ.get("META_SAM_MODEL_ID", "sam-3.1")
    if not api_key or not meta_model:
        print("MISSING META_API_KEY or META_MODEL_ID; no request made")
        return 2
    base = os.environ.get("META_API_BASE") or "https://api.meta.ai/v1"
    sam = SamClient(api_key=api_key, model_id=sam_model, base_url=base)
    meta = MetaClient(api_key=api_key, model_id=meta_model, base_url=base)
    result = run_pair_live(
        Path(args.fixture), sam, meta, Path(args.out), args.prompt,
        boxes_from_plan=args.boxes_from_plan,
    )
    print(
        f"pair={result.pair_id} verified={len(result.verified)} "
        f"not_compared={len(result.not_compared)} "
        f"rejected={len(result.rejected)} report={result.report_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
