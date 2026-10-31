"""The one list of tools this repository publishes to an AI assistant.

``mcp/manifest.json`` is generated from :data:`TOOLS` - never edited by hand -
by ``python -m aec.tool_registry --write-manifest``, and a drift test asserts
the committed file equals the generated one.

Each entry carries the six manifest keys (``name``, ``description``,
``transport``, ``status``, ``input_schema``, ``example``), a ``read_only``
flag, and a ``handler`` reference. ``input_schema`` is shorthand for the
manifest; the JSON Schema the protocol publishes is derived from it, so the
two cannot disagree.
"""

from __future__ import annotations

import argparse
import importlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

MANIFEST_SCHEMA = "piccompare-aec-capabilities/1.0"
MANIFEST_NOTE = (
    "Generated from src/aec/tool_registry.py by "
    "python -m aec.tool_registry --write-manifest; do not edit it by hand. "
    "The registry is the single source of truth for the tools this repository "
    "offers AI assistants over the Model Context Protocol (MCP): transport and "
    "status say how each tool is served today, and the protocol's JSON Schema "
    "is derived from the same entry."
)
REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "mcp" / "manifest.json"


@dataclass(frozen=True)
class HandlerRef:
    """A handler named by module and attribute, imported when it is resolved.

    A reference rather than an imported callable on purpose: importing this
    module must not import the imaging stack behind ``aec.ops`` (OpenCV,
    Pillow, shapely), so the manifest can be regenerated, and the server
    started, without it. ``resolve()`` returns the callable.
    """

    module: str
    attribute: str

    def resolve(self) -> Callable[..., Any]:
        target: Any = importlib.import_module(self.module)
        for part in self.attribute.split("."):
            target = getattr(target, part)
        if not callable(target):
            raise TypeError(
                f"handler {self.module}:{self.attribute} is not callable"
            )
        return cast(Callable[..., Any], target)


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    transport: str
    status: str
    input_schema: dict[str, str]
    example: str
    read_only: bool
    handler: HandlerRef


OPS = "aec.ops"
CLIENT = "aec.client"

