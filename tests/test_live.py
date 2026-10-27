from __future__ import annotations

import json
from pathlib import Path

from aec.evidence import verify
from aec.live import run_pair_live
from aec.meta import MetaClient
from aec.sam import SamResult

ROOT = Path(__file__).resolve().parent.parent


class FakeSam:
    def __init__(self, fixture_dir: Path) -> None:
        payload = json.loads((fixture_dir / "sam31.json").read_text())
        self.objects = [
            payload["sides"]["a"]["pages"][0]["objects"],
            payload["sides"]["b"]["pages"][0]["objects"],
        ]
        self.calls = 0

    def segment(self, image: bytes, prompt: str, page: int = 0) -> SamResult:
        objects = self.objects[self.calls % 2]
        self.calls += 1
        return SamResult(
            objects=objects,
            usage={"input_tokens": 1},
            model="fake-sam",
            calls=1,
            latency_ms=1,
        )


def verifying_transport(url, headers, payload, timeout):
    context = json.loads(payload["messages"][1]["content"])
    decisions = [
        {
            "finding_id": finding["finding_id"],
            "status": "verified",
            "reasons": ["fake live critic"],
            "evidence_refs": finding["evidence_refs"][:1],
        }
        for finding in context["findings"]
    ]
    return {
        "model": "fake-meta",
        "choices": [{"message": {"content": json.dumps({"decisions": decisions})}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }


def test_live_path_with_fake_clients(tmp_path) -> None:
    fixture = ROOT / "fixtures" / "aec" / "resize-01"
    sam = FakeSam(fixture)
    meta = MetaClient(
        api_key="test-key",
        model_id="fake-meta",
        transport=verifying_transport,
        sleep=lambda seconds: None,
    )
    result = run_pair_live(fixture, sam, meta, tmp_path)
    assert result.verified
    assert result.report_path is not None
    assert result.report.usage["network"] is True
    assert result.report.usage["meta_model"] == "fake-meta"
    assert result.report.evidence["receipts"]["sam"]["calls"] == 2
    assert verify(result.report_path, inputs_dir=fixture).ok


def test_live_path_refuses_split_without_meta_call(tmp_path) -> None:
    fixture = ROOT / "fixtures" / "aec" / "split-01"
    sam = FakeSam(fixture)
    meta = MetaClient(
        api_key="test-key",
        model_id="fake-meta",
        transport=verifying_transport,
        sleep=lambda seconds: None,
    )
    result = run_pair_live(fixture, sam, meta, tmp_path)
    assert not result.verified
    assert result.not_compared
    assert all(
        finding.change_type == "room_split" for finding in result.not_compared
    )
    assert result.report.usage["meta_api_calls"] == 0
    assert result.report.evidence["receipts"]["meta"]["calls"] == 0
    assert verify(result.report_path, inputs_dir=fixture).ok
