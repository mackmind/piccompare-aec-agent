from __future__ import annotations

import pytest
from factories import defaults, fake_meta_client

from aec.planner import Planner, PlannerError


def test_planner_returns_valid_spec() -> None:
    client = fake_meta_client(
        {
            "pair_id": "p1",
            "units": "m",
            "px_per_unit": 100,
            "element_types": ["room"],
            "area_tolerance_m2": 0.05,
            "dimension_tolerance_px": 2,
            "angle_tolerance_deg": 1,
            "material_area_delta_m2": 0.1,
            "scale_source": "config",
        }
    )
    spec = Planner(client).plan("measure rooms", defaults())
    assert spec.px_per_unit == 100


def test_planner_rejects_invalid_spec() -> None:
    client = fake_meta_client({"pair_id": "p1"})
    with pytest.raises(PlannerError):
        Planner(client).plan("measure rooms", defaults())
