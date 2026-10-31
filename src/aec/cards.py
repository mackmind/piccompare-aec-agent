"""Deterministic raster evidence cards cropped from the plan inputs.

A card is a local Pillow crop of the fixture page raster (``a.png`` or
``b.png``) around the measured element's box. It needs no engine comparison
session, no network and no model, so the same input always yields the same PNG
bytes within one Pillow version.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from io import BytesIO
from pathlib import Path

from PIL import Image

from aec.models import PageGeometry


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
