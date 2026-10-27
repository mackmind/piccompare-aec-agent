---
name: piccompare-print
description: DRAFT — print/barcode revision verification using the PicCompare AEC measurement workflow. Not yet backed by print fixtures or a live model.
---

# PicCompare print/barcode verification (draft)

## When to use

Planned for prepress analysts comparing print artwork, barcode payloads and
title-block revisions. **Status: draft.** The public repository currently
implements the AEC measurement workflow only.

## Prerequisites

- The implemented `piccompare-aec` skill and its CLI.
- Synthetic print fixtures with explicit ground truth; no customer artwork.

## Workflow

1. Use `python -m aec measure` only after print fixtures and the barcode/
   title-block checks are implemented.
2. Until then, use the AEC skill on synthetic plans and label the result as a
   draft.
3. Never claim print production readiness or barcode certification.

## Evidence

Target the same hashed report contract: measured element evidence, input hashes,
model receipts and replay digest. No “signed” claim.

## Limitations

- Print fixtures and barcode/title-block checks are not implemented publicly.
- No production, certification or color-accuracy claim.
- This skill is a draft for a future integration, not a shipped capability.
