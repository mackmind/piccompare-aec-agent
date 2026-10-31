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


def _tool(name: str) -> tool_registry.Tool:
    return next(tool for tool in TOOLS if tool.name == name)


def _assert_valid_input_schema(schema: dict[str, object]) -> None:
    """Check the structural rules a JSON Schema validator enforces here.

    ``jsonschema`` is not a permitted dependency, so this asserts what the meta
    schema would: an object type, properties and required agreeing, a known
    type per property, string-only enum values and typed array items.
    """
    scalar_types = {"string", "integer", "number", "boolean"}
    assert schema["type"] == "object"
    properties = schema["properties"]
    required = schema["required"]
    assert isinstance(properties, dict) and properties
    assert isinstance(required, list)
    assert set(required) <= set(properties)
    for name, prop in properties.items():
        assert isinstance(name, str) and isinstance(prop, dict), name
        assert prop["type"] in scalar_types | {"array", "object"}, prop
        if "enum" in prop:
            assert prop["type"] == "string"
            assert prop["enum"] and all(isinstance(value, str) for value in prop["enum"])
        if prop["type"] == "array":
            assert prop["items"]["type"] in scalar_types
        if "format" in prop:
            assert prop["type"] == "string" and isinstance(prop["format"], str)


def test_every_tool_derives_a_valid_input_schema() -> None:
    for tool in TOOLS:
        _assert_valid_input_schema(tool.json_schema)


def test_measure_derives_a_fixture_only_object() -> None:
    schema = _tool("aec.measure").json_schema
    assert schema == {
        "type": "object",
        "properties": {
            "fixture": {"type": "string"},
            "out": {"type": "string"},
        },
        "required": ["fixture"],
    }


def test_verify_derives_a_report_only_object() -> None:
    schema = _tool("aec.verify").json_schema
    assert schema == {
        "type": "object",
        "properties": {
            "report": {"type": "string"},
            "inputs_dir": {"type": "string"},
        },
        "required": ["report"],
    }


def test_crop_derives_three_required_strings() -> None:
    schema = _tool("piccompare.get_crop").json_schema
    assert schema == {
        "type": "object",
        "properties": {
            "comparison_id": {"type": "string"},
            "region_id": {"type": "string"},
            "view": {"type": "string"},
        },
        "required": ["comparison_id", "region_id", "view"],
    }


def test_enum_shorthand_becomes_a_string_enum() -> None:
    export = _tool("aec.export").json_schema["properties"]["format"]
    assert export == {"type": "string", "enum": ["svg", "dxf", "both"]}
    side = _tool("piccompare.get_page_image").json_schema["properties"]["side"]
    assert side == {"type": "string", "enum": ["a", "b"]}


def test_path_shorthand_becomes_a_path_formatted_string() -> None:
    document_a = _tool("piccompare.compare_documents").json_schema["properties"]["a"]
    assert document_a == {"type": "string", "format": "path"}


def test_array_shorthand_becomes_a_typed_array() -> None:
    schema = _tool("aec.eval").json_schema
    assert schema["properties"]["pairs"] == {
        "type": "array",
        "items": {"type": "string"},
    }
    assert "pairs" not in schema["required"]
    assert schema["properties"]["live"] == {"type": "boolean"}
    # The documented default is offline, so a caller may omit ``live``.
    assert "live" not in schema["required"]


def test_unknown_shorthand_raises_instead_of_guessing() -> None:
    with pytest.raises(tool_registry.SchemaError, match="unknown shorthand"):
        tool_registry.derive_input_schema({"value": "float"})


@pytest.mark.parametrize("shorthand", ["|null", "svg||dxf"])
def test_malformed_shorthand_raises(shorthand: str) -> None:
    with pytest.raises(tool_registry.SchemaError):
        tool_registry.derive_input_schema({"value": shorthand})


def test_the_manifest_still_carries_the_shorthand() -> None:
    text = MANIFEST.read_text(encoding="utf-8")
    assert '"input_schema": {"fixture": "string", "out": "string|null"}' in text
    protocol = tool_registry.tools_list()[0]
    assert "input_schema" not in protocol


def test_protocol_entries_carry_the_camel_case_schema() -> None:
    for entry in tool_registry.tools_list():
        assert set(entry) == {"name", "description", "inputSchema"}
        _assert_valid_input_schema(entry["inputSchema"])
