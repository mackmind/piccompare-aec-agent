# Submission checklist

Event: Meta Global AI Developer Hackathon, Indie Developer track,
2026-10-27 to 2026-11-04. Portal deadline: 2026-11-04 21:00 Eastern Time (ET).

AEC means architecture, engineering and construction: the industry that designs
and builds buildings. For a plain-language explanation of the project and the
words used here, start with the [README](../README.md).

## Repository

- [x] Public MIT repository (a permissive open-source licence):
      https://github.com/mackmind/piccompare-aec-agent
- [x] No engine source, engine imports, customer data or secrets.
- [x] Generated test plans with known correct answers.
- [x] Offline pipeline passes 12/12 pairs with 0 false positives (reported changes
      that are not real).
- [x] Read-only engine smoke test passes on a local demo edition and a local
      commercial build of PicCompare; each run record is tied to the exact code
      revision.
- [x] Live SAM/Muse receipt (a run record): Meta's `sam-3.1` (Segment Anything
      Model for outlining objects) and `muse-spark-1.3-contributor` (language
      model) were exercised
      2026-10-28 and **committed** as `demo/live-report.json` (`usage.provider =
      live_meta`, 10 SAM calls, 1 Muse call, report digest `e9fb9a08…`). It records
      1 verified finding (ROOM A: 16.040 → 17.988 square metres) and verifies
      against the committed examples. SAM answers only on a stream and needs **box
      prompts** (rectangles that say where to look) on line art; word prompts such
      as "room" return no objects.
- [ ] Final public head with the complete event code: **pending boundary review**.
- [ ] Video link: **not yet recorded**.
- [ ] Portal submission: **not yet filed**.

## Claims register

| Claim | Allowed now? | Evidence |
|---|---|---|
| Offline AEC (architecture, engineering and construction) pipeline works on 12 generated pairs | Yes | `runs/eval/metrics.json`; 12/12 |
| The engine's command-line compare and regions commands work on a local PicCompare build | Yes | `scripts/engine_smoke.py` run record, tied to the code revision |
| Measures room resize and wall move on generated plans | Yes, generated plans only | 7 verified findings |
| Refuses split/merge definitions | Yes | 4 definition mismatches; `not_compared` |
| Report is fingerprinted (hashed) and replayable | Yes | `python -m aec verify` on the offline and live reports (`runs/live/resize-01/report.json` verifies) |
| Uses the live SAM 3.1 and Muse Spark models | Yes | `demo/live-report.json` (`live_meta`, both model ids, 10 SAM + 1 Muse call); `scripts/smoke_meta.py` and `scripts/smoke_sam.py --live --box` |
| Live evaluation scores the prepared examples | Partial | local run `runs/eval/live-full3/metrics.json` (not published): **10 of 12 pairs clean — 5 of 11 expected findings verified, 4 definition mismatches refused, 2 label-only findings missed, 0 false positives**. Offline 12/12 is the scored evidence |
| Faster or cheaper than human review | **No** | no measured human comparison |
| Real-world accuracy | **No** | generated plans only |
| Full CAD (computer-aided design) reconstruction | **No** | measured SVG (scalable vector graphics) or DXF (drawing exchange format) overlay only |
| Digitally signed, certified or court-admissible | **Never** | not implemented |
| Art authentication, map-making or land surveying | **No** | out of scope |

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

The demo video is not yet recorded. The live run records exist (see the
checklist); the scored evidence is the offline deterministic (repeatable)
evaluation, because live outlines carry boundary noise and no OCR (text reading)
labels are available in this environment.
