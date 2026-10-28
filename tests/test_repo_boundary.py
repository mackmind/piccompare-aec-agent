from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import check_boundary

ROOT = Path(__file__).resolve().parent.parent


def test_boundary_checker_passes_on_clean_repo() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_boundary.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_manifest_hashes_content_not_checkout(tmp_path: Path) -> None:
    # A raw-byte hash of a text fixture would differ between a clone (CRLF on
    # Windows) and the released tarball (LF), so the fixture manifest did not
    # verify in a clean download. Text is normalised; binaries are not.
    from aec.evidence import sha256_content

    lf = tmp_path / "lf.json"
    crlf = tmp_path / "crlf.json"
    lf.write_bytes(b'{"a": 1}\n')
    crlf.write_bytes(b'{"a": 1}\r\n')
    assert sha256_content(lf) == sha256_content(crlf)
    png_a = tmp_path / "a.png"
    png_b = tmp_path / "b.png"
    png_a.write_bytes(b"\x89PNG\r\n\x1a\n")
    png_b.write_bytes(b"\x89PNG\n\x1a\n")
    assert sha256_content(png_a) != sha256_content(png_b)


def test_internal_record_names_are_refused() -> None:
    assert check_boundary.name_errors(Path("docs/LIVE-HANDOFF.md"))
    assert check_boundary.name_errors(Path("054-STATUS.md"))
    assert check_boundary.name_errors(Path("decision-log.md"))
    assert check_boundary.name_errors(Path("REVIEW.md"))
    assert not check_boundary.name_errors(Path("docs/LIVE-RUN.md"))
    assert not check_boundary.name_errors(Path("docs/preview.md"))


def test_pyproject_is_mit_and_python_311_plus() -> None:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'license = { text = "MIT" }' in text
    assert 'requires-python = ">=3.11"' in text
