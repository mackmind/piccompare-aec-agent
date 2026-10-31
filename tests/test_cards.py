"""Evidence cards: contract, cropper, collector and report wiring."""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import pytest
from factories import sample_report
from PIL import Image, ImageStat
from pydantic import ValidationError

from aec.cards import CardError, card_box, render_card
from aec.models import EvidenceCard, PageGeometry, Report

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "fixtures" / "aec" / "resize-01"
PAGE = PageGeometry(page=0, width=1600, height=1200)


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


def test_card_box_is_the_padded_polygon_bbox() -> None:
    polygon = [[100.0, 100.0], [500.0, 100.0], [500.0, 500.0], [100.0, 500.0]]
    assert card_box(polygon, PAGE) == [92, 92, 508, 508]


def test_card_box_rounds_outward_on_fractional_polygons() -> None:
    polygon = [[100.4, 100.0], [500.6, 100.0], [500.6, 500.9], [100.4, 500.9]]
    assert card_box(polygon, PAGE) == [92, 92, 509, 509]


def test_card_box_pads_then_clamps_at_both_page_edges() -> None:
    top_left = [[0.0, 0.0], [20.0, 0.0], [20.0, 20.0], [0.0, 20.0]]
    assert card_box(top_left, PAGE) == [0, 0, 28, 28]
    bottom_right = [
        [1500.0, 1100.0],
        [1600.0, 1100.0],
        [1600.0, 1200.0],
        [1500.0, 1200.0],
    ]
    assert card_box(bottom_right, PAGE) == [1492, 1092, 1600, 1200]


def test_card_box_keeps_a_one_pixel_box_for_a_zero_pad_point() -> None:
    assert card_box([[5.0, 5.0]], PAGE, pad_px=0) == [5, 5, 6, 6]


def test_card_box_rejects_an_empty_polygon() -> None:
    with pytest.raises(CardError):
        card_box([], PAGE)


def test_card_box_rejects_a_polygon_outside_the_page() -> None:
    with pytest.raises(CardError):
        card_box([[2000.0, 2000.0], [2100.0, 2100.0]], PAGE)


def test_card_box_rejects_a_negative_pad() -> None:
    with pytest.raises(CardError):
        card_box([[100.0, 100.0], [200.0, 200.0]], PAGE, pad_px=-1)


def test_render_card_is_a_deterministic_rgb_png() -> None:
    image_path = FIXTURE / "a.png"
    box = [92, 92, 508, 508]
    first = render_card(image_path, box)
    second = render_card(image_path, box)
    assert first == second
    assert first.startswith(b"\x89PNG\r\n\x1a\n")
    with Image.open(BytesIO(first)) as image:
        assert image.mode == "RGB"
        assert image.size == (416, 416)
        assert max(ImageStat.Stat(image).stddev) > 0  # plan pixels, not a blank tile


def test_render_card_caps_the_long_side() -> None:
    data = render_card(FIXTURE / "b.png", [0, 0, 1600, 1200], max_side=200)
    with Image.open(BytesIO(data)) as image:
        assert image.size == (200, 150)


def test_render_card_rejects_a_box_outside_the_image() -> None:
    with pytest.raises(CardError):
        render_card(FIXTURE / "a.png", [1600, 0, 1700, 10])
    with pytest.raises(CardError):
        render_card(FIXTURE / "a.png", [10, 10, 10, 20])


def test_render_card_rejects_a_non_positive_max_side() -> None:
    with pytest.raises(CardError):
        render_card(FIXTURE / "a.png", [0, 0, 10, 10], max_side=0)
