"""Drive the MCP server the way a client drives it: a real subprocess over pipes.

The first half of this file is the behavioural contract: each test writes frames
to the child's stdin and reads frames from its stdout, so a regression in
framing, id matching, stdout purity or the EOF exit is what those tests catch.
No handler is imported and called directly to stand in for the server.

The second half covers the pure layers a pipe test cannot reach on its own:
argument validation, the twelve name mappings (against a recording stub, not a
real handler), message sanitizing and the framing branches that need a frame a
polite client would never send. pytest-cov cannot trace the child process, so
without these the module would look almost untested.
"""

from __future__ import annotations

import io
import json
import os
import queue
import re
import subprocess
import sys
import threading
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from aec import __version__, mcp_server, tool_registry
from aec.mcp_server import (
    INVALID_PARAMS,
    INVALID_REQUEST,
    PARSE_ERROR,
    EngineUnavailable,
    InvalidParams,
    _engine_client,
    _validate_arguments,
    safe_message,
    serve,
)

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = "fixtures/aec/resize-01"
SAMPLE_REPORT = "demo/sample-report.json"
PROTOCOL = "2025-06-18"
FRAME_TIMEOUT = 5.0
CALL_TIMEOUT = 10.0
# A Windows drive path or a UNC path: what a handler error must never leak.
# The lookbehind keeps the ``s:/`` of an ``https://`` URL out of the match.
ABSOLUTE_PATH = re.compile(r"(?<![A-Za-z0-9_])(?:[A-Za-z]:[\\/]|\\\\)\S*")


