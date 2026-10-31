"""The Model Context Protocol server: newline-delimited JSON-RPC 2.0 on stdio.

One frame per line on stdin, one frame per line on stdout, and nothing else on
stdout - a log line there would corrupt the stream, so every log goes to stderr.
The process ends when stdin closes, with exit code 0; MCP has no ``shutdown``
method, so EOF is the only way out.

Methods: ``initialize``, ``notifications/initialized``, ``tools/list``,
``tools/call`` and ``ping``. The tool set and every published JSON Schema come
from :mod:`aec.tool_registry`; this module adds no tool of its own and re-types
no schema. It does add one thing the registry deliberately cannot: an explicit
adapter per tool, because two published argument names differ from the client's
parameters (``a``/``b`` against ``path_a``/``path_b``) and two differ from the
function's (``out`` against ``out_dir``). ``**arguments`` is never forwarded.

Errors follow JSON-RPC: an unknown method is ``-32601``, params that do not
match the published schema are ``-32602``, and a handler that raises is a tool
result with ``isError: true`` whose text is sanitized - no absolute path, no
secret from the environment. The one exception to "a frame without an id is
never answered" is a line that is not a JSON object at all: it is not a frame,
so it gets the ``-32700`` parse error the protocol requires, with a null id. A
well-formed frame that omits its id is a notification: handled silently if it is
one of ours, ignored otherwise, never answered.

The server speaks the 2025-06-18 revision of MCP - the initialize handshake and
the tools capability, no resources, prompts, sampling or tasks. A client that
asks for another supported revision gets that revision back; any other request
is answered with this one, as the protocol requires of a server that cannot
speak what was asked.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import sys
import types
from collections.abc import Callable
from pathlib import Path
from typing import Any, TextIO

from aec import __version__, tool_registry
from aec.client import PicCompareClient
from aec.engine import EngineNotFound, resolve_engine

SERVER_NAME = "piccompare-aec"
PROTOCOL_VERSION = "2025-06-18"
SUPPORTED_PROTOCOL_VERSIONS = (PROTOCOL_VERSION, "2025-03-26", "2024-11-05")
REPO_ROOT = Path(__file__).resolve().parents[2]
# The external engine keeps its own comparison state here; ``runs/`` is this
# repository's scratch area and is not tracked.
DEFAULT_PROFILE_DIR = REPO_ROOT / "runs" / "mcp" / "profile"

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

# Client-to-server notifications the protocol defines. They carry no id and
# never produce a frame, whatever the client puts in the frame.
NOTIFICATION_METHODS = frozenset(
    {
        "notifications/initialized",
        "notifications/cancelled",
        "notifications/roots/list_changed",
    }
)

# A path may contain spaces (``C:\Program Files\...``), so a path token ends at
# a quote or a newline, not at the first whitespace: stopping at a space would
# redact the head and send the rest of the path to the client.
_WINDOWS_PATH = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z]:[\\/][^\"'\r\n]*")
_UNC_PATH = re.compile(r"\\\\[^\"'\r\n]*")
_POSIX_PATH = re.compile(r"(?<![A-Za-z0-9_:./])/(?:[^\"'/\r\n]+/)*[^\"'\r\n]*")
# Only the key matters; the value is never printed anywhere by this repository.
_SECRET_ENV = ("META_API_KEY",)


class InvalidParams(ValueError):
    """Params that do not match the published contract; answered with -32602."""


class EngineUnavailable(RuntimeError):
    """No local PicCompare engine resolves, so an engine tool cannot run."""


def safe_message(text: str) -> str:
    """Make a message fit to send a client: no absolute path, no secret.

    Handler errors quote whatever the failing library put in them, and that can
    be an absolute path. The client needs to know what failed, not where this
    machine keeps its files.
    """
    cleaned = text
    for pattern in (_WINDOWS_PATH, _UNC_PATH, _POSIX_PATH):
        cleaned = pattern.sub("<path>", cleaned)
    for name in _SECRET_ENV:
        secret = os.environ.get(name, "")
        if secret:
            cleaned = cleaned.replace(secret, "<redacted>")
    return cleaned[:2000]


def _log(message: str) -> None:
    print(f"aec-mcp: {message}", file=sys.stderr, flush=True)


TOOLS_BY_NAME: dict[str, tool_registry.Tool] = {
    tool.name: tool for tool in tool_registry.TOOLS
}


def _object_params(params: Any, method: str) -> dict[str, Any]:
    if params is None:
        return {}
    if not isinstance(params, dict):
        raise InvalidParams(f"{method}: params must be an object")
    return params


def _check_value(tool: str, argument: str, schema: dict[str, Any], value: Any) -> None:
    kind = schema.get("type")
    if kind == "string":
        valid = isinstance(value, str)
    elif kind == "number":
        valid = isinstance(value, (int, float)) and not isinstance(value, bool)
    elif kind == "integer":
        valid = isinstance(value, int) and not isinstance(value, bool)
    elif kind == "boolean":
        valid = isinstance(value, bool)
    elif kind == "array":
        if not isinstance(value, list):
            raise InvalidParams(f"{tool}: {argument} must be an array")
        items = schema.get("items")
        if isinstance(items, dict):
            for item in value:
                _check_value(tool, f"{argument}[]", items, item)
        valid = True
    else:
        raise TypeError(f"{tool}: no check for schema type {kind!r} of {argument}")
    if not valid:
        raise InvalidParams(f"{tool}: {argument} must be {kind}")
    allowed = schema.get("enum")
    if isinstance(allowed, list) and value not in allowed:
        choices = ", ".join(str(choice) for choice in allowed)
        raise InvalidParams(f"{tool}: {argument} must be one of {choices}")


def _validate_arguments(
    tool: tool_registry.Tool, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Check a call against the schema this tool publishes, before any work.

    An argument the schema does not name is refused rather than dropped: a
    silently ignored ``cards`` flag would let a caller believe cards were
    written. A null value for an optional argument counts as omitted, which is
    how every handler in the registry treats it already.
    """
    schema = tool.json_schema
    properties: dict[str, Any] = schema["properties"]
    required: list[str] = schema["required"]
    unexpected = sorted(set(arguments) - set(properties))
    if unexpected:
        raise InvalidParams(f"{tool.name}: unknown argument(s) {', '.join(unexpected)}")
    given: dict[str, Any] = {}
    for key, value in arguments.items():
        if value is None:
            if key in required:
                raise InvalidParams(f"{tool.name}: {key} is required and cannot be null")
            continue
        _check_value(tool.name, key, properties[key], value)
        given[key] = value
    missing = [key for key in required if key not in given]
    if missing:
        raise InvalidParams(
            f"{tool.name}: missing required argument(s) {', '.join(missing)}"
        )
    return given


