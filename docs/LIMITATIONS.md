# Limitations

This page lists what the tool cannot do, in plain terms. These limits are part of
the submission, not caveats added afterwards.

- **Synthetic data only.** The public test pairs are clean, generated plans with
  known correct answers. They do not represent scanned, noisy or real customer
  drawings.
- **Live evidence exists, with limits.** Meta's SAM 3.1 (an image-segmentation
  model that outlines objects) and Muse Spark (a language model) were exercised
  live on 2026-10-28. At the last recorded run, the live evaluation left 10 of 12
  pairs clean: 5 of the 11 expected findings verified, 4 definition mismatches
  refused, 2 label-only findings missed (SAM returns no text and this environment
  has no OCR, or text reading), and 0 false changes. SAM answers only box prompts
  on line art, and the outline largely follows the proposed box, so the demo shows
  segmentation of a proposed region, not independent room discovery. Live comparisons widen the
  allowed measurement margins. The offline deterministic run (the same input
  always gives the same output) is 12/12 and is the scored evidence.
- **No real-world accuracy claim.** The 12/12 result is a synthetic evaluation,
  not a human-time or production-accuracy study.
- **No full CAD.** CAD means computer-aided design. SVG and DXF are drawing file
  formats; they contain measured room outlines, labels, areas and dimensions
  only. Doors, windows, layers, text and full wall reconstruction are not
  implemented.
- **No OCR** (optical character recognition, or reading text from images) **or
  title-block understanding.** Scale is supplied by configuration or a scale bar;
  it is not inferred from text.
- **No art authentication.** Condition and restoration documentation is a future
  direction; the app does not authenticate a work.
- **No cartography** (map-making) **or surveying coordinate support.** No
  projections, coordinate systems or survey control.
- **No signed evidence.** The report is hashed (fingerprinted) and replayable; it
  is not a digital signature, certification or court-admissibility claim.
- **Deterministic critic.** The offline review step is a guard for test
  evaluation, not a substitute for the live Muse Spark reviewer.
