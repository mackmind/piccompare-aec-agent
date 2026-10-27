from __future__ import annotations

import pytest

from aec.scale import ScaleCalibration


def test_scale_converts_px_to_m2() -> None:
    scale = ScaleCalibration.from_known_dimension(
        px_per_unit=100,
        units="m",
        known_dimension_px=100,
        known_dimension_real=1.0,
    )
    assert scale.to_real_area(10000) == pytest.approx(1.0)
    assert scale.to_real_length(250) == pytest.approx(2.5)


def test_scale_from_scale_bar() -> None:
    scale = ScaleCalibration.from_scale_bar(bar_px=500, bar_real=5.0, units="m")
    assert scale.px_per_unit == pytest.approx(100)
    assert scale.to_real_area(160000) == pytest.approx(16.0)


def test_scale_rejects_invalid_values() -> None:
    with pytest.raises(ValueError):
        ScaleCalibration(px_per_unit=0, units="m", source="config")
    with pytest.raises(ValueError):
        ScaleCalibration.from_known_dimension(
            units="m", known_dimension_px=0, known_dimension_real=1.0
        )
