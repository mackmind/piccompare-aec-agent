---
name: piccompare-aec
description: Measure room/space changes across two floor plans and verify definitions before claiming changes. Use for AEC revision review with the PicCompare AEC CLI.
---

# PicCompare AEC measurement skill

## When to use

Use this skill when a user asks whether two floor-plan revisions changed a room,
space or measured area — and when a pixel diff is not enough. The skill refuses
to compare elements whose definitions differ (for example a room split or two
rooms merged).

## Prerequisites

- Python 3.11+ with this repository installed (`pip install -e ".[dev]"`).
- A fixture directory containing `a.png`, `b.png`, `config.json`,
  `ground_truth.json` and `sam31.json`.
- For live SAM/Muse runs: `META_API_KEY`, the exact model IDs and network
  access. The current public workflow is deterministic/offline.

## Workflow

1. Run `python -m aec measure --fixture fixtures/aec/resize-01 --out runs/measure/resize-01`.
2. Read `report.md` and `report.json`; check `findings`, `not_compared` and
   `evidence`.
3. Run `python -m aec verify --report runs/measure/resize-01/report.json --inputs-dir fixtures/aec/resize-01`.
4. Export a measured overlay when requested:
   `python -m aec export --report ... --out runs/export`.

## Evidence

Every finding must cite element IDs and measurement refs. The report contains
input hashes, element hashes, measurement hashes and a replay digest. A
definition mismatch is reported as `not_compared`, never as a verified change.
The report is hashed and replayable; it is never “signed”.

## Limitations

- Synthetic clean plans only in the current public workflow.
- No semantic CAD reconstruction; SVG/DXF are measured overlays, not full CAD.
- No live SAM or Muse call in the offline default; live calls require credentials
  and are not yet exercised by this repo.
- No art authentication, cartography or surveying coordinate support.
