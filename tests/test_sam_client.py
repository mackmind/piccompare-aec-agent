from __future__ import annotations

import pytest

from aec.sam import SamClient, SamSchemaError, SamUnavailable


class SequenceTransport:
    def __init__(self, responses) -> None:
        self.responses = responses
        self.calls: list[dict] = []

    def __call__(self, url, headers, payload, timeout):
        self.calls.append({"url": url, "headers": headers, "payload": payload})
        response = self.responses[min(len(self.calls) - 1, len(self.responses) - 1)]
        if isinstance(response, BaseException):
            raise response
        return response


def test_missing_key_makes_no_request() -> None:
    client = SamClient(api_key="")
    with pytest.raises(SamUnavailable):
        client.segment(b"png", "room")
    assert client.calls == 0


def test_sam_request_uses_responses_endpoint() -> None:
    transport = SequenceTransport([{"objects": [{"label": "room"}], "model": "sam-test"}])
    client = SamClient(api_key="secret", transport=transport)
    result = client.segment(b"png", "room", page=0)
    assert transport.calls[0]["url"].endswith("/responses")
    assert transport.calls[0]["payload"]["model"] == "sam-3.1"
    assert "input_image" in str(transport.calls[0]["payload"])
    assert result.objects[0]["label"] == "room"
    assert result.calls == 1


def test_sam_retries_429() -> None:
    transport = SequenceTransport([{"status": 429}, {"objects": []}])
    client = SamClient(
        api_key="secret", transport=transport, sleep=lambda s: None, max_attempts=2
    )
    result = client.segment(b"png", "room")
    assert result.calls == 2


def test_sam_bad_response_raises() -> None:
    transport = SequenceTransport([{"unexpected": True}])
    client = SamClient(api_key="secret", transport=transport)
    with pytest.raises(SamSchemaError):
        client.segment(b"png", "room")
