"""Evidence cards: contract, cropper, collector and report wiring."""

from __future__ import annotations

import json

import pytest
from factories import sample_report
from pydantic import ValidationError

from aec.models import EvidenceCard, Report


def card(**overrides):
    values = {
        "finding_id": "room_resized:resize-01:a:0:room:0",
        "side": "a",
        "path": "cards/room_resized_resize-01_a_0_room_0-a.png",
        "sha256": "a" * 64,
        "bytes": 1024,
        "box_px": [92, 92, 508, 508],
        "page": 0,
        "source": "plan_raster",
    }
    values.update(overrides)
    return EvidenceCard(**values)


def test_evidence_card_contract_roundtrips() -> None:
    built = card()
    data = json.loads(built.model_dump_json())
    assert data["side"] == "a"
    assert data["source"] == "plan_raster"
    assert data["box_px"] == [92, 92, 508, 508]
    assert EvidenceCard.model_validate(data) == built


def test_evidence_card_rejects_a_short_sha256() -> None:
    with pytest.raises(ValidationError):
        card(sha256="abc")


def test_evidence_card_rejects_a_non_hex_sha256() -> None:
    with pytest.raises(ValidationError):
        card(sha256="g" * 64)


def test_evidence_card_rejects_absolute_and_backslash_paths() -> None:
    for bad in ["/cards/x.png", "cards\\x.png", "C:/cards/x.png"]:
        with pytest.raises(ValidationError):
            card(path=bad)


def test_evidence_card_requires_four_box_values() -> None:
    with pytest.raises(ValidationError):
        card(box_px=[1, 2, 3])


def test_evidence_card_requires_negative_bytes_and_page_to_be_rejected() -> None:
    with pytest.raises(ValidationError):
        card(bytes=-1)
    with pytest.raises(ValidationError):
        card(page=-1)


def test_evidence_card_requires_known_side_and_source() -> None:
    with pytest.raises(ValidationError):
        card(side="c")
    with pytest.raises(ValidationError):
        card(source="engine_crop")


def test_report_defaults_to_no_cards_and_accepts_an_old_json() -> None:
    report = sample_report()
    assert report.evidence_cards == []
    data = json.loads(report.model_dump_json())
    assert data["evidence_cards"] == []
    data.pop("evidence_cards")  # a report written before the field existed
    loaded = Report.model_validate(data)
    assert loaded.evidence_cards == []


def test_report_accepts_cards() -> None:
    report = sample_report().model_copy(update={"evidence_cards": [card()]})
    assert report.evidence_cards[0].finding_id == card().finding_id
