"""The registry is the single source of truth for the published tool manifest."""

from __future__ import annotations

from pathlib import Path

import pytest

from aec import tool_registry
from aec.tool_registry import TOOLS, HandlerRef

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "mcp" / "manifest.json"
MANIFEST_KEYS = (
    "name",
    "description",
    "transport",
    "status",
    "input_schema",
    "example",
)
PUBLISHED_NAMES = [
    "aec.measure",
    "aec.verify",
    "aec.export",
    "aec.engine_info",
    "aec.batch",
    "aec.eval",
    "piccompare.compare_documents",
    "piccompare.get_regions",
    "piccompare.get_crop",
    "piccompare.get_page_image",
    "piccompare.export_report",
    "piccompare.align",
]


def test_committed_manifest_matches_the_generated_one() -> None:
    # Hand-editing mcp/manifest.json is what this test exists to catch: the
    # published contract is generated from TOOLS, never written by hand.
    assert MANIFEST.read_text(encoding="utf-8") == tool_registry.render_manifest()


def test_render_is_stable_and_ends_with_one_newline() -> None:
    first = tool_registry.render_manifest()
    assert first == tool_registry.render_manifest()
    assert first.endswith("}\n") and not first.endswith("\n\n")


def test_the_twelve_published_names_are_kept() -> None:
    assert [tool.name for tool in TOOLS] == PUBLISHED_NAMES


def test_every_entry_carries_the_six_manifest_keys() -> None:
    for tool in TOOLS:
        for key in MANIFEST_KEYS:
            value = getattr(tool, key)
            assert value, f"{tool.name} has an empty {key}"
        assert tool.status in {"available", "external", "draft", "planned"}
        assert all(
            isinstance(name, str) and isinstance(kind, str)
            for name, kind in tool.input_schema.items()
        )
        assert isinstance(tool.read_only, bool)


def test_every_entry_carries_a_handler_that_resolves_to_a_callable() -> None:
    for tool in TOOLS:
        assert isinstance(tool.handler, HandlerRef)
        assert callable(tool.handler.resolve())


def test_importing_the_registry_does_not_import_the_imaging_stack() -> None:
    # The manifest generator must run without OpenCV, Pillow or shapely, so a
    # handler is a reference resolved on call, never an import at module load.
    import subprocess
    import sys

    code = (
        "import sys; import aec.tool_registry; "
        "loaded = {'cv2', 'PIL', 'shapely'} & set(sys.modules); "
        "print(sorted(loaded))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "[]"


def test_resolving_a_handler_that_is_not_callable_fails_loudly() -> None:
    with pytest.raises(TypeError, match="not callable"):
        HandlerRef("aec.ops", "EXPORT_FORMATS").resolve()


def test_write_manifest_regenerates_the_file_byte_for_byte(
    tmp_path, monkeypatch, capsys
) -> None:
    target = tmp_path / "manifest.json"
    monkeypatch.setattr(tool_registry, "MANIFEST_PATH", target)
    assert tool_registry.main(["--write-manifest"]) == 0
    assert target.read_text(encoding="utf-8") == tool_registry.render_manifest()
    assert "manifest.json" in capsys.readouterr().out


def test_main_prints_the_manifest_without_writing(
    tmp_path, monkeypatch, capsys
) -> None:
    target = tmp_path / "manifest.json"
    monkeypatch.setattr(tool_registry, "MANIFEST_PATH", target)
    assert tool_registry.main([]) == 0
    assert not target.exists()
    assert capsys.readouterr().out == tool_registry.render_manifest()


def test_the_module_entry_point_prints_the_manifest() -> None:
    # The command in the manifest's own note has to be runnable as written.
    import subprocess
    import sys

    completed = subprocess.run(
        [sys.executable, "-m", "aec.tool_registry"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == tool_registry.render_manifest()
