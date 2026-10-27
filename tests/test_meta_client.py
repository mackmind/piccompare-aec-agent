from __future__ import annotations

import json

import pytest

from aec.meta import MetaClient, MetaSchemaError, MetaUnavailable


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


def response(content: object) -> dict:
    return {
        "model": "muse-test",
        "choices": [{"message": {"content": json.dumps(content)}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }


def test_missing_api_key_makes_no_request() -> None:
    client = MetaClient(api_key="", model_id="m")
    with pytest.raises(MetaUnavailable):
        client.chat_json("s", "u", {"type": "object"})
    assert client.calls == 0


def test_payload_uses_documented_envelope() -> None:
    transport = SequenceTransport([response({"ok": True})])
    client = MetaClient(
        api_key="secret",
        model_id="muse-test",
        transport=transport,
    )
    result = client.chat_json("s", "u", {"type": "object"}, max_tokens=321)
    payload = transport.calls[0]["payload"]
    assert payload["max_completion_tokens"] == 321
    assert "max_output_tokens" not in payload
    assert payload["response_format"]["json_schema"]["strict"] is True
    assert result.content == {"ok": True}
    assert result.calls == 1


def test_429_retries_then_succeeds() -> None:
    transport = SequenceTransport([{"status": 429}, response({"ok": True})])
    client = MetaClient(
        api_key="secret",
        model_id="muse-test",
        transport=transport,
        sleep=lambda seconds: None,
        max_attempts=2,
    )
    result = client.chat_json("s", "u", {"type": "object"})
    assert result.calls == 2


def test_bad_content_raises_schema_error() -> None:
    transport = SequenceTransport(
        [{"choices": [{"message": {"content": "not json"}}]}]
    )
    client = MetaClient(api_key="secret", model_id="muse-test", transport=transport)
    with pytest.raises(MetaSchemaError):
        client.chat_json("s", "u", {"type": "object"})
