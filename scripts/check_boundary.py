#!/usr/bin/env python3
"""Fail if engine source, a secret or a non-public artifact enters this repo.

Task 1 checks location, forbidden imports/markers, secrets and forbidden file
names. Task 5 adds fixture-manifest count and hash checks.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_PARTS = {
    ".git",
    ".venv-aec",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "runs",
    "piccompare_aec_agent.egg-info",
}
SKIP_RELATIVE = {"scripts/check_boundary.py", "tests/test_repo_boundary.py"}
TEXT_SUFFIXES = {".py", ".md", ".json", ".toml", ".txt", ".yaml", ".yml", ".cfg", ".ini"}
FORBIDDEN_IMPORT = re.compile(
    r"^\s*(?:from|import)\s+(?:core(?:\.|\s)|PySide6|PyQt6|fitz|pymupdf|_piccompare_core)\b",
    re.MULTILINE,
)
FORBIDDEN_MARKERS = [
    "PUBLIC_KEYS",
    "license_policy",
    "BEGIN PRIVATE KEY",
    "BEGIN RSA PRIVATE KEY",
    "BEGIN OPENSSH PRIVATE KEY",
    "ComparisonPipeline",
    "core.diff_v2",
    "PicCompare_commercial.spec",
]
SECRET_PATTERNS = [
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"(?i)\bpassword\s*[:=]\s*['\"][^'\"]{4,}['\"]"),
]
FORBIDDEN_NAMES = {
    ".env",
    "active-pair.json",
    "tree-map.json",
    "id_rsa",
    "id_ed25519",
}
FORBIDDEN_NAME_TOKENS = {"handoff", "backlog", "decision", "status", "review"}
FORBIDDEN_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".pyc", ".pyo"}


def name_errors(relative: Path) -> list[str]:
    """Internal record names that must not ship in the public tree."""
    errors: list[str] = []
    if relative.name.lower() in FORBIDDEN_NAMES:
        errors.append(f"forbidden file name: {relative}")
    tokens = set(re.split(r"[-_.]", relative.stem.lower()))
    errors.extend(
        f"internal record name {token!r} in the public tree: {relative}"
        for token in sorted(FORBIDDEN_NAME_TOKENS & tokens)
    )
    return errors


def iter_files():
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if any(part in SKIP_PARTS for part in relative.parts):
            continue
        yield path, relative


def main() -> int:
    errors: list[str] = []
    for parent in [ROOT, *ROOT.parents]:
        if parent.name.startswith("PicCompare"):
            errors.append(f"repo is inside an engine tree: {parent}")

    for path, relative in iter_files():
        if relative.as_posix() in SKIP_RELATIVE:
            continue
        errors.extend(name_errors(relative))
        if relative.suffix.lower() in FORBIDDEN_SUFFIXES:
            errors.append(f"forbidden file type: {relative}")
        if relative.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as error:
            errors.append(f"unreadable text file {relative}: {error}")
            continue
        if FORBIDDEN_IMPORT.search(text):
            errors.append(f"engine/Qt import in {relative}")
        for marker in FORBIDDEN_MARKERS:
            if marker in text:
                errors.append(f"engine marker {marker!r} in {relative}")
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                errors.append(f"secret-looking string {pattern.pattern!r} in {relative}")

    manifest_path = ROOT / "fixtures" / "manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        pairs = manifest.get("pairs", [])
        if not 10 <= len(pairs) <= 12:
            errors.append(f"expected 10-12 fixture pairs, got {len(pairs)}")
        for pair in pairs:
            pair_dir = ROOT / "fixtures" / "aec" / str(pair["pair_id"])
            for name, expected in pair.get("files", {}).items():
                path = pair_dir / name
                if not path.is_file():
                    errors.append(f"missing fixture file: {path.relative_to(ROOT)}")
                else:
                    digest = hashlib.sha256(path.read_bytes()).hexdigest()
                    if digest != expected:
                        errors.append(f"fixture hash mismatch: {path.relative_to(ROOT)}")

    if errors:
        for error in errors:
            print(f"FAIL {error}")
        return 1
    print("boundary PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
