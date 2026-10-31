"""Render an AEC report as one standalone HTML page.

The page carries its CSS inline and no JavaScript, and it loads no font, script
or image from the network, so it opens from a chat attachment, a USB stick or a
CI artifact with no server behind it. Every value taken from the report goes
through :func:`_text`, which escapes quotes as well as brackets: a value can
land in an attribute (``alt``, ``src``) as well as in text.

The renderer reads no clock and adds no timestamp of its own, so two renders of
the same report are byte-identical. Its one piece of I/O is reading card images
when ``embed_cards`` is set; those become ``data:`` URIs, so the page stays a
single file. The section order mirrors the Markdown renderer in
:mod:`aec.report`, including its rule that the evidence-cards section disappears
entirely when a report has no cards; the wording is this page's own, so the two
renderers cannot drift into quoting each other.
"""

from __future__ import annotations

import base64
import html
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from aec.models import EvidenceCard, Finding, Report

VIEWER_CSS = """
body { margin: 0; background: #f7f7f9; color: #16181d;
  font: 15px/1.5 "Segoe UI", system-ui, sans-serif; }
main { max-width: 1080px; margin: 0 auto; padding: 24px 20px 64px; }
h1 { font-size: 24px; margin: 0 0 12px; }
h2 { font-size: 18px; margin: 0 0 10px; }
section { margin-top: 32px; }
.demo-notice { margin: 0 0 16px; padding: 10px 12px; border: 1px solid #d9a521;
  border-radius: 6px; background: #fff5d6; }
.meta { display: flex; flex-wrap: wrap; gap: 6px 10px; margin: 0; }
.meta dt { font-weight: 600; }
.meta dd { margin: 0 16px 0 0; }
table { width: 100%; border-collapse: collapse; background: #ffffff; }
th, td { border: 1px solid #d7dbe3; padding: 6px 8px; text-align: left;
  vertical-align: top; }
th { background: #eceff4; font-weight: 600; white-space: nowrap; }
code { font: 13px/1.4 Consolas, ui-monospace, monospace; word-break: break-all; }
.note, .empty, .reasons { color: #545a66; }
ul { margin: 0; padding-left: 20px; }
.card-grid { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 12px; }
figure { margin: 0; padding: 8px; border: 1px solid #d7dbe3; background: #ffffff; }
img { display: block; max-width: 340px; height: auto; border: 1px solid #c4c9d3; }
figcaption { margin-top: 6px; color: #545a66; font-size: 13px; }
"""


class ViewerError(ValueError):
    """A page cannot be rendered from this report and these arguments."""


def render_report_html(
    report: Report,
    *,
    card_url_prefix: str | None = None,
    embed_cards: bool = False,
    cards_dir: Path | None = None,
) -> str:
    """Render ``report`` as a complete HTML document, byte-identically.

    ``card_url_prefix`` is a same-origin URL path a card image is served under,
    so its ``src`` becomes ``<prefix>/<basename>``; without one a card keeps the
    path recorded in the report, which is relative to the report's directory.
    ``embed_cards`` inlines the PNG bytes read from ``cards_dir`` as ``data:``
    URIs instead, which is the only reason this function touches the disk.
    """
    parts = [
        _header(report),
        _section(
            "findings",
            "Findings",
            _findings_body(report.findings, "No verified material change."),
        ),
        _section("not-compared", "Not compared", _not_compared_body(report)),
        _section(
            "rejected",
            "Rejected",
            _findings_body(report.rejected, "No candidate was refused."),
        ),
        _section("measurements", "Measurements", _measurements_body(report)),
    ]
    if report.evidence_cards:
        parts.append(
            _section(
                "evidence-cards",
                "Evidence cards",
                _cards_body(
                    report,
                    card_url_prefix=card_url_prefix,
                    embed_cards=embed_cards,
                    cards_dir=cards_dir,
                ),
            )
        )
    parts.extend(
        [
            _section("digest", "Report digest", _digest_body(report)),
            _section("limitations", "Limitations", _limitations_body(report)),
            _section("usage", "Usage", _usage_body(report)),
        ]
    )
    return "\n".join(
        [
            "<!DOCTYPE html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            f"<title>{_text(f'PicCompare AEC report - {report.plan.pair_id}')}</title>",
            "<style>" + VIEWER_CSS + "</style>",
            "</head>",
            "<body>",
            "<main>",
            *parts,
            "</main>",
            "</body>",
            "</html>",
            "",
        ]
    )


def _text(value: object) -> str:
    """Escape one report value for text and attribute contexts alike."""
    return html.escape(str(value), quote=True)


def _code(value: object) -> str:
    return f"<code>{_text(value)}</code>"


def _joined(values: Sequence[object]) -> str:
    """One escaped cell holding a comma-separated list, or ``none``."""
    if not values:
        return _text("none")
    return _text(", ".join(str(value) for value in values))


def _section(section_id: str, title: str, body: str) -> str:
    return (
        f'<section id="{_text(section_id)}">\n'
        f"<h2>{_text(title)}</h2>\n"
        f"{body}\n"
        "</section>"
    )


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    """Build a table. A cell is a fragment this module escaped already."""
    head = "".join(f"<th>{_text(header)}</th>" for header in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>"
        for row in rows
    )
    return "\n".join(
        [
            "<table>",
            f"<thead><tr>{head}</tr></thead>",
            f"<tbody>{body}</tbody>",
            "</table>",
        ]
    )


def _header(report: Report) -> str:
    return "\n".join(
        [
            '<header id="header">',
            "<h1>PicCompare AEC report</h1>",
            f'<p class="demo-notice"><strong>{_text(report.demo_notice)}</strong></p>',
            '<dl class="meta">',
            f"<dt>Pair</dt><dd>{_code(report.plan.pair_id)}</dd>",
            f"<dt>Generated</dt><dd>{_text(report.generated_at)}</dd>",
            "</dl>",
            "</header>",
        ]
    )


