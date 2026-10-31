# Architecture

This page explains how the public code is organised. It is written for people who
want to read or audit the code; the [README](../README.md) explains the product in
plain terms.

The repository is the public half of a floor-plan revision checker: it measures
rooms on two versions of a plan, checks whether the same room is defined the same
way, and writes a report that can be re-run.

## Boundary

The public repository is the open-source integration layer (MIT licence: a
permissive open-source licence). The PicCompare engine is an external, separately
licensed dependency. No engine source
is imported, copied or published. The engine is found at run time and called
through its documented command-line interface (CLI: the text commands a program
can run).

## Components

| Component | File | Role |
|---|---|---|
| Data contracts | `src/aec/models.py` | the validated records passed between stages (plan, element, finding, evidence card, report); no engine types |
| Engine resolver | `src/aec/engine.py` | explicit folder → environment switch (`PICCOMPARE_DEMO=1`) or `tree-map.json` → `active-pair.json`; no hard-coded folder |
| Engine client | `src/aec/client.py` | one separate program run per documented command; JSON (plain-text data) responses; typed failures |
| Region proposer | `src/aec/propose.py` | model-free candidate rectangles: threshold the dark strokes, close the gaps, keep the enclosed paper regions; a box only tells SAM where to look |
| SAM client | `src/aec/sam.py` | Segment Anything Model 3.1 client; its network connection can be replaced in tests |
| SAM adapter | `src/aec/sam_adapter.py` | model response → `SamObject` (a validated data record) |
| Mask adapter | `src/aec/masks.py` | binary mask → closed polygon (an outline made of straight edges) |
| Geometry/scale | `src/aec/geometry.py`, `scale.py` | area, line segments, angles, centre point, overlap score (IoU), real-world units |
| Elements | `src/aec/elements.py` | measured rooms, spaces and walls from SAM objects |
| Correspondence | `src/aec/correspondence.py` | matched / ambiguous / definition mismatch / unmatched |
| Comparison | `src/aec/compare.py` | comparable measurements and candidate findings |
| Meta client | `src/aec/meta.py` | client for Meta's model service (its interface follows the widely used OpenAI chat format) |
| Planner/critic | `src/aec/planner.py`, `critic.py` | brief → PlanSpec; review that checks the evidence |
| Pipeline | `src/aec/pipeline.py` | offline end-to-end run on a prepared example |
| Live pipeline | `src/aec/live.py` | live run: one SAM box prompt per proposed region per side, the tolerance widening live masks need, and the Muse-backed review call |
| Report/evidence | `src/aec/report.py`, `evidence.py` | plain-text JSON and Markdown; fingerprints (hashes); replay |
| Report viewer | `src/aec/viewer.py` | a report rendered as one standalone HTML page: inline CSS, no JavaScript and no remote asset, every value escaped; the sections and their order mirror the Markdown renderer, and a card image is relative, served under a same-origin prefix, or inlined as a `data:` URI |
| Evidence cards | `src/aec/cards.py` | deterministic PNG crop of the plan around a finding's measured box, one per side, with its hash and size recorded; a crop that cannot be made is recorded as skipped |
| Evaluation | `src/aec/evaluation.py` | scores an offline or live run against the prepared ground truth: verified, refused, missed and false changes; writes `metrics.json` |
| Batch/export | `src/aec/batch.py`, `export.py` | sorting by how much a change matters; measured SVG (scalable vector graphics) or DXF (drawing exchange format) drawing overlays |
| Operations | `src/aec/ops.py` | the data-returning operations both front ends call (measure, verify, export, engine info); JSON-safe values and typed errors, no printing |
| Command line | `src/aec/cli.py`, `__main__.py` | argument parsing, printing and exit codes; `python -m aec` runs this |
| Package | `src/aec/__init__.py` | the package marker and the single version string (`aec --version`) |
| Tool registry | `src/aec/tool_registry.py` | the one list of published tools, each with its input schema and handler; `mcp/manifest.json` is generated from it and a test compares the two |
| MCP server | `src/aec/mcp_server.py` | JSON-RPC 2.0 on standard input and output, one frame per line and nothing else on standard output; sends each `tools/call` to its handler from the registry |
| Local web app | `src/aec/webapp.py` | a loopback-only HTTP server for a browser page: pick a fixture pair, measure it, read the report with its evidence cards, re-verify and export it; one session token for every state change, no JavaScript, no remote asset, and every requested file resolved inside its own run directory |
| Error redaction | `src/aec/redact.py` | one function that makes an error message safe to show on any surface: absolute paths become `<path>`, given secrets become `<redacted>`; the MCP server and the command line share it |

