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

## Region proposal - deterministic, no model

The live path has two steps before anything is measured: propose candidate
rectangles, then segment each one.

**Why the boxes are not asked for in words.** On these line-art plans, SAM 3.1
answers a box prompt (a rectangle that says where to look) but returns no
objects for concept prompts such as "room". The model cannot be asked to find
the rooms on this input, so the candidates come from the drawing itself.

**Proposal, with no model.** `src/aec/propose.py` reads the plan raster,
thresholds the dark strokes, closes hairline gaps, and takes the bounding
rectangle of each enclosed paper region. It keeps boxes above `min_area_ratio`
(1% by default) and below 40% of the page area, drops the page background and
its margin, removes near-duplicates (overlap score, or IoU, of at least 0.8),
and drops a parent box when two or more strictly contained boxes tile at least
80% of it. That last rule is how a room split by a new wall yields the two
halves instead of the old whole, while a room that merely contains furniture
keeps its parent box. The step is plain OpenCV geometry: the same bytes produce
the same boxes on a given OpenCV build, with no network, no model and no key.

**Segmentation, within the boxes.** Each proposed box is sent to SAM 3.1 as a
box prompt, one call per box per side. SAM returns a mask, the mask becomes a
polygon, and that polygon is what the comparison measures. A box whose SAM call
raises `SamError` is counted and skipped, so one bad region does not lose the
other rooms of that side.

**What this is and is not.** It is segmentation of a proposed region, not room
discovery. The proposer returns rectangles around free space; it does not read
labels, furniture or text, and a title block or scale bar can be proposed like
any other region. The rectangle only decides where SAM looks; the room outline
is SAM's mask. On the two examples the tests check (`resize-01` side a and
`split-01` side b), every ground-truth room must have a proposal at an IoU of
at least 0.5 (`tests/test_propose.py`); that is a test floor on synthetic
plans, not a real-world accuracy claim.

The **Data flow** below shows the offline run, which reads recorded model output
(`sam31.json`) instead of calling the model. The live run puts proposal and
segmentation in the place where the offline run reads that record.

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
