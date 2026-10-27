from __future__ import annotations

import json

from factories import report, sample_report

from aec.evidence import build_evidence, verify
from aec.report import write_report


def test_clean_report_verifies(tmp_path) -> None:
    json_path, _ = write_report(report("p1", high=1), tmp_path)
    assert verify(json_path).ok


def test_tampered_finding_fails_replay(tmp_path) -> None:
    json_path, _ = write_report(report("p1", high=1), tmp_path)
    data = json.loads(json_path.read_text(encoding="utf-8"))
    data["findings"][0]["claim"] = "tampered claim"
    json_path.write_text(json.dumps(data), encoding="utf-8")
    result = verify(json_path)
    assert not result.ok
    assert "digest" in " ".join(result.reasons)


def test_tampered_input_fails(tmp_path) -> None:
    input_path = tmp_path / "a.png"
    input_path.write_bytes(b"original")
    sample = sample_report(rooms=1)
    evidence = build_evidence(
        inputs={"a.png": input_path},
        elements=sample.elements_a,
        measurements=sample.measurements,
    )
    payload = sample.model_copy(update={"evidence": evidence})
    json_path, _ = write_report(payload, tmp_path / "out")
    assert verify(json_path, inputs_dir=tmp_path).ok
    input_path.write_bytes(b"changed")
    result = verify(json_path, inputs_dir=tmp_path)
    assert not result.ok
    assert any("input hash" in reason for reason in result.reasons)


def test_missing_inputs_dir_fails_closed(tmp_path) -> None:
    input_path = tmp_path / "a.png"
    input_path.write_bytes(b"original")
    sample = sample_report(rooms=1)
    evidence = build_evidence(inputs={"a.png": input_path})
    payload = sample.model_copy(update={"evidence": evidence})
    json_path, _ = write_report(payload, tmp_path / "out")
    result = verify(json_path)
    assert not result.ok
    assert any("inputs directory" in reason for reason in result.reasons)
