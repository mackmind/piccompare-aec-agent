"""Pixel-to-real-unit calibration for floor plans."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Units = Literal["m", "mm"]
Source = Literal["known_dimension", "scale_bar", "config"]


@dataclass(frozen=True)
class ScaleCalibration:
    px_per_unit: float
    units: Units
    source: Source
    known_dimension_px: float | None = None
    known_dimension_real: float | None = None

    def __post_init__(self) -> None:
        if self.px_per_unit <= 0:
            raise ValueError("px_per_unit must be positive")
        if self.units not in ("m", "mm"):
            raise ValueError("units must be 'm' or 'mm'")
        if self.source not in ("known_dimension", "scale_bar", "config"):
            raise ValueError("unsupported scale source")

    def to_real_length(self, length_px: float) -> float:
        return length_px / self.px_per_unit

    def to_real_area(self, area_px2: float) -> float:
        return area_px2 / (self.px_per_unit * self.px_per_unit)

    @classmethod
    def from_known_dimension(
        cls,
        units: Units,
        known_dimension_px: float,
        known_dimension_real: float,
        px_per_unit: float | None = None,
    ) -> ScaleCalibration:
        if known_dimension_px <= 0 or known_dimension_real <= 0:
            raise ValueError("known dimensions must be positive")
        computed = px_per_unit if px_per_unit is not None else (
            known_dimension_px / known_dimension_real
        )
        return cls(
            px_per_unit=computed,
            units=units,
            source="known_dimension",
            known_dimension_px=known_dimension_px,
            known_dimension_real=known_dimension_real,
        )

    @classmethod
    def from_scale_bar(
        cls,
        bar_px: float,
        bar_real: float,
        units: Units,
    ) -> ScaleCalibration:
        if bar_px <= 0 or bar_real <= 0:
            raise ValueError("scale bar values must be positive")
        return cls(
            px_per_unit=bar_px / bar_real,
            units=units,
            source="scale_bar",
            known_dimension_px=bar_px,
            known_dimension_real=bar_real,
        )
