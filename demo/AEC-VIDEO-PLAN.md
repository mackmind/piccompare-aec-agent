# AEC demo video plan

**Status:** offline cut can be recorded now; the live SAM/Muse cut is pending
credentials and is not claimed yet. Hard cap: 3:00.

## Storyboard

| Time | Shot | On screen | Voiceover |
|---|---|---|---|
| 0:00–0:20 | Problem | Two floor-plan revisions; a hand-measured room | “A pixel diff shows ink changed. It does not tell you whether the same room was measured the same way.” |
| 0:20–0:45 | Measure | `python -m aec measure --fixture fixtures/aec/resize-01` | “The agent segments rooms, measures area, segments and angles, and matches the same element across revisions.” |
| 0:45–1:15 | Verified change | `report.md`: room resize, area delta | “This room is 2.0 square metres larger, and the measurements support it.” |
| 1:15–1:45 | Refusal | `python -m aec measure --fixture fixtures/aec/split-01`; show `not_compared` | “This room was split into two. The definitions are not the same, so the agent refuses to claim a change.” |
| 1:45–2:10 | Evidence | `python -m aec verify ...` PASS | “Every report is hashed and replayable. It is not signed.” |
| 2:10–2:30 | Batch | `python scripts/run_batch.py`; 5 high findings, 6 refused | “Across a batch, the material changes rise to the top and the definitions it cannot compare stay visible.” |
| 2:30–2:45 | Export | SVG/DXF measured overlay | “The measured rooms export as an overlay a reviewer can open.” |
| 2:45–3:00 | Close | Tagline + repo URL | “Evidence humans can check; agents can replay.” |

## Commands

```bash
python scripts/make_plans.py --out fixtures --seed 7
python scripts/run_eval.py --fixtures fixtures --out runs/eval
python -m aec measure --fixture fixtures/aec/resize-01 --out runs/video/resize
python -m aec measure --fixture fixtures/aec/split-01 --out runs/video/split
python -m aec verify --report runs/video/resize/report.json --inputs-dir fixtures/aec/resize-01
python scripts/run_batch.py --reports runs/eval --out runs/batch
python -m aec export --report runs/video/resize/report.json --out runs/video/export
```

## Do not claim

- Live SAM/Muse output in the offline cut.
- Real-world accuracy or human-time savings.
- Full CAD, signed evidence, art authentication or cartography.
