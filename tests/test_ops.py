"""Unit tests for the data-returning operations behind the CLI handlers.

Each function must return a JSON-safe mapping or raise a typed error, because
the same call is what an assistant tool server will make.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from conftest import make_engine_tree, write_manifest
from factories import sample_report

from aec.engine import EngineNotFound
from aec.evidence import report_digest
from aec.ops import OpsError, engine_info, export, measure, verify
from aec.report import write_report

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "fixtures" / "aec" / "resize-01"


def _assert_json_safe(value: dict[str, Any]) -> None:
    """A tool result has to survive a JSON round trip unchanged."""
    assert isinstance(value, dict)
    assert json.loads(json.dumps(value, ensure_ascii=True)) == value


def test_measure_returns_the_pair_summary_and_the_report_path(tmp_path: Path) -> None:
    result = measure(FIXTURE, tmp_path)
    _assert_json_safe(result)
    assert result["pair_id"] == "resize-01"
    assert result["verified"] >= 1
    assert result["not_compared"] == 0
    assert result["rejected"] == 0
    assert result["report"] == str(tmp_path / "report.json")
    assert (tmp_path / "report.json").is_file()
    # Cards were not requested, so the count is unknown rather than zero.
    assert result["cards"] is None


def test_measure_without_an_output_directory_writes_no_report() -> None:
    result = measure(FIXTURE)
    _assert_json_safe(result)
    assert result["report"] is None
    assert result["cards"] is None


def test_measure_refuses_cards_without_an_output_directory() -> None:
    with pytest.raises(OpsError, match="--cards needs --out"):
        measure(FIXTURE, cards=True)


def test_measure_counts_the_cards_it_wrote(tmp_path: Path) -> None:
    result = measure(FIXTURE, tmp_path, cards=True)
    assert result["cards"] == len(list((tmp_path / "cards").glob("*.png")))
    assert result["cards"] >= 1


def test_verify_returns_ok_for_a_report_it_just_wrote(tmp_path: Path) -> None:
    measure(FIXTURE, tmp_path)
    result = verify(tmp_path / "report.json", FIXTURE)
    _assert_json_safe(result)
    assert result == {"ok": True, "reasons": []}


def test_verify_defaults_to_the_reports_own_fixture_directory(tmp_path: Path) -> None:
    # The tool takes the report alone: the directory is read from the report's
    # pair id under fixtures/aec/.
    measure(FIXTURE, tmp_path)
    assert verify(tmp_path / "report.json")["ok"] is True


def test_verify_returns_reasons_for_a_tampered_report(tmp_path: Path) -> None:
    measure(FIXTURE, tmp_path)
    path = tmp_path / "report.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["elements_a"][0]["area_m2"] = data["elements_a"][0]["area_m2"] + 1.0
    path.write_text(json.dumps(data, ensure_ascii=True), encoding="ascii")
    result = verify(path, FIXTURE)
    assert result["ok"] is False
    assert any("element hash mismatch" in reason for reason in result["reasons"])


def test_verify_fails_closed_when_no_fixture_matches_the_pair_id(
    tmp_path: Path,
) -> None:
    measure(FIXTURE, tmp_path)
    path = tmp_path / "report.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["plan"]["pair_id"] = "no-such-pair-99"
    data["digest"] = report_digest(data)
    path.write_text(json.dumps(data, ensure_ascii=True), encoding="ascii")
    result = verify(path)
    assert result["ok"] is False
    assert any("no inputs directory" in reason for reason in result["reasons"])


def test_verify_reports_an_unreadable_report_as_a_reason(tmp_path: Path) -> None:
    # No fixture lookup can survive this, so the default has to fall back to
    # "no inputs directory" rather than raise.
    path = tmp_path / "report.json"
    path.write_text("{not json", encoding="utf-8")
    result = verify(path)
    assert result["ok"] is False
    assert any("unreadable report" in reason for reason in result["reasons"])


def test_export_writes_both_formats(tmp_path: Path) -> None:
    json_path, _ = write_report(sample_report(rooms=2), tmp_path / "report")
    result = export(json_path, out=tmp_path / "export")
    _assert_json_safe(result)
    assert result["pair_id"] == "p1"
    assert result["out"] == str(tmp_path / "export")
    assert sorted(Path(path).suffix for path in result["files"]) == [".dxf", ".svg"]
    for path in result["files"]:
        assert Path(path).is_file()


def test_export_writes_only_the_requested_format(tmp_path: Path) -> None:
    json_path, _ = write_report(sample_report(rooms=1), tmp_path / "report")
    result = export(json_path, format="svg", out=tmp_path / "export")
    assert [Path(path).suffix for path in result["files"]] == [".svg"]
    assert not (tmp_path / "export" / "p1.dxf").exists()


def test_export_refuses_an_unknown_format(tmp_path: Path) -> None:
    json_path, _ = write_report(sample_report(rooms=1), tmp_path / "report")
    with pytest.raises(OpsError, match="format"):
        export(json_path, format="pdf", out=tmp_path / "export")


@pytest.mark.parametrize("pair_id", ["../evil", "..", ".", "a/b", "a\\b", "C:evil"])
def test_export_refuses_a_pair_id_that_is_not_a_file_name(
    tmp_path: Path, pair_id: str
) -> None:
    """The pair id becomes the written file name, so it cannot name a place.

    Only a crafted report reaches this: the id is copied into the file name
    with no constraint, and ``../evil`` wrote outside the export folder.
    """
    json_path, _ = write_report(sample_report(rooms=1), tmp_path / "report")
    data = json.loads(json_path.read_text(encoding="utf-8"))
    data["plan"]["pair_id"] = pair_id
    json_path.write_text(json.dumps(data, ensure_ascii=True), encoding="ascii")
    out = tmp_path / "export"
    with pytest.raises(OpsError, match="unsafe pair id"):
        export(json_path, out=out)
    assert not out.exists()
    written = sorted(
        path.relative_to(tmp_path).as_posix()
        for path in tmp_path.rglob("*")
        if path.is_file()
    )
    assert written == ["report/report.json", "report/report.md"]


def test_engine_info_returns_the_resolved_tree(tmp_path: Path) -> None:
    write_manifest(tmp_path, comm="PicCompare_TestC")
    make_engine_tree(tmp_path, "PicCompare_TestC")
    result = engine_info(tmp_path)
    _assert_json_safe(result)
    assert Path(result["tree"]).name == "PicCompare_TestC"
    assert result["version"] == "9.99.0"
    assert result["source"] == "manifest"
    assert result["cli_exists"] is True
    assert result["python_exists"] is True
    assert result["demo_mode"] is False


def test_engine_info_raises_when_no_engine_resolves(tmp_path: Path) -> None:
    with pytest.raises(EngineNotFound):
        engine_info(tmp_path)
