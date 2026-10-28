---
name: piccompare-print
description: DRAFT — print and barcode revision verification using the PicCompare AEC (architecture, engineering and construction) measurement workflow. Not yet backed by print test examples or a live model.
---

# PicCompare print and barcode verification (draft)

## When to use

Planned for prepress analysts comparing print artwork, barcode payloads and
title-block revisions. **Status: draft.** The public repository currently
implements the AEC measurement workflow only.

## Prerequisites

- The implemented `piccompare-aec` skill and its command-line tool.
- Generated print test examples with explicit known correct answers; no customer
  artwork.

## Workflow

1. Use `python -m aec measure` only after print test examples and the barcode and
   title-block checks are implemented.
2. Until then, use the AEC skill on generated plans and label the result as a
   draft.
3. Never claim print production readiness or barcode certification.

## Evidence

Target the same fingerprinted (hashed) report contract: measured element evidence,
input fingerprints, model run records and a replay digest (a fingerprint of the
whole report). No "signed" claim.

## Limitations

- Print test examples and barcode/title-block checks are not implemented publicly.
- No production, certification or colour-accuracy claim.
- This skill is a draft for a future integration, not a shipped capability.
