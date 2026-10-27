"""Resolve the external PicCompare engine tree without importing it."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

VERSION_RE = re.compile(r'^VERSION\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)


class EngineNotFound(RuntimeError):
    pass


@dataclass(frozen=True)
class EngineRef:
    tree: Path
    python: Path
    cli: Path
    version: str
    source: str
    warnings: tuple[str, ...]
    demo_mode: bool

    @property
    def cli_exists(self) -> bool:
        return self.cli.is_file()

    @property
    def python_exists(self) -> bool:
        return self.python.is_file()


def default_workspace_root() -> Path:
    override = os.environ.get("PICCOMPARE_WORKSPACE")
    if override:
        return Path(override).resolve()
    return Path(__file__).resolve().parents[3]


def _read_json(path: Path, warnings: list[str]) -> dict[str, Any]:
    if not path.is_file():
        warnings.append(f"missing {path.name}")
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        warnings.append(f"unreadable {path.name}: {error}")
        return {}
    return data if isinstance(data, dict) else {}


def _version(tree: Path) -> str:
    constants = tree / "src" / "constants.py"
    if not constants.is_file():
        return "unknown"
    match = VERSION_RE.search(constants.read_text(encoding="utf-8", errors="replace"))
    return match.group(1) if match else "unknown"


def _build_ref(
    tree: Path,
    venv: str,
    source: str,
    warnings: list[str],
    demo_mode: bool,
) -> EngineRef:
    resolved = tree.resolve()
    if not resolved.is_dir():
        raise EngineNotFound(f"engine tree does not exist: {resolved}")
    python = (
        resolved / venv / "Scripts" / "python.exe"
        if os.name == "nt"
        else resolved / venv / "bin" / "python"
    )
    return EngineRef(
        tree=resolved,
        python=python,
        cli=resolved / "src" / "agent_cli.py",
        version=_version(resolved),
        source=source,
        warnings=tuple(warnings),
        demo_mode=demo_mode,
    )


def resolve_engine(
    workspace_root: str | Path | None = None,
    engine_tree: str | Path | None = None,
) -> EngineRef:
    root = Path(workspace_root).resolve() if workspace_root else default_workspace_root()
    warnings: list[str] = []
    manifest = _read_json(root / "active-pair.json", warnings)
    venv = str(manifest.get("venv") or ".venv-045")
    demo_mode = os.environ.get("PICCOMPARE_DEMO") == "1"

    if engine_tree:
        tree = Path(engine_tree)
        tree = tree.resolve() if tree.is_absolute() else (root / tree).resolve()
        return _build_ref(tree, venv, "explicit", warnings, demo_mode)

    if demo_mode:
        tree_map = _read_json(root / "tree-map.json", warnings)
        demo = (tree_map.get("hackathon_demo") or {}).get("tree")
        if demo and (root / str(demo)).is_dir():
            return _build_ref(root / str(demo), venv, "demo", warnings, True)
        warnings.append("PICCOMPARE_DEMO=1 but no usable tree-map demo tree")

    comm = manifest.get("comm")
    if comm and (root / str(comm)).is_dir():
        return _build_ref(root / str(comm), venv, "manifest", warnings, demo_mode)

    raise EngineNotFound(
        "no usable engine tree: pass --engine-tree, set a valid active-pair.json "
        "comm entry, or set PICCOMPARE_DEMO=1 with tree-map.json"
    )
