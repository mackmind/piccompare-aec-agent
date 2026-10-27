# Impact

## User and workflow

The user is an AEC analyst reviewing a floor-plan revision: an architect,
construction reviewer or space planner who must decide whether a room resize, a
wall move, a split or a merge is real — and by how much.

A pixel diff can show that ink changed. It cannot tell the reviewer whether the
same room was measured the same way on both plans. PicCompare AEC Agent measures
the elements, matches them across revisions, and refuses to claim a change when
the definitions differ.

## What is measured today

Offline, on 12 synthetic pairs with exact ground truth:

- 12/12 pairs pass.
- 11 expected findings: 7 verified, 4 definition mismatches refused.
- 0 false positives.
- A pixel-change baseline would flag 11 changes; the agent refuses the 4
  definitions it cannot compare.

This is a technical proof on synthetic data, not a human-time study or a
real-world accuracy claim.

## Why it matters

The value is not “another diff”. It is a review that can say:

- this room is 2.0 m² larger and the measurements support it;
- this room was split into two; the definitions are not the same, so the agent
  will not claim a measured change;
- here is the hashed evidence a second reviewer or agent can replay.

## Next validation step

Run the same workflow with a design partner on redacted real plans, measure
reviewer time and false-change acceptance, and keep the synthetic results
separate from real-world claims.
