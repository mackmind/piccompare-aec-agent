"""AEC command-line interface.

The handlers here print and set the exit code; the work, and every value they
print, comes from :mod:`aec.ops` so a terminal and an assistant share one path.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from aec import __version__, ops, webapp
from aec.engine import EngineNotFound


def _measure(args: argparse.Namespace) -> int:
    try:
        result = ops.measure(args.fixture, args.out, cards=args.cards)
    except ops.OpsError as error:
        print(f"FAIL {error}")
        return 2
    print(
        f"pair={result['pair_id']} verified={result['verified']} "
        f"not_compared={result['not_compared']} rejected={result['rejected']}"
    )
    if result["report"]:
        print(f"report={result['report']}")
    if args.cards:
        print(f"cards={result['cards']}")
    return 0


def _verify(args: argparse.Namespace) -> int:
    result = ops.verify(args.report, args.inputs_dir)
    if result["ok"]:
        print("PASS report verifies")
        return 0
    for reason in result["reasons"]:
        print(f"FAIL {reason}")
    return 1


def _export(args: argparse.Namespace) -> int:
    result = ops.export(args.report, format=args.format, out=args.out)
    print(f"exported {result['pair_id']} to {result['out']}")
    return 0


def _view(args: argparse.Namespace) -> int:
    try:
        result = ops.view(args.report, args.out, args.inputs_dir)
    except ops.OpsError as error:
        print(f"FAIL {error}")
        return 2
    if not result["ok"]:
        for reason in result["reasons"]:
            print(f"FAIL {reason}")
        return 1
    print(result["out"])
    return 0


def _engine_info(args: argparse.Namespace) -> int:
    try:
        result = ops.engine_info(args.workspace_root, args.engine_tree)
    except EngineNotFound as error:
        print(f"ENGINE NOT FOUND: {error}")
        return 1
    print(f"tree={result['tree']}")
    print(f"version={result['version']}")
    print(f"source={result['source']}")
    print(f"python={result['python']} exists={result['python_exists']}")
    print(f"cli={result['cli']} exists={result['cli_exists']}")
    return 0


def _serve(args: argparse.Namespace) -> int:
    try:
        return webapp.serve(
            workspace=Path(args.workspace),
            fixtures=Path(args.fixtures),
            port=args.port,
            open_browser=not args.no_open,
        )
    except webapp.WebAppError as error:
        print(f"FAIL {error}")
        return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aec")
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    measure = subparsers.add_parser("measure", help="measure one fixture pair")
    measure.add_argument("--fixture", required=True)
    measure.add_argument("--out")
    measure.add_argument(
        "--cards",
        action="store_true",
        help="write PNG evidence cards under the report directory",
    )
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

    view = subparsers.add_parser("view", help="render a report as one HTML page")
    view.add_argument("--report", required=True)
    view.add_argument("--inputs-dir")
    view.add_argument("--out", required=True)
    view.set_defaults(handler=_view)

    engine_info = subparsers.add_parser("engine-info", help="resolve engine tree")
    engine_info.add_argument("--workspace-root")
    engine_info.add_argument("--engine-tree")
    engine_info.set_defaults(handler=_engine_info)

    serve = subparsers.add_parser(
        "serve", help="serve the local web page on loopback"
    )
    serve.add_argument(
        "--port", type=int, default=0, help="0 picks an ephemeral port"
    )
    serve.add_argument("--fixtures", default="fixtures/aec")
    serve.add_argument("--workspace", default="runs/web")
    serve.add_argument(
        "--no-open",
        action="store_true",
        help="print the URL without opening a browser",
    )
    serve.set_defaults(handler=_serve)

    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
