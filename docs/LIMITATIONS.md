# Limitations

- **Synthetic data only.** The public fixtures are clean generated plans with
  exact ground truth. They do not represent scanned, noisy or real customer
  drawings.
- **Live evidence exists, with limits.** SAM 3.1 and Muse Spark were exercised live on
  2026-10-28. The live evaluation leaves **10 of 12** pairs clean — 5 of 11 expected
  findings verified, 4 definition mismatches refused, 2 findings missed and 0 false
  positives. Both misses are label-only changes: SAM returns no text and this
  environment has no OCR. SAM also answers only box prompts on line art, so regions
  are proposed from the plan geometry, and the live comparison widens its segment/
  angle tolerances and floors the material area delta (see `docs/LIVE-RUN.md`).
  The offline deterministic run is 12/12 and is the scored evidence.
- **No real-world accuracy claim.** The 12/12 result is a synthetic evaluation,
  not a human-time or production-accuracy study.
- **No full CAD.** SVG and DXF contain measured room polygons, labels, areas and
  dimensions only; doors, windows, layers, text and semantic wall reconstruction
  are not implemented.
- **No OCR or title-block understanding.** Scale is supplied by config/scale bar;
  it is not inferred from text.
- **No art authentication.** Condition/restoration documentation is a future
  direction; the app does not authenticate a work.
- **No cartography or surveying coordinate support.** No projections, coordinate
  systems or survey control.
- **No signed evidence.** The report is hashed and replayable; it is not a
  signature, certification or court-admissibility claim.
- **Deterministic critic.** The offline critic is a guard for fixture evaluation,
  not a substitute for the live Muse Spark critic.
