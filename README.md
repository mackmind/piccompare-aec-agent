# PicCompare AEC Agent

**Every batch. Every doc. Every pixel. Eyes or APIs — both first-class.
See it. Check it. Replay it.**

PicCompare AEC Agent (architecture, engineering and construction) reviews two
versions of a floor plan — a drawing of a building seen from above, showing rooms
and walls. It measures each room on both versions, matches the same room across
them, and reports a change only when both versions define that room in the same
way. Each result is a report with digital fingerprints, so another person can
re-run the check and confirm it.

"AEC" stands for architecture, engineering and construction: the industry that
designs and builds buildings. The word "agent" here means an automated assistant
that carries out the review steps.

This is the public, open-source part of an entry in the Meta Global AI Developer
Hackathon (Indie Developer track, 2026-10-27 to 2026-11-04). The PicCompare
comparison engine — the program that renders and compares the drawings — is a
separate, separately licensed product and is not included here.

Repository: https://github.com/mackmind/piccompare-aec-agent

## What it is

PicCompare AEC Agent measures rooms and spaces on two floor-plan revisions: two
successive versions of the same drawing. It matches the same elements (rooms,
spaces and walls) across the two versions, refuses to compare elements whose
definitions differ (for example, a room that was split into two), and produces a
report that can be re-run and verified.

It is an integration layer. The PicCompare engine remains a separate,
separately licensed dependency. This repository does not contain engine source
code, customer documents or secrets.

## Quick start

The commands below create an isolated Python environment (a virtual environment,
or venv; the folder is named `.venv-aec`), install the tool, and run the offline
workflow on the included example plans. They are written for Windows; on other
systems use `python` and the `bin/` folder instead of `Scripts/`. You do not need
to understand every command: they are listed so a reviewer can reproduce the
results.

```bash
py -3.13 -m venv .venv-aec
.venv-aec/Scripts/python.exe -m pip install -e ".[dev]"
.venv-aec/Scripts/python.exe scripts/make_plans.py --out fixtures --seed 7
.venv-aec/Scripts/python.exe scripts/run_eval.py --fixtures fixtures --out runs/eval
.venv-aec/Scripts/python.exe -m aec measure --fixture fixtures/aec/resize-01 --out runs/measure/resize-01
.venv-aec/Scripts/python.exe -m aec verify --report runs/measure/resize-01/report.json --inputs-dir fixtures/aec/resize-01
.venv-aec/Scripts/python.exe -m aec export --report runs/measure/resize-01/report.json --out runs/export
# needs a local PicCompare build; not run by the automated checks
.venv-aec/Scripts/python.exe scripts/engine_smoke.py --engine-tree <path to a local demo build> --out runs/engine-smoke
```

What the steps do:

1. create a private Python environment and install this repository;
2. generate 12 prepared test pairs of floor plans;
3. run the offline evaluation and print its score;
4. measure one example pair and write a report;
5. re-check that report from its saved evidence;
6. export the measured rooms as a drawing overlay.

Inspect the committed examples:
[demo/sample-report.md](demo/sample-report.md), the live run record
[demo/live-report.md](demo/live-report.md) and the measured overlay
[demo/overlays/resize-01.svg](demo/overlays/resize-01.svg).

Run the project's checks:

```bash
.venv-aec/Scripts/python.exe -m pytest -q
.venv-aec/Scripts/python.exe -m ruff check .
.venv-aec/Scripts/python.exe -m mypy src/aec
.venv-aec/Scripts/python.exe scripts/check_boundary.py
```

`pytest` runs the tests, `ruff` checks code style, `mypy` checks type
annotations, and the boundary check confirms that no engine source code or
secret entered this public repository.

## How it works

```text
two versions of a floor plan + settings + prepared model output
        ↓
segment the proposed room regions (Meta's Segment Anything Model, or SAM)
        ↓
match the same room across both versions
        ↓
compare measurements (only rooms that match)
        ↓
review step: verify the change, or refuse if the definition differs
        ↓
report with digital fingerprints + a re-run command
        ↓
optional drawing overlay (SVG or DXF) and batch summary
```

