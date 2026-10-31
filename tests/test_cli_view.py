"""`aec view`: one report in, one self-contained HTML page out."""

from __future__ import annotations

from pathlib import Path

from aec.cli import main

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "demo" / "sample-report.json"
FIXTURE = ROOT / "fixtures" / "aec" / "resize-01"


def _copy_sample(destination: Path) -> Path:
    destination.write_text(SAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    return destination


def test_view_writes_one_standalone_page(tmp_path: Path, capsys) -> None:
    out = tmp_path / "page.html"
    assert main(["view", "--report", str(SAMPLE), "--out", str(out)]) == 0
    page = out.read_text(encoding="utf-8")
    # The sample's finding, and its cards inlined rather than linked.
    assert "room_resized:resize-01:a:0:room:0" in page
    assert "delta +2.000" in page
    assert page.count("data:image/png;base64,") == 2
    assert 'src="cards/' not in page
    assert "http://" not in page and "https://" not in page
    assert str(tmp_path) not in page
    assert capsys.readouterr().out.strip() == str(out)


def test_view_accepts_the_inputs_directory_it_was_given(tmp_path: Path) -> None:
    out = tmp_path / "page.html"
    code = main(
        [
            "view",
            "--report",
            str(SAMPLE),
            "--out",
            str(out),
            "--inputs-dir",
            str(FIXTURE),
        ]
    )
    assert code == 0
    assert out.is_file()


def test_view_refuses_a_report_whose_inputs_do_not_verify(
    tmp_path: Path, capsys
) -> None:
    out = tmp_path / "page.html"
    report = _copy_sample(tmp_path / "report.json")
    # The copied report names a.png and b.png, and this directory has neither.
    code = main(
        ["view", "--report", str(report), "--out", str(out), "--inputs-dir", str(tmp_path)]
    )
    assert code == 1
    assert not out.exists()
    assert "FAIL" in capsys.readouterr().out


def test_view_reports_a_missing_report_without_its_location(
    tmp_path: Path, capsys
) -> None:
    out = tmp_path / "page.html"
    code = main(["view", "--report", str(tmp_path / "absent.json"), "--out", str(out)])
    assert code == 2
    assert not out.exists()
    printed = capsys.readouterr().out
    assert "FAIL" in printed
    assert str(tmp_path) not in printed
    assert "<path>" in printed


def test_view_names_a_missing_card_by_its_relative_path(
    tmp_path: Path, capsys
) -> None:
    # A report copied without its cards directory: the page cannot be made
    # self-contained, and the message must not reveal where the copy lives.
    report = _copy_sample(tmp_path / "report.json")
    out = tmp_path / "page.html"
    assert main(["view", "--report", str(report), "--out", str(out)]) == 2
    printed = capsys.readouterr().out
    assert "cards/" in printed
    assert str(tmp_path) not in printed
    assert not out.exists()


def test_view_refuses_to_replace_its_own_report(tmp_path: Path, capsys) -> None:
    report = _copy_sample(tmp_path / "report.json")
    original = report.read_text(encoding="utf-8")
    assert main(["view", "--report", str(report), "--out", str(report)]) == 2
    assert report.read_text(encoding="utf-8") == original
    assert "refusing" in capsys.readouterr().out
