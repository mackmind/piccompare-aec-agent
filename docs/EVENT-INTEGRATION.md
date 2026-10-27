# Event integration notes

## Engine resolution

The integration resolves a PicCompare engine tree in this order:

1. `--engine-tree PATH` (explicit);
2. `PICCOMPARE_DEMO=1` + `tree-map.json` `hackathon_demo.tree`;
3. `active-pair.json` `comm`;
4. otherwise fail with `EngineNotFound`.

There is no hard-coded 054/055 fallback. A future 054H or 055H tree is selected
by re-pointing the manifest/tree-map or passing an explicit path. The venv name
comes from `active-pair.json` `venv`. The engine is called through
`<tree>/src/agent_cli.py`; this repository never imports engine modules.

## Live Meta/SAM credentials

The clients read credentials only from the shell environment:

- `META_API_KEY` — never committed, logged or written to a report.
- `META_MODEL_ID` — exact Muse Spark id from the event console.
- `META_SAM_MODEL_ID` — exact SAM 3.1 id; default `sam-3.1` is a seam default,
  confirm the console value.
- `META_API_BASE` — default `https://api.meta.ai/v1`.
- `PICCOMPARE_SAM31_DIR` — optional fixture payload directory.

The Meta chat client uses `max_completion_tokens` and strict `json_schema`; it
does not send `max_output_tokens`. SAM uses the separate `/responses` endpoint.

## Live gates (not yet exercised)

1. `python scripts/smoke_sam.py --live --image <plan>.png --prompt room`
2. Run the planner/critic with a live `MetaClient`.
3. Run the live evaluation and store the receipt.

No live call, key or purchase has been made by this repository. Offline fixture
payloads are deterministic and are not live model output.