A **fixture** is a prepared test example. `sam31.json` is a SAM-shaped record
generated from the plan spec, not model output: it carries the ground-truth room
outlines for both sides with a fixed score, so the offline run is deterministic
(the same input always gives the same result).

The assistant path calls the same functions: `aec.mcp_server` reads one JSON-RPC
2.0 frame per line and sends each `tools/call` to the handler named in
`aec.tool_registry`, which is the same `aec.ops`, `aec.batch`, `aec.evaluation` or
`aec.client` function the command line calls, so a result cannot differ between
the two paths.

## Region proposal - deterministic, no model

The live path has two steps before anything is measured: propose candidate
rectangles, then segment each one.

**Why the boxes are not asked for in words.** On these line-art plans, SAM 3.1
answers a box prompt (a rectangle that says where to look) but returns no
objects for concept prompts such as "room". The model cannot be asked to find
the rooms on this input, so the candidates come from the drawing itself.

**Proposal, with no model.** `src/aec/propose.py` reads the plan raster,
thresholds the dark strokes, closes hairline gaps, and takes the bounding
rectangle of each enclosed paper region. It keeps boxes above `min_area_ratio`
(1% by default) and below 40% of the page area, drops the page background and
its margin, removes near-duplicates (overlap score, or IoU, of at least 0.8),
and drops a parent box when two or more strictly contained boxes tile at least
80% of it. That last rule is how a room split by a new wall yields the two
halves instead of the old whole, while a room that merely contains furniture
keeps its parent box. The step is plain OpenCV geometry: the same bytes produce
the same boxes on a given OpenCV build, with no network, no model and no key.

**Segmentation, within the boxes.** Each proposed box is sent to SAM 3.1 as a
box prompt, one call per box per side. SAM returns a mask, the mask becomes a
polygon, and that polygon is what the comparison measures. A box whose SAM call
raises `SamError` is counted and skipped, so one bad region does not lose the
other rooms of that side.

**What this is and is not.** It is segmentation of a proposed region, not room
discovery. The proposer returns rectangles around free space; it does not read
labels, furniture or text, and a title block or scale bar can be proposed like
any other region. The rectangle only decides where SAM looks; the room outline
is SAM's mask. `tests/test_propose.py` covers all 12 fixture pairs on both
sides: every one of the 96 ground-truth rooms gets a proposed box at an IoU of
at least 0.5, and the measured best-overlap range is 0.923 to 0.959. That is a
test floor on synthetic plans, not a real-world accuracy claim.

The **Data flow** below shows the offline run, which reads the generated
SAM-shaped record (`sam31.json`) instead of calling the model. The live run puts
proposal and segmentation in the place where the offline run reads that record.

## Data flow

```text
prepared example: settings + a.png/b.png + sam31.json
        ↓
SAM adapter → measured elements (room_id, polygon, area, segments, angles)
        ↓
correspondence → match status for each element
        ↓
comparison → measured differences
        ↓
review step → verified / rejected / not compared
        ↓
report.json and report.md + evidence fingerprints + report digest
        ↓
verify_report / SVG / DXF / batch summary
```

## Invariants

- Only matched elements produce comparable measurements.
- A split or merge is a definition mismatch, never a verified change.
- Evidence and measurement references are required for verification.
- The report notice is exact; JSON uses plain ASCII characters, and Markdown uses
  UTF-8, the standard text encoding for most languages.
- The report is fingerprinted (hashed) and replayable, never "signed".
- The engine is external; no engine imports.
- The public repository contains no customer documents, secrets or plans.
