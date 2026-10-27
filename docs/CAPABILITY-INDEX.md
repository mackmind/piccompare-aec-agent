# AEC capability index

Status: public scaffold capabilities, 2026-10-27. No live SAM/Muse call has been
exercised by this repository yet.

| Capability | Status | Entry point |
|---|---|---|
| Synthetic plan generation | available | `python scripts/make_plans.py --out fixtures --seed 7` |
| Offline AEC measurement | available | `python -m aec measure --fixture ... --out ...` |
| Report replay verification | available | `python -m aec verify --report ... --inputs-dir ...` |
| SVG/DXF measured export | available | `python -m aec export --report ... --out ...` |
| Batch materiality triage | available | `python scripts/run_batch.py --reports ... --out ...` |
| Offline fixture evaluation | available | `python scripts/run_eval.py --fixtures fixtures --out runs/eval` |
| Engine tree resolution | available (mock-tested) | `python -m aec engine-info --engine-tree ...` |
| Live SAM 3.1 | client seam only; not exercised | `scripts/smoke_sam.py --live --image ...` |
| Live Muse Spark planner/critic | client seam only; not exercised | `aec.meta.MetaClient` |
| Legal exhibit workflow | draft | `skills/piccompare-legal/SKILL.md` |
| Print/barcode workflow | draft | `skills/piccompare-print/SKILL.md` |
| Full CAD reconstruction | not implemented | — |
| Art authentication / cartography / surveying | not implemented | — |
