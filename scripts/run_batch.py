#!/usr/bin/env python3
"""Read per-pair AEC reports and write a materiality-sorted batch summary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from aec.batch import to_dict, triage
from aec.models import Report

REPO_ROOT = Path(__file__).resolve().parent.parent


def run_batch(reports_dir: Path, out_dir: Path) -> dict:
    reports: list[Report] = []
    paths: dict[str, str] = {}
    for path in sorted(reports_dir.glob("*/report.json")):
        report = Report.model_validate_json(path.read_text(encoding="utf-8"))
        reports.append(report)
        paths[report.plan.pair_id] = str(path)
    summary = triage(reports, paths)
    payload = to_dict(summary)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(
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
    (out_dir / "summary.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8", newline="\n"
    )
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reports", default=str(REPO_ROOT / "runs" / "eval"))
    parser.add_argument("--out", default=str(REPO_ROOT / "runs" / "batch"))
    args = parser.parse_args(argv)
    payload = run_batch(Path(args.reports), Path(args.out))
    print(
        f"batch: {payload['totals']['pairs']} pairs, "
        f"{payload['totals']['high']} high, "
        f"{payload['totals']['not_compared']} refused"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
