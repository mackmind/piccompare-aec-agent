"""Evidence cards: contract, cropper, collector and report wiring."""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from typing import Literal

import pytest
from factories import sample_report
from PIL import Image, ImageStat
from pydantic import ValidationError

from aec import cards as cards_module
from aec.cards import (
    CardError,
    card_box,
    card_filename,
    collect_cards,
    element_side,
    render_card,
)
from aec.evidence import sha256_file
from aec.models import Element, EvidenceCard, Finding, PageGeometry, Report
from aec.pipeline import run_pair

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "fixtures" / "aec" / "resize-01"
PAGE = PageGeometry(page=0, width=1600, height=1200)
A_ROOM = "resize-01:a:0:room:0"
B_ROOM = "resize-01:b:0:room:0"


def finding(
    finding_id: str,
    element_ids: list[str],
    materiality: Literal["high", "medium", "low"] = "high",
) -> Finding:
    return Finding(
        finding_id=finding_id,
        change_type="room_resized",
        element_ids=element_ids,
        materiality=materiality,
        status="verified",
        claim="c",
        evidence_refs=list(element_ids),
        measurement_refs=[],
        reasons=[],
    )


def pair_elements() -> dict[str, Element]:
    result = run_pair(FIXTURE)
    return {element.element_id: element for element in [*result.elements_a, *result.elements_b]}


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


def test_card_box_rejects_a_polygon_wholly_left_of_the_page() -> None:
    # Clamping this used to return [0, 0, 1, 1]: a one-pixel sliver written as
    # that finding's crop.
    with pytest.raises(CardError, match="outside the page"):
        card_box([[-100.0, -100.0], [-50.0, -50.0]], PAGE)


def test_card_box_rejects_a_polygon_wholly_above_the_page() -> None:
    # Inside the page horizontally, but every y is above the top edge.
    with pytest.raises(CardError, match="outside the page"):
        card_box([[100.0, -100.0], [200.0, -50.0]], PAGE)


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


def test_render_card_rejects_a_box_without_four_values() -> None:
    with pytest.raises(CardError):
        render_card(FIXTURE / "a.png", [0, 0, 10])


def test_element_side_reads_the_pipeline_id_convention() -> None:
    assert element_side("resize-01:a:0:room:0") == "a"
    assert element_side("resize-01:b:0:room:0") == "b"
    assert element_side("resize-01:c:0:room:0") is None
    assert element_side("custom-1") is None


def test_card_filename_is_safe_and_stable() -> None:
    name = card_filename("room_resized:resize-01:a:0:room:0", "a")
    assert name == "room_resized_resize-01_a_0_room_0-a.png"
    assert ":" not in name and name.endswith("-a.png")
    assert card_filename(":::", "b") == "card-b.png"


def test_collect_cards_writes_one_card_per_side(tmp_path) -> None:
    result = run_pair(FIXTURE)
    evidence: dict = {}
    cards = collect_cards(
        tmp_path, FIXTURE, result.verified, pair_elements(), evidence=evidence
    )
    assert [(item.side, item.box_px) for item in cards] == [
        ("a", [92, 92, 508, 508]),
        ("b", [92, 92, 558, 508]),
    ]
    assert len({(item.finding_id, item.side) for item in cards}) == 2
    for item in cards:
        png = tmp_path / item.path
        assert png.is_file()
        assert sha256_file(png) == item.sha256
        assert png.stat().st_size == item.bytes
        assert item.source == "plan_raster"
        assert item.page == 0
        assert item.path.startswith("cards/")
        assert "\\" not in item.path
    assert evidence["cards_truncated"] is False
    assert evidence["cards_dropped"] == 0
    assert evidence["cards_skipped"] == []


def test_collect_cards_dedupes_a_repeated_finding(tmp_path) -> None:
    result = run_pair(FIXTURE)
    duplicated = [*result.verified, *result.verified]
    cards = collect_cards(tmp_path, FIXTURE, duplicated, pair_elements())
    assert len(cards) == 2


def test_collect_cards_orders_by_materiality_then_finding_id(tmp_path) -> None:
    low = finding("z_low", [A_ROOM, B_ROOM], "low")
    high_b = finding("b_high", [A_ROOM, B_ROOM], "high")
    high_a = finding("a_high", [A_ROOM, B_ROOM], "high")
    cards = collect_cards(
        tmp_path, FIXTURE, [low, high_b, high_a], pair_elements()
    )
    assert [(item.finding_id, item.side) for item in cards] == [
        ("a_high", "a"),
        ("a_high", "b"),
        ("b_high", "a"),
        ("b_high", "b"),
        ("z_low", "a"),
        ("z_low", "b"),
    ]


def test_collect_cards_caps_at_the_limit_and_flags_truncation(tmp_path) -> None:
    result = run_pair(FIXTURE)
    evidence: dict = {}
    cards = collect_cards(
        tmp_path, FIXTURE, result.verified, pair_elements(), limit=1, evidence=evidence
    )
    assert [item.side for item in cards] == ["a"]
    assert evidence["cards_truncated"] is True
    assert evidence["cards_dropped"] == 1


