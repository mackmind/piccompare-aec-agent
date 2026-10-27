from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def venv_python(tree: Path, venv: str = ".venv-045") -> Path:
    if sys.platform == "win32":
        return tree / venv / "Scripts" / "python.exe"
    return tree / venv / "bin" / "python"


def make_engine_tree(
    root: Path,
    name: str = "PicCompare_TestC",
    version: str = "9.99.0",
) -> Path:
    tree = root / name
    (tree / "src").mkdir(parents=True, exist_ok=True)
    python = venv_python(tree)
    python.parent.mkdir(parents=True, exist_ok=True)
    python.write_bytes(b"")
    (tree / "src" / "agent_cli.py").write_text("# stub\n", encoding="utf-8")
    (tree / "src" / "mcp_server.py").write_text("# stub\n", encoding="utf-8")
    (tree / "src" / "constants.py").write_text(
        f'VERSION = "{version}"\n', encoding="utf-8"
    )
    return tree


def write_manifest(root: Path, comm: str, venv: str = ".venv-045") -> Path:
    path = root / "active-pair.json"
    path.write_text(
        json.dumps(
            {
                "gpl": "PicCompare-vTest",
                "comm": comm,
                "venv": venv,
                "version": "9.99.0",
            }
        ),
        encoding="utf-8",
    )
    return path


def write_tree_map(root: Path, demo_tree: str | None = "PicCompare_9.99H") -> Path:
    path = root / "tree-map.json"
    payload: dict[str, object] = {"schema": "piccompare.tree-map/1.0"}
    if demo_tree is not None:
        payload["hackathon_demo"] = {
            "tree": demo_tree,
            "selector": "PICCOMPARE_DEMO=1",
        }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class FakeRunner:
    def __init__(
        self,
        payloads: dict[str, dict] | None = None,
        returncodes: dict[str, int] | None = None,
        stdout_overrides: dict[str, str] | None = None,
    ) -> None:
        self.payloads = payloads or {}
        self.returncodes = returncodes or {}
        self.stdout_overrides = stdout_overrides or {}
        self.calls: list[dict] = []

    def __call__(self, argv, **kwargs):
        subcommand = argv[2] if len(argv) > 2 else ""
        self.calls.append({"argv": list(argv), "kwargs": kwargs})
        stdout = self.stdout_overrides.get(
            subcommand,
            json.dumps(self.payloads.get(subcommand, {"ok": True})),
        )
        return subprocess.CompletedProcess(
            argv,
            self.returncodes.get(subcommand, 0),
            stdout=stdout,
            stderr="",
        )


class RecordingTransport:
    def __init__(self, responses=None) -> None:
        if responses is None:
            responses = [{"choices": [{"message": {"content": "{}"}}]}]
        self.responses = responses if isinstance(responses, list) else [responses]
        self.calls: list[dict] = []

    def __call__(self, url, headers, payload, timeout):
        self.calls.append({"url": url, "headers": dict(headers), "payload": payload})
        response = self.responses[min(len(self.calls) - 1, len(self.responses) - 1)]
        if isinstance(response, BaseException):
            raise response
        return response