class Server:
    """One ``python -m aec.mcp_server`` process with draining reader threads.

    A blocked ``readline`` cannot be given a timeout on Windows, so a thread
    drains stdout into a queue and the tests take from it with a deadline. The
    stderr drain exists so a noisy handler can never fill a pipe and stall.
    """

    def __init__(self, environment: dict[str, str] | None = None) -> None:
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env.update(environment or {})
        self.process = subprocess.Popen(
            [sys.executable, "-m", "aec.mcp_server"],
            cwd=ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
            env=env,
        )
        self.frames: list[dict[str, Any]] = []
        self._stdout: queue.Queue[str] = queue.Queue()
        self._stderr: list[str] = []
        self._next_id = 0
        self._threads = [
            threading.Thread(target=self._read_stdout, daemon=True),
            threading.Thread(target=self._read_stderr, daemon=True),
        ]
        for thread in self._threads:
            thread.start()

    def _read_stdout(self) -> None:
        assert self.process.stdout is not None
        for line in self.process.stdout:
            self._stdout.put(line)
        self._stdout.put("")

    def _read_stderr(self) -> None:
        assert self.process.stderr is not None
        for line in self.process.stderr:
            self._stderr.append(line)

    def stderr(self) -> str:
        if self.process.poll() is not None:
            for thread in self._threads:
                thread.join(timeout=FRAME_TIMEOUT)
        return "".join(self._stderr)

    def send(self, frame: dict[str, Any]) -> None:
        assert self.process.stdin is not None
        self.process.stdin.write(json.dumps(frame, ensure_ascii=True) + "\n")
        self.process.stdin.flush()

    def send_raw(self, line: str) -> None:
        assert self.process.stdin is not None
        self.process.stdin.write(line + "\n")
        self.process.stdin.flush()

    def receive(self, timeout: float = FRAME_TIMEOUT) -> dict[str, Any]:
        try:
            line = self._stdout.get(timeout=timeout)
        except queue.Empty:
            raise AssertionError(
                f"no frame within {timeout}s; stderr:\n{self.stderr()}"
            ) from None
        assert line.strip(), (
            f"the server closed stdout without an answer; stderr:\n{self.stderr()}"
        )
        try:
            frame = json.loads(line)
        except ValueError:
            raise AssertionError(
                f"stdout carried a line that is not a protocol frame: {line!r}"
            ) from None
        assert frame["jsonrpc"] == "2.0", frame
        self.frames.append(frame)
        return frame

    def request(
        self, method: str, params: Any = None, timeout: float = FRAME_TIMEOUT
    ) -> dict[str, Any]:
        self._next_id += 1
        identifier = self._next_id
        frame: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": identifier,
            "method": method,
        }
        if params is not None:
            frame["params"] = params
        self.send(frame)
        response = self.receive(timeout)
        assert response.get("id") == identifier, f"answer to another frame: {response}"
        return response

    def call(
        self, name: str, arguments: dict[str, Any], timeout: float = CALL_TIMEOUT
    ) -> dict[str, Any]:
        return self.request(
            "tools/call", {"name": name, "arguments": arguments}, timeout
        )

    def payload(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        response = self.call(name, arguments)
        assert "error" not in response, response
        result = response["result"]
        assert result["isError"] is False, result
        block = result["content"][0]
        assert block["type"] == "text"
        return json.loads(block["text"])

    def close(self) -> int:
        if self.process.poll() is None:
            try:
                if self.process.stdin is not None:
                    self.process.stdin.close()
            except OSError:
                pass
        code = self.process.wait(timeout=CALL_TIMEOUT)
        for thread in self._threads:
            thread.join(timeout=FRAME_TIMEOUT)
        return code

    def stop(self) -> None:
        if self.process.poll() is None:
            self.process.kill()
            self.process.wait(timeout=CALL_TIMEOUT)
        for thread in self._threads:
            thread.join(timeout=FRAME_TIMEOUT)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            if stream is not None and not stream.closed:
                stream.close()


@pytest.fixture()
def server() -> Iterator[Server]:
    instance = Server()
    try:
        yield instance
    finally:
        instance.stop()


@pytest.fixture()
def ready(server: Server) -> Server:
    """A handshaken session, as a real client opens one."""
    server.request(
        "initialize",
        {
            "protocolVersion": PROTOCOL,
            "capabilities": {},
            "clientInfo": {"name": "pytest", "version": "0"},
        },
    )
    server.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
    return server


def test_initialize_answers_with_identity_and_tool_capability(server: Server) -> None:
    response = server.request(
        "initialize",
        {
            "protocolVersion": PROTOCOL,
            "capabilities": {},
            "clientInfo": {"name": "pytest", "version": "0"},
        },
    )
    result = response["result"]
    assert result["protocolVersion"] == PROTOCOL
    assert result["serverInfo"] == {"name": "piccompare-aec", "version": __version__}
    assert result["capabilities"] == {"tools": {"listChanged": False}}


def test_initialize_answers_an_unknown_protocol_version_with_a_supported_one(
    server: Server,
) -> None:
    response = server.request("initialize", {"protocolVersion": "1999-01-01"})
    assert response["result"]["protocolVersion"] == PROTOCOL


def test_initialized_notification_gets_no_frame(server: Server) -> None:
    # Two notifications, then a request: if either notification produced a frame
    # the request below would read it and fail the id match.
    server.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
    server.send({"jsonrpc": "2.0", "method": "notifications/not_one_of_ours"})
    response = server.request("ping")
    assert response["result"] == {}


def test_tools_list_publishes_the_registry_schemas(ready: Server) -> None:
    response = ready.request("tools/list")
    tools = response["result"]["tools"]
    assert [tool["name"] for tool in tools] == [
        tool.name for tool in tool_registry.TOOLS
    ]
    # Same entries, not a re-typed copy: the derived camelCase schema included.
    assert tools == tool_registry.tools_list()
    assert all(set(tool) == {"name", "description", "inputSchema"} for tool in tools)


def test_tools_call_verify_accepts_the_committed_sample_report(ready: Server) -> None:
    # No inputs_dir is sent: the documented default is the fixture directory the
    # report names for itself, and this report names resize-01.
    payload = ready.payload("aec.verify", {"report": SAMPLE_REPORT})
    assert payload == {"ok": True, "reasons": []}


def test_tools_call_measure_writes_a_report_that_verifies(
    ready: Server, tmp_path: Path
) -> None:
    out = tmp_path / "measure"
    payload = ready.payload(
        "aec.measure", {"fixture": FIXTURE, "out": str(out)}
    )
    assert payload["pair_id"] == "resize-01"
    assert payload["verified"] >= 1
    assert payload["report"] == str(out / "report.json")
    assert (out / "report.json").is_file()
    assert ready.payload("aec.verify", {"report": payload["report"]})["ok"] is True


def test_tools_call_eval_runs_offline_and_scores_the_fixture(
    ready: Server, tmp_path: Path
) -> None:
    # The published arguments are strings, and run_eval's first use is
    # ``fixtures / "aec"``: a str has no ``/``, so this call used to come back
    # as an unsupported-operand TypeError instead of a score.
    out = tmp_path / "eval"
    response = ready.call(
        "aec.eval",
        {
            "fixtures": "fixtures",
            "out": str(out),
            "pairs": ["resize-01"],
            "live": False,
        },
    )
    result = response["result"]
    assert result["isError"] is False, result
    metrics = json.loads(result["content"][0]["text"])
    assert metrics["mode"] == "offline_deterministic"
    assert metrics["totals"]["pairs"] == 1
    assert metrics["totals"]["pairs_passed"] == 1
    assert metrics["totals"]["false_positives"] == 0
    assert (out / "metrics.json").is_file()


def test_an_unknown_tool_is_an_invalid_params_error(ready: Server) -> None:
    response = ready.call("aec.nope", {})
    assert response["error"]["code"] == -32602
    assert "unknown tool" in response["error"]["message"]


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("aec.measure", {"out": "runs/x"}),
        ("aec.measure", {"fixture": 7}),
        # R-10: cards are a CLI-only flag, so the published contract refuses one.
        ("aec.measure", {"fixture": FIXTURE, "cards": True}),
        ("aec.export", {"report": "r.json", "format": "pdf", "out": "runs"}),
        ("aec.verify", {"report": None}),
        ("aec.eval", {"fixtures": "fixtures", "out": "runs/eval", "live": "yes"}),
    ],
    ids=[
        "missing-required",
        "wrong-type",
        "unknown-argument",
        "outside-enum",
        "null-required",
        "wrong-boolean",
    ],
)
def test_arguments_that_do_not_match_the_schema_are_invalid_params(
    ready: Server, name: str, arguments: dict[str, Any]
) -> None:
    response = ready.call(name, arguments)
    assert response["error"]["code"] == -32602, response
    assert "error" not in response.get("result", {})


