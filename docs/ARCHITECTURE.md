# Architecture

## Boundary

The public repository is the MIT integration layer. The PicCompare engine is an
external proprietary dependency. No engine source is imported, copied or
published. The engine is resolved at runtime and called through the documented
CLI contract.

## Components

| Component | File | Role |
|---|---|---|
| Engine resolver | `src/aec/engine.py` | explicit path → `PICCOMPARE_DEMO=1`/`tree-map.json` → `active-pair.json` comm; no hard-coded tree |
| Engine client | `src/aec/client.py` | one subprocess per facade tool; JSON; typed failures |
| SAM client | `src/aec/sam.py` | SAM 3.1 `/responses` seam with injected transport |
| SAM adapter | `src/aec/sam_adapter.py` | payload → `SamObject` |
| Mask adapter | `src/aec/masks.py` | binary mask → closed polygon |
| Geometry/scale | `src/aec/geometry.py`, `scale.py` | area, segments, angles, centroid, IoU, real units |
| Elements | `src/aec/elements.py` | measured elements from SAM objects |
| Correspondence | `src/aec/correspondence.py` | matched/ambiguous/definition mismatch/unmatched |
| Comparison | `src/aec/compare.py` | comparable measurements and candidate findings |
| Meta client | `src/aec/meta.py` | OpenAI-compatible chat/structured-output seam |
| Planner/critic | `src/aec/planner.py`, `critic.py` | brief → PlanSpec; evidence-aware verification |
| Pipeline | `src/aec/pipeline.py` | offline end-to-end fixture run |
| Report/evidence | `src/aec/report.py`, `evidence.py` | ASCII JSON + Markdown; hashes; replay |
| Batch/export | `src/aec/batch.py`, `export.py` | materiality triage; SVG/DXF measured overlays |

## Data flow

```text
fixture config + a.png/b.png + sam31.json
        ↓
SAM adapter → Element objects (room_id, polygon, area, segments, angles)
        ↓
correspondence → ElementMatch status
        ↓
comparison → MeasurementDelta
        ↓
critic → verified / rejected / not_compared
        ↓
report.json/report.md + evidence hashes + digest
        ↓
verify_report / SVG / DXF / batch summary
```

## Invariants

- Only matched elements produce comparable measurements.
- A split or merge is a definition mismatch, never a verified change.
- Evidence refs and measurement refs are required for verification.
- The report notice is exact; JSON is ASCII, Markdown is UTF-8.
- The report is hashed and replayable, never “signed”.
- The engine is external; no engine imports.
- The public repo contains no customers, secrets, plans or commercial components.
