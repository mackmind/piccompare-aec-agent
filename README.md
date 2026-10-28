# PicCompare AEC Agent

**Every batch. Every doc. Every pixel. Eyes or APIs — both first-class.
See it. Check it. Replay it.**

A public, MIT-licensed AEC measurement-verification integration for the Meta
Global AI Developer Hackathon (Indie Developer track, 2026-10-27 to 2026-11-04).

Repository: https://github.com/mackmind/piccompare-aec-agent

## What it is

PicCompare AEC Agent measures rooms and spaces on two floor-plan revisions,
matches the same elements, refuses to compare elements whose definitions differ,
and emits a hashed, replayable evidence report. It is an integration layer; the
PicCompare engine remains a separate proprietary dependency.

## Status

The **offline deterministic pipeline is implemented and tested**:

- 12 synthetic plan pairs with exact ground truth.
- 11 expected findings; 7 verified; 4 definition mismatches refused; 0 false
  positives.
- A baseline pixel-change approach would flag 11 changes; the agent refuses the
  4 definitions it cannot compare.
- Report replay verifies clean reports and fails tampered reports.
- SVG/DXF measured overlays, batch triage and agent skills are available.
- A read-only engine smoke (`capabilities`/`compare`/`regions`) passes against
  the 0.55H demo edition and the 0.55 commercial tree; each receipt is bound to
  the tree head. The engine remains an external dependency.
- **The live SAM 3.1 and Muse Spark path is exercised** (2026-10-28). One live
  pair, `resize-01`, is committed as [demo/live-report.json](demo/live-report.json):
  it records 10 SAM calls and 1 Muse call and reports the one real change. It
  verifies with the same command as any other report:
  `python -m aec verify --report demo/live-report.json --inputs-dir fixtures/aec/resize-01`.
  The live fixture evaluation is **10 of 12 pairs clean — 5 of 11 expected
  findings verified, 4 definition mismatches refused, 2 findings missed (label-only
  changes, no OCR) and 0 false positives**; the details and the scoring policy are
  in [docs/LIVE-RUN.md](docs/LIVE-RUN.md). The offline 12/12 evaluation remains the
  scored evidence.

## Quick start

```bash
py -3.13 -m venv .venv-aec
.venv-aec/Scripts/python.exe -m pip install -e ".[dev]"
.venv-aec/Scripts/python.exe scripts/make_plans.py --out fixtures --seed 7
.venv-aec/Scripts/python.exe scripts/run_eval.py --fixtures fixtures --out runs/eval
.venv-aec/Scripts/python.exe -m aec measure --fixture fixtures/aec/resize-01 --out runs/measure/resize-01
.venv-aec/Scripts/python.exe -m aec verify --report runs/measure/resize-01/report.json --inputs-dir fixtures/aec/resize-01
.venv-aec/Scripts/python.exe -m aec export --report runs/measure/resize-01/report.json --out runs/export
# needs a local PicCompare tree; not part of CI
.venv-aec/Scripts/python.exe scripts/engine_smoke.py --engine-tree <tree> --out runs/engine-smoke
```

Inspect the committed sample evidence:
[demo/sample-report.md](demo/sample-report.md), the live receipt
[demo/live-report.md](demo/live-report.md) and the measured overlay
[demo/overlays/resize-01.svg](demo/overlays/resize-01.svg).

Run the gates:

```bash
.venv-aec/Scripts/python.exe -m pytest -q
.venv-aec/Scripts/python.exe -m ruff check .
.venv-aec/Scripts/python.exe -m mypy src/aec
.venv-aec/Scripts/python.exe scripts/check_boundary.py
```

## How it works

```text
floor-plan pair + config + SAM-shaped fixture payloads
        ↓
SAM adapter → measured elements (polygons, areas, segments, angles)
        ↓
element correspondence (matched / ambiguous / definition mismatch)
        ↓
measurement comparison (only matched elements)
        ↓
deterministic critic (or Muse Spark critic in a live run)
        ↓
hashed report.json + report.md + replay verification
        ↓
optional SVG/DXF measured overlay and batch summary
```

The engine is external. The client resolves a 055H/055C tree through
`tree-map.json`, `active-pair.json` or an explicit `--engine-tree`; it never
imports engine modules and never hard-codes a tree name.

## Evidence

Each report includes input hashes, element hashes, measurement hashes, a report
digest and a replay command. The report is **hashed and replayable, not signed**.
Definition mismatches are listed under `not_compared`, never as verified changes.

## Limitations

- Synthetic, clean plans only; no real-world accuracy claim.
- No OCR, furniture, dimensions or title-block semantic understanding.
- No full CAD reconstruction; SVG/DXF contain measured overlays only.
- Live masks carry boundary noise, so a live comparison widens tolerances
  (`docs/LIVE-RUN.md`) and cannot see label-only changes without OCR; see
  `docs/LIMITATIONS.md`.
- No art authentication, cartography or surveying coordinate support.

## Licence

MIT for this repository only. The PicCompare engine is a separate proprietary
product and is not included. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

## What was built during the event

The AEC measurement/verification workflow, synthetic fixtures, correspondence,
definition re-verification, offline evaluation, report/replay and export are
event-built. The PicCompare engine is a pre-existing dependency and is not
included. No internal plans or commercial components are published here.
