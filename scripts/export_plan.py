#!/usr/bin/env python3
"""Export a measured plan report to SVG and/or DXF."""

from __future__ import annotations

import argparse
from pathlib import Path

from aec.export import export_dxf, export_svg
from aec.models import Report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report")
    parser.add_argument("--format", choices=["svg", "dxf", "both"], default="both")
    parser.add_argument("--out", default="runs/export")
    args = parser.parse_args(argv)
    report = Report.model_validate_json(Path(args.report).read_text(encoding="utf-8"))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = report.plan.pair_id
    if args.format in {"svg", "both"}:
        export_svg(report, out / f"{stem}.svg")
    if args.format in {"dxf", "both"}:
        export_dxf(report, out / f"{stem}.dxf")
    print(f"exported {stem} to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
