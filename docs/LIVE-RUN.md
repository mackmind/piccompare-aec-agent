# Live SAM/Muse runbook

How to exercise the live Meta Model API path with your own credentials. The
default pipeline is deterministic and offline; nothing here runs in CI.

## Preconditions

- `META_API_KEY` is exported in the shell only, never committed.
- `META_MODEL_ID` (Muse Spark) and `META_SAM_MODEL_ID` (SAM 3.1) are known.
- A local PicCompare tree with `src/agent_cli.py`, or an explicit `--engine-tree`.

The engine is called through its documented CLI. This repository never imports
engine modules.

## 1. Resolve the engine (read-only)

```bash
python -m aec engine-info --engine-tree <055H tree>
# or resolve through tree-map / active-pair.json
python -m aec engine-info --workspace-root ..
```

Expected: tree, version, venv python and `agent_cli.py`. For a full read-only
check of `capabilities`, `compare` and `regions`, run:

```bash
python scripts/engine_smoke.py --engine-tree <055H tree> --out runs/engine-smoke
```

It writes a receipt bound to the tree head and dirtiness. If the engine refuses
with `RESOURCE_LIMIT` while the machine is loaded, pass
`--pin-available-gib 16`; the receipt records the pinned value.

## 2. Meta chat smoke

```bash
META_API_KEY=... META_MODEL_ID=... python scripts/smoke_meta.py
```

Expected: model id, calls and usage. No key means exit 2 and no request.

## 3. SAM 3.1 smoke

```bash
META_API_KEY=... META_SAM_MODEL_ID=... \
python scripts/smoke_sam.py --live --image fixtures/aec/resize-01/a.png --prompt room
```

Expected: object count, model, calls and latency. Validate the live response
shape here; if it differs, change only `normalise_response` and the live object
mapping, never the report contract.

### Verified live shape (2026-10-28)

The endpoint only emits segmentation records on a **stream**: a non-streaming
request returns one assistant message with empty text and zero tokens. The
client now sends `stream: true` and `metadata: {"mask_encoding": "one_bit"}`,
joins the `response.output_text.delta` events and parses the documented token
grammar:

```
<0f>1<|box;x1=96;y1=97;x2=504;y2=503;w=1600;h=1200|><|mask;x=0;y=0;data=407,409,!…|>
```

- `data=` is **height,width**; the mask origin (`x`,`y`) is relative to its box,
  so the image-space polygon is the decoded contour plus the box origin.
- Masks are range-coded; decoding uses Meta's `meta-sam-parser` (SAM License,
  install with `pip install -e .[live]`). Without it the box becomes a
  rectangle polygon and the object still loads.
- **Concept prompts do not work on these line-art plans**: `room`, `wall`,
  `door` and `table` each returned **0 objects** on `resize-01/a` and
  `identical-01/a` (live, 2026-10-28). A **box prompt** returns a mask whose
  polygon matches the ground-truth room (ROOM A: box 97,97–504,503 against
  100,100–500,500, IoU ≈ 0.95). Propose regions from the plan geometry and let
  SAM produce the masks; do not expect concept segmentation on line art.

```bash
# Box prompt (region proposed by the caller), live:
META_API_KEY=... META_SAM_MODEL_ID=... \
python scripts/smoke_sam.py --fixture fixtures/aec/resize-01 --side a --live \
  --image fixtures/aec/resize-01/a.png --box 100,100,500,500
```

## 4. One live pair

```bash
META_API_KEY=... META_MODEL_ID=... META_SAM_MODEL_ID=... \
python scripts/run_live_pair.py --fixture fixtures/aec/resize-01 --out runs/live/resize-01
```

Expected: a live report with receipt fields, verified/not-compared counts and a
replay PASS. If the split/merge fixture verifies a split as a change, stop: the
definition guard failed.

## Do not claim

- Live model use before a live receipt exists.
- Real-world accuracy, human-time savings, full CAD, signed evidence, art
  authentication or cartography.

## Live results (2026-10-28)

- **Muse chat: PASS** — `muse-spark-1.3-contributor`, 1 call, 403 tokens for the
  JSON smoke. Muse is a reasoning model: reasoning tokens count against
  `max_completion_tokens`, and the AEC critic needed **8192** (at 2048 it hit
  `finish_reason=length` with empty content on a real review context).
- **SAM: PASS with box prompts** — a mask decoded and matched the room polygon
  (ROOM A: 97,97–504,503 against ground truth 100,100–500,500, IoU ≈ 0.95).
- **SAM concept prompts: 0 objects** on `resize-01/a`, `identical-01/a`,
  `merge-01/a` for `room`, `wall`, `door` and `table`. Propose regions from the
  plan geometry (`aec.propose.propose_boxes`, `--boxes-from-plan`) and let SAM
  segment each box; that recovers every room on all seven fixtures at IoU
  0.92–0.96.
- **One live pair** (`resize-01`, proposed regions): 5 verified findings, 0 not
  compared, 0 rejected, report digest `f6965242…`, receipts `live_meta`,
  `sam-3.1`, `muse-spark-1.3-contributor`, 55 SAM calls. The live report
  **verifies** (`python -m aec verify --report runs/live/resize-01/report.json
  --inputs-dir fixtures/aec/resize-01` → PASS), so the hashed-and-replayable
  claim covers live evidence too.
- **The live eval scores 8 of 12 pairs** (`run_eval.py --live --fixtures fixtures`,
  2026-10-28): identical, noise, merge-01/02 (refusals), resize-02, split-02 (refusal) and
  wall_move-01/02 pass. The four misses are the known limits below, not tuning:
  - **no plan labels without OCR** — `label_change-01` (and the label part of `mixed-01`) cannot
    be seen; SAM returns no text;
  - **thin partitions are smoothed** — on `split-01` SAM's box mask covers the whole room, so the
    split is not refused (the offline vector path does refuse it);
  - **residual mask noise** — two false `room_resized` findings across 12 pairs at the 5× band.
  Live masks are simplified to plan-like vertices and the comparison tolerances are widened 5×
  (recorded in each report's usage note); scoring aligns live elements to ground-truth rooms by
  polygon IoU because SAM supplies no labels. Offline remains 12/12.
