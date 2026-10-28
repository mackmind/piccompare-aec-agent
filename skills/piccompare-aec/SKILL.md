---
name: piccompare-aec
description: Measure room and space changes across two floor plans and verify definitions before claiming changes. Use for architecture, engineering and construction (AEC) revision review with the PicCompare AEC command-line tool.
---

# PicCompare AEC measurement skill

AEC means architecture, engineering and construction. This skill measures rooms
on two versions of a floor plan and refuses to claim a change when the two
versions define a room differently.

## When to use

Use this skill when a user asks whether two floor-plan revisions changed a room,
space or measured area, and when a simple picture comparison is not enough. The
skill refuses to compare elements whose definitions differ (for example, a room
split in two, or two rooms merged).

## Prerequisites

- Python 3.11 or newer, with this repository installed
  (`pip install -e ".[dev]"`).
- A test-example folder containing `a.png`, `b.png`, `config.json`,
  `ground_truth.json` (the known correct answer) and `sam31.json` (recorded
  Segment Anything Model output).
- For live SAM/Muse runs: `META_API_KEY`, the exact model IDs and network access.
  The current public default workflow is deterministic (the same input always
  gives the same output) and offline.

## Workflow

1. Run `python -m aec measure --fixture fixtures/aec/resize-01 --out runs/measure/resize-01`.
2. Read `report.md` and `report.json`; check `findings`, `not_compared`
   (comparisons refused) and `evidence`.
3. Run `python -m aec verify --report runs/measure/resize-01/report.json --inputs-dir fixtures/aec/resize-01`.
4. Export a measured overlay when requested:
   `python -m aec export --report ... --out runs/export`.

## Evidence

Every finding must cite element IDs and measurement references. The report
contains fingerprints (hashes) of the inputs, elements and measurements, plus a
replay digest (a fingerprint of the whole report). A definition mismatch is
reported as `not_compared`, never as a verified change. The report is
fingerprinted and replayable; it is never “signed”.

## Limitations

- Generated clean plans only in the current public workflow.
- No semantic CAD (computer-aided design) reconstruction; SVG and DXF are
  measured overlays (scalable vector graphics and drawing exchange format), not
  full CAD.
- The offline default makes no model call. A live SAM/Muse Spark run needs
  credentials and is documented in `docs/LIVE-RUN.md`; at the last run it left
  10 of 12 test pairs clean, missing the two label-only changes for want of OCR
  (text reading). SAM answers only box prompts on line art, so the regions are
  proposed from the plan geometry.
- No art authentication, map-making or land-surveying coordinate support.