# One adapter per published tool. The handler half of the call comes from the
# registry; only the argument names are mapped here, because the published
# schema and the Python signature disagree in five places.
Adapter = Callable[[Callable[..., Any], dict[str, Any]], Any]


def _measure(handler: Callable[..., Any], arguments: dict[str, Any]) -> Any:
    return handler(arguments["fixture"], arguments.get("out"))


def _verify(handler: Callable[..., Any], arguments: dict[str, Any]) -> Any:
    # inputs_dir is optional: omitted, ops.verify uses the fixture directory the
    # report names for itself (fixtures/aec/<pair_id>) and fails closed when
    # that directory is not there.
    return handler(arguments["report"], arguments.get("inputs_dir"))


def _export(handler: Callable[..., Any], arguments: dict[str, Any]) -> Any:
    return handler(
        arguments["report"], format=arguments["format"], out=arguments["out"]
    )


def _engine_info(handler: Callable[..., Any], arguments: dict[str, Any]) -> Any:
    return handler(arguments.get("workspace_root"), arguments.get("engine_tree"))


def _batch(handler: Callable[..., Any], arguments: dict[str, Any]) -> Any:
    # run_batch(reports_dir, out_dir): the published names are shorter.
    return handler(arguments["reports"], arguments["out"])


def _eval(handler: Callable[..., Any], arguments: dict[str, Any]) -> Any:
    # run_eval(fixtures, out_dir, pairs, *, live). The documented default is
    # offline, so an omitted ``live`` means False rather than a schema refusal.
    return handler(
        arguments["fixtures"],
        arguments["out"],
        arguments.get("pairs"),
        live=arguments.get("live", False),
    )


