from __future__ import annotations

import pytest
from conftest import FakeRunner, make_engine_tree, write_manifest

from aec.client import EngineProtocolError, EngineToolError, PicCompareClient
from aec.engine import resolve_engine


def _client(tmp_path, runner):
    write_manifest(tmp_path, comm="PicCompare_TestC")
    make_engine_tree(tmp_path, "PicCompare_TestC")
    return PicCompareClient(
        resolve_engine(workspace_root=tmp_path),
        profile_dir=tmp_path / "profile",
        runner=runner,
    )


def test_compare_builds_documented_argv(tmp_path) -> None:
    runner = FakeRunner(
        {
            "compare": {
                "comparison_id": "c1",
                "status": "complete",
                "pages_a": 1,
                "pages_b": 1,
            }
        }
    )
    client = _client(tmp_path, runner)
    result = client.compare("a.png", "b.png", dpi=110, align="none")
    assert result.data["comparison_id"] == "c1"
    argv = runner.calls[0]["argv"]
    assert "compare" in argv and "--json" in argv and "--profile-dir" in argv
    assert runner.calls[0]["kwargs"]["env"]["QT_QPA_PLATFORM"] == "offscreen"
    assert runner.calls[0]["kwargs"]["cwd"] == str(client.engine.tree)


def test_partial_exit_is_accepted(tmp_path) -> None:
    runner = FakeRunner(
        {
            "compare": {
                "comparison_id": "c1",
                "status": "partial",
                "pages_a": 1,
                "pages_b": 1,
            }
        },
        returncodes={"compare": 5},
    )
    client = _client(tmp_path, runner)
    result = client.compare("a.png", "b.png")
    assert result.partial


def test_bad_exit_raises_tool_error(tmp_path) -> None:
    runner = FakeRunner({}, returncodes={"compare": 3})
    client = _client(tmp_path, runner)
    with pytest.raises(EngineToolError):
        client.compare("a.png", "b.png")


def test_non_json_raises_protocol_error(tmp_path) -> None:
    runner = FakeRunner({"compare": {}}, stdout_overrides={"compare": "not json"})
    client = _client(tmp_path, runner)
    with pytest.raises(EngineProtocolError):
        client.compare("a.png", "b.png")