def test_a_failing_handler_is_a_result_error_without_an_absolute_path(
    ready: Server, tmp_path: Path
) -> None:
    missing = tmp_path / "not-a-fixture"
    response = ready.call("aec.measure", {"fixture": str(missing)})
    result = response["result"]
    assert result["isError"] is True
    text = result["content"][0]["text"]
    assert "aec.measure failed" in text and "FileNotFoundError" in text
    assert str(missing) not in text
    assert ABSOLUTE_PATH.search(text) is None, text


def test_an_engine_tool_without_a_local_engine_is_a_typed_result_error(
    tmp_path: Path,
) -> None:
    # An empty workspace root: no active-pair.json, no tree-map.json, so the
    # engine cannot resolve and the tool must refuse with a readable message.
    instance = Server(
        {"PICCOMPARE_WORKSPACE": str(tmp_path), "PICCOMPARE_DEMO": ""}
    )
    try:
        response = instance.call(
            "piccompare.align",
            {"a": "a.pdf", "b": "b.pdf", "page_a": 0, "page_b": 0},
        )
        result = response["result"]
        assert result["isError"] is True
        text = result["content"][0]["text"]
        assert "no PicCompare engine resolves" in text
        assert ABSOLUTE_PATH.search(text) is None, text
    finally:
        instance.stop()


def test_an_unknown_method_is_a_method_not_found_error(server: Server) -> None:
    # There is no shutdown method in MCP; EOF is the only way out.
    for method in ("shutdown", "resources/list"):
        response = server.request(method)
        assert response["error"]["code"] == -32601, response
        assert "method not found" in response["error"]["message"]


def test_a_line_that_is_not_json_is_a_parse_error(server: Server) -> None:
    server.send_raw("this is not a frame")
    response = server.receive()
    assert response["id"] is None
    assert response["error"]["code"] == -32700
    # The session survives a garbled line.
    assert server.request("ping")["result"] == {}


def test_closing_stdin_ends_the_process_with_exit_zero(server: Server) -> None:
    assert server.request("ping")["result"] == {}
    assert server.close() == 0


def test_logs_go_to_stderr_and_stdout_carries_frames_only(server: Server) -> None:
    assert server.request("ping")["result"] == {}
    assert server.close() == 0
    # One frame read, so the startup line was not on stdout; it is on stderr.
    assert len(server.frames) == 1
    assert "aec-mcp" in server.stderr()


def test_every_published_tool_has_an_explicit_argument_mapping() -> None:
    # A new registry entry must not fall through to a blind **arguments call.
    from aec.mcp_server import TOOL_ADAPTERS

    assert set(TOOL_ADAPTERS) == {tool.name for tool in tool_registry.TOOLS}


# --- the pure layers: validation, name mapping, sanitizing, framing --------


