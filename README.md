# PicCompare AEC Agent — public scaffold

A public scaffold for PicCompare's AEC measurement-verification entry in the
Meta Global AI Developer Hackathon (Indie Developer track, 2026-10-27 to
2026-11-04).

**Status:** scaffold only. The functional workflow is being built during the
event. This repository does not contain a working AEC implementation yet.

**Working one-liner:** Every batch. Every doc. Every pixel. Eyes or APIs — both
first-class. See it. Check it. Replay it.

## What this repository is

The public, MIT-licensed integration layer. It is where the event's public AEC
measurement-verification code, synthetic fixtures, public report schema and
tests will live as they are built during the event.

## What this repository is not

- It is not the PicCompare engine. The engine is a separate proprietary product;
  it is not included, linked or licensed here.
- It does not include customer, employer or confidential documents.
- It does not include internal plans, design documents, commercial strategy or
  private evaluation data.
- It does not grant any licence to the PicCompare engine or its commercial
  components.

## Development gates

The public repository runs `pytest`, `ruff`, `mypy`, the repository boundary
check (`scripts/check_boundary.py`) and the bootstrap acceptance check
(`scripts/accept_aec.py --offline`) in CI. The boundary check rejects engine
imports, engine markers, secrets and local machine manifests.

## Licence

MIT for this repository only. See [LICENSE](LICENSE) and [NOTICE](NOTICE). The
PicCompare engine remains separate and proprietary.

## Event

Meta Global AI Developer Hackathon, Indie Developer track, October 27 –
November 4, 2026. Submission deadline: November 4, 2026, 9:00 PM ET.
