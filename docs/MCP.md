# Calling the AEC tools from an AI assistant

This page explains how an AI assistant calls the tools in this repository
directly, instead of typing terminal commands. MCP (the Model Context Protocol)
is the standard an assistant uses to start a local program and call the tools it
publishes. The program is `aec.mcp_server`; it speaks JSON-RPC 2.0 (a plain-text
request and response format) on standard input and standard output, one message
per line, and logs to standard error only.

The same operations remain available on the command line. The server and
`python -m aec` call one shared set of functions, so a result cannot differ
between the two paths.

## Install

One line, from a clone of this repository (the virtual environment itself is the
first step of the [Quick start](../README.md#quick-start)):

```bash
.venv-aec/Scripts/python.exe -m pip install -e .
```

This installs two commands: `aec` for the terminal and `aec-mcp` for the
server. Nothing else is installed: the server adds no dependency.

## Start the server

```bash
python -m aec.mcp_server
```

Run it this way in a client configuration (the module form works without the
console script being on the search path). Do not type into it: it reads protocol
frames, not commands. Closing its input ends it, with exit code 0; there is no
`shutdown` method in MCP.

## Client configuration

Claude Desktop keeps its servers in `claude_desktop_config.json`. Add this entry
and restart the application:

```json
{
  "mcpServers": {
    "piccompare-aec": {
      "command": "python",
      "args": ["-m", "aec.mcp_server"]
    }
  }
}
```

Qoder accepts the same shape in the MCP servers section of its settings:

```json
{
  "mcpServers": {
    "piccompare-aec": {
      "command": "python",
      "args": ["-m", "aec.mcp_server"]
    }
  }
}
```

`command: python` means the interpreter that has this package installed. On
Windows with the repository's environment that is
`<repository>\.venv-aec\Scripts\python.exe`, so use that full path when `python`
on the search path is a different interpreter. If the client starts the server
from another directory, give absolute paths to the plans, reports and output
folders in the tool arguments.

## Tools

Twelve tools are published. The argument names below are the ones the protocol
publishes; the input schema for each tool, including which arguments are
required, is returned by `tools/list`, and a call that does not match it is
refused before any work starts.

| Tool | Arguments | What it does |
|---|---|---|
| `aec.measure` | `fixture`, `out` (optional) | Measure one plan pair and write a fingerprinted report under `out`. Without `out` nothing is written and only the counts are returned. |
| `aec.verify` | `report`, `inputs_dir` (optional) | Re-check a report from its stored fingerprints. `inputs_dir` defaults to `fixtures/aec/<pair_id>`, the folder the report names for itself; when that folder is absent the check fails closed rather than certifying inputs it never read. |
| `aec.export` | `report`, `format` (`svg`, `dxf` or `both`), `out` | Write the measured rooms as an overlay under `out`. |
| `aec.engine_info` | `workspace_root`, `engine_tree` (both optional) | Report which local PicCompare build resolves and whether its interpreter and command file exist. |
| `aec.batch` | `reports`, `out` | Combine the per-pair reports under `reports` into `summary.json` and `summary.md` under `out`, sorted by materiality. |
| `aec.eval` | `fixtures`, `out`, `pairs` (optional list), `live` (optional, default `false`) | Run the fixture evaluation and write `metrics.json` under `out`. Omitting `live`, or sending `false`, is the offline default, which makes no model call. |
| `piccompare.compare_documents` | `a`, `b`, `dpi`, `align` | External engine: compare two documents and return a comparison id. |
| `piccompare.get_regions` | `comparison_id`, `kind`, `limit` | External engine: changed regions with page size and position. |
| `piccompare.get_crop` | `comparison_id`, `region_id`, `view` | External engine: a cropped image of one changed region. |
| `piccompare.get_page_image` | `comparison_id`, `side` (`a` or `b`), `page` | External engine: one rendered page. |
| `piccompare.export_report` | `comparison_id`, `format` | External engine: the engine's own report file. |
| `piccompare.align` | `a`, `b`, `page_a`, `page_b` | External engine: the alignment mapping between two pages. |

A successful call returns a result whose `content[0].text` is the JSON payload
the equivalent command-line operation would print. A failing call returns
`isError: true` with a one-line reason in the same place.

## A session by hand

A short session proves the wiring without a client. Each input line below is one
frame; the three response lines are what the server writes back.

```bash
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"shell","version":"0"}}}' \
  '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"aec.verify","arguments":{"report":"demo/sample-report.json"}}}' \
  '{"jsonrpc":"2.0","id":3,"method":"ping"}' \
  | python -m aec.mcp_server
```

The second frame is a notification (no `id`), so it produces no response. The
fourth returns `{}`. The third answers with the verification result:

```json
{"jsonrpc": "2.0", "id": 2, "result": {"content": [{"type": "text", "text": "{\n  \"ok\": true,\n  \"reasons\": []\n}"}], "isError": false}}
```

Run the same frames with `demo/sample-report.json` replaced by a report you
measured yourself, and the answer is recomputed from that report's fingerprints.

## Safety model

- **Local, standard input and output only.** The server opens no network port
  and needs no credentials for the offline workflow. It runs with your user
  account's file access, so configure it only in a client you trust.
- **Read-only tools:** `aec.verify`, `aec.engine_info`, `piccompare.get_regions`
  and `piccompare.align` only read and compute. The other eight write.
- **Writes name their directory, or use the profile.** The local tools that
  write files take an explicit `out` and create their files under it
  (`aec.measure` writes nothing when `out` is omitted); nothing is written to
  the repository unless the caller names a folder inside it. The six
  `piccompare.*` tools take no `out`: `piccompare.compare_documents` records
  its comparison state in the external engine's profile directory, and
  `piccompare.get_crop`, `piccompare.get_page_image` and
  `piccompare.export_report` write their image and report files there too. The
  profile is `runs/mcp/profile`; set `PICCOMPARE_MCP_PROFILE` to move it.
- **The external engine is optional.** `aec.measure`, `aec.verify`, `aec.export`,
  `aec.engine_info`, `aec.batch` and `aec.eval` work on their own. The six
  engine tools refuse with a typed error when no local PicCompare build
  resolves, and `aec.engine_info` explains what was found.
- **Errors are sanitized.** A handler failure comes back as text with absolute
  paths removed and any `META_API_KEY` value redacted. No key, path or secret is
  ever written into a protocol error.
- **One frame per line on standard output.** Logs go to standard error, so a
  client never reads a log line as a response.

## Limits

- `aec.measure` cannot request evidence cards over MCP: the published schema has
  no card flag, and adding one would change a contract the manifest freezes.
  Cards are a command-line feature (`aec measure --cards`); when a report has
  them, they are in the report the call returns.
- `aec.eval` with `live: true` needs `META_API_KEY` and `META_MODEL_ID` and makes
  network calls; see [LIVE-RUN.md](LIVE-RUN.md). The default is offline.
- The tool list is fixed: the server advertises no resources, prompts, sampling
  or tasks, and `listChanged` is false.
- The server speaks the 2025-06-18 revision of MCP. A client that asks for
  another revision it does not support is answered with this one, as the
  protocol requires.
- An argument the schema does not name is refused rather than ignored, so a
  misspelled flag fails loudly instead of silently doing less.
