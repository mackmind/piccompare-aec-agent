# Submission checklist

Event: Meta Global AI Developer Hackathon, Indie Developer track,
2026-10-27 to 2026-11-04. Portal deadline: 2026-11-04 21:00 ET.

## Repository

- [x] Public MIT repository: https://github.com/mackmind/piccompare-aec-agent
- [x] No engine source, engine imports, customer data or secrets.
- [x] Synthetic fixtures and exact ground truth.
- [x] Offline pipeline passes 12/12 pairs with 0 false positives.
- [x] Read-only engine smoke passes on the 0.55H demo edition and the 0.55
      commercial tree; receipts bind the tree head.
- [x] Live SAM/Muse receipt: `sam-3.1` and `muse-spark-1.3-contributor` exercised
      2026-10-28 (see `runs/live/resize-01/report.json`, `usage.provider = live_meta`).
      SAM only answers on a stream and needs **box prompts** on line art; concept
      prompts return no objects.
- [ ] Final public head with the complete event code: **pending boundary review**.
- [ ] Video URL: **not yet recorded**.
- [ ] Portal submission: **not yet filed**.

## Claims register

| Claim | Allowed now? | Evidence |
|---|---|---|
| Offline AEC pipeline works on 12 synthetic pairs | Yes | `runs/eval/metrics.json`; 12/12 |
| Engine CLI compare/regions works on a local tree | Yes | `scripts/engine_smoke.py` receipt, head-bound |
| Measures room resize/wall move on synthetic plans | Yes, synthetic only | 7 verified findings |
| Refuses split/merge definitions | Yes | 4 definition mismatches; `not_compared` |
| Report is hashed/replayable | Yes | `python -m aec verify` |
| Uses live SAM 3.1 and Muse Spark | Yes | `runs/live/resize-01/report.json` (`live_meta`, both model ids, 55 SAM + 1 Muse call); `scripts/smoke_meta.py` and `scripts/smoke_sam.py --live --box` |
| Faster/cheaper than human review | **No** | no human baseline |
| Real-world accuracy | **No** | synthetic only |
| Full CAD | **No** | measured SVG/DXF overlay only |
| Signed/certified/court-admissible | **Never** | not implemented |
| Art authentication/cartography/surveying | **No** | out of scope |

## Judge-facing links

| Item | Value |
|---|---|
| Repository | https://github.com/mackmind/piccompare-aec-agent |
| Demo video | not yet recorded |
| Architecture | `docs/ARCHITECTURE.md` |
| Dataset | `docs/DATASET.md` |
| Limitations | `docs/LIMITATIONS.md` |
| Sample report | `demo/sample-report.json` and `demo/sample-report.md` |
| Measured overlays | `demo/overlays/resize-01.svg` and `.dxf` |

## Pre-submission gates

```bash
python -m pytest -q
python -m ruff check .
python -m mypy src/aec
python scripts/check_boundary.py
python scripts/run_eval.py --fixtures fixtures --out runs/eval
python -m aec verify --report runs/eval/resize-01/report.json --inputs-dir fixtures/aec/resize-01
python scripts/engine_smoke.py --engine-tree <tree> --out runs/engine-smoke  # local engine only
```

The demo video is not yet recorded. The live receipts exist (see the checklist); the scored
evidence is the offline deterministic evaluation, because live masks carry boundary noise and
no OCR labels are available in this environment.
