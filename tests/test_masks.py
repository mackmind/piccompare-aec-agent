from __future__ import annotations

import numpy as np
import pytest

from aec.geometry import polygon_area_px
from aec.masks import MaskError, mask_to_polygon


def test_mask_to_polygon_square_area() -> None:
    mask = np.zeros((10, 10), dtype=np.uint8)
    mask[2:9, 2:9] = 1
    polygon = mask_to_polygon(mask, tolerance_px=0.5)
    assert polygon[0] == polygon[-1]
    assert polygon_area_px(polygon) == pytest.approx(36, abs=1)


def test_empty_mask_raises() -> None:
    with pytest.raises(MaskError):
        mask_to_polygon(np.zeros((10, 10), dtype=np.uint8))
