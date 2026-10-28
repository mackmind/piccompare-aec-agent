# Public report contracts

This page is for programmers who read or write the report files. It lists every
field, its type and its allowed values. The report is a JSON document (a plain-text
data format) validated with pydantic (a Python data-validation library); unknown
fields are rejected. JSON files use ASCII characters only; Markdown files use
UTF-8, the standard text encoding for most languages.

Field-name terms: `px` means pixels; `m2` means square metres; `deg` means degrees;
`IoU` means intersection over union, an overlap score from 0 to 1 (1.0 is a perfect
match); `bbox` means bounding box, the smallest rectangle around an object;
`polygon` means an outline made of straight edges; `enum` means a fixed list of
allowed values. ASCII means plain English characters, without accents or symbols.

## PlanSpec

| Field | Type | Invariant |
|---|---|---|
| `pair_id` | string | stable test-example id |
| `units` | `m` or `mm` | real-world units |
| `px_per_unit` | float | > 0 |
| `element_types` | list | room/space/wall/column/stair |
| `area_tolerance_m2` | float | > 0 |
| `dimension_tolerance_px` | float | > 0 |
| `angle_tolerance_deg` | float | > 0 |
| `material_area_delta_m2` | float | > 0 |
| `match_iou_threshold` | float | 0..1, default 0.5 |
| `match_centroid_tolerance_px` | float | > 0, default 8 |
| `match_area_ratio_tolerance` | float | >= 0, default 0.25 |
| `scale_source` | enum | known_dimension/scale_bar/config |

## PageGeometry

`page` (>=0), `width` (>0), `height` (>0).

## SamObject

`object_id`, `page`, `label` (room/space/wall/column/stair/unknown),
`bbox_px` (4), `polygon_px` (>=3 points), `score` (0..1), `source`
(`sam31`/`stub`).

## Element

`element_id`, `page`, `element_type`, `label`, `polygon_px`, `area_px2`,
`area_m2`, `centroid_px`, `segments_px`, `angles_deg`, `source_objects`,
`confidence` (0..1).

## ElementMatch

`a_id`, `b_id`, `status` (`matched`/`ambiguous`/`definition_mismatch`/
`unmatched`), `iou`, `centroid_delta_px`, `area_ratio`, `reasons`.

## MeasurementDelta

`element_id`, `status` (`comparable`/`not_compared`/`no_material_change`),
`area_delta_m2`, `segment_deltas_px`, `angle_deltas_deg`, `reasons`.

## Finding

`finding_id`, `change_type` (`room_resized`, `wall_moved`, `room_split`,
`room_merged`, `room_added`, `room_removed`, `label_changed`,
`no_material_change`), `element_ids`, `materiality`
(`high`/`medium`/`low`), `status` (`verified`/`rejected`/`not_compared`),
`claim`, `evidence_refs`, `measurement_refs`, `reasons`.

## Report

`schema_version` (`piccompare-aec-report/1.0`), `demo_notice`
(`HACKATHON DEMO — NOT AN EVIDENCE RECORD`), `generated_at`, `engine`,
`inputs`, `settings`, `plan`, `pages`, `elements_a`, `elements_b`, `matches`,
`measurements`, `findings`, `rejected`, `not_compared`, `evidence`, `usage`,
`limitations`, `digest`.

The report writer must reject an altered demo notice. A clean report is
fingerprinted (hashed) and replayable, never "signed".