TOOLS: list[Tool] = [
    Tool(
        name="aec.measure",
        description=(
            "Measure one generated floor-plan pair and write a fingerprinted "
            "(hashed) report."
        ),
        transport="cli",
        status="available",
        input_schema={"fixture": "string", "out": "string|null"},
        example=(
            "python -m aec measure --fixture fixtures/aec/resize-01 "
            "--out runs/measure/resize-01"
        ),
        read_only=False,
        handler=HandlerRef(OPS, "measure"),
    ),
    Tool(
        name="aec.verify",
        description=(
            "Verify the report fingerprint, input fingerprints, element "
            "fingerprints and measurement fingerprints."
        ),
        transport="cli",
        status="available",
        input_schema={"report": "string", "inputs_dir": "string|null"},
        example=(
            "python -m aec verify --report runs/measure/resize-01/report.json "
            "--inputs-dir fixtures/aec/resize-01"
        ),
        read_only=True,
        handler=HandlerRef(OPS, "verify"),
    ),
    Tool(
        name="aec.export",
        description=(
            "Export a measured plan to SVG (scalable vector graphics) and/or "
            "DXF (a standard computer-aided design exchange format)."
        ),
        transport="cli",
        status="available",
        input_schema={"report": "string", "format": "svg|dxf|both", "out": "string"},
        example=(
            "python -m aec export --report runs/measure/resize-01/report.json "
            "--out runs/export"
        ),
        read_only=False,
        handler=HandlerRef(OPS, "export"),
    ),
    Tool(
        name="aec.engine_info",
        description=(
            "Find a local PicCompare build from a configuration file or an "
            "explicit folder path."
        ),
        transport="cli",
        status="available",
        input_schema={"workspace_root": "string|null", "engine_tree": "string|null"},
        example="python -m aec engine-info --engine-tree ../PicCompare_0.55C",
        read_only=True,
        handler=HandlerRef(OPS, "engine_info"),
    ),
    Tool(
        name="aec.batch",
        description=(
            "Combine per-pair reports into one summary sorted by how much each "
            "change matters."
        ),
        transport="cli",
        status="available",
        input_schema={"reports": "string", "out": "string"},
        example="python scripts/run_batch.py --reports runs/eval --out runs/batch",
        read_only=False,
        handler=HandlerRef("aec.batch", "run_batch"),
    ),
    Tool(
        name="aec.eval",
        description=(
            "Run the test-example evaluation, offline (repeatable, no model "
            "call) or live (Meta's model service)."
        ),
        transport="cli",
        status="available",
        input_schema={
            "fixtures": "string",
            "out": "string",
            "pairs": "string[]|null",
            "live": "boolean",
        },
        example="python scripts/run_eval.py --fixtures fixtures --out runs/eval",
        read_only=False,
        handler=HandlerRef("aec.evaluation", "run_eval"),
    ),
    Tool(
        name="piccompare.compare_documents",
        description="External engine: repeatable document comparison.",
        transport="engine-cli",
        status="external",
        input_schema={
            "a": "path",
            "b": "path",
            "dpi": "integer",
            "align": "string",
        },
        example="agent_cli.py compare a.pdf b.pdf --dpi 110 --align none --json",
        read_only=False,
        handler=HandlerRef(CLIENT, "PicCompareClient.compare"),
    ),
    Tool(
        name="piccompare.get_regions",
        description="External engine: changed regions and page size and position.",
        transport="engine-cli",
        status="external",
        input_schema={
            "comparison_id": "string",
            "kind": "string",
            "limit": "integer",
        },
        example="agent_cli.py regions --comparison-id c1 --kind all --limit 200 --json",
        read_only=True,
        handler=HandlerRef(CLIENT, "PicCompareClient.regions"),
    ),
    Tool(
        name="piccompare.get_crop",
        description="External engine: cropped image file for a changed region.",
        transport="engine-cli",
        status="external",
        input_schema={
            "comparison_id": "string",
            "region_id": "string",
            "view": "string",
        },
        example="agent_cli.py crop --comparison-id c1 --region-id r1 --view diff --json",
        read_only=False,
        handler=HandlerRef(CLIENT, "PicCompareClient.crop"),
    ),
    Tool(
        name="piccompare.get_page_image",
        description="External engine: page image file.",
        transport="engine-cli",
        status="external",
        input_schema={
            "comparison_id": "string",
            "side": "a|b",
            "page": "integer",
        },
        example="agent_cli.py page --comparison-id c1 --side a --page 0 --json",
        read_only=False,
        handler=HandlerRef(CLIENT, "PicCompareClient.page_image"),
    ),
    Tool(
        name="piccompare.export_report",
        description="External engine: engine-generated report file.",
        transport="engine-cli",
        status="external",
        input_schema={"comparison_id": "string", "format": "string"},
        example="agent_cli.py report --comparison-id c1 --format md --json",
        read_only=False,
        handler=HandlerRef(CLIENT, "PicCompareClient.report"),
    ),
    Tool(
        name="piccompare.align",
        description="External engine: alignment mapping between two pages.",
        transport="engine-cli",
        status="external",
        input_schema={
            "a": "path",
            "b": "path",
            "page_a": "integer",
            "page_b": "integer",
        },
        example="agent_cli.py align a.pdf b.pdf --page-a 0 --page-b 0 --method ecc --json",
        read_only=True,
        handler=HandlerRef(CLIENT, "PicCompareClient.align"),
    ),
]


def render_manifest() -> str:
    """The exact text of ``mcp/manifest.json``, newline-terminated."""
    blocks: list[str] = []
    for tool in TOOLS:
        fields = [
            ("name", json.dumps(tool.name, ensure_ascii=True)),
            ("description", json.dumps(tool.description, ensure_ascii=True)),
            ("transport", json.dumps(tool.transport, ensure_ascii=True)),
            ("status", json.dumps(tool.status, ensure_ascii=True)),
            # The shorthand schema stays on one line; the rest of the file is
            # indented JSON, which is how the committed file reads today.
            (
                "input_schema",
                json.dumps(
                    tool.input_schema, ensure_ascii=True, separators=(", ", ": ")
                ),
            ),
            ("example", json.dumps(tool.example, ensure_ascii=True)),
        ]
        lines = ",\n".join(f'      "{key}": {value}' for key, value in fields)
        blocks.append("    {\n" + lines + "\n    }")
    return (
        "{\n"
        f'  "schema": {json.dumps(MANIFEST_SCHEMA, ensure_ascii=True)},\n'
        f'  "note": {json.dumps(MANIFEST_NOTE, ensure_ascii=True)},\n'
        '  "tools": [\n'
        + ",\n".join(blocks)
        + "\n  ]\n}\n"
    )


def _display(path: Path) -> str:
    """Repo-relative path for messages, so no absolute path is ever printed."""
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.name


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aec.tool_registry")
    parser.add_argument(
        "--write-manifest",
        action="store_true",
        help="rewrite mcp/manifest.json from TOOLS",
    )
    args = parser.parse_args(argv)
    text = render_manifest()
    if args.write_manifest:
        MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        MANIFEST_PATH.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {_display(MANIFEST_PATH)}")
        return 0
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
