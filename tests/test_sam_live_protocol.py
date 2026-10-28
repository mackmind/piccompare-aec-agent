"""SAM 3.1 live protocol: streaming, token parsing, optional mask decoding."""

from __future__ import annotations

import json

from aec.sam import (
    SamClient,
    _join_sse,
    box_prompt,
    build_request,
    normalise_response,
    parse_output_text,
)

# One real box-prompt record (image 1600x1200, ROOM A box 100,100-500,500).
SAMPLE = (
    "<0f>1<|box;x1=96;y1=97;x2=504;y2=503;w=1600;h=1200|>"
    "<|mask;x=0;y=0;data=407,409,!!!!#PB.zSsi%*%sFx[g28vesn*L`[QHL4v8*ny[S13Em*VOk$$?Yw5^+N"
    "(G3+xyjk6BmBZmp:0aLh_q8f9[oXDFTYD@!boL5e:zSx{FxUxjp@WJNBI_sUyrF)F8RM5d?5Dp?U:'v92Xj"
    ":O30H8qBBML%h6Q!Esa/2J@)|>\n"
)


def test_build_request_streams_one_bit_masks():
    request = build_request("sam-3.1", b"png", "room")
    assert request["stream"] is True
    assert request["metadata"] == {"mask_encoding": "one_bit"}
    assert request["model"] == "sam-3.1"
    content = request["input"][0]["content"]
    assert content[0] == {"type": "input_text", "text": "room"}
    assert content[1]["type"] == "input_image"
    assert content[1]["image_url"].startswith("data:image/png;base64,")


def test_box_prompt_token_shape():
    assert box_prompt(100, 100, 500, 500, 1600, 1200) == (
        "<0f>1<|box;x1=100;y1=100;x2=500;y2=500;w=1600;h=1200|>")


def test_parse_box_record_and_optional_mask():
    objects = parse_output_text(SAMPLE, "room")
    assert len(objects) == 1
    obj = objects[0]
    # The mask polygon sits within a few pixels of the prompted 100,100-500,500
    # (the contour is simplified to plan-like vertices, so it is not the box).
    x1, y1, x2, y2 = obj["bbox"]
    assert abs(x1 - 96) <= 8 and abs(y1 - 97) <= 8
    assert abs(x2 - 504) <= 8 and abs(y2 - 503) <= 8
    assert obj["label"] == "room"
    assert len(obj["polygon"]) >= 5
    if obj["mask_available"]:
        xs = [point[0] for point in obj["polygon"]]
        ys = [point[1] for point in obj["polygon"]]
        # A decoded mask is blitted in IMAGE space, not mask-local space.
        assert min(xs) >= 90 and max(xs) <= 510
        assert min(ys) >= 90 and max(ys) <= 510


def test_parse_without_the_optional_parser_falls_back_to_the_box(monkeypatch):
    import aec.sam as sam
    monkeypatch.setattr(sam, "_decode_mask", lambda *a, **k: None)
    objects = sam.parse_output_text(SAMPLE, "room")
    assert len(objects) == 1
    assert objects[0]["mask_available"] is False
    assert objects[0]["bbox"] == [96, 97, 504, 503]   # the model's box token
    assert len(objects[0]["polygon"]) == 5          # closed rectangle


def test_parse_empty_concept_output_is_no_objects():
    assert parse_output_text("", "room") == []
    assert parse_output_text("\n", "room") == []


def test_join_sse_collects_deltas_and_completed_metadata():
    def event(kind: str, **fields) -> bytes:
        return b"data: " + json.dumps({"type": kind, **fields}).encode() + b"\n"

    lines = [
        b"event: response.created\n",
        event("response.created"),
        event("response.output_text.delta",
              delta="<0f>1<|box;x1=1;y1=2;x2=3;y2=4;w=10;h=10|>"),
        event("response.output_text.delta", delta="\n"),
        event("response.completed",
              response={"model": "sam-3.1",
                        "usage": {"images_processed": 1}}),
        b"data: [DONE]\n",
    ]
    joined = _join_sse(lines)
    assert joined["output_text"].startswith("<0f>1<|box;x1=1")
    assert joined["model"] == "sam-3.1"
    assert joined["usage"] == {"images_processed": 1}


