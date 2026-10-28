# PicCompare AEC evidence report

**HACKATHON DEMO — NOT AN EVIDENCE RECORD**

- Pair: `resize-01`
- Generated: 2026-10-28T11:15:51+00:00
- Findings: 1 verified, 0 rejected, 0 not compared
- Report digest: `e9fb9a0822a1d3f8741768188e5f5c2b591cf9ee618ac70609b8b5643330fbb7`

## Findings

| Type | Materiality | Evidence | Claim |
|---|---|---|---|
| room_resized | high | resize-01:a:0:room:1, resize-01:b:0:room:0 | area_delta; segment_delta; area 16.040 -> 17.988 m2 (delta +1.947) |

## Not compared

None.

## Limitations

- Live SAM masks carry boundary noise; segment/angle tolerances are 5.0x the plan's and the material area delta is floored at 0.3 m2 (see the usage note).
- SAM supplies no room labels; the evaluator aligns live elements to ground-truth rooms by polygon IoU (scoring only).
- A proposed region that is not a room (title block, scale bar) is compared like any other element.
- Synthetic fixture used for this live-path test only; no real-world claim.

This is a hashed, replayable evidence report. It is not signed and is not an evidence record.
