# Architecture

This page explains how the public code is organised. It is written for people who
want to read or audit the code; the [README](../README.md) explains the product in
plain terms.

The repository is the public half of a floor-plan revision checker: it measures
rooms on two versions of a plan, checks whether the same room is defined the same
way, and writes a report that can be re-run.

## Boundary

The public repository is the open-source integration layer (MIT licence: a
permissive open-source licence). The PicCompare engine is an external, separately
licensed dependency. No engine source
is imported, copied or published. The engine is found at run time and called
through its documented command-line interface (CLI: the text commands a program
can run).

## Components

| Component | File | Role |
|---|---|---|
| Engine resolver | `src/aec/engine.py` | explicit folder → environment switch (`PICCOMPARE_DEMO=1`) or `tree-map.json` → `active-pair.json`; no hard-coded folder |
| Engine client | `src/aec/client.py` | one separate program run per documented command; JSON (plain-text data) responses; typed failures |
| SAM client | `src/aec/sam.py` | Segment Anything Model 3.1 client; its network connection can be replaced in tests |
| SAM adapter | `src/aec/sam_adapter.py` | model response → `SamObject` (a validated data record) |
| Mask adapter | `src/aec/masks.py` | binary mask → closed polygon (an outline made of straight edges) |
| Geometry/scale | `src/aec/geometry.py`, `scale.py` | area, line segments, angles, centre point, overlap score (IoU), real-world units |
| Elements | `src/aec/elements.py` | measured rooms, spaces and walls from SAM objects |
| Correspondence | `src/aec/correspondence.py` | matched / ambiguous / definition mismatch / unmatched |
| Comparison | `src/aec/compare.py` | comparable measurements and candidate findings |
| Meta client | `src/aec/meta.py` | client for Meta's model service (its interface follows the widely used OpenAI chat format) |
| Planner/critic | `src/aec/planner.py`, `critic.py` | brief → PlanSpec; review that checks the evidence |
| Pipeline | `src/aec/pipeline.py` | offline end-to-end run on a prepared example |
| Report/evidence | `src/aec/report.py`, `evidence.py` | plain-text JSON and Markdown; fingerprints (hashes); replay |
| Batch/export | `src/aec/batch.py`, `export.py` | sorting by how much a change matters; measured SVG (scalable vector graphics) or DXF (drawing exchange format) drawing overlays |

A **fixture** is a prepared test example. `sam31.json` holds recorded model output
so the offline run is deterministic (the same input always gives the same result).

## Data flow

```text
prepared example: settings + a.png/b.png + sam31.json
        ↓
SAM adapter → measured elements (room_id, polygon, area, segments, angles)
        ↓
correspondence → match status for each element
        ↓
comparison → measured differences
        ↓
review step → verified / rejected / not compared
        ↓
report.json and report.md + evidence fingerprints + report digest
        ↓
verify_report / SVG / DXF / batch summary
```

## Invariants

- Only matched elements produce comparable measurements.
- A split or merge is a definition mismatch, never a verified change.
- Evidence and measurement references are required for verification.
- The report notice is exact; JSON uses plain ASCII characters, and Markdown uses
  UTF-8, the standard text encoding for most languages.
- The report is fingerprinted (hashed) and replayable, never "signed".
- The engine is external; no engine imports.
- The public repository contains no customer documents, secrets, plans or
  commercial components.
