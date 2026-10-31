---
name: piccompare-aec
description: Measure room and space changes across two floor plans and verify definitions before claiming changes. Use for architecture, engineering and construction (AEC) revision review with the PicCompare AEC MCP server or command-line tool.
---

# PicCompare AEC measurement skill

AEC means architecture, engineering and construction. This skill measures rooms
on two versions of a floor plan and refuses to claim a change when the two
versions define a room differently.

## When to use

Use this skill when a user asks whether two floor-plan revisions changed a room,
space or measured area, and when a simple picture comparison is not enough. The
skill refuses to compare elements whose definitions differ (for example, a room
split in two, or two rooms merged).

## Prerequisites

- Python 3.11 or newer, with this repository installed
  (`pip install -e ".[dev]"`).
- Prefer an assistant with this repository's MCP server configured: it starts
  with `python -m aec.mcp_server` and serves the same operations as tools (see
  `docs/MCP.md`). The commands below are the fallback when no server is
  available.
- A test-example folder containing `a.png`, `b.png`, `config.json`,
  `ground_truth.json` (the known correct answer) and `sam31.json` (recorded
  Segment Anything Model output).
- For live SAM/Muse runs: `META_API_KEY`, the exact model IDs and network access.
  The current public default workflow is deterministic (the same input always
  gives the same output) and offline.

## Workflow

1. Prefer the MCP server when it is available and the command line otherwise.
   With a server, call `aec.measure` with
   `{"fixture": "fixtures/aec/resize-01", "out": "runs/measure/resize-01"}`;
   without one, run
   `python -m aec measure --fixture fixtures/aec/resize-01 --out runs/measure/resize-01`.
2. Read `report.md` and `report.json`; check `findings`, `not_compared`
   (comparisons refused) and `evidence`. A tool result carries the same counts
   and the report path.
3. Verify with `aec.verify` and
   `{"report": "runs/measure/resize-01/report.json"}`; the server defaults the
   inputs folder to the one the report names. On the command line, run
   `python -m aec verify --report runs/measure/resize-01/report.json --inputs-dir fixtures/aec/resize-01`.
4. Export a measured overlay when requested: `aec.export` with
   `{"report": "runs/measure/resize-01/report.json", "format": "both", "out": "runs/export"}`,
   or `python -m aec export --report ... --out runs/export`.
5. If neither a server nor the command line is available, say that the check
   was not run. Never report a measurement you did not measure.

## Evidence

Every finding must cite element IDs and measurement references. The report
contains fingerprints (hashes) of the inputs, elements and measurements, plus a
replay digest (a fingerprint of the whole report). A definition mismatch is
reported as `not_compared`, never as a verified change. The report is
fingerprinted and replayable; it is never “signed”.

## Limitations

- Generated clean plans only in the current public workflow.
- No semantic CAD (computer-aided design) reconstruction; SVG and DXF are
  measured overlays (scalable vector graphics and drawing exchange format), not
  full CAD.
- The offline default makes no model call. A live SAM/Muse Spark run needs
  credentials and is documented in `docs/LIVE-RUN.md`; at the last run it left
  10 of 12 test pairs clean, missing the two label-only changes for want of OCR
  (text reading). SAM answers only box prompts on line art, so the regions are
  proposed from the plan geometry.
- No art authentication, map-making or land-surveying coordinate support.
