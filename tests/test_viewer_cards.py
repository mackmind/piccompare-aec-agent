"""Evidence cards in the viewer: the table, the images and their three sources."""

from __future__ import annotations

import base64
import hashlib
import re
import shutil
from pathlib import Path

import pytest

from aec.models import Report
from aec.pipeline import run_pair
from aec.viewer import ViewerError, render_report_html

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "fixtures" / "aec" / "resize-01"
DATA_URI = re.compile(r'src="data:image/png;base64,([^"]+)"')


@pytest.fixture(scope="module")
def card_report(tmp_path_factory: pytest.TempPathFactory) -> tuple[Report, Path]:
    """A real report with its cards written beside it, as a run leaves them."""
    directory = tmp_path_factory.mktemp("card-report")
    result = run_pair(FIXTURE, directory, cards=True)
    assert result.report.evidence_cards
    return result.report, directory


@pytest.fixture(scope="module")
def plain_report() -> Report:
    return run_pair(FIXTURE).report


def test_the_card_table_carries_the_path_hash_and_size(
    card_report: tuple[Report, Path],
) -> None:
    report, _ = card_report
    page = render_report_html(report)
    for card in report.evidence_cards:
        assert card.path in page
        assert card.sha256 in page
        assert f"<td>{card.bytes}</td>" in page
        assert f'alt="{card.finding_id} side {card.side}"' in page


def test_a_card_defaults_to_its_relative_report_path(
    card_report: tuple[Report, Path],
) -> None:
    report, _ = card_report
    page = render_report_html(report)
    for card in report.evidence_cards:
        assert f'src="{card.path}"' in page


def test_a_card_prefix_is_joined_to_the_basename(
    card_report: tuple[Report, Path],
) -> None:
    report, _ = card_report
    page = render_report_html(report, card_url_prefix="/run/abc123/card/")
    for card in report.evidence_cards:
        name = card.path.rpartition("/")[2]
        assert f'src="/run/abc123/card/{name}"' in page


def test_embedded_cards_are_data_uris_matching_the_recorded_hash(
    card_report: tuple[Report, Path],
) -> None:
    report, directory = card_report
    page = render_report_html(report, embed_cards=True, cards_dir=directory)
    payloads = DATA_URI.findall(page)
    assert len(payloads) == len(report.evidence_cards)
    for card, payload in zip(report.evidence_cards, payloads, strict=True):
        data = base64.b64decode(payload)
        assert len(data) == card.bytes
        assert hashlib.sha256(data).hexdigest() == card.sha256


def test_the_cards_section_sits_between_measurements_and_digest(
    card_report: tuple[Report, Path],
) -> None:
    report, _ = card_report
    page = render_report_html(report)
    assert (
        page.index('<section id="measurements">')
        < page.index('<section id="evidence-cards">')
        < page.index('<section id="digest">')
    )


def test_a_report_without_cards_has_no_cards_section(plain_report: Report) -> None:
    assert not plain_report.evidence_cards
    page = render_report_html(plain_report)
    assert 'id="evidence-cards"' not in page
    assert "Evidence cards" not in page


def test_the_page_never_carries_an_absolute_path(
    card_report: tuple[Report, Path],
) -> None:
    report, directory = card_report
    page = render_report_html(report, embed_cards=True, cards_dir=directory)
    assert str(directory) not in page
    assert directory.as_posix() not in page
    assert "file://" not in page
    assert not re.search(r"[A-Za-z]:[\\/]", page)


@pytest.mark.parametrize(
    "prefix",
    [
        "C:/reports",
        "file:///tmp/reports",
        "https://cdn.example.com/reports",
        "//host/reports",
        "cards\\nested",
    ],
)
def test_a_prefix_that_is_a_location_is_refused(
    card_report: tuple[Report, Path], prefix: str
) -> None:
    report, _ = card_report
    with pytest.raises(ViewerError, match="same-origin"):
        render_report_html(report, card_url_prefix=prefix)


def test_embedding_needs_the_directory_that_holds_the_cards(
    card_report: tuple[Report, Path],
) -> None:
    report, _ = card_report
    with pytest.raises(ViewerError, match="embed_cards"):
        render_report_html(report, embed_cards=True)


def test_a_missing_card_names_only_its_relative_path(
    card_report: tuple[Report, Path], tmp_path: Path
) -> None:
    report, _ = card_report
    with pytest.raises(ViewerError) as error:
        render_report_html(report, embed_cards=True, cards_dir=tmp_path)
    message = str(error.value)
    assert report.evidence_cards[0].path in message
    assert str(tmp_path) not in message


def test_an_embedded_card_whose_bytes_no_longer_match_is_refused(
    card_report: tuple[Report, Path], tmp_path: Path
) -> None:
    """The table prints the recorded hash, so altered bytes must not be inlined.

    The web app's card route already refuses a file edited after the run; this
    keeps the standalone page saying the same thing rather than showing the
    altered image beside the old hash.
    """
    report, directory = card_report
    copied = tmp_path / "copied"
    shutil.copytree(directory, copied)
    card = report.evidence_cards[0]
    image = copied / card.path
    image.write_bytes(image.read_bytes() + b"tampered")
    with pytest.raises(ViewerError) as error:
        render_report_html(report, embed_cards=True, cards_dir=copied)
    message = str(error.value)
    assert card.path in message
    assert str(copied) not in message
