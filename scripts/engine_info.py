#!/usr/bin/env python3
"""Resolve and print the external engine tree without importing it."""

from __future__ import annotations

import argparse

from aec.engine import EngineNotFound, resolve_engine


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-root")
    parser.add_argument("--engine-tree")
    args = parser.parse_args(argv)
    try:
        ref = resolve_engine(args.workspace_root, args.engine_tree)
    except EngineNotFound as error:
        print(f"ENGINE NOT FOUND: {error}")
        return 1
    print(f"tree={ref.tree}")
    print(f"version={ref.version}")
    print(f"source={ref.source}")
    print(f"python={ref.python} exists={ref.python_exists}")
    print(f"cli={ref.cli} exists={ref.cli_exists}")
    print(f"demo_mode={ref.demo_mode}")
    for warning in ref.warnings:
        print(f"warning={warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
