# Live model runbook (SAM 3.1 and Muse Spark)

This page is a step-by-step operational guide ("runbook") for running the
workflow with Meta's live models. It needs your own credentials and network
access. The default pipeline is offline and deterministic (the same input always
gives the same output); nothing on this page runs in the automated checks.

Terms: SAM 3.1 is Meta's Segment Anything Model, which outlines objects in an
image. Muse Spark is Meta's language model. The Meta Model API is the service that
exposes them to programs; an API is a way for one program to call another. JSON is
a plain-text data format that both people and programs can read.

## Preconditions

- `META_API_KEY` is exported in the shell only, never committed. "Exported" means
  set as an environment variable: a setting passed to programs.
- `META_MODEL_ID` (Muse Spark) and `META_SAM_MODEL_ID` (SAM 3.1) are known.
- A local copy of the PicCompare program containing `src/agent_cli.py`, or an
  explicit `--engine-tree` folder.

The engine is called through its documented command-line interface (CLI). This
repository never imports engine modules.

## 1. Find the engine (read-only)

```bash
python -m aec engine-info --engine-tree <path to a local demo build>
# or resolve through tree-map / active-pair.json
python -m aec engine-info --workspace-root ..
```

Expected: folder, version, Python environment and `agent_cli.py`. For a full
read-only check of `capabilities`, `compare` and `regions`, run:

```bash
python scripts/engine_smoke.py --engine-tree <path to a local demo build> --out runs/engine-smoke
```

It writes a receipt (a record of what was run) bound to the code revision and to
whether the folder had uncommitted changes. If the engine refuses with
`RESOURCE_LIMIT` (its out-of-memory guard) while the machine is loaded, pass
`--pin-available-gib 16`; the receipt records the pinned value.

## 2. Meta chat smoke test

A "smoke test" is a quick check that the connection works.

```bash
META_API_KEY=... META_MODEL_ID=... python scripts/smoke_meta.py
```

Expected: model id, call count and usage. No key means exit code 2 and no request.

## 3. SAM 3.1 smoke test

```bash
META_API_KEY=... META_SAM_MODEL_ID=... \
python scripts/smoke_sam.py --fixture fixtures/aec/resize-01 --side a --live \
  --image fixtures/aec/resize-01/a.png --prompt room
```

Expected: object count, model, call count and response time. Validate the live
response shape here; if it differs, change only `normalise_response` and the live
object mapping, never the report contract.

### Verified live shape (2026-10-28)

The service address (endpoint) only emits segmentation records on a **stream**
(the answer arrives in pieces, not all at once): a non-streaming request returns
one assistant message with empty text and zero tokens (word pieces counted by the
model). The client now sends `stream: true` and
`metadata: {"mask_encoding": "one_bit"}`, joins the `response.output_text.delta`
events and parses the documented token grammar:

```
<0f>1<|box;x1=96;y1=97;x2=504;y2=503;w=1600;h=1200|><|mask;x=0;y=0;data=407,409,!…|>
```

- `data=` is **height,width**; the mask origin (`x`,`y`) is relative to its box,
  so the image-space outline is the decoded contour plus the box origin.
- Masks (the outlined areas) are range-coded (compressed); decoding uses Meta's
  `meta-sam-parser` (SAM License, install with `pip install -e .[live]`). Without
  it the box becomes a rectangle outline and the object still loads.
- **Word-based prompts do not work on these line-art plans**: `room`, `wall`,
  `door` and `table` each returned **0 objects** on `resize-01/a` and
  `identical-01/a` (live, 2026-10-28). A **box prompt** (a rectangle that tells
  the model where to look) returns an outline: the box `97,97–504,503` decoded to
  the polygon (outline) `97,100–502,499`, so it tracks ROOM A at
  `100,100–500,500` (overlap score 0.985). On these examples the outline largely
  follows the proposed box, so the demo shows **segmentation of a proposed
  region**, not independent room discovery. Propose regions from the plan
  geometry and let SAM produce the outlines; do not expect word-based
  segmentation on line art.

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

Expected: a live report with run-record fields, verified/not-compared counts and a
replay PASS. If the split/merge example verifies a split as a change, stop: the
definition guard failed.

## Do not claim

- Live model use before a live run record exists.
- Real-world accuracy, human-time savings, full computer-aided design, digitally
  signed evidence, art authentication or map-making.

## Live results (2026-10-28)

- **Muse chat: PASS.** `muse-spark-1.3-contributor`, 1 call, 403 tokens (word
  pieces) for the JSON smoke test. Muse is a reasoning model: its internal
  reasoning uses the same `max_completion_tokens` budget as the visible answer,
  and the review step needed **8192** (at 2048 it hit `finish_reason=length` with
  empty content on a real review context).
- **SAM: PASS with box prompts.** The box `97,97–504,503` decoded to the outline
  `97,100–502,499`, so it tracks ROOM A at `100,100–500,500` (overlap score
  0.985). Because the outline largely follows the proposed box, this is
  segmentation of a proposed region, not independent room discovery.
- **SAM word prompts: 0 objects** on `resize-01/a`, `identical-01/a`, `merge-01/a`
  for `room`, `wall`, `door` and `table`. Propose regions from the plan geometry
  (`aec.propose.propose_boxes`, `--boxes-from-plan`) and let SAM outline each box;
  that recovers every room on all seven test pairs at overlap scores of
  0.92–0.96.
- **One live pair** (`resize-01`, proposed regions): 1 verified finding (ROOM A
  16.040 → 17.988 square metres), 0 not compared, 0 rejected, report digest
  `e9fb9a08…`, run records `live_meta`, `sam-3.1`,
  `muse-spark-1.3-contributor`, 10 SAM calls and 1 Muse call. The report is
  committed as `demo/live-report.json` and **verifies**, so the
  fingerprinted-and-replayable claim covers live evidence too.
- **At the last recorded run, the live evaluation left 10 of 12 pairs clean**
  (`run_eval.py --fixtures fixtures --live --out runs/eval/live`, 2026-10-28): of
  the 11 expected findings, **5 verified, 4 definition mismatches refused**
  (merge-01/02 and split-01/02), **2 missing** and **0 false positives**. Both
  misses are label-only changes (`label_change-01` and part of `mixed-01`): SAM
  returns no text and this environment has no OCR (text reading). Offline remains
  12/12 and is the scored evidence.
- **Policy, disclosed in every live report.** Mask outlines are simplified to
  plan-like corner points (6 pixels); the allowed size and angle margins are
  widened five times, and the minimum area for a material change is floored at
  0.3 square metres (the noise a 400-pixel mask edge produces), so the configured
  `area_tolerance_m2` is not consulted. Scoring aligns live elements to the known
  room outlines by overlap, because SAM supplies no labels. When two outlines
  have different numbers of corner points, they are compared on a common
  resampling (a shared set of points), not by pairing unlike edges. A box whose
  segmentation fails is counted and skipped, not fatal. One proposed region per
  plan is not a room (the title-block or scale-bar band); it is compared like any
  other element.
- **The demo banner is an edition notice.** Every report starts with
  `HACKATHON DEMO — NOT AN EVIDENCE RECORD`; it marks the demo edition. It does
  not withdraw the fingerprinted, replayable report contract.
