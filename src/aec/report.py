"""Build and write the AEC evidence report."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aec.evidence import report_digest
from aec.models import (
    DEMO_NOTICE,
    Element,
    ElementMatch,
    Finding,
    MeasurementDelta,
    PageGeometry,
    PlanSpec,
    Report,
)


def build_report(
    *,
    engine: dict[str, Any],
    inputs: dict[str, Any],
    settings: dict[str, Any],
    plan: PlanSpec,
    pages: list[PageGeometry],
    elements_a: list[Element],
    elements_b: list[Element],
    matches: list[ElementMatch],
    measurements: list[MeasurementDelta],
    findings: list[Finding],
    rejected: list[Finding],
    not_compared: list[Finding],
    evidence: dict[str, Any],
    usage: dict[str, Any],
    limitations: list[str],
    generated_at: str | None = None,
) -> Report:
    report = Report(
        schema_version="piccompare-aec-report/1.0",
        demo_notice=DEMO_NOTICE,
        generated_at=generated_at or datetime.now(UTC).isoformat(timespec="seconds"),
        engine=engine,
        inputs=inputs,
        settings=settings,
        plan=plan,
        pages=pages,
        elements_a=elements_a,
        elements_b=elements_b,
        matches=matches,
        measurements=measurements,
        findings=findings,
        rejected=rejected,
        not_compared=not_compared,
        evidence=evidence,
        usage=usage,
        limitations=limitations,
        digest="",
    )
    return report.model_copy(update={"digest": report_digest(report)})


def render_markdown(report: Report) -> str:
    lines = [
        "# PicCompare AEC evidence report",
        "",
        f"**{report.demo_notice}**",
        "",
        f"- Pair: `{report.plan.pair_id}`",
        f"- Generated: {report.generated_at}",
        f"- Findings: {len(report.findings)} verified, {len(report.rejected)} rejected, "
        f"{len(report.not_compared)} not compared",
        f"- Report digest: `{report.digest}`",
        "",
        "## Findings",
        "",
    ]
    if report.findings:
        lines.extend(["| Type | Materiality | Evidence | Claim |", "|---|---|---|---|"])
        for finding in report.findings:
            lines.append(
                f"| {finding.change_type} | {finding.materiality} | "
                f"{', '.join(finding.evidence_refs)} | {finding.claim} |"
            )
    else:
        lines.append("No verified material findings.")
    lines.extend(["", "## Not compared", ""])
    if report.not_compared:
        for finding in report.not_compared:
            lines.append(
                f"- `{finding.finding_id}` — {finding.claim} ({', '.join(finding.reasons)})"
            )
    else:
        lines.append("None.")
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {limitation}" for limitation in report.limitations)
    lines.extend(
        [
            "",
            "This is a hashed, replayable evidence report. It is not signed and "
            "is not an evidence record.",
            "",
        ]
    )
    return "\n".join(lines)


def write_report(report: Report, out_dir: str | Path) -> tuple[Path, Path]:
    if report.demo_notice != DEMO_NOTICE:
        raise ValueError("report demo notice is not the exact required string")
    report = report.model_copy(update={"digest": report_digest(report)})
    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / "report.json"
    md_path = directory / "report.md"
    json_path.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=True) + "\n",
        encoding="ascii",
    )
    markdown = render_markdown(report)
    if DEMO_NOTICE not in markdown:
        raise ValueError("report Markdown lost the demo notice")
    md_path.write_text(markdown, encoding="utf-8", newline="\n")
    return json_path, md_path