def _compare_documents(handler: Callable[..., Any], arguments: dict[str, Any]) -> Any:
    # Published a/b; the client takes path_a/path_b.
    result = handler(
        arguments["a"],
        arguments["b"],
        dpi=arguments["dpi"],
        align=arguments["align"],
    )
    return result.data


def _regions(handler: Callable[..., Any], arguments: dict[str, Any]) -> Any:
    result = handler(
        arguments["comparison_id"],
        kind=arguments["kind"],
        limit=arguments["limit"],
    )
    return result.data


def _crop(handler: Callable[..., Any], arguments: dict[str, Any]) -> Any:
    result = handler(
        arguments["comparison_id"],
        arguments["region_id"],
        view=arguments["view"],
    )
    return result.data


def _page_image(handler: Callable[..., Any], arguments: dict[str, Any]) -> Any:
    result = handler(
        arguments["comparison_id"], arguments["side"], arguments["page"]
    )
    return result.data


def _export_report(handler: Callable[..., Any], arguments: dict[str, Any]) -> Any:
    result = handler(arguments["comparison_id"], format=arguments["format"])
    return result.data


def _align(handler: Callable[..., Any], arguments: dict[str, Any]) -> Any:
    # Published a/b; the client takes path_a/path_b.
    result = handler(
        arguments["a"],
        arguments["b"],
        page_a=arguments["page_a"],
        page_b=arguments["page_b"],
    )
    return result.data


TOOL_ADAPTERS: dict[str, Adapter] = {
    "aec.measure": _measure,
    "aec.verify": _verify,
    "aec.export": _export,
    "aec.engine_info": _engine_info,
    "aec.batch": _batch,
    "aec.eval": _eval,
    "piccompare.compare_documents": _compare_documents,
    "piccompare.get_regions": _regions,
    "piccompare.get_crop": _crop,
    "piccompare.get_page_image": _page_image,
    "piccompare.export_report": _export_report,
    "piccompare.align": _align,
}


def _engine_client() -> Any:
    """Build the external-engine client on first use, or refuse as a typed error."""
    try:
        reference = resolve_engine()
    except EngineNotFound as error:
        raise EngineUnavailable(
            "no PicCompare engine resolves on this machine; this repository is "
            "the integration only, so point the workspace at a local build "
            "(active-pair.json or tree-map.json) or set PICCOMPARE_DEMO=1"
        ) from error
    profile = os.environ.get("PICCOMPARE_MCP_PROFILE") or str(DEFAULT_PROFILE_DIR)
    return PicCompareClient(reference, profile_dir=profile)


def _error(identifier: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": identifier,
        "error": {"code": code, "message": safe_message(message)},
    }


def _render(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True)


