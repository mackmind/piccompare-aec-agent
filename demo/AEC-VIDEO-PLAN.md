# Demo video plan

This is the recording plan for the hackathon demo video. AEC means architecture,
engineering and construction. SAM 3.1 is Meta's image-segmentation model, which
outlines objects; Muse Spark is Meta's language model.

**Status:** both cuts can be recorded. The offline cut is deterministic (the same
input always gives the same result) and scored (12/12). The live cut is available
since 2026-10-28: Muse and SAM 3.1 both answer live, and the cut must show the run
records from `runs/live/`. At the last run the live cut left 10 of 12 pairs clean;
the two misses are label-only changes that need text reading, which is not
implemented. If the live cut is used, say on screen that the rectangles to inspect
are proposed from the plan geometry because SAM 3.1 does not answer word prompts
on line art and its outline largely follows the proposed rectangle — segmentation
of a proposed region, not independent room discovery — and that the allowed
comparison margin is widened for outline noise. Hard cap: 3 minutes.

## Storyboard

| Time | Shot | On screen | Voiceover |
|---|---|---|---|
| 0:00–0:20 | Problem | Two floor-plan revisions; a hand-measured room | "A simple picture comparison shows that ink changed. It does not tell you whether the same room was measured the same way." |
| 0:20–0:45 | Measure | `python -m aec measure --fixture fixtures/aec/resize-01` | "The tool outlines rooms, measures area, wall segments and angles, and matches the same room across revisions." |
| 0:45–1:15 | Verified change | `report.md`: room resize, area difference | "This room is 2.0 square metres larger, and the measurements support it." |
| 1:15–1:45 | Refusal | `python -m aec measure --fixture fixtures/aec/split-01`; show the `not_compared` list (comparisons refused) | "This room was split into two. The definitions are not the same, so the tool refuses to claim a change." |
| 1:45–2:10 | Evidence | `python -m aec verify ...` PASS | "Every report is fingerprinted and replayable. It is not signed." |
| 2:10–2:30 | Batch | `python scripts/run_batch.py`; 5 high-priority findings, refused definitions visible | "Across a batch, the changes that matter rise to the top, and the definitions it cannot compare stay visible." |
| 2:30–2:45 | Export | Measured overlay in SVG or DXF (two drawing file formats) | "The measured rooms export as a drawing overlay a reviewer can open." |
| 2:45–3:00 | Close | Tagline + repository link | "Evidence humans can check; programs can replay." |

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

- Live SAM or Muse output in the offline cut.
- Real-world accuracy or human-time savings.
- Full computer-aided design reconstruction, digitally signed evidence, art
  authentication or map-making.
