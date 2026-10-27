# Limitations

- **Synthetic data only.** The public fixtures are clean generated plans with
  exact ground truth. They do not represent scanned, noisy or real customer
  drawings.
- **No live model evidence yet.** The SAM 3.1 and Muse Spark client seams exist,
  but the public run is deterministic/offline. Live SAM/Muse must be exercised
  before any live-model claim.
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
