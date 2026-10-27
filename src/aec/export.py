"""Export measured plan overlays to SVG and DXF."""

from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

import ezdxf

from aec.models import Element, Report


def _elements(report: Report) -> list[Element]:
    return report.elements_b or report.elements_a


def _points(element: Element) -> list[tuple[float, float]]:
    return [(float(x), float(y)) for x, y in element.polygon_px]


def export_svg(report: Report, path: Path) -> None:
    width = report.pages[0].width if report.pages else 1600
    height = report.pages[0].height if report.pages else 1200
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="20" y="30" font-size="20" font-family="sans-serif">'
        f'{escape(report.plan.pair_id)} — {escape(report.demo_notice)}</text>',
    ]
    for element in _elements(report):
        points = " ".join(f"{x:.2f},{y:.2f}" for x, y in _points(element))
        parts.append(
            f'<polygon points="{points}" fill="#eeeeee" stroke="#111111" '
            f'stroke-width="4"/>'
        )
        cx, cy = element.centroid_px
        label = element.room_id or element.label
        parts.append(
            f'<text x="{cx:.2f}" y="{cy:.2f}" font-size="16" '
            f'font-family="sans-serif">{escape(label)} {element.area_m2:.2f} m²</text>'
        )
    parts.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(parts) + "\n", encoding="utf-8", newline="\n")


def export_dxf(report: Report, path: Path) -> None:
    document = ezdxf.new("R2010")  # type: ignore[attr-defined]
    document.header["$INSUNITS"] = 6 if report.plan.units == "m" else 4
    for layer, color in (("ROOMS", 7), ("LABELS", 2), ("AREAS", 3)):
        if layer not in document.layers:
            document.layers.add(layer, color=color)
    modelspace = document.modelspace()
    for element in _elements(report):
        points = _points(element)
        modelspace.add_lwpolyline(
            points, close=True, dxfattribs={"layer": "ROOMS"}
        )
        cx, cy = element.centroid_px
        label = element.room_id or element.label
        modelspace.add_text(
            label, dxfattribs={"layer": "LABELS", "height": 18}
        ).set_placement((cx, cy + 8))
        modelspace.add_text(
            f"{element.area_m2:.2f} m2", dxfattribs={"layer": "AREAS", "height": 14}
        ).set_placement((cx, cy - 14))
    path.parent.mkdir(parents=True, exist_ok=True)
    document.saveas(path)