In a live run, Meta's Muse Spark language model performs the planning and review
steps. In the default offline run, a fixed deterministic review step does the
same job, so the result is identical on every machine and needs no credentials.

The rectangles to inspect are proposed from the plan geometry, not found by SAM
on its own: on these line drawings SAM answers a box prompt (a rectangle that
says where to look) but returns no objects for words such as "room". The demo
therefore shows segmentation of a proposed region, not independent room
discovery.

The engine is external: this repository finds a local PicCompare build and calls
its documented command-line interface. It never imports engine code and never
hard-codes a folder name.

## Status

The offline workflow is complete and tested on 12 prepared plan pairs: 12 of 12
pairs pass, with 7 verified changes, 4 comparisons refused because the room
definitions differ, and no false changes. Meta's live models (SAM 3.1 and Muse
Spark) were exercised on 2026-10-28. At the last recorded run, the live evaluation
left 10 of 12 pairs clean: 5 of the 11 expected findings verified, 4 definition
mismatches refused, 2 label-only changes missed because the tool cannot read text,
and 0 false changes. The offline result remains the scored evidence, and this is
not a real-world accuracy claim. Details are in
[docs/LIVE-RUN.md](docs/LIVE-RUN.md).

## Evidence

Each report contains digital fingerprints (hashes) of the inputs, the measured
elements, the measurements and the whole report, plus the command needed to
re-run the check. The report is **hashed and replayable, not signed**. When two
rooms cannot be compared because their definitions differ, they are listed under
`not_compared` and are never shown as a verified change.

## Limitations

- Synthetic, clean plans only; no real-world accuracy claim. The example plans
  are generated, not scanned customer drawings.
- No OCR (software that reads text from images), so text labels, furniture and
  title-block text are not understood.
- No full CAD (computer-aided design) reconstruction; the SVG (scalable vector
  graphics) and DXF (drawing exchange format) files contain measured room
  outlines only.
- Live model masks carry boundary noise, so a live comparison widens the allowed
  measurement margin; see [docs/LIMITATIONS.md](docs/LIMITATIONS.md).
- No art authentication, map-making or land-surveying coordinate support.

## Words used here

- **floor plan** — a drawing of a building seen from above, showing rooms and walls.
- **revision** — one version in a series of updated drawings.
- **element** — a room, space, wall, column or stair measured on the plan.
- **definition mismatch** — the two versions do not describe the same element the
  same way (for example, a room split into two), so the tool refuses to compare
  them.
- **fixture** — a prepared test example. Its **ground truth** is the known correct
  answer.
- **deterministic** — the same input always produces the same output.
- **hash (digital fingerprint)** — a short code computed from a file. If the file
  changes, the code changes, so tampering is detectable. A **digest** is the same
  idea for the whole report.
- **replay** — re-run the check from the saved evidence and compare the result.
- **SAM** — Segment Anything Model, Meta's model for drawing outlines around
  objects in an image.
- **Muse Spark** — Meta's language model, used in a live run to plan and review.
- **API** — a way for one program to call another. The tagline's "eyes or APIs"
  means a person can inspect the result, or another program can consume it.
- **command line** — the text commands shown in Quick start.
- **JSON** — a plain-text data format that both people and programs can read.
- **engine** — the separate PicCompare program that renders and compares images.
- **SVG / DXF** — two drawing file formats. SVG is for scalable vector graphics;
  DXF is a standard computer-aided design exchange format.

## Licence

MIT licence (a permissive open-source licence) for this repository only. The
PicCompare engine is a separate, separately licensed product and is not included.
See [LICENSE](LICENSE) and [NOTICE](NOTICE).

## What was built during the event

The measurement and verification workflow, the prepared test plans, the matching
and refusal logic, the offline evaluation, the report and replay checks, and the
drawing export were built during the event. The PicCompare engine is a
pre-existing dependency and is not included. No internal plans or commercial
components are published here.
