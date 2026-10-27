# Live SAM/Muse handoff

Status: **not exercised**. The clients, live pipeline and smoke scripts exist and
are fake-transport tested. This document is the credential-swap runbook.

## Preconditions

- The app revision is stable enough for a read-only engine smoke.
- `active-pair.json` / `tree-map.json` point to the intended 054H or 055H tree, or
  an explicit `--engine-tree` is available.
- Event credits/card are active; the exact Muse Spark and SAM 3.1 model IDs are
  known; `META_API_KEY` is in the shell only.
- No app-tree edit is needed.

## 1. Resolve the engine (read-only)

```bash
python -m aec engine-info --engine-tree PicCompare_0.54H
# or, for 055H, the manifest/tree-map must point there; no hard-coded name
python -m aec engine-info --workspace-root ..
```

Expected: the tree, version, venv python and `agent_cli.py` paths are printed.
If the app is mid-revision, record the blocker; do not patch it.

## 2. Meta chat smoke

```bash
META_API_KEY=... META_MODEL_ID=... python scripts/smoke_meta.py
```

Expected: model id, calls and usage; no key means exit 2 and no request.

## 3. SAM 3.1 smoke

```bash
META_API_KEY=... META_SAM_MODEL_ID=... \
python scripts/smoke_sam.py --live --image fixtures/aec/resize-01/a.png --prompt room
```

Expected: object count, model, calls and latency. The live SAM response shape
must be validated here; if it differs, change only `normalise_response` and the
live object mapping, not the report contract.

## 4. One live pair

```bash
META_API_KEY=... META_MODEL_ID=... META_SAM_MODEL_ID=... \
python scripts/run_live_pair.py --fixture fixtures/aec/resize-01 --out runs/live/resize-01
```

Expected: a live report with receipt fields, verified/not-compared counts and a
replay PASS. If the split/merge fixture still verifies a split as a change, stop:
the definition guard failed.

## 5. Record and submit

- Copy the live receipt/model IDs into `docs/SUBMISSION.md` and the video.
- Record the 3-minute video from `demo/AEC-VIDEO-PLAN.md`; the live cut must show
  live receipts. Keep the offline cut as a labeled backup.
- Submit by **2026-11-04 18:00 CET** internal / 21:00 ET portal.

## Do not claim

- Live model use before a live receipt exists.
- Real-world accuracy, human-time savings, full CAD, signed evidence, art
  authentication or cartography.