def test_normalise_response_prefers_legacy_objects_and_parses_text():
    legacy = normalise_response({"objects": [{"label": "x"}]})
    assert legacy == [{"label": "x"}]
    parsed = normalise_response({"output_text": SAMPLE})
    assert len(parsed) == 1 and parsed[0]["label"] == "object"
    try:
        normalise_response({})
    except Exception as error:  # SamSchemaError
        assert type(error).__name__ == "SamSchemaError"
    else:  # pragma: no cover
        raise AssertionError("an empty response must raise")


def test_client_segment_uses_the_streamed_text():
    def transport(url, headers, payload, timeout):
        assert payload["stream"] is True
        return {"output_text": SAMPLE, "model": "sam-3.1", "usage": {}}

    client = SamClient(api_key="k", transport=transport)
    result = client.segment(b"png", "room")
    assert result.calls == 1
    assert len(result.objects) == 1
    assert result.model == "sam-3.1"


def test_client_requires_credentials():
    import pytest

    from aec.sam import SamUnavailable
    with pytest.raises(SamUnavailable):
        SamClient(api_key="").segment(b"png", "room")


def test_calls_reports_only_this_segment():
    def transport(url, headers, payload, timeout):
        return {"output_text": SAMPLE, "model": "sam-3.1", "usage": {},
                "completed": True}

    client = SamClient(api_key="k", transport=transport)
    first = client.segment(b"png", "box")
    second = client.segment(b"png", "box")
    assert first.calls == 1 and second.calls == 1
    assert client.calls == 2


def test_stream_error_and_truncation_raise():
    import pytest

    from aec.sam import SamTransportError

    failing = SamClient(api_key="k", max_attempts=1,
                        transport=lambda *a: {"error": "boom"})
    with pytest.raises(SamTransportError):
        failing.segment(b"png", "room")

    truncated = SamClient(api_key="k", max_attempts=1,
                          transport=lambda *a: {"output_text": SAMPLE,
                                                "completed": False})
    with pytest.raises(SamTransportError):
        truncated.segment(b"png", "room")


def test_completed_empty_text_is_zero_objects():
    # A concept prompt that finds nothing is a legitimate 0-object result.
    client = SamClient(api_key="k",
                       transport=lambda *a: {"output_text": "", "completed": True})
    assert client.segment(b"png", "room").objects == []


def test_mask_before_box_pairs_into_one_record():
    text = ("<|mask;x=0;y=0;data=10,20,!abc|>"
            "<|box;x1=5;y1=6;x2=25;y2=16;w=100;h=100|>")
    objects = parse_output_text(text, "room")
    assert len(objects) == 1
    assert objects[0]["bbox"] == [5.0, 6.0, 25.0, 16.0]


def test_mask_dimensions_and_offset_are_unconditional(monkeypatch):
    import aec.sam as sam

    seen = {}

    def fake_decode(x, y, height, width, payload, image_width, image_height):
        seen.update(x=x, y=y, height=height, width=width,
                    image_width=image_width, image_height=image_height)
        return None

    monkeypatch.setattr(sam, "_decode_mask", fake_decode)
    # data=H,W with H != W, and a non-zero mask origin inside a box.
    text = ("<|box;x1=100;y1=200;x2=500;y2=600;w=1600;h=1200|>"
            "<|mask;x=7;y=9;data=40,300,payload|>")
    objects = sam.parse_output_text(text, "room")
    assert seen == {"x": 107, "y": 209, "height": 40, "width": 300,
                    "image_width": 1600, "image_height": 1200}
    assert objects[0]["mask_available"] is False     # decode returned None
    assert objects[0]["bbox"] == [100.0, 200.0, 500.0, 600.0]
