# Synthetic floor-plan dataset

Status: generated 2026-10-27; synthetic only; no customer, employer or
confidential data.

## Pairs

12 pairs under `fixtures/aec/<pair_id>/`:

| Variant | Pair IDs | Intended change |
|---|---|---|
| identical | `identical-01` | none |
| resize | `resize-01`, `resize-02` | one room grows by 2.0 m² |
| wall move | `wall_move-01`, `wall_move-02` | one wall moves 20 px |
| split | `split-01`, `split-02` | one room split into two |
| merge | `merge-01`, `merge-02` | two rooms merged into one |
| label change | `label_change-01` | label only |
| noise | `noise-01` | scan noise only |
| mixed | `mixed-01` | resize + label change |

Each pair contains:

- `a.png`, `b.png` — 1600×1200 synthetic plans, 100 px = 1 m, with a scale bar
  and a title block.
- `config.json` — `PlanSpec` fields and the variant.
- `ground_truth.json` — room polygons, exact areas, centroids and expected
  changes/findings.
- `sam31.json` — deterministic SAM-3.1-shaped mask/bbox payloads for both
  sides, used by the offline adapter tests.

`fixtures/manifest.json` is global, not per pair: it holds the SHA-256 of every
generated file in all 12 pairs.

## Scale and units

`px_per_unit = 100`, `units = m`. Ground-truth areas are computed from the
closed polygons; the report must carry both pixel and real units.

## Reproduce

```bash
python scripts/make_plans.py --out fixtures --seed 7
python scripts/verify_fixtures.py --offline --geometry-only
```

The geometry verifier checks manifest hashes, closed polygons, exact areas and
change references; `scripts/run_eval.py` adds the pipeline evaluation and the
metrics (`runs/eval/metrics.json`).

## Limitations

- Plans are clean synthetic line art, not representative scans.
- No OCR, furniture, dimensions or title-block text understanding.
- Scale is provided by the config/scale bar; it is not inferred.
- No customer data and no real-world accuracy claim.
