# PicCompare AEC evidence report

**HACKATHON DEMO — NOT AN EVIDENCE RECORD**

- Pair: `resize-01`
- Generated: 2026-10-31T01:20:37+00:00
- Findings: 1 verified, 0 rejected, 0 not compared
- Report digest: `6b47760e97b04cc2d1dfba009b75219a71a444dffc9dcebe7d5f7a3404eba1c9`

## Findings

| Type | Materiality | Evidence | Claim |
|---|---|---|---|
| room_resized | high | resize-01:a:0:room:0, resize-01:b:0:room:0 | area_delta; segment_delta; area 16.000 -> 18.000 m2 (delta +2.000) |

## Not compared

None.

## Evidence cards

| Finding | Change type | Side | Path | SHA-256 | Bytes |
|---|---|---|---|---|---|
| `room_resized:resize-01:a:0:room:0` | room_resized | a | `cards/room_resized_resize-01_a_0_room_0-a.png` | `8e2880c471b4b3aecb0df3bf0c5a380529d4c2eb7f0e84832dba629db1a13dbe` | 2192 |
| `room_resized:resize-01:a:0:room:0` | room_resized | b | `cards/room_resized_resize-01_a_0_room_0-b.png` | `9760d48373e7ed327d476246121b5c0ccfc2cb3e0994ed32a8dc8b0ec4b9e512` | 2233 |

## Limitations

- Synthetic plans only; no real-world accuracy claim.
- Deterministic offline critic; no live Meta call in this run.
- Evidence cards are raster crops of the plan at the measured element's box; they show what was measured, not that the measurement is correct.

This is a hashed, replayable evidence report. It is not signed and is not an evidence record.
