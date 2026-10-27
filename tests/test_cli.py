from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from aec.cli import main

ROOT = Path(__file__).resolve().parent.parent


def test_cli_prints_version(capsys) -> None:
    with pytest.raises(SystemExit) as error:
        main(["--version"])
    assert error.value.code == 0
    assert "0.1.0" in capsys.readouterr().out


def test_module_entry_prints_version() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "aec", "--version"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "0.1.0" in result.stdout


def test_cli_measure_and_verify(tmp_path) -> None:
    fixture = ROOT / "fixtures" / "aec" / "resize-01"
    assert main(["measure", "--fixture", str(fixture), "--out", str(tmp_path)]) == 0
    report = tmp_path / "report.json"
    assert report.is_file()
    assert main(
        ["verify", "--report", str(report), "--inputs-dir", str(fixture)]
    ) == 0


def test_cli_export(tmp_path) -> None:
    fixture = ROOT / "fixtures" / "aec" / "resize-01"
    assert main(["measure", "--fixture", str(fixture), "--out", str(tmp_path)]) == 0
    out = tmp_path / "export"
    assert main(
        ["export", "--report", str(tmp_path / "report.json"), "--out", str(out)]
    ) == 0
    assert (out / "resize-01.svg").is_file()
    assert (out / "resize-01.dxf").is_file()
