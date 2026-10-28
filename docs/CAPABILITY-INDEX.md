# Capability index (what the tool can do today)

This page lists what the tool can do, in plain terms. AEC means architecture,
engineering and construction: the industry that designs and builds buildings.

Status: public capabilities as of 2026-10-28. The live SAM 3.1 (Segment Anything
Model, for outlining objects) and Muse Spark (a language model) path has been
exercised; `demo/live-report.json` is a committed live run record and verifies
against the committed examples.

| Capability | Status | How to run it |
|---|---|---|
| Generate prepared test plans | available | `python scripts/make_plans.py --out fixtures --seed 7` |
| Offline measurement (no model call) | available | `python -m aec measure --fixture ... --out ...` |
| Re-run a report from its evidence | available | `python -m aec verify --report ... --inputs-dir ...` |
| Export measured rooms as SVG or DXF drawings | available | `python -m aec export --report ... --out ...` |
| Sort a batch by how much each change matters | available | `python scripts/run_batch.py --reports ... --out ...` |
| Offline evaluation on the prepared examples | available | `python scripts/run_eval.py --fixtures fixtures --out runs/eval` |
| Find a local PicCompare build | available (tested with a stand-in) | `python -m aec engine-info --engine-tree ...` |
| Live Segment Anything Model 3.1 | exercised 2026-10-28 (box prompts work; word prompts return no objects on line art) | `scripts/smoke_sam.py --live --box ...` |
| Live Muse Spark language model | exercised 2026-10-28 (planning and review) | `scripts/smoke_meta.py`, `aec.meta.MetaClient` |
| Live evaluation | available; at the last run, 10 of 12 pairs clean (see `docs/LIVE-RUN.md`) | `python scripts/run_eval.py --fixtures fixtures --live --out runs/eval/live` |
| Committed live run record | available; verifies like any report | `python -m aec verify --report demo/live-report.json --inputs-dir fixtures/aec/resize-01` |
| Legal exhibit workflow | draft | `skills/piccompare-legal/SKILL.md` |
| Print and barcode workflow | draft | `skills/piccompare-print/SKILL.md` |
| Full computer-aided design reconstruction | not implemented | — |
| Art authentication, map-making or land surveying | not implemented | — |

SVG means scalable vector graphics; DXF is a standard computer-aided design
exchange format. For other terms, see the glossary in the [README](../README.md).
