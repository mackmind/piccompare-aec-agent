"""Engine integration; runs only when AEC_ENGINE_TREE names a local tree."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.engine
def test_engine_smoke_against_named_tree(tmp_path: Path) -> None:
    tree = os.environ.get("AEC_ENGINE_TREE", "").strip()
    if not tree:
        pytest.skip("AEC_ENGINE_TREE is not set")
    out = tmp_path / "smoke"
    command = [
        sys.executable,
        str(ROOT / "scripts" / "engine_smoke.py"),
        "--engine-tree",
        tree,
        "--out",
        str(out),
    ]
    pin = os.environ.get("AEC_ENGINE_PIN_GIB", "").strip()
    if pin:
        command += ["--pin-available-gib", pin]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    completed = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    receipt = json.loads((out / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["result"] == "pass"
    assert receipt["engine"]["tree"] == Path(tree).name
    assert "head" in receipt["engine"]
    assert [step["command"] for step in receipt["steps"]] == [
        "capabilities",
        "compare",
        "regions",
    ]
    assert all(step["exit_code"] == 0 for step in receipt["steps"])
