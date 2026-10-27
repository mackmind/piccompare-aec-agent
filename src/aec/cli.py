"""AEC command-line interface."""

from __future__ import annotations

import argparse
from pathlib import Path

from aec import __version__
from aec.engine import EngineNotFound, resolve_engine
from aec.evidence import verify
from aec.export import export_dxf, export_svg
from aec.models import Report
from aec.pipeline import run_pair


def _measure(args: argparse.Namespace) -> int:
    out = Path(args.out) if args.out else None
    result = run_pair(Path(args.fixture), out)
    print(
        f"pair={result.pair_id} verified={len(result.verified)} "
        f"not_compared={len(result.not_compared)} rejected={len(result.rejected)}"
    )
    if result.report_path:
        print(f"report={result.report_path}")
    return 0


def _verify(args: argparse.Namespace) -> int:
    result = verify(
        Path(args.report), Path(args.inputs_dir) if args.inputs_dir else None
    )
    if result.ok:
        print("PASS report verifies")
        return 0
    for reason in result.reasons:
        print(f"FAIL {reason}")
    return 1


def _export(args: argparse.Namespace) -> int:
    report = Report.model_validate_json(
        Path(args.report).read_text(encoding="utf-8")
    )
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = report.plan.pair_id
    if args.format in {"svg", "both"}:
        export_svg(report, out / f"{stem}.svg")
    if args.format in {"dxf", "both"}:
        export_dxf(report, out / f"{stem}.dxf")
    print(f"exported {stem} to {out}")
    return 0


def _engine_info(args: argparse.Namespace) -> int:
    try:
        ref = resolve_engine(args.workspace_root, args.engine_tree)
    except EngineNotFound as error:
        print(f"ENGINE NOT FOUND: {error}")
        return 1
    print(f"tree={ref.tree}")
    print(f"version={ref.version}")
    print(f"source={ref.source}")
    print(f"python={ref.python} exists={ref.python_exists}")
    print(f"cli={ref.cli} exists={ref.cli_exists}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aec")
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    measure = subparsers.add_parser("measure", help="measure one fixture pair")
    measure.add_argument("--fixture", required=True)
    measure.add_argument("--out")
    measure.set_defaults(handler=_measure)

    verify_parser = subparsers.add_parser("verify", help="verify a report")
    verify_parser.add_argument("--report", required=True)
    verify_parser.add_argument("--inputs-dir")
    verify_parser.set_defaults(handler=_verify)

    export = subparsers.add_parser("export", help="export measured plan")
    export.add_argument("--report", required=True)
    export.add_argument("--format", choices=["svg", "dxf", "both"], default="both")
    export.add_argument("--out", default="runs/export")
    export.set_defaults(handler=_export)

    engine_info = subparsers.add_parser("engine-info", help="resolve engine tree")
    engine_info.add_argument("--workspace-root")
    engine_info.add_argument("--engine-tree")
    engine_info.set_defaults(handler=_engine_info)

    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
