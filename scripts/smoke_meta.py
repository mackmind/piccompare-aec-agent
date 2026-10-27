#!/usr/bin/env python3
"""Live Meta Model API smoke; no request without credentials."""

from __future__ import annotations

import argparse
import os

from aec.meta import MetaClient, MetaError

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["ok"],
    "properties": {"ok": {"type": "boolean"}},
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", default="Return {\"ok\": true} as JSON.")
    args = parser.parse_args(argv)
    api_key = os.environ.get("META_API_KEY", "")
    model_id = os.environ.get("META_MODEL_ID", "")
    if not api_key or not model_id:
        print("MISSING META_API_KEY or META_MODEL_ID; no request made")
        return 2
    client = MetaClient(api_key=api_key, model_id=model_id)
    try:
        result = client.chat_json("Return only JSON.", args.prompt, SCHEMA)
    except MetaError as error:
        print(f"META SMOKE FAIL: {type(error).__name__}")
        return 1
    print(f"model={result.model} calls={result.calls} usage={result.usage}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
