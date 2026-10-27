"""Build measured elements from SAM objects."""

from __future__ import annotations

from collections.abc import Sequence

from aec.geometry import angles_deg, centroid_px, polygon_area_px, segments_px
from aec.models import Element, SamObject
from aec.scale import ScaleCalibration


def build_elements(
    objects: Sequence[SamObject],
    scale: ScaleCalibration,
    fixture: str,
) -> list[Element]:
    elements: list[Element] = []
    for index, obj in enumerate(objects):
        polygon = [(float(x), float(y)) for x, y in obj.polygon_px]
        area_px = polygon_area_px(polygon)
        centroid = centroid_px(polygon)
        elements.append(
            Element(
                element_id=f"{fixture}:{obj.page}:{obj.label}:{index}",
                page=obj.page,
                element_type=obj.label,
                label=obj.label,
                polygon_px=[list(point) for point in polygon],
                area_px2=area_px,
                area_m2=scale.to_real_area(area_px),
                centroid_px=[centroid[0], centroid[1]],
                segments_px=segments_px(polygon),
                angles_deg=angles_deg(polygon),
                source_objects=[obj.object_id],
                confidence=obj.score,
            )
        )
    return elements
