# Capability index (what the tool can do today)

This page lists what the tool can do, in plain terms. AEC means architecture,
engineering and construction: the industry that designs and builds buildings.

Status: public capabilities as of 2026-10-31. The live SAM 3.1 (Segment Anything
Model, for outlining objects) and Muse Spark (a language model) path has been
exercised; `demo/live-report.json` is a committed live run record and verifies
against the committed examples.

| Capability | Status | How to run it |
|---|---|---|
| Generate prepared test plans | available | `python scripts/make_plans.py --out fixtures --seed 7` |
| Offline measurement (no model call) | available | `python -m aec measure --fixture ... --out ...` |
| PNG evidence cards in a report | available; `aec measure --cards` adds up to 12 crops (one per side of at most six verified findings), each with its file path, hash and size; a crop that cannot be made is recorded as skipped | `python -m aec measure --fixture fixtures/aec/resize-01 --cards --out runs/measure/resize-01` |
| Re-run a report from its evidence | available | `python -m aec verify --report ... --inputs-dir ...` |
| Export measured rooms as SVG or DXF drawings | available | `python -m aec export --report ... --out ...` |
| Sort a batch by how much each change matters | available | `python scripts/run_batch.py --reports ... --out ...` |
| Offline evaluation on the prepared examples | available | `python scripts/run_eval.py --fixtures fixtures --out runs/eval` |
| Find a local PicCompare build | available (tested with a stand-in) | `python -m aec engine-info --engine-tree ...` |
| Propose candidate regions from the plan (no model) | available; across the 12 fixture pairs, every one of the 96 ground-truth rooms gets a proposed box at a best overlap score (IoU) of 0.923 to 0.959, against a test floor of 0.5; a blank page proposes nothing; a proposal is not room discovery | `python scripts/run_live_pair.py --fixture fixtures/aec/resize-01 --boxes-from-plan` |
| Live Segment Anything Model 3.1 | exercised 2026-10-28 (box prompts work; word prompts return no objects on line art) | `scripts/smoke_sam.py --live --box ...` |
| Live Muse Spark language model | exercised 2026-10-28 (planning and review) | `scripts/smoke_meta.py`, `aec.meta.MetaClient` |
| Live evaluation | available; at the last run, 10 of 12 pairs clean (see `docs/LIVE-RUN.md`) | `python scripts/run_eval.py --fixtures fixtures --live --out runs/eval/live` |
| Committed live run record | available; verifies like any report | `python -m aec verify --report demo/live-report.json --inputs-dir fixtures/aec/resize-01` |
| Call the tools from an AI assistant (MCP) | available; a local server publishes the same operations as 12 tools over JSON-RPC 2.0 on standard input and output, with no network port and no extra dependency | `python -m aec.mcp_server`, configured as in [docs/MCP.md](MCP.md) |
| View and measure from a local web page | available; loopback only, per-session token, no authentication | `python -m aec serve` |
| Legal exhibit workflow | draft | `skills/piccompare-legal/SKILL.md` |
| Print and barcode workflow | draft | `skills/piccompare-print/SKILL.md` |
| Full computer-aided design reconstruction | not implemented | — |
| Art authentication, map-making or land surveying | not implemented | — |

SVG means scalable vector graphics; DXF is a standard computer-aided design
exchange format. For other terms, see the glossary in the [README](../README.md).
