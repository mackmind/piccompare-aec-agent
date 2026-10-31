#!/usr/bin/env python3
"""Stamp the final gate with the branch head and copy it to runs/gates/ext.json.

Thin wrapper: it runs `scripts/run_gates.py --phase final` unchanged, then reads the
receipt that script writes and copies the step results into `{head, dirty, ok, steps[]}`.
It refuses to run on a dirty tree and never reports success on an unreadable receipt.

The default output is a gate path, not an internal evidence path; pass an explicit
`--out runs/ext/<name>.json` to keep a workstream receipt under `runs/ext/`.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
GATE_SCRIPT = "scripts/run_gates.py"
GATE_RECEIPT = ROOT / "runs" / "gates" / "final.json"
DEFAULT_OUT = "runs/gates/ext.json"


def git_output(*args: str) -> str:
    """Return git stdout, raising when git itself fails."""
    completed = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False
    )
    if completed.returncode != 0:
        raise RuntimeError("git command failed: git " + " ".join(args))
    return completed.stdout


def step_name(command: list[str]) -> str:
    """Map a gate command to the short step name used in the receipt."""
    joined = " ".join(command).replace("\\", "/")
    if "-m pytest" in joined:
        return "pytest"
    if "-m ruff" in joined:
        return "ruff"
    if "-m mypy" in joined:
        return "mypy"
    if "check_boundary.py" in joined:
        return "boundary"
    if "accept_aec.py" in joined:
        return "acceptance"
    raise ValueError("unrecognised gate step")


def display(path: Path) -> str:
    """Repo-relative path for messages, so no absolute path is ever printed."""
    if ROOT in path.parents:
        return path.relative_to(ROOT).as_posix()
    return path.name


def read_steps() -> list[dict]:
    """Parse runs/gates/final.json into receipt steps, or raise."""
    label = display(GATE_RECEIPT)
    if not GATE_RECEIPT.is_file():
        raise RuntimeError(f"missing gate receipt: {label}")
    try:
        receipt = json.loads(GATE_RECEIPT.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise RuntimeError(f"unreadable gate receipt: {label} ({type(error).__name__})") from error
    results = receipt.get("results")
    if not isinstance(results, list) or not results:
        raise RuntimeError(f"gate receipt has no results: {label}")
    steps: list[dict] = []
    for result in results:
        command = result.get("command")
        returncode = result.get("returncode")
        if not isinstance(command, list) or not command or not isinstance(returncode, int):
            raise RuntimeError(f"malformed step in {label}")
        try:
            name = step_name([str(part) for part in command])
        except ValueError as error:
            raise RuntimeError(f"{error}: {Path(str(command[-1])).name}") from error
        steps.append({"name": name, "returncode": returncode, "ok": returncode == 0})
    names = [step["name"] for step in steps]
    if len(set(names)) != len(names):
        raise RuntimeError(f"duplicate step names in {label}")
    return steps


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the final gate and write a head-stamped receipt."
    )
    parser.add_argument(
        "--out",
        default=DEFAULT_OUT,
        help=f"receipt path relative to the repo root (default: {DEFAULT_OUT})",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    out = Path(args.out)
    if not out.is_absolute():
        out = ROOT / out
    out = out.resolve()

    try:
        head = git_output("rev-parse", "HEAD").strip()
        dirty = bool(git_output("status", "--porcelain").strip())
    except RuntimeError as error:
        print(f"FAIL {error}", file=sys.stderr)
        return 3

    if dirty:
        print(
            "FAIL working tree is dirty; commit or stash before running the gate",
            file=sys.stderr,
        )
        return 2

    # Drop the previous gate receipt: a crashed gate must not be read as green.
    GATE_RECEIPT.unlink(missing_ok=True)
    completed = subprocess.run([PY, GATE_SCRIPT, "--phase", "final"], cwd=ROOT, check=False)
    try:
        steps = read_steps()
    except RuntimeError as error:
        print(f"FAIL {error}", file=sys.stderr)
        return 3

    ok = completed.returncode == 0 and all(step["ok"] for step in steps)
    receipt = {"head": head, "dirty": dirty, "ok": ok, "steps": steps}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    for step in steps:
        print(f"{step['name']}: rc={step['returncode']} ok={step['ok']}")
    print(f"{'PASS' if ok else 'FAIL'} receipt written to {display(out)}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
