"""Minimal public CLI scaffold.

The AEC workflow commands are added by later tasks. This entry point exists so
the package metadata and CI can be exercised without importing engine modules.
"""

from __future__ import annotations

import argparse

from . import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aec")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("command", nargs="?", default="help")
    args = parser.parse_args(argv)
    print(f"piccompare-aec-agent {__version__} ({args.command})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