class Server:
    """One protocol session: frames in, responses out, no state but the engine."""

    def __init__(self) -> None:
        self._client: Any = None
        self._methods: dict[str, Callable[[Any], dict[str, Any]]] = {
            "initialize": self._initialize,
            "ping": self._ping,
            "tools/list": self._tools_list,
            "tools/call": self._tools_call,
        }

    def handle(self, line: str) -> dict[str, Any] | None:
        """Answer one line, or return None when there is nothing to answer."""
        try:
            request = json.loads(line)
        except ValueError:
            _log("refused a line that is not JSON")
            return _error(None, PARSE_ERROR, "parse error: the line is not JSON")
        if not isinstance(request, dict):
            _log("refused a frame that is not a JSON object")
            return _error(
                None, INVALID_REQUEST, "invalid request: a frame is a JSON object"
            )

        identifier = request.get("id")
        if (
            "id" in request
            and identifier is not None
            and not isinstance(identifier, (str, int))
        ):
            return _error(
                None, INVALID_REQUEST, "invalid request: id must be a string or a number"
            )
        has_id = identifier is not None

        method = request.get("method")
        if isinstance(method, str) and method in NOTIFICATION_METHODS:
            _log(f"notification {method}")
            return None
        if not has_id:
            # No id to answer to: run nothing, say nothing.
            _log(f"ignored {method!r} without an id")
            return None
        if request.get("jsonrpc") != "2.0":
            return _error(
                identifier, INVALID_REQUEST, 'invalid request: jsonrpc must be "2.0"'
            )
        if not isinstance(method, str) or not method:
            return _error(identifier, INVALID_REQUEST, "invalid request: no method")

        handler = self._methods.get(method)
        if handler is None:
            return _error(identifier, METHOD_NOT_FOUND, f"method not found: {method}")
        try:
            result = handler(request.get("params"))
        except InvalidParams as error:
            return _error(identifier, INVALID_PARAMS, str(error))
        return {"jsonrpc": "2.0", "id": identifier, "result": result}

    def _initialize(self, params: Any) -> dict[str, Any]:
        values = _object_params(params, "initialize")
        requested = values.get("protocolVersion")
        version = (
            requested
            if isinstance(requested, str)
            and requested in SUPPORTED_PROTOCOL_VERSIONS
            else PROTOCOL_VERSION
        )
        return {
            "protocolVersion": version,
            "serverInfo": {"name": SERVER_NAME, "version": __version__},
            "capabilities": {"tools": {"listChanged": False}},
        }

    def _ping(self, params: Any) -> dict[str, Any]:
        _object_params(params, "ping")
        return {}

    def _tools_list(self, params: Any) -> dict[str, Any]:
        _object_params(params, "tools/list")
        return {"tools": tool_registry.tools_list()}

    def _tools_call(self, params: Any) -> dict[str, Any]:
        values = _object_params(params, "tools/call")
        name = values.get("name")
        if not isinstance(name, str) or not name:
            raise InvalidParams("tools/call needs a string name")
        tool = TOOLS_BY_NAME.get(name)
        if tool is None:
            raise InvalidParams(f"unknown tool: {name}")
        raw = values.get("arguments")
        if raw is None:
            raw = {}
        if not isinstance(raw, dict):
            raise InvalidParams(f"{name}: arguments must be an object")
        arguments = _validate_arguments(tool, raw)
        try:
            payload = self._invoke(tool, arguments)
        except Exception as error:  # noqa: BLE001 - a tool failure is a result
            message = safe_message(
                f"{name} failed ({type(error).__name__}): {error}"
            )
            _log(message)
            return {"content": [{"type": "text", "text": message}], "isError": True}
        return {
            "content": [{"type": "text", "text": _render(payload)}],
            "isError": False,
        }

    def _invoke(
        self, tool: tool_registry.Tool, arguments: dict[str, Any]
    ) -> Any:
        handler = tool.handler.resolve()
        if tool.transport == "engine-cli":
            # The registry names an unbound method; bind the engine client to it.
            handler = types.MethodType(handler, self._engine())
        adapter = TOOL_ADAPTERS[tool.name]
        # A tool must not be able to reach the protocol stream: anything it
        # prints goes to stderr, where the logs live.
        with contextlib.redirect_stdout(sys.stderr):
            return adapter(handler, arguments)

    def _engine(self) -> Any:
        if self._client is None:
            self._client = _engine_client()
        return self._client


def serve(stdin: TextIO, stdout: TextIO) -> int:
    """Serve frames until stdin reaches EOF; return the process exit code."""
    server = Server()
    _log(f"ready on stdin/stdout with {len(tool_registry.TOOLS)} tools")
    for line in stdin:
        text = line.strip()
        if not text:
            continue
        try:
            response = server.handle(text)
        except Exception as error:  # noqa: BLE001 - one bad frame must not end the session
            _log(f"internal error: {type(error).__name__}")
            response = _error(None, INTERNAL_ERROR, "internal error")
        if response is not None:
            stdout.write(json.dumps(response, ensure_ascii=True) + "\n")
            stdout.flush()
    _log("stdin closed; exiting")
    return 0


def _use_utf8() -> None:
    """MCP frames are UTF-8; make the console streams agree on any code page."""
    for stream in (sys.stdin, sys.stdout):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="aec-mcp",
        description="Serve the published AEC tools over MCP on stdin and stdout.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.parse_args(argv)
    _use_utf8()
    try:
        return serve(sys.stdin, sys.stdout)
    except BrokenPipeError:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
