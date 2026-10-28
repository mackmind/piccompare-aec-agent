---
name: piccompare-legal
description: DRAFT — legal exhibit verification using the PicCompare AEC (architecture, engineering and construction) measurement workflow. Not yet backed by legal test examples or a live model.
---

# PicCompare legal exhibit verification (draft)

## When to use

Planned for legal analysts comparing scanned exhibits, signature pages and
inserted pages. **Status: draft.** The public repository currently implements
the AEC measurement workflow only; do not use this skill as a production legal
verification claim.

## Prerequisites

- The implemented `piccompare-aec` skill and its command-line tool.
- Generated legal test pairs with explicit known correct answers. No customer,
  confidential or employer documents.

## Workflow

1. Use `python -m aec measure` only after legal test examples and the
   corresponding comparison workflow are implemented.
2. Until then, use the AEC skill on generated floor plans and label the result
   as a draft.
3. Keep every finding tied to evidence; never claim a legal conclusion.

## Evidence

The same fingerprinted (hashed) report contract is the target: input fingerprints,
element and crop references, model run records and a replay digest (a fingerprint
of the whole report). No "signed" claim.

## Limitations

- Legal test examples are not implemented in the public repository.
- No legal advice, authentication or court-admissibility claim.
- This skill is a draft for a future integration, not a shipped capability.
