"""Data-returning operations behind the AEC command line.

Each function returns a JSON-safe mapping or raises; :mod:`aec.cli` keeps the
printing and the exit codes, and the tool server calls the same functions. No
subprocess, no shell. Moved out of the CLI handlers during W3-2 so the same
code serves a terminal and an assistant.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from aec.engine import resolve_engine
from aec.evidence import read_report, report_digest
from aec.evidence import verify as verify_report
from aec.export import export_dxf, export_svg
from aec.models import Report
from aec.pipeline import run_pair
from aec.redact import redact
from aec.viewer import ViewerError, render_report_html

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPORT_FORMATS = ("svg", "dxf", "both")
# The export writes one file per format under the output folder, named after
# the pair id, so that id has to be a plain file name: no separator, no drive
# letter, no "." or "..".
SAFE_PAIR_ID = re.compile(r"^[A-Za-z0-9._-]+$")


class OpsError(ValueError):
    """A request the operation refuses; the message is safe to show a caller."""


def _fixture_directory(report_path: Path) -> Path | None:
    """The fixture directory named by the report itself, when it still exists.

    Returns ``None`` rather than guessing: verification then fails closed with
    "no inputs directory" instead of certifying inputs it never read.
    """
    try:
        report = Report.model_validate_json(report_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    candidate = REPO_ROOT / "fixtures" / "aec" / report.plan.pair_id
    return candidate if candidate.is_dir() else None


def measure(
    fixture: str | Path,
    out: str | Path | None = None,
    *,
    cards: bool = False,
) -> dict[str, Any]:
    """Measure one fixture pair, optionally writing a report and evidence cards."""
    out_dir = Path(out) if out is not None else None
    if cards and out_dir is None:
        raise OpsError(
            "--cards needs --out: cards are written under the report directory"
        )
    result = run_pair(Path(fixture), out_dir, cards=cards)
    return {
        "pair_id": result.pair_id,
        "verified": len(result.verified),
        "not_compared": len(result.not_compared),
        "rejected": len(result.rejected),
        "report": str(result.report_path) if result.report_path else None,
        # Unknown when cards were not requested, as opposed to requested and
        # all skipped, which is 0.
        "cards": len(result.report.evidence_cards) if cards else None,
    }


def verify(
    report: str | Path,
    inputs_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Re-check a report from its stored fingerprints.

    ``inputs_dir`` defaults to the fixture directory the report names for
    itself (``fixtures/aec/<pair_id>``), so a caller that measured a fixture
    can verify the report without being told where the inputs live. When that
    directory is absent the check still fails closed: every recorded input
    fingerprint is then reported as unverifiable.
    """
    report_path = Path(report)
    directory = (
        Path(inputs_dir) if inputs_dir is not None else _fixture_directory(report_path)
    )
    result = verify_report(report_path, directory)
    return {"ok": result.ok, "reasons": list(result.reasons)}


def view(
    report: str | Path,
    out: str | Path,
    inputs_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Render one report as a self-contained HTML page.

    ``inputs_dir`` switches on the same re-check :func:`verify` performs, so a
    page is written only for a report whose inputs were read again; without it
    the page is built from the report alone, which is what an archived report or
    a CI artifact needs. A report that fails that check returns ``ok`` false and
    nothing is written.

    Raises :class:`OpsError` when the report cannot be read or validated, when
    its digest does not cover its own content, or when a card image is missing.
    No message carries an absolute path.
    """
    report_path = Path(report)
    try:
        data = read_report(report_path)
    except OSError as error:
        raise OpsError(f"cannot read report: {redact(str(error))}") from error
    except ValueError as error:
        detail = " ".join(redact(str(error)).split())[:300]
        raise OpsError(f"report is not valid: {detail}") from error
    try:
        model = Report.model_validate(data)
    except ValueError as error:
        detail = " ".join(redact(str(error)).split())[:300]
        raise OpsError(f"report is not valid: {detail}") from error
    if inputs_dir is not None:
        checked = verify(report_path, inputs_dir)
        if not checked["ok"]:
            return {
                "ok": False,
                "out": None,
                "pair_id": model.plan.pair_id,
                "reasons": list(checked["reasons"]),
            }
    out_path = Path(out)
    if out_path.resolve() == report_path.resolve():
        raise OpsError("refusing to replace the report with its own page")
    # Without --inputs-dir nothing else reads the digest, so an edited report
    # would render beside a digest that no longer covers it. The comparison is
    # on the raw mapping: a model round-trip would default a field the file
    # never carried and report a false mismatch.
    if data.get("digest") != report_digest(data):
        raise OpsError("report digest mismatch")
    try:
        page = render_report_html(
            model, embed_cards=True, cards_dir=report_path.parent
        )
    except ViewerError as error:
        raise OpsError(str(error)) from error
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(page, encoding="utf-8", newline="\n")
    except (OSError, UnicodeError) as error:
        raise OpsError(f"cannot write page: {redact(str(error))}") from error
    return {
        "ok": True,
        "out": str(out_path),
        "pair_id": model.plan.pair_id,
        "reasons": [],
    }


def export(
    report: str | Path,
    *,
    format: str = "both",
    out: str | Path = "runs/export",
) -> dict[str, Any]:
    """Write the measured rooms of a report as an SVG and/or DXF overlay.

    The files are named after the report's pair id, which must be a plain file
    name; anything else raises ``OpsError`` rather than writing outside ``out``.
    """
    if format not in EXPORT_FORMATS:
        raise OpsError(
            f"unknown export format {format!r}; expected one of "
            + ", ".join(EXPORT_FORMATS)
        )
    model = Report.model_validate_json(Path(report).read_text(encoding="utf-8"))
    stem = model.plan.pair_id
    # Refused before anything is created, so a crafted report cannot name a
    # file outside the export folder on the write.
    if not SAFE_PAIR_ID.fullmatch(stem) or stem in {".", ".."}:
        raise OpsError("unsafe pair id")
    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    files: list[str] = []
    if format in {"svg", "both"}:
        path = out_dir / f"{stem}.svg"
        export_svg(model, path)
        files.append(str(path))
    if format in {"dxf", "both"}:
        path = out_dir / f"{stem}.dxf"
        export_dxf(model, path)
        files.append(str(path))
    return {
        "pair_id": stem,
        "format": format,
        "out": str(out_dir),
        "files": files,
    }


def engine_info(
    workspace_root: str | Path | None = None,
    engine_tree: str | Path | None = None,
) -> dict[str, Any]:
    """Find a local PicCompare build; raise ``EngineNotFound`` when none resolves."""
    ref = resolve_engine(workspace_root, engine_tree)
    return {
        "tree": str(ref.tree),
        "version": ref.version,
        "source": ref.source,
        "python": str(ref.python),
        "python_exists": ref.python_exists,
        "cli": str(ref.cli),
        "cli_exists": ref.cli_exists,
        "demo_mode": ref.demo_mode,
        "warnings": list(ref.warnings),
    }
