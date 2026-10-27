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
python -m aec engine-info --engine-tree PicCompare_0.54H
# or resolve through active-pair.json / PICCOMPARE_DEMO=1
python -m aec engine-info --workspace-root ..
```

Expected: tree, version, venv python and `agent_cli.py`. For a full read-only
check of `capabilities`, `compare` and `regions`, run:

```bash
python scripts/engine_smoke.py --engine-tree PicCompare_0.54H --out runs/engine-smoke
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
