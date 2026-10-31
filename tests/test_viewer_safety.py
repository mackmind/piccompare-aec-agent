"""Escaping and determinism: a hostile report renders as inert text, twice alike.

The page is a document a stranger may open, so a report field is data and never
markup. The tags below are read back with :class:`html.parser.HTMLParser`
rather than by searching for substrings: only a parser can say whether a payload
became a live element or stayed text, and only a parser can see an injected
attribute.
"""

from __future__ import annotations

import html as html_module
from html.parser import HTMLParser

import pytest
from factories import sample_report

from aec.models import EvidenceCard, Finding, MeasurementDelta, Report
from aec.viewer import render_report_html

PAYLOAD = r'<script>alert(1)</script> & "quoted" C:\Users\someone\plan.png'
QUOTED_BREAK = '" onmouseover="alert(1)'
WINDOWS_PATH = r"C:\Users\someone\plan.png"


class TagCollector(HTMLParser):
    """Every start tag and its attributes, with character references decoded."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag, dict(attrs)))


@pytest.fixture(scope="module")
def hostile_report() -> Report:
    """A report whose every free-text field carries the same payload."""
    base = sample_report()
    finding = Finding(
        finding_id=f"f1{QUOTED_BREAK}",
        change_type="room_resized",
        element_ids=[f"e1{QUOTED_BREAK}"],
        materiality="high",
        status="verified",
        claim=PAYLOAD,
        evidence_refs=["e"],
        measurement_refs=["m"],
        reasons=[PAYLOAD],
    )
    measurement = MeasurementDelta(
        element_id=f"m1{QUOTED_BREAK}",
        status="comparable",
        area_delta_m2=1.5,
        segment_deltas_px=[1.0],
        angle_deltas_deg=[0.5],
        reasons=[PAYLOAD],
    )
    card = EvidenceCard(
        finding_id=finding.finding_id,
        side="a",
        path=f'cards/a{QUOTED_BREAK}.png',
        sha256="ab" * 32,
        bytes=12,
        box_px=[0, 0, 1, 1],
        page=0,
        source="plan_raster",
    )
    return base.model_copy(
        update={
            "plan": base.plan.model_copy(update={"pair_id": PAYLOAD}),
            "demo_notice": PAYLOAD,
            "generated_at": f'2026-01-01T00:00:00+00:00{QUOTED_BREAK}',
            "findings": [finding],
            "measurements": [measurement],
            "evidence_cards": [card],
            "limitations": [PAYLOAD],
            "usage": {"note": PAYLOAD, "nested": {"a": [1, "<b>"]}},
        }
    )


def test_no_payload_becomes_a_live_element(hostile_report: Report) -> None:
    page = render_report_html(hostile_report)
    collector = TagCollector()
    collector.feed(page)
    names = {tag for tag, _ in collector.tags}
    assert "script" not in names
    assert "iframe" not in names and "object" not in names and "embed" not in names
    for _, attrs in collector.tags:
        for name in attrs:
            assert not name.startswith("on"), name
        for value in attrs.values():
            assert "javascript:" not in (value or "").lower()


def test_the_payload_arrives_as_escaped_text(hostile_report: Report) -> None:
    page = render_report_html(hostile_report)
    assert PAYLOAD not in page
    assert html_module.escape(PAYLOAD, quote=True) in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page


def test_quotes_and_ampersands_are_escaped(hostile_report: Report) -> None:
    page = render_report_html(hostile_report)
    assert "&quot;quoted&quot;" in page
    assert "&amp;" in page
    # The breakout would close an attribute early if the quote were not escaped.
    assert QUOTED_BREAK not in page


def test_the_windows_path_stays_text_and_never_becomes_a_location(
    hostile_report: Report,
) -> None:
    page = render_report_html(hostile_report)
    assert WINDOWS_PATH in page
    collector = TagCollector()
    collector.feed(page)
    for tag, attrs in collector.tags:
        if tag in {"img", "a", "link", "iframe", "script"}:
            assert not (attrs.get("src") or "").startswith("C:")
            assert not (attrs.get("href") or "").startswith("C:")


def test_two_renders_of_the_same_report_are_byte_identical(
    hostile_report: Report,
) -> None:
    assert render_report_html(hostile_report) == render_report_html(hostile_report)


def test_usage_key_order_does_not_change_the_page() -> None:
    # A dict built in another order is the same data; the page must not reveal
    # the order the caller happened to use.
    first = sample_report().model_copy(update={"usage": {"b": 1, "a": 2}})
    second = sample_report().model_copy(update={"usage": {"a": 2, "b": 1}})
    assert render_report_html(first) == render_report_html(second)
