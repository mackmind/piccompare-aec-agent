# Impact

## Who it is for

The user works in architecture, engineering and construction (AEC): the industry
that designs and builds buildings. Typically an architect, a construction reviewer
or a space planner. Their job is to decide whether a room resize, a wall move, a
split or a merge between two versions of a floor plan is real, and by how much.

A simple picture comparison can show that ink changed. It cannot tell the
reviewer whether the same room was measured the same way on both plans.
PicCompare AEC Agent measures the elements, matches them across revisions, and
refuses to claim a change when the definitions differ.

## What is measured today

Offline, on 12 prepared test pairs with known correct answers:

- 12 of 12 pairs pass.
- 11 expected findings: 7 verified, 4 definition mismatches refused.
- 0 false positives (reported changes that are not real).
- A simple picture-comparison baseline would flag 11 changes; the agent refuses
  the 4 definitions it cannot compare.

This is a technical proof on generated data, not a human-time study or a
real-world accuracy claim.

## Why it matters

The value is not "another difference view". It is a review that can say:

- this room is 2.0 square metres larger and the measurements support it;
- this room was split into two; the definitions are not the same, so the agent
  will not claim a measured change;
- here is the fingerprinted evidence a second reviewer or program can re-run.

## Next validation step

Run the same workflow with a design partner on redacted real plans, measure
reviewer time and how often false changes are accepted, and keep the generated
test results separate from real-world claims.
