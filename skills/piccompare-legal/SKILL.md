---
name: piccompare-legal
description: DRAFT — legal exhibit verification using the PicCompare AEC measurement workflow. Not yet backed by legal fixtures or a live model.
---

# PicCompare legal exhibit verification (draft)

## When to use

Planned for legal analysts comparing scanned exhibits, signature pages and
inserted pages. **Status: draft.** The public repository currently implements
the AEC measurement workflow only; do not use this skill as a production legal
verification claim.

## Prerequisites

- The implemented `piccompare-aec` skill and its CLI.
- Synthetic legal fixture pairs with explicit ground truth. No customer,
  confidential or employer documents.

## Workflow

1. Use `python -m aec measure` only after legal fixtures and the corresponding
   comparison workflow are implemented.
2. Until then, use the AEC skill on synthetic floor plans and label the result
   as a draft.
3. Keep every finding tied to evidence; never claim a legal conclusion.

## Evidence

The same hashed report contract is the target: input hashes, element/crop
references, model receipts and a replay digest. No “signed” claim.

## Limitations

- Legal fixtures are not implemented in the public repo.
- No legal advice, authentication or court-admissibility claim.
- This skill is a draft for a future integration, not a shipped capability.