def test_collect_cards_with_a_zero_limit_writes_nothing(tmp_path) -> None:
    result = run_pair(FIXTURE)
    evidence: dict = {}
    cards = collect_cards(
        tmp_path, FIXTURE, result.verified, pair_elements(), limit=0, evidence=evidence
    )
    assert cards == []
    assert evidence["cards_truncated"] is True
    assert not (tmp_path / "cards").exists()


def test_collect_cards_honours_an_explicit_side_list(tmp_path) -> None:
    result = run_pair(FIXTURE)
    cards = collect_cards(
        tmp_path, FIXTURE, result.verified, pair_elements(), sides=("a",)
    )
    assert [item.side for item in cards] == ["a"]


def test_collect_cards_skips_a_missing_page_raster(tmp_path) -> None:
    result = run_pair(FIXTURE)
    evidence: dict = {}
    cards = collect_cards(
        tmp_path,
        tmp_path / "no-such-fixture",
        result.verified,
        pair_elements(),
        evidence=evidence,
    )
    assert cards == []
    assert len(evidence["cards_skipped"]) == 2
    assert all("page raster" in skip["reason"] for skip in evidence["cards_skipped"])


def test_collect_cards_skips_a_missing_element(tmp_path) -> None:
    result = run_pair(FIXTURE)
    evidence: dict = {}
    cards = collect_cards(tmp_path, FIXTURE, result.verified, {}, evidence=evidence)
    assert cards == []
    assert all("missing element" in skip["reason"] for skip in evidence["cards_skipped"])


def test_collect_cards_refuses_an_oversized_file(tmp_path, monkeypatch) -> None:
    result = run_pair(FIXTURE)
    monkeypatch.setattr(cards_module, "MAX_CARD_BYTES", 1)
    evidence: dict = {}
    cards = collect_cards(
        tmp_path, FIXTURE, result.verified, pair_elements(), evidence=evidence
    )
    assert cards == []
    assert evidence["cards_truncated"] is False
    assert all("MAX_CARD_BYTES" in skip["reason"] for skip in evidence["cards_skipped"])
    assert not any((tmp_path / "cards").glob("*.png"))


def test_collect_cards_skips_a_page_without_a_raster(tmp_path) -> None:
    elements = pair_elements()
    sourceless = elements[A_ROOM].model_copy(
        update={"element_id": "resize-02:a:1:room:0", "page": 1}
    )
    by_id = {sourceless.element_id: sourceless}
    evidence: dict = {}
    cards = collect_cards(
        tmp_path,
        FIXTURE,
        [finding("page1", [sourceless.element_id])],
        by_id,
        evidence=evidence,
    )
    assert cards == []
    reasons = [skip["reason"] for skip in evidence["cards_skipped"]]
    assert any("page 1" in reason for reason in reasons)


def test_collect_cards_skips_a_degenerate_polygon(tmp_path) -> None:
    elements = pair_elements()
    empty = elements[A_ROOM].model_copy(update={"polygon_px": []})
    evidence: dict = {}
    cards = collect_cards(
        tmp_path,
        FIXTURE,
        [finding("empty", [empty.element_id])],
        {empty.element_id: empty},
        sides=("a",),
        evidence=evidence,
    )
    assert cards == []
    assert "empty polygon" in evidence["cards_skipped"][0]["reason"]


def test_collect_cards_avoids_a_filename_collision(tmp_path) -> None:
    first = finding("a:b", [A_ROOM])
    second = finding("a/b", [A_ROOM])
    cards = collect_cards(
        tmp_path, FIXTURE, [first, second], pair_elements(), sides=("a",)
    )
    assert len(cards) == 2
    assert len({item.path for item in cards}) == 2
    for item in cards:
        assert (tmp_path / item.path).is_file()


def test_collect_cards_reports_an_unreadable_raster(tmp_path, monkeypatch) -> None:
    result = run_pair(FIXTURE)

    def broken_open(*args, **kwargs):
        raise OSError("cannot read")

    monkeypatch.setattr(cards_module.Image, "open", broken_open)
    evidence: dict = {}
    cards = collect_cards(
        tmp_path, FIXTURE, result.verified, pair_elements(), evidence=evidence
    )
    assert cards == []
    assert all("unreadable" in skip["reason"] for skip in evidence["cards_skipped"])


def test_collect_cards_rejects_a_negative_limit(tmp_path) -> None:
    result = run_pair(FIXTURE)
    with pytest.raises(CardError):
        collect_cards(
            tmp_path, FIXTURE, result.verified, pair_elements(), limit=-1
        )


def test_collect_cards_falls_back_to_positional_sides(tmp_path) -> None:
    elements = pair_elements()
    left = elements[A_ROOM].model_copy(update={"element_id": "left"})
    right = elements[B_ROOM].model_copy(update={"element_id": "right"})
    cards = collect_cards(
        tmp_path,
        FIXTURE,
        [finding("no-side", ["left", "right"])],
        {"left": left, "right": right},
    )
    assert [(item.side, item.box_px) for item in cards] == [
        ("a", [92, 92, 508, 508]),
        ("b", [92, 92, 558, 508]),
    ]
