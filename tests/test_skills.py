from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_each_skill_has_frontmatter_and_required_sections() -> None:
    for path in sorted((ROOT / "skills").glob("*/SKILL.md")):
        text = path.read_text(encoding="utf-8")
        assert text.startswith("---\n"), path
        for section in ["## When to use", "## Workflow", "## Evidence", "## Limitations"]:
            assert section in text, f"{path} missing {section}"


def test_manifest_tools_are_schema_valid() -> None:
    manifest = json.loads((ROOT / "mcp" / "manifest.json").read_text(encoding="utf-8"))
    tools = manifest["tools"]
    assert 10 <= len(tools) <= 15
    for tool in tools:
        assert {"name", "description", "transport", "status", "input_schema", "example"} <= set(
            tool
        )
        assert tool["status"] in {"available", "external", "draft", "planned"}
        assert tool["example"]


def test_skills_do_not_claim_live_or_signed_capability() -> None:
    aec = (ROOT / "skills" / "piccompare-aec" / "SKILL.md").read_text(encoding="utf-8")
    # Round 14: live runs exist; the skill must still scope the default and the
    # limits, and must keep deferring the live path to the runbook.
    assert "offline default" in aec
    assert "docs/LIVE-RUN.md" in aec
    assert "never “signed”" in aec or "never “signed”" in aec
    legal = (ROOT / "skills" / "piccompare-legal" / "SKILL.md").read_text(encoding="utf-8")
    assert "draft" in legal.lower()
    print_skill = (ROOT / "skills" / "piccompare-print" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "draft" in print_skill.lower()
