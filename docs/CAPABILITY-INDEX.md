# AEC capability index

Status: public scaffold capabilities, 2026-10-28. The live SAM 3.1 / Muse Spark
path is exercised; `demo/live-report.json` is a committed live receipt and it
verifies against the committed fixtures.

| Capability | Status | Entry point |
|---|---|---|
| Synthetic plan generation | available | `python scripts/make_plans.py --out fixtures --seed 7` |
| Offline AEC measurement | available | `python -m aec measure --fixture ... --out ...` |
| Report replay verification | available | `python -m aec verify --report ... --inputs-dir ...` |
| SVG/DXF measured export | available | `python -m aec export --report ... --out ...` |
| Batch materiality triage | available | `python scripts/run_batch.py --reports ... --out ...` |
| Offline fixture evaluation | available | `python scripts/run_eval.py --fixtures fixtures --out runs/eval` |
| Engine tree resolution | available (mock-tested) | `python -m aec engine-info --engine-tree ...` |
| Live SAM 3.1 | exercised 2026-10-28 (box prompts; concept prompts return no objects on line art) | `scripts/smoke_sam.py --live --box ...` |
| Live Muse Spark planner/critic | exercised 2026-10-28 (planner + evidence critic) | `scripts/smoke_meta.py`, `aec.meta.MetaClient` |
| Live fixture evaluation | available; 10 of 12 pairs clean (see `docs/LIVE-RUN.md`) | `python scripts/run_eval.py --fixtures fixtures --live --out runs/eval/live` |
| Committed live receipt | available; verifies like any report | `python -m aec verify --report demo/live-report.json --inputs-dir fixtures/aec/resize-01` |
| Legal exhibit workflow | draft | `skills/piccompare-legal/SKILL.md` |
| Print/barcode workflow | draft | `skills/piccompare-print/SKILL.md` |
| Full CAD reconstruction | not implemented | — |
| Art authentication / cartography / surveying | not implemented | — |
