# Event integration notes

This page explains how the public code finds and calls a local PicCompare build,
and how live-model credentials are supplied. Terms: SAM 3.1 is Meta's Segment
Anything Model, which outlines objects in an image; Muse Spark is Meta's language
model. "CLI" means command-line interface: the documented text commands the
integration runs. "JSON" is a plain-text data format.

## How the engine is found

The integration looks for a PicCompare build in this order:

1. `--engine-tree PATH` (an explicit folder);
2. `PICCOMPARE_DEMO=1` plus `tree-map.json` (a local configuration file that
   points to a build) → `hackathon_demo.tree`;
3. `active-pair.json` → `comm`;
4. otherwise it fails with `EngineNotFound`.

There is no hard-coded version fallback. The demo build is selected by
re-pointing the tree map or passing an explicit path; a future build is selected
the same way. The Python environment name comes from `active-pair.json`. The
engine is called through `<tree>/src/agent_cli.py`; this repository never imports
engine modules.

## Read-only engine smoke test

A "smoke test" is a quick check that the integration works. `scripts/engine_smoke.py`
calls `capabilities`, `compare` and `regions` through the documented command-line
interface and writes a receipt (a run record) tied to the exact code revision and
to whether the folder had uncommitted changes. It passed against the demo edition
and the commercial build (`compare` complete, pages 1/1, 12 regions).

The engine allows image work against free memory minus a safety margin of
`max(512 MiB, total/4)`. On a loaded machine the allowance reaches zero and the
engine refuses with `RESOURCE_LIMIT` (its out-of-memory guard); `--pin-available-gib`
sets the engine's documented memory override `PICCOMPARE_AVAILABLE_BYTES` for that
run, and the run record stores the pinned value. The automated checks do not run
this test because the engine is not in this repository.

## Live Meta/SAM credentials

The clients read credentials only from the shell environment (settings passed to
programs):

- `META_API_KEY` — never committed, logged or written to a report.
- `META_MODEL_ID` — the exact Muse Spark model id from the event console.
- `META_SAM_MODEL_ID` — the exact SAM 3.1 model id; the default `sam-3.1` is a
  placeholder, so confirm the console value.
- `META_API_BASE` — default `https://api.meta.ai/v1`.

The Meta chat client uses `max_completion_tokens` (the model's output budget) and
a strict JSON-schema check (the model's answer must have the required fields); it
does not send `max_output_tokens`. SAM uses the separate `/responses` endpoint
(the service address for that model).

## Live checks (exercised 2026-10-28)

1. `python scripts/smoke_sam.py --fixture fixtures/aec/resize-01 --side a --live --box 100,100,500,500`
2. `python scripts/smoke_meta.py` for the chat, planning and review path.
3. `python scripts/run_live_pair.py --fixture fixtures/aec/resize-01 --out runs/live/resize-01 --boxes-from-plan`
4. `python scripts/run_eval.py --fixtures fixtures --live --out runs/eval/live`

Results are recorded in `docs/LIVE-RUN.md`. The credentialed runs were made by
the maintainer; the key is never committed, logged or written to a report, and
none is needed for the offline pipeline. One live run is committed as
`demo/live-report.json` and verifies against the committed examples.

Offline test payloads are deterministic (the same input gives the same output)
and are not live model output.
