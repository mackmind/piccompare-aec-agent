"""Aggregate per-pair AEC reports into a materiality-sorted batch summary."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aec.models import Report


@dataclass(frozen=True)
class PairSummary:
    pair_id: str
    verified: int
    high: int
    medium: int
    low: int
    rejected: int
    not_compared: int
    report_path: str | None = None


@dataclass(frozen=True)
class BatchSummary:
    pairs: list[PairSummary]
    totals: dict[str, int]


def _summary(report: Report, report_path: str | None = None) -> PairSummary:
    findings = report.findings
    return PairSummary(
        pair_id=report.plan.pair_id,
        verified=len(findings),
        high=sum(1 for finding in findings if finding.materiality == "high"),
        medium=sum(1 for finding in findings if finding.materiality == "medium"),
        low=sum(1 for finding in findings if finding.materiality == "low"),
        rejected=len(report.rejected),
        not_compared=len(report.not_compared),
        report_path=report_path,
    )


def triage(
    reports: list[Report],
    report_paths: dict[str, str] | None = None,
) -> BatchSummary:
    paths = report_paths or {}
    pairs = [
        _summary(report, paths.get(report.plan.pair_id))
        for report in reports
    ]
    pairs.sort(
        key=lambda pair: (
            -pair.high,
            -pair.medium,
            -pair.low,
            pair.pair_id,
        )
    )
    totals = {
        "pairs": len(pairs),
        "verified": sum(pair.verified for pair in pairs),
        "high": sum(pair.high for pair in pairs),
        "medium": sum(pair.medium for pair in pairs),
        "low": sum(pair.low for pair in pairs),
        "rejected": sum(pair.rejected for pair in pairs),
        "not_compared": sum(pair.not_compared for pair in pairs),
    }
    return BatchSummary(pairs=pairs, totals=totals)


def to_dict(summary: BatchSummary) -> dict[str, Any]:
    return {
        "schema": "piccompare-aec-batch/1.0",
        "pairs": [
            {
                "pair_id": pair.pair_id,
                "verified": pair.verified,
                "high": pair.high,
                "medium": pair.medium,
                "low": pair.low,
                "rejected": pair.rejected,
                "not_compared": pair.not_compared,
                "report_path": pair.report_path,
            }
            for pair in summary.pairs
        ],
        "totals": summary.totals,
    }


def run_batch(reports_dir: str | Path, out_dir: str | Path) -> dict[str, Any]:
    """Combine every ``*/report.json`` under ``reports_dir`` into one summary.

    Writes ``summary.json`` and ``summary.md`` under ``out_dir`` and returns the
    same payload, so a caller gets the data without re-reading the files. Moved
    here from ``scripts/run_batch.py`` (W3-2): ``scripts/`` is not a package.
    """
    reports: list[Report] = []
    paths: dict[str, str] = {}
    for path in sorted(Path(reports_dir).glob("*/report.json")):
        report = Report.model_validate_json(path.read_text(encoding="utf-8"))
        reports.append(report)
        paths[report.plan.pair_id] = str(path)
    summary = triage(reports, paths)
    payload = to_dict(summary)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
        encoding="ascii",
    )
    lines = [
        "# AEC batch summary",
        "",
        f"Pairs: {summary.totals['pairs']} | verified: {summary.totals['verified']} "
        f"| refused: {summary.totals['not_compared']} "
        f"| rejected: {summary.totals['rejected']}",
        "",
        "| Pair | High | Medium | Low | Refused | Report |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for pair in summary.pairs:
        lines.append(
            f"| {pair.pair_id} | {pair.high} | {pair.medium} | {pair.low} "
            f"| {pair.not_compared} | {pair.report_path or ''} |"
        )
    (out / "summary.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8", newline="\n"
    )
    return payload
