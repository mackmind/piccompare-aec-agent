"""Deterministic raster evidence cards cropped from the plan inputs.

A card is a local Pillow crop of the fixture page raster (``a.png`` or
``b.png``) around the measured element's box. It needs no engine comparison
session, no network and no model, so the same input always yields the same PNG
bytes within one Pillow version.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from io import BytesIO
from pathlib import Path
from typing import Any, Literal

from PIL import Image

from aec.evidence import sha256_bytes
from aec.models import Element, EvidenceCard, Finding, PageGeometry

MAX_CARD_BYTES = 2 * 1024 * 1024
MATERIALITY_ORDER = {"high": 0, "medium": 1, "low": 2}
_UNSAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")
CARD_LIMITATION = (
    "Evidence cards are raster crops of the plan at the measured element's box; "
    "they show what was measured, not that the measurement is correct."
)


class CardError(ValueError):
    """A card cannot be produced from the supplied geometry or raster."""


def card_box(
    polygon_px: Sequence[Sequence[float]],
    page: PageGeometry,
    *,
    pad_px: int = 8,
) -> list[int]:
    """Return the padded polygon bounding box, clamped to the page.

    The result is a Pillow crop box ``[left, upper, right, lower]``: the right
    and lower edges are exclusive. Coordinates round outward so the full
    polygon stays inside the crop.
    """
    if pad_px < 0:
        raise CardError("pad_px must not be negative")
    points = [(float(point[0]), float(point[1])) for point in polygon_px]
    if not points:
        raise CardError("empty polygon: a card box needs at least one point")
    left = min(page.width, max(0, math.floor(min(x for x, _ in points)) - pad_px))
    top = min(page.height, max(0, math.floor(min(y for _, y in points)) - pad_px))
    right = min(page.width, max(0, math.ceil(max(x for x, _ in points)) + pad_px))
    bottom = min(page.height, max(0, math.ceil(max(y for _, y in points)) + pad_px))
    if right <= left:
        right = min(page.width, left + 1)
    if bottom <= top:
        bottom = min(page.height, top + 1)
    if right <= left or bottom <= top:
        raise CardError("card box lies outside the page")
    return [left, top, right, bottom]


def render_card(
    image_path: str | Path,
    box_px: Sequence[int],
    *,
    max_side: int = 512,
) -> bytes:
    """Crop ``box_px`` from the raster and return deterministic PNG bytes.

    The crop is converted to RGB and scaled down to ``max_side`` when needed.
    ``optimize=False`` keeps the encoder settings fixed; Pillow still owns the
    exact PNG bytes, which is why cards are hashed per run rather than pinned
    across Pillow versions.
    """
    if max_side < 1:
        raise CardError("max_side must be positive")
    if len(box_px) != 4:
        raise CardError("box_px needs four values")
    left, top, right, bottom = (int(value) for value in box_px)
    with Image.open(Path(image_path)) as image:
        width, height = image.size
        if not (0 <= left < right <= width and 0 <= top < bottom <= height):
            raise CardError("card box is outside the image")
        crop = image.convert("RGB").crop((left, top, right, bottom))
        if max(crop.size) > max_side:
            ratio = max_side / max(crop.size)
            crop = crop.resize(
                (max(1, round(crop.width * ratio)), max(1, round(crop.height * ratio))),
                Image.Resampling.LANCZOS,
            )
        buffer = BytesIO()
        crop.save(buffer, format="PNG", optimize=False)
    return buffer.getvalue()


def card_filename(finding_id: str, side: str) -> str:
    """Return a filesystem-safe card name for one finding and side.

    Finding ids contain colons (``room_resized:resize-01:a:0:room:0``), which
    Windows forbids in a file name, so every unsafe run collapses to ``_``.
    """
    stem = _UNSAFE_NAME.sub("_", finding_id).strip("._-") or "card"
    return f"{stem}-{side}.png"


def element_side(element_id: str) -> str | None:
    """Return the side encoded in an element id, when there is one.

    The pipeline builds ids as ``<pair>:<side>:<page>:<label>:<index>``, so
    the second field names the plan version the element came from.
    """
    parts = element_id.split(":")
    if len(parts) >= 2 and parts[1] in {"a", "b"}:
        return parts[1]
    return None


def _element_for_side(finding: Finding, side: str) -> str | None:
    for element_id in finding.element_ids:
        if element_side(element_id) == side:
            return element_id
    if (
        len(finding.element_ids) == 2
        and not any(element_side(element_id) for element_id in finding.element_ids)
    ):
        return finding.element_ids[0] if side == "a" else finding.element_ids[1]
    return None


def collect_cards(
    report_dir: str | Path,
    fixture_dir: str | Path,
    findings: Sequence[Finding],
    elements_by_id: Mapping[str, Element],
    *,
    sides: Sequence[Literal["a", "b"]] = ("a", "b"),
    limit: int = 12,
    max_side: int = 512,
    evidence: dict[str, Any] | None = None,
) -> list[EvidenceCard]:
    """Write one PNG per finding and side and return the matching contracts.

    Cards are ordered by materiality (high, medium, low) and then by
    ``finding_id``; the limit applies to that ordered candidate list before
    rendering, so a failed card never pulls in a lower-ranked one. Only page-0
    rasters are supported, because the fixture pair ships one image per side.
    A missing element, missing raster, degenerate polygon or oversized PNG is
    recorded in ``evidence["cards_skipped"]`` instead of raising, so one bad
    finding cannot abort the whole run.
    """
    if limit < 0:
        raise CardError("limit must not be negative")
    ordered = sorted(
        findings,
        key=lambda item: (MATERIALITY_ORDER[item.materiality], item.finding_id),
    )
    candidates: list[tuple[Finding, Literal["a", "b"]]] = []
    seen: set[tuple[str, str]] = set()
    for item in ordered:
        for side in sides:
            key = (item.finding_id, side)
            if key in seen:
                continue
            seen.add(key)
            candidates.append((item, side))
    selected = candidates[:limit]
    directory = Path(report_dir) / "cards"
    fixture = Path(fixture_dir)
    cards: list[EvidenceCard] = []
    skipped: list[dict[str, str]] = []
    used_names: dict[str, str] = {}

    def skip(item: Finding, side: Literal["a", "b"], reason: str) -> None:
        skipped.append(
            {"finding_id": item.finding_id, "side": side, "reason": reason}
        )

    for item, side in selected:
        element_id = _element_for_side(item, side)
        if element_id is None:
            skip(item, side, f"no element for side {side}")
            continue
        element = elements_by_id.get(element_id)
        if element is None:
            skip(item, side, f"missing element {element_id}")
            continue
        if element.page != 0:
            skip(item, side, f"no page raster for page {element.page}")
            continue
        image_path = fixture / f"{side}.png"
        if not image_path.is_file():
            skip(item, side, f"missing page raster {side}.png")
            continue
        try:
            with Image.open(image_path) as image:
                width, height = image.size
            page = PageGeometry(page=0, width=width, height=height)
            box = card_box(element.polygon_px, page)
            data = render_card(image_path, box, max_side=max_side)
        except CardError as error:
            skip(item, side, str(error))
            continue
        except OSError:
            skip(item, side, f"unreadable page raster {side}.png")
            continue
        if len(data) > MAX_CARD_BYTES:
            skip(item, side, f"card exceeds MAX_CARD_BYTES ({len(data)} bytes)")
            continue
        name = card_filename(item.finding_id, side)
        if name in used_names and used_names[name] != item.finding_id:
            suffix = sha256_bytes(item.finding_id.encode("utf-8"))[:8]
            name = f"{Path(name).stem}-{suffix}.png"
        used_names[name] = item.finding_id
        directory.mkdir(parents=True, exist_ok=True)
        (directory / name).write_bytes(data)
        cards.append(
            EvidenceCard(
                finding_id=item.finding_id,
                side=side,
                path=f"cards/{name}",
                sha256=sha256_bytes(data),
                bytes=len(data),
                box_px=box,
                page=0,
                source="plan_raster",
            )
        )
    if evidence is not None:
        evidence["cards_truncated"] = len(candidates) > len(selected)
        evidence["cards_dropped"] = len(candidates) - len(selected)
        evidence["cards_skipped"] = skipped
    return cards
