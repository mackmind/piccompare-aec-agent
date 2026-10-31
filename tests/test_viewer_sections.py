"""The report viewer's text sections, rendered from a real fixture report."""

from __future__ import annotations

import html as html_module
from pathlib import Path

import pytest
from factories import sample_report

from aec.models import Report
from aec.pipeline import run_pair
from aec.viewer import render_report_html

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "fixtures" / "aec" / "resize-01"
SECTION_IDS = [
    "findings",
    "not-compared",
    "rejected",
    "measurements",
    "digest",
    "limitations",
    "usage",
]


@pytest.fixture(scope="module")
def fixture_report() -> Report:
    """The real offline report for resize-01, measured once for this module."""
    return run_pair(FIXTURE).report


def test_the_finding_row_names_the_change_and_both_elements(
    fixture_report: Report,
) -> None:
    page = render_report_html(fixture_report)
    finding = fixture_report.findings[0]
    assert finding.finding_id in page
    assert finding.change_type in page
    assert finding.materiality in page
    # Both sides of the finding must be visible; an element id that appears
    # only in the measurements table would not identify the finding's pair.
    for element_id in finding.element_ids:
        assert element_id in page


def test_the_measurement_table_carries_the_area_delta(fixture_report: Report) -> None:
    page = render_report_html(fixture_report)
    changed = [item for item in fixture_report.measurements if item.area_delta_m2]
    assert changed
    assert f"{changed[0].area_delta_m2:+.3f}" in page


def test_the_page_carries_the_report_digest(fixture_report: Report) -> None:
    page = render_report_html(fixture_report)
    assert fixture_report.digest in page


def test_every_limitation_is_rendered(fixture_report: Report) -> None:
    page = render_report_html(fixture_report)
    assert fixture_report.limitations
    for limitation in fixture_report.limitations:
        # Text is escaped with quotes, so the apostrophe in "element's" arrives
        # as an entity; compare against the escaped form, not the raw string.
        assert html_module.escape(limitation, quote=True) in page


def test_the_header_names_the_pair_the_time_and_the_demo_notice(
    fixture_report: Report,
) -> None:
    page = render_report_html(fixture_report)
    assert fixture_report.plan.pair_id in page
    assert fixture_report.generated_at in page
    assert html_module.escape(fixture_report.demo_notice, quote=True) in page


def test_the_sections_appear_in_the_documented_order(fixture_report: Report) -> None:
    page = render_report_html(fixture_report)
    positions = [page.index(f'<section id="{name}">') for name in SECTION_IDS]
    assert positions == sorted(positions)
    assert page.index('<header id="header">') < positions[0]


def test_the_page_is_one_standalone_document(fixture_report: Report) -> None:
    page = render_report_html(fixture_report)
    assert page.startswith("<!DOCTYPE html>")
    assert '<meta charset="utf-8">' in page
    assert "<style>" in page and "</style>" in page
    # No script and no remote asset: the page must open with no network at all.
    assert "<script" not in page.lower()
    assert "http://" not in page and "https://" not in page
    assert page.rstrip().endswith("</html>")


def test_empty_sections_say_so_in_the_viewer_s_own_words() -> None:
    page = render_report_html(sample_report())
    assert "No verified material change." in page
    assert "Every element was compared." in page
    assert "No candidate was refused." in page
    assert "No measurement was recorded." in page
    assert "No limitation was recorded." in page
    assert "No usage was recorded." in page