def _findings_body(findings: Sequence[Finding], empty: str) -> str:
    if not findings:
        return f'<p class="empty">{_text(empty)}</p>'
    rows = [
        [
            _code(finding.finding_id),
            _text(finding.change_type),
            _text(finding.materiality),
            _joined(finding.element_ids),
            _text(finding.claim),
            _joined(finding.reasons),
        ]
        for finding in findings
    ]
    return _table(
        ["Finding", "Change type", "Materiality", "Elements", "Claim", "Reasons"],
        rows,
    )


def _not_compared_body(report: Report) -> str:
    if not report.not_compared:
        return '<p class="empty">Every element was compared.</p>'
    items = [
        f"<li>{_code(finding.finding_id)} &ndash; {_text(finding.claim)} "
        f'<span class="reasons">({_joined(finding.reasons)})</span></li>'
        for finding in report.not_compared
    ]
    return "\n".join(["<ul>", *items, "</ul>"])


def _delta(value: float | None) -> str:
    return "n/a" if value is None else f"{value:+.3f}"


def _delta_list(values: Sequence[float]) -> str:
    return ", ".join(f"{value:.3f}" for value in values) if values else "none"


def _measurements_body(report: Report) -> str:
    if not report.measurements:
        return '<p class="empty">No measurement was recorded.</p>'
    rows = [
        [
            _code(measurement.element_id),
            _text(measurement.status),
            _text(_delta(measurement.area_delta_m2)),
            _text(_delta_list(measurement.segment_deltas_px)),
            _text(_delta_list(measurement.angle_deltas_deg)),
            _joined(measurement.reasons),
        ]
        for measurement in report.measurements
    ]
    return _table(
        [
            "Element",
            "Status",
            "Area delta (m2)",
            "Segment deltas (px)",
            "Angle deltas (deg)",
            "Reasons",
        ],
        rows,
    )


def _cards_body(
    report: Report,
    *,
    card_url_prefix: str | None,
    embed_cards: bool,
    cards_dir: Path | None,
) -> str:
    change_types = {
        item.finding_id: item.change_type
        for item in [*report.findings, *report.rejected, *report.not_compared]
    }
    prefix = None if card_url_prefix is None else _checked_prefix(card_url_prefix)
    rows = [
        [
            _code(card.finding_id),
            _text(change_types.get(card.finding_id, "unknown")),
            _text(card.side),
            _code(card.path),
            _code(card.sha256),
            _text(card.bytes),
        ]
        for card in report.evidence_cards
    ]
    figures = [
        _figure(
            card,
            _card_src(
                card,
                prefix=prefix,
                embed_cards=embed_cards,
                cards_dir=cards_dir,
            ),
        )
        for card in report.evidence_cards
    ]
    return "\n".join(
        [
            _table(
                ["Finding", "Change type", "Side", "Path", "SHA-256", "Bytes"],
                rows,
            ),
            '<div class="card-grid">',
            *figures,
            "</div>",
        ]
    )


def _checked_prefix(prefix: str) -> str:
    """Refuse a prefix that is a location rather than a same-origin URL path.

    A drive letter, a scheme, a protocol-relative host or a backslash would put
    an absolute path or a remote asset into the page.
    """
    if ":" in prefix or "\\" in prefix or prefix.startswith("//"):
        raise ViewerError(
            "card_url_prefix must be a same-origin URL path, not a location"
        )
    return prefix.rstrip("/")


def _card_src(
    card: EvidenceCard,
    *,
    prefix: str | None,
    embed_cards: bool,
    cards_dir: Path | None,
) -> str:
    if embed_cards:
        return _data_uri(card, cards_dir)
    if prefix is None:
        return card.path
    return f"{prefix}/{card.path.rpartition('/')[2]}"


def _data_uri(card: EvidenceCard, cards_dir: Path | None) -> str:
    if cards_dir is None:
        raise ViewerError(
            "embed_cards needs the directory that holds the report's cards"
        )
    try:
        data = (cards_dir / card.path).read_bytes()
    except OSError as error:
        # Only the report's relative path goes in the message: the absolute
        # location is exactly what this module must never emit.
        raise ViewerError(f"cannot read card image: {card.path}") from error
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


def _figure(card: EvidenceCard, src: str) -> str:
    alt = f"{card.finding_id} side {card.side}"
    return "\n".join(
        [
            "<figure>",
            f'<img src="{_text(src)}" alt="{_text(alt)}">',
            f"<figcaption>{_text(alt)}</figcaption>",
            "</figure>",
        ]
    )


def _digest_body(report: Report) -> str:
    return "\n".join(
        [
            f"<p>{_code(report.digest)}</p>",
            '<p class="note">The digest is a SHA-256 over every other field of '
            "this report.</p>",
        ]
    )


def _limitations_body(report: Report) -> str:
    if not report.limitations:
        return '<p class="empty">No limitation was recorded.</p>'
    items = [f"<li>{_text(limitation)}</li>" for limitation in report.limitations]
    return "\n".join(["<ul>", *items, "</ul>"])


def _usage_value(value: Any) -> str:
    """A usage value as escaped text; anything structured stays canonical JSON."""
    if isinstance(value, str):
        return _text(value)
    return _text(json.dumps(value, ensure_ascii=True, sort_keys=True))


def _usage_body(report: Report) -> str:
    if not report.usage:
        return '<p class="empty">No usage was recorded.</p>'
    rows = [
        [_text(field), _usage_value(value)]
        for field, value in sorted(report.usage.items())
    ]
    return _table(["Field", "Value"], rows)
