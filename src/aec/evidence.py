"""Hash and replay evidence for AEC reports."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aec.models import Element, MeasurementDelta, Report


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def sha256_value(value: Any) -> str:
    return sha256_bytes(canonical_json(value).encode("ascii"))


def element_hash(element: Element) -> str:
    return sha256_value(element.model_dump(mode="json"))


def measurement_hash(measurement: MeasurementDelta) -> str:
    return sha256_value(measurement.model_dump(mode="json"))


def build_evidence(
    *,
    inputs: dict[str, Path] | None = None,
    elements: list[Element] | None = None,
    measurements: list[MeasurementDelta] | None = None,
    receipts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "inputs": {
            name: sha256_file(path) for name, path in (inputs or {}).items()
        },
        "elements": {
            element.element_id: element_hash(element)
            for element in (elements or [])
        },
        "measurements": {
            measurement.element_id: measurement_hash(measurement)
            for measurement in (measurements or [])
        },
        "receipts": receipts or {},
    }


def report_digest(report: Report | dict[str, Any]) -> str:
    if isinstance(report, Report):
        data = report.model_dump(mode="json", exclude={"digest"})
    else:
        data = {key: value for key, value in report.items() if key != "digest"}
    return sha256_value(data)


@dataclass(frozen=True)
class VerifyResult:
    ok: bool
    reasons: list[str]


def verify(report_path: Path, inputs_dir: Path | None = None) -> VerifyResult:
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
        report = Report.model_validate(data)
    except (OSError, ValueError) as error:
        return VerifyResult(False, [f"unreadable report: {error}"])
    reasons: list[str] = []
    if data.get("digest") != report_digest(data):
        reasons.append("report digest mismatch")
    for name, expected in report.evidence.get("inputs", {}).items():
        if inputs_dir is None:
            reasons.append(f"cannot verify input {name}: no inputs directory")
            continue
        path = inputs_dir / name
        if not path.is_file():
            reasons.append(f"missing input {name}")
        elif sha256_file(path) != expected:
            reasons.append(f"input hash mismatch: {name}")
    for element in [*report.elements_a, *report.elements_b]:
        expected = report.evidence.get("elements", {}).get(element.element_id)
        if expected is not None and element_hash(element) != expected:
            reasons.append(f"element hash mismatch: {element.element_id}")
    for measurement in report.measurements:
        expected = report.evidence.get("measurements", {}).get(measurement.element_id)
        if expected is not None and measurement_hash(measurement) != expected:
            reasons.append(f"measurement hash mismatch: {measurement.element_id}")
    return VerifyResult(not reasons, reasons)