class Recorder:
    """A stand-in handler: records the call, returns a payload with ``data``.

    The engine adapters unwrap ``ToolResult.data``, so the stub has to carry the
    same attribute; it is never a real client or a real handler.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append((args, kwargs))
        return SimpleNamespace(data={"recorded": True})


def test_local_adapters_map_published_names_onto_the_signatures() -> None:
    handler = Recorder()
    adapters = mcp_server.TOOL_ADAPTERS
    adapters["aec.measure"](handler, {"fixture": "f"})
    assert handler.calls[-1] == (("f", None), {})
    adapters["aec.measure"](handler, {"fixture": "f", "out": "o"})
    assert handler.calls[-1] == (("f", "o"), {})
    adapters["aec.verify"](handler, {"report": "r"})
    assert handler.calls[-1] == (("r", None), {})
    adapters["aec.verify"](handler, {"report": "r", "inputs_dir": "d"})
    assert handler.calls[-1] == (("r", "d"), {})
    adapters["aec.export"](handler, {"report": "r", "format": "svg", "out": "o"})
    assert handler.calls[-1] == (("r",), {"format": "svg", "out": "o"})
    adapters["aec.engine_info"](handler, {})
    assert handler.calls[-1] == ((None, None), {})
    adapters["aec.batch"](handler, {"reports": "rs", "out": "o"})
    assert handler.calls[-1] == (("rs", "o"), {})
    adapters["aec.eval"](handler, {"fixtures": "fx", "out": "o", "live": True})
    assert handler.calls[-1] == (("fx", "o", None), {"live": True})
    adapters["aec.eval"](
        handler, {"fixtures": "fx", "out": "o", "pairs": ["p"], "live": False}
    )
    assert handler.calls[-1] == (("fx", "o", ["p"]), {"live": False})


def test_engine_adapters_rename_a_and_b_and_unwrap_the_result() -> None:
    handler = Recorder()
    adapters = mcp_server.TOOL_ADAPTERS
    assert adapters["piccompare.compare_documents"](
        handler, {"a": "A", "b": "B", "dpi": 110, "align": "none"}
    ) == {"recorded": True}
    assert handler.calls[-1] == (("A", "B"), {"dpi": 110, "align": "none"})
    assert adapters["piccompare.align"](
        handler, {"a": "A", "b": "B", "page_a": 0, "page_b": 1}
    ) == {"recorded": True}
    assert handler.calls[-1] == (("A", "B"), {"page_a": 0, "page_b": 1})
    adapters["piccompare.get_regions"](
        handler, {"comparison_id": "c", "kind": "all", "limit": 5}
    )
    assert handler.calls[-1] == (("c",), {"kind": "all", "limit": 5})
    adapters["piccompare.get_crop"](
        handler, {"comparison_id": "c", "region_id": "r", "view": "diff"}
    )
    assert handler.calls[-1] == (("c", "r"), {"view": "diff"})
    adapters["piccompare.get_page_image"](
        handler, {"comparison_id": "c", "side": "a", "page": 2}
    )
    assert handler.calls[-1] == (("c", "a", 2), {})
    adapters["piccompare.export_report"](
        handler, {"comparison_id": "c", "format": "md"}
    )
    assert handler.calls[-1] == (("c",), {"format": "md"})


def test_validation_accepts_the_schema_and_nulls_optional_arguments() -> None:
    measure = mcp_server.TOOLS_BY_NAME["aec.measure"]
    assert _validate_arguments(measure, {"fixture": "f"}) == {"fixture": "f"}
    # Null for an optional argument is the same as leaving it out.
    assert _validate_arguments(measure, {"fixture": "f", "out": None}) == {
        "fixture": "f"
    }


@pytest.mark.parametrize(
    ("name", "arguments", "message"),
    [
        ("aec.measure", {}, "missing required argument"),
        ("aec.measure", {"fixture": None}, "required and cannot be null"),
        ("aec.measure", {"fixture": 3}, "fixture must be string"),
        ("aec.measure", {"fixture": "f", "cards": True}, "unknown argument"),
        (
            "aec.export",
            {"report": "r", "format": "pdf", "out": "o"},
            "must be one of svg, dxf, both",
        ),
        (
            "aec.eval",
            {"fixtures": "f", "out": "o", "pairs": "p", "live": False},
            "pairs must be an array",
        ),
        (
            "aec.eval",
            {"fixtures": "f", "out": "o", "pairs": ["p", 2], "live": False},
            r"pairs\[\] must be string",
        ),
        (
            "aec.eval",
            {"fixtures": "f", "out": "o", "live": 0},
            "live must be boolean",
        ),
        (
            "piccompare.align",
            {"a": "A", "b": "B", "page_a": True, "page_b": 0},
            "page_a must be integer",
        ),
    ],
)
def test_validation_refuses_every_mismatch(
    name: str, arguments: dict[str, Any], message: str
) -> None:
    with pytest.raises(InvalidParams, match=message):
        _validate_arguments(mcp_server.TOOLS_BY_NAME[name], arguments)


def test_a_schema_type_with_no_check_fails_loudly() -> None:
    with pytest.raises(TypeError, match="no check for schema type"):
        mcp_server._check_value("t", "x", {"type": "object"}, {})


def test_safe_message_strips_absolute_paths_and_env_secrets(monkeypatch) -> None:
    monkeypatch.setenv("META_API_KEY", "sk-live-very-secret")
    text = safe_message(
        "failed: C:\\Users\\someone\\plan.json, \\\\server\\share\\x, "
        "/home/someone/y, key sk-live-very-secret"
    )
    assert "C:" not in text and "server\\share" not in text and "/home" not in text
    assert "sk-live-very-secret" not in text
    assert "failed: <path>" in text
    assert len(safe_message("x" * 5000)) == 2000


def test_safe_message_leaves_a_url_alone() -> None:
    # A protocol version or documentation link must survive the path patterns.
    url = "https://modelcontextprotocol.io/specification/2025-06-18"
    assert safe_message(f"see {url}") == f"see {url}"


@pytest.mark.parametrize(
    ("line", "code"),
    [
        ("{not json", PARSE_ERROR),
        ("[1, 2]", INVALID_REQUEST),
        ('{"jsonrpc":"2.0","id":1}', INVALID_REQUEST),
        ('{"jsonrpc":"1.0","id":1,"method":"ping"}', INVALID_REQUEST),
        ('{"jsonrpc":"2.0","id":{},"method":"ping"}', INVALID_REQUEST),
        ('{"jsonrpc":"2.0","id":1,"method":"ping","params":[]}', INVALID_PARAMS),
        (
            '{"jsonrpc":"2.0","id":1,"method":"initialize","params":[]}',
            INVALID_PARAMS,
        ),
        ('{"jsonrpc":"2.0","id":1,"method":"tools/list","params":[]}', INVALID_PARAMS),
        ('{"jsonrpc":"2.0","id":1,"method":"tools/call","params":[]}', INVALID_PARAMS),
        ('{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{}}', INVALID_PARAMS),
        (
            '{"jsonrpc":"2.0","id":1,"method":"tools/call",'
            '"params":{"name":"aec.measure","arguments":[]}}',
            INVALID_PARAMS,
        ),
    ],
)
def test_handle_answers_malformed_requests_with_the_right_code(
    line: str, code: int
) -> None:
    response = mcp_server.Server().handle(line)
    assert response is not None
    assert response["error"]["code"] == code, response


def test_handle_never_answers_a_frame_without_an_id() -> None:
    server = mcp_server.Server()
    for line in (
        '{"jsonrpc":"2.0","method":"notifications/initialized"}',
        '{"jsonrpc":"2.0","method":"aec/unknown"}',
        '{"jsonrpc":"2.0","id":null,"method":"ping"}',
    ):
        assert server.handle(line) is None


def test_engine_client_refuses_without_a_resolvable_engine(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("PICCOMPARE_WORKSPACE", str(tmp_path))
    monkeypatch.delenv("PICCOMPARE_DEMO", raising=False)
    with pytest.raises(EngineUnavailable, match="no PicCompare engine resolves"):
        _engine_client()


def test_serve_answers_every_frame_until_eof() -> None:
    stdin = io.StringIO('{"jsonrpc":"2.0","id":1,"method":"ping"}\n\n')
    stdout = io.StringIO()
    assert serve(stdin, stdout) == 0
    frames = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert frames == [{"jsonrpc": "2.0", "id": 1, "result": {}}]


def test_main_prints_the_version_and_exits_zero(capsys) -> None:
    with pytest.raises(SystemExit) as exit_info:
        mcp_server.main(["--version"])
    assert exit_info.value.code == 0
    assert __version__ in capsys.readouterr().out
