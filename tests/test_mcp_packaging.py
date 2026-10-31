"""The server's packaging contract: one console script, no new dependency.

The second test is the one the brief asks for: the server's transitive imports
must stay inside the standard library plus the six declared packages. It must
not assert "stdlib only" - importing ``aec.ops`` loads OpenCV, Pillow, shapely,
ezdxf, numpy and pydantic, and those pull in their own support modules. The
check therefore resolves the declared dependencies' own requirements and allows
exactly that closure, so a genuinely new dependency fails the test.
"""

from __future__ import annotations

import importlib
import json
import re
import subprocess
import sys
import tomllib
from importlib.metadata import PackageNotFoundError, packages_distributions, requires
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECT = "piccompare-aec-agent"
# The module names the brief names, in the spelling the import system uses.
DECLARED_MODULES = {"numpy", "shapely", "cv2", "ezdxf", "PIL", "pydantic"}
# Cython adds this pseudo-module to sys.modules when shapely's extensions load.
# It belongs to no distribution and cannot be installed, so it is not a package
# dependency; every other name has to resolve to one.
NO_DISTRIBUTION = {"cython_runtime"}
REQUIREMENT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*")

RESOLVE_EVERY_HANDLER = """
import json
import sys

import aec.mcp_server
from aec import tool_registry

for tool in tool_registry.TOOLS:
    tool.handler.resolve()

# Only real top-level module names: `$coverage` is injected into a covered
# child by pytest-cov and is not importable by anyone, and `_`-prefixed names
# are Cython and interpreter internals.
print(json.dumps(sorted(
    name
    for name in {module.split(".")[0] for module in sys.modules}
    if name.isidentifier()
    and not name.startswith("_")
    and name not in sys.stdlib_module_names
)))
"""


def _pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_the_mcp_console_script_is_declared_beside_aec() -> None:
    assert _pyproject()["project"]["scripts"] == {
        "aec": "aec.cli:main",
        "aec-mcp": "aec.mcp_server:main",
    }


def test_every_console_script_target_resolves_to_a_callable() -> None:
    for name, target in _pyproject()["project"]["scripts"].items():
        module_name, _, attribute = target.partition(":")
        module = importlib.import_module(module_name)
        assert callable(getattr(module, attribute)), name


def _declared_roots() -> set[str]:
    return {
        _normalise(REQUIREMENT_NAME.match(requirement).group(0))  # type: ignore[union-attr]
        for requirement in _pyproject()["project"]["dependencies"]
        if REQUIREMENT_NAME.match(requirement)
    }


def _normalise(name: str) -> str:
    """PEP 503 spelling, so pydantic_core and pydantic-core compare equal."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _dependency_closure(roots: set[str]) -> set[str]:
    """Every distribution reachable from the roots through Requires-Dist."""
    seen: set[str] = set()
    pending = list(roots)
    while pending:
        name = _normalise(pending.pop())
        if name in seen:
            continue
        seen.add(name)
        try:
            declared = requires(name) or []
        except PackageNotFoundError:
            continue
        for requirement in declared:
            match = REQUIREMENT_NAME.match(requirement.strip())
            if match:
                pending.append(match.group(0))
    return seen


def test_the_server_imports_nothing_outside_the_six_declared_packages() -> None:
    completed = subprocess.run(
        [sys.executable, "-c", RESOLVE_EVERY_HANDLER],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    observed = set(json.loads(completed.stdout))

    # Not a stdlib-only claim: the six must actually be there, or the check is
    # passing on a server that never imported its handlers.
    assert DECLARED_MODULES | {"aec"} <= observed

    allowed = _dependency_closure(_declared_roots()) | {_normalise(PROJECT)}
    owners = packages_distributions()
    unexpected = {
        module: sorted(set(owners.get(module, [])))
        for module in sorted(observed - NO_DISTRIBUTION)
        if not {_normalise(name) for name in owners.get(module, [])} & allowed
    }
    assert not unexpected, f"imports outside the declared packages: {unexpected}"
