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
python scripts/smoke_sam.py --fixture fixtures/aec/resize-01 --side a --live \
  --image fixtures/aec/resize-01/a.png --prompt room
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
  polygon matches the ground-truth room: the box `97,97–504,503` against
  ROOM A `100,100–500,500` decodes to a polygon `97,100–502,499` (IoU ≈ 0.985).
  On these fixtures the mask largely tracks the proposed box, so the demo shows
  **segmentation of a proposed region**, not independent room discovery.
  Propose regions from the plan geometry and let SAM produce the masks; do not
  expect concept segmentation on line art.

```bash
# Box prompt (region proposed by the caller), live:
META_API_KEY=... META_SAM_MODEL_ID=... \
python scripts/smoke_sam.py --fixture fixtures/aec/resize-01 --side a --live \
  --image fixtures/aec/resize-01/a.png --box 100,100,500,500
```

## 4. One live pair

```bash
META_API_KEY=... META_MODEL_ID=... META_SAM_MODEL_ID=... \
python scripts/run_live_pair.py --fixture fixtures/aec/resize-01 \
  --out runs/live/resize-01 --boxes-from-plan
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
- **SAM: PASS with box prompts** — the box `97,97–504,503` decoded to a polygon
  `97,100–502,499`, so the mask tracks ROOM A (`100,100–500,500`, IoU ≈ 0.985).
- **SAM concept prompts: 0 objects** on `resize-01/a`, `identical-01/a`,
  `merge-01/a` for `room`, `wall`, `door` and `table`. Propose regions from the
  plan geometry (`aec.propose.propose_boxes`, `--boxes-from-plan`) and let SAM
  segment each box; that recovers every room on all seven fixtures at IoU
  0.92–0.96.
- **One live pair** (`resize-01`, proposed regions): 1 verified finding (ROOM A
  16.040 → 17.988 m²), 0 not compared, 0 rejected, report digest `e9fb9a08…`,
  receipts `live_meta`, `sam-3.1`, `muse-spark-1.3-contributor`, **10 SAM calls**
  and 1 Muse call. The report is committed as `demo/live-report.json` and
  **verifies**, so the hashed-and-replayable claim covers live evidence too.
- **The live eval leaves 10 of 12 pairs clean** (`run_eval.py --fixtures fixtures
  --live --out runs/eval/live`, 2026-10-28): of the 11 expected findings,
  **5 verified, 4 definition mismatches refused** (merge-01/02, split-01/02),
  **2 missing** and **0 false positives**. Both misses are label-only changes
  (`label_change-01`, part of `mixed-01`): SAM returns no text and this
  environment has no OCR. Offline remains 12/12 and is the scored evidence.
- **Policy, disclosed in every live report.** Mask contours are simplified to
  plan-like vertices (6 px); `dimension_tolerance_px` and `angle_tolerance_deg`
  are widened 5× and the material area delta is floored at 0.3 m² (the noise a
  400 px mask edge produces), so `area_tolerance_m2` is not consulted; scoring
  aligns live elements to ground-truth rooms by polygon IoU, because SAM supplies
  no labels. When two element polygons have different vertex counts they are
  compared on a common resampling, not by zipping unlike edges. A box whose
  segmentation fails is counted and skipped, not fatal, and one proposed region
  per plan is not a room (title block/scale-bar band), so it is compared like any
  other element.
- **The demo banner is an edition notice.** Every report starts with
  `HACKATHON DEMO — NOT AN EVIDENCE RECORD`; it marks the demo edition, it does
  not withdraw the hashed, replayable report contract.
