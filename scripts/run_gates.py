#!/usr/bin/env python3
"""Run the AEC repository gates and write a receipt."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
TASKS = {f"T{i}" for i in range(1, 18)}


def run(cmd: list[str]) -> dict:
    started = time.perf_counter()
    completed = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    return {
        "command": cmd,
        "returncode": completed.returncode,
        "duration_ms": int((time.perf_counter() - started) * 1000),
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task")
    parser.add_argument("--phase")
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args(argv)
    if args.list:
        print("\n".join(sorted(TASKS, key=lambda value: int(value[1:]))))
        return 0

    commands = [
        [PY, "-m", "pytest", "-q"],
        [PY, "-m", "ruff", "check", "."],
        [PY, "-m", "mypy", "src/aec"],
        [PY, "scripts/check_boundary.py"],
        [PY, "scripts/accept_aec.py", "--offline"],
    ]
    results = [run(command) for command in commands]
    receipt = {
        "task": args.task or args.phase or "full",
        "results": results,
        "ok": all(result["returncode"] == 0 for result in results),
    }
    out = ROOT / "runs" / "gates" / f"{args.task or args.phase or 'full'}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, indent=2, ensure_ascii=True), encoding="utf-8")
    for result in results:
        print(result["command"], "->", result["returncode"])
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
