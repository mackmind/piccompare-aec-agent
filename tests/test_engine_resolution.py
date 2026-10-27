from __future__ import annotations

import pytest
from conftest import make_engine_tree, write_manifest, write_tree_map

from aec.engine import EngineNotFound, resolve_engine


def test_manifest_comm_resolution(tmp_path) -> None:
    write_manifest(tmp_path, comm="PicCompare_TestC")
    make_engine_tree(tmp_path, "PicCompare_TestC")
    ref = resolve_engine(workspace_root=tmp_path)
    assert ref.tree.name == "PicCompare_TestC"
    assert ref.source == "manifest"
    assert ref.version == "9.99.0"


def test_demo_tree_wins_when_env_set(tmp_path, monkeypatch) -> None:
    write_manifest(tmp_path, comm="PicCompare_TestC")
    write_tree_map(tmp_path, "PicCompare_TestH")
    make_engine_tree(tmp_path, "PicCompare_TestH")
    monkeypatch.setenv("PICCOMPARE_DEMO", "1")
    ref = resolve_engine(workspace_root=tmp_path)
    assert ref.tree.name == "PicCompare_TestH"
    assert ref.source == "demo"


def test_explicit_tree_wins(tmp_path) -> None:
    tree = make_engine_tree(tmp_path, "PicCompare_Explicit")
    ref = resolve_engine(workspace_root=tmp_path, engine_tree=tree)
    assert ref.source == "explicit"
    assert ref.tree == tree.resolve()


def test_missing_manifest_raises(tmp_path) -> None:
    with pytest.raises(EngineNotFound):
        resolve_engine(workspace_root=tmp_path)
