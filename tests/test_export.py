from __future__ import annotations

import ezdxf
from factories import sample_report

from aec.export import export_dxf, export_svg


def test_svg_contains_one_polygon_per_room(tmp_path) -> None:
    report = sample_report(rooms=3)
    path = tmp_path / "plan.svg"
    export_svg(report, path)
    text = path.read_text(encoding="utf-8")
    assert text.count("<polygon") == 3
    assert "m²" in text
    assert "HACKATHON DEMO" in text


def test_dxf_round_trips_room_layers(tmp_path) -> None:
    report = sample_report(rooms=3)
    path = tmp_path / "plan.dxf"
    export_dxf(report, path)
    document = ezdxf.readfile(path)
    assert len(document.modelspace().query("LWPOLYLINE[layer=='ROOMS']")) == 3
