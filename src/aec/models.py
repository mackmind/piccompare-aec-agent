"""Pydantic contracts for the AEC measurement-verification workflow.

The public integration uses these contracts; no PicCompare engine module is
imported here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

DEMO_NOTICE = "HACKATHON DEMO \u2014 NOT AN EVIDENCE RECORD"
REPORT_SCHEMA = "piccompare-aec-report/1.0"

T = TypeVar("T", bound=BaseModel)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PlanSpec(StrictModel):
    pair_id: str
    units: Literal["m", "mm"]
    px_per_unit: float = Field(gt=0)
    element_types: list[Literal["room", "space", "wall", "column", "stair"]]
    area_tolerance_m2: float = Field(gt=0)
    dimension_tolerance_px: float = Field(gt=0)
    angle_tolerance_deg: float = Field(gt=0)
    material_area_delta_m2: float = Field(gt=0)
    match_iou_threshold: float = Field(default=0.5, ge=0, le=1)
    match_centroid_tolerance_px: float = Field(default=8.0, gt=0)
    match_area_ratio_tolerance: float = Field(default=0.25, ge=0)
    scale_source: Literal["known_dimension", "scale_bar", "config"]


class PageGeometry(StrictModel):
    page: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class SamObject(StrictModel):
    object_id: str
    room_id: str | None = None
    room_label: str | None = None
    page: int = Field(ge=0)
    label: Literal["room", "space", "wall", "column", "stair", "unknown"]
    bbox_px: list[float] = Field(min_length=4, max_length=4)
    polygon_px: list[list[float]] = Field(min_length=3)
    score: float = Field(ge=0, le=1)
    source: Literal["sam31", "stub"]


class Element(StrictModel):
    element_id: str
    room_id: str | None = None
    page: int = Field(ge=0)
    element_type: str
    label: str
    polygon_px: list[list[float]]
    area_px2: float = Field(ge=0)
    area_m2: float = Field(ge=0)
    centroid_px: list[float]
    segments_px: list[float]
    angles_deg: list[float]
    source_objects: list[str]
    confidence: float = Field(ge=0, le=1)


class ElementMatch(StrictModel):
    a_id: str | None
    b_id: str | None
    status: Literal["matched", "ambiguous", "definition_mismatch", "unmatched"]
    iou: float | None
    centroid_delta_px: float | None
    area_ratio: float | None
    reasons: list[str]


class MeasurementDelta(StrictModel):
    element_id: str
    status: Literal["comparable", "not_compared", "no_material_change"]
    area_delta_m2: float | None
    segment_deltas_px: list[float]
    angle_deltas_deg: list[float]
    reasons: list[str]


class Finding(StrictModel):
    finding_id: str
    change_type: Literal[
        "room_resized",
        "wall_moved",
        "room_split",
        "room_merged",
        "room_added",
        "room_removed",
        "label_changed",
        "no_material_change",
    ]
    element_ids: list[str]
    materiality: Literal["high", "medium", "low"]
    status: Literal["verified", "rejected", "not_compared"]
    claim: str
    evidence_refs: list[str]
    measurement_refs: list[str]
    reasons: list[str]


class Report(StrictModel):
    schema_version: Literal["piccompare-aec-report/1.0"]
    demo_notice: str
    generated_at: str
    engine: dict[str, Any]
    inputs: dict[str, Any]
    settings: dict[str, Any]
    plan: PlanSpec
    pages: list[PageGeometry]
    elements_a: list[Element]
    elements_b: list[Element]
    matches: list[ElementMatch]
    measurements: list[MeasurementDelta]
    findings: list[Finding]
    rejected: list[Finding]
    not_compared: list[Finding]
    evidence: dict[str, Any]
    usage: dict[str, Any]
    limitations: list[str]
    digest: str


def dump_ascii_json(value: BaseModel, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value.model_dump(), indent=2, ensure_ascii=True) + "\n",
        encoding="ascii",
    )


def load_json_model(path: Path, model_type: type[T]) -> T:
    return model_type.model_validate_json(path.read_text(encoding="utf-8"))
