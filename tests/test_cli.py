from __future__ import annotations

import pytest

from aec.cli import main


def test_cli_prints_version(capsys) -> None:
    with pytest.raises(SystemExit) as error:
        main(["--version"])
    assert error.value.code == 0
    assert "0.1.0" in capsys.readouterr().out
