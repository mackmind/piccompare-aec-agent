"""Minimal SAM 3.1 /responses client.

The live endpoint streams one ``output_text`` line of token records per frame
(``<0f>id<|box;x1=..;y1=..;x2=..;y2=..;w=..;h=..|><|mask;x=..;y=..;data=H,W,payload|>``).
A record may carry its box and mask in either order and several records may share
a frame. Boxes are plain text; masks use Meta's range-coded payload and are
decoded only when the official ``meta-sam-parser`` package is installed (SAM
License, an OPTIONAL extra - this repository stays MIT-only at runtime).

Without that package a record still yields a usable object: its box becomes a
rectangle polygon and ``mask_available`` is False.

A stream that fails, is refused, is truncated or ends before
``response.completed`` raises: an empty result must mean "the model reported no
objects", never "the call went wrong".
"""
from __future__ import annotations

import base64
import http.client
import json
import math
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Literal, cast

DEFAULT_BASE = "https://api.meta.ai/v1"
Transport = Callable[[str, dict[str, str], dict[str, Any], float], dict[str, Any]]

# Mask contours wiggle by a pixel or two along a drawn edge; without this the
# polygon carries 30+ vertices and every edge/angle delta is noise.
MASK_SIMPLIFY_PX = 6.0
RECORD_RE = re.compile(r"<\|box;(?P<box>[^|]*)\|>|<\|mask;(?P<mask>[^|]*)\|>")


class SamError(RuntimeError):
    pass


class SamUnavailable(SamError):
    pass


class SamTransportError(SamError):
    def __init__(self, message: str, *, status_code: int | None = None,
                 retryable: bool = False) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


class SamSchemaError(SamError):
    pass


@dataclass(frozen=True)
class SamResult:
    objects: list[dict[str, Any]]
    usage: dict[str, Any]
    model: str
    calls: int
    latency_ms: int


def _fields(token: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in token.split(";"):
        if "=" in part:
            key, value = part.split("=", 1)
            out[key.strip()] = value.strip()
    return out


def _to_int(value: Any, default: int | None = None) -> int | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return int(math.floor(number))


def box_prompt(x1: int, y1: int, x2: int, y2: int, width: int, height: int) -> str:
    """The documented object-prompt token for one box (pixels, image size)."""
    return (f"<0f>1<|box;x1={int(x1)};y1={int(y1)};x2={int(x2)};y2={int(y2)};"
            f"w={int(width)};h={int(height)}|>")


def _decode_mask(x: int, y: int, height: int, width: int, payload: str,
                 image_width: int, image_height: int) -> Any:
    """Full-image 0/1 raster for a mask token, or None when unsupported."""
    try:
        import numpy as np
        from meta_sam_parser import SegmentationMask, decode_mask_to_raster
    except Exception:  # noqa: BLE001 - the parser is an optional extra
        return None
    encoding: Literal["one_bit", "lossless"] = (
        "one_bit" if payload.startswith("!") else "lossless")
    try:
        mask = SegmentationMask(encoding=encoding, payload=payload,
                                width=int(width), height=int(height))
        raster = np.frombuffer(decode_mask_to_raster(mask), dtype=np.uint8)
    except Exception:  # noqa: BLE001 - a bad payload must not lose the box
        return None
    if raster.size != int(width) * int(height):
        return None
    canvas = np.zeros((int(image_height), int(image_width)), dtype=np.uint8)
    x0 = max(0, int(x))
    y0 = max(0, int(y))
    x1 = min(int(image_width), x0 + int(width))
    y1 = min(int(image_height), y0 + int(height))
    if x1 > x0 and y1 > y0:
        # A clipped mask starts at its own column/row, not at zero.
        source = raster.reshape(int(height), int(width))
        canvas[y0:y1, x0:x1] = source[y0 - int(y): y1 - int(y),
                                      x0 - int(x): x1 - int(x)]
    return canvas


def _polygon_from_mask(canvas: Any,
                       tolerance_px: float = MASK_SIMPLIFY_PX) -> list[list[float]] | None:
    try:
        from aec.masks import mask_to_polygon
        return [[float(px), float(py)] for px, py in mask_to_polygon(canvas, tolerance_px)]
    except Exception:  # noqa: BLE001 - fall back to the box rectangle
        return None


def _rectangle(x1: float, y1: float, x2: float, y2: float) -> list[list[float]]:
    return [[x1, y1], [x2, y1], [x2, y2], [x1, y2], [x1, y1]]


def _records(text: str) -> list[dict[str, Any]]:
    """Split token text into records; a box and a mask belong to one record."""
    records: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for match in RECORD_RE.finditer(text):
        if match.group("box") is not None:
            fields = _fields(match.group("box"))
            box = tuple(_to_int(fields.get(key)) for key in ("x1", "y1", "x2", "y2"))
            if any(value is None for value in box):
                continue
            size = (_to_int(fields.get("w"), 0) or 0, _to_int(fields.get("h"), 0) or 0)
            if current is None or current["box"] is not None:
                current = {"box": None, "mask": None}
                records.append(current)
            current["box"] = (box, size)
            continue
        fields = _fields(match.group("mask"))
        data = (fields.get("data") or "").split(",", 2)
        if len(data) != 3:
            continue
        height = _to_int(data[0])
        width = _to_int(data[1])
        if height is None or width is None or height <= 0 or width <= 0:
            continue
        origin = (_to_int(fields.get("x"), 0) or 0, _to_int(fields.get("y"), 0) or 0)
        if current is None or current["mask"] is not None:
            current = {"box": None, "mask": None}
            records.append(current)
        current["mask"] = (origin, height, width, data[2])
    return records


def parse_output_text(text: str, label: str = "object") -> list[dict[str, Any]]:
    """Objects from one streamed token line; boxes always, masks when decodable."""
    objects: list[dict[str, Any]] = []
    for index, record in enumerate(_records(text), start=1):
        box = record["box"]
        mask = record["mask"]
        image_width, image_height = box[1] if box else (0, 0)
        polygon: list[list[float]] | None = None
        bbox: list[float] | None = None
        mask_available = False
        if box is not None:
            x1, y1, x2, y2 = (float(value) for value in box[0])
            polygon = _rectangle(x1, y1, x2, y2)
            bbox = [min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)]
        if mask is not None:
            (mask_x, mask_y), height, width, payload = mask
            # A mask token's x/y are relative to its box; the box carries the
            # image-space origin. A mask-only record keeps its own origin.
            origin_x = mask_x + (int(box[0][0]) if box else 0)
            origin_y = mask_y + (int(box[0][1]) if box else 0)
            if image_width and image_height:
                canvas = _decode_mask(origin_x, origin_y, height, width, payload,
                                      image_width, image_height)
                decoded = _polygon_from_mask(canvas) if canvas is not None else None
                if decoded:
                    polygon = decoded
                    mask_available = True
                    xs = [point[0] for point in decoded]
                    ys = [point[1] for point in decoded]
                    bbox = [min(xs), min(ys), max(xs), max(ys)]
            if bbox is None:
                bbox = [float(origin_x), float(origin_y),
                        float(origin_x + width), float(origin_y + height)]
                polygon = _rectangle(*bbox)
        if bbox is None:
            continue
        objects.append({
            "object_id": str(index),
            "label": label,
            "bbox": bbox,
            "polygon": polygon,
            "mask_available": mask_available,
        })
    return objects


def _join_sse(lines: Iterable[bytes | str],
              deadline: float | None = None) -> dict[str, Any]:
    """Join a Responses event stream: text, model, usage, completion and error."""
    parts: list[str] = []
    model: str | None = None
    usage: dict[str, Any] = {}
    completed = False
    error: str | None = None
    for raw in lines:
        if deadline is not None and time.monotonic() > deadline:
            error = error or "stream exceeded its deadline"
            break
        line = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
        line = line.strip()
        if not line.startswith("data:"):
            continue
        body = line[5:].strip()
        if body == "[DONE]":
            break
        try:
            event = json.loads(body)
        except json.JSONDecodeError:
            continue
        kind = event.get("type")
        if kind == "response.output_text.delta":
            parts.append(str(event.get("delta") or ""))
        elif kind == "response.completed":
            completed = True
            response = event.get("response") or {}
            model = str(response.get("model") or model or "")
            usage = response.get("usage") or usage
        elif kind in ("error", "response.failed", "response.incomplete"):
            error = error or str(event.get("error") or event.get("message") or kind)
        elif isinstance(kind, str) and "refusal" in kind:
            error = error or kind
    return {"output_text": "".join(parts), "model": model, "usage": usage,
            "completed": completed, "error": error}


def _default_transport(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    deadline = time.monotonic() + timeout
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content_type = response.headers.get("Content-Type", "")
            if "text/event-stream" in content_type:
                joined = _join_sse(response, deadline)
                if joined.get("error"):
                    raise SamTransportError(f"SAM stream error: {joined['error']}",
                                            retryable=True)
                if not joined.get("completed"):
                    raise SamTransportError(
                        "SAM stream ended before response.completed", retryable=True)
                return joined
            body = json.loads(response.read().decode("utf-8"))
            if not isinstance(body, dict):
                raise SamTransportError("SAM response body is not an object",
                                        retryable=True)
            body.setdefault("completed", True)
            return cast(dict[str, Any], body)
    except urllib.error.HTTPError as error:
        return {"status": error.code, "body": error.read().decode("utf-8", "replace")}
    except (http.client.HTTPException, json.JSONDecodeError) as error:
        # A truncated body or unparsable payload is a transport fault, and the
        # caller's retry loop is the right place to handle it.
        raise ConnectionError(f"{type(error).__name__}: {error}") from error


def build_request(model: str, image: bytes, prompt: str) -> dict[str, Any]:
    encoded = base64.b64encode(image).decode("ascii")
    return {
        "model": model,
        "input": [
            {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {
                        "type": "input_image",
                        "image_url": f"data:image/png;base64,{encoded}",
                    },
                ],
            }
        ],
        # The live endpoint only emits segmentation records on a stream, and the
        # smallest payload is the one-bit mask encoding.
        "stream": True,
        "metadata": {"mask_encoding": "one_bit"},
    }


def normalise_response(response: dict[str, Any],
                       label: str = "object") -> list[dict[str, Any]]:
    objects = response.get("objects")
    if objects is None and isinstance(response.get("output_text"), str):
        return parse_output_text(str(response["output_text"]), label)
    if objects is None:
        objects = response.get("output")
    if isinstance(objects, dict):
        objects = objects.get("objects")
    if not isinstance(objects, list):
        raise SamSchemaError("SAM response has no objects/output array")
    return [obj for obj in objects if isinstance(obj, dict)]


class SamClient:
    def __init__(
        self,
        *,
        api_key: str,
        model_id: str = "sam-3.1",
        base_url: str = DEFAULT_BASE,
        transport: Transport | None = None,
        sleep: Callable[[float], None] | None = None,
        max_attempts: int = 2,
        timeout: float = 120.0,
    ) -> None:
        self.api_key = api_key
        self.model_id = model_id
        self.base_url = base_url.rstrip("/")
        self.transport = transport or _default_transport
        self.sleep = sleep or time.sleep
        self.max_attempts = max(1, max_attempts)
        self.timeout = timeout
        self._calls = 0

    @property
    def calls(self) -> int:
        return self._calls

    def _url(self) -> str:
        if self.base_url.endswith("/responses"):
            return self.base_url
        return f"{self.base_url}/responses"

    def segment(self, image: bytes, prompt: str, page: int = 0,
                label: str | None = None) -> SamResult:
        if not self.api_key:
            raise SamUnavailable("META_API_KEY is not set; no request was made")
        if not self.model_id:
            raise SamUnavailable("SAM model id is not set; no request was made")
        payload = build_request(self.model_id, image, prompt)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        started = time.perf_counter()
        start_calls = self._calls
        response: dict[str, Any] | None = None
        for attempt in range(self.max_attempts):
            self._calls += 1
            try:
                response = self.transport(self._url(), headers, payload, self.timeout)
            except (OSError, SamTransportError) as error:
                retryable = getattr(error, "retryable", True)
                if retryable and attempt + 1 < self.max_attempts:
                    self.sleep(0.5 * (2**attempt))
                    continue
                raise SamTransportError(
                    f"transport failed after {self._calls - start_calls} call(s): "
                    f"{type(error).__name__}: {error}",
                    retryable=bool(retryable),
                ) from error
            status = response.get("status")
            if isinstance(status, int) and status >= 400:
                retryable = status in {429, 500, 502, 503, 504}
                if retryable and attempt + 1 < self.max_attempts:
                    self.sleep(0.5 * (2**attempt))
                    continue
                raise SamTransportError(
                    f"HTTP {status} after {self._calls - start_calls} call(s)",
                    status_code=status,
                    retryable=retryable,
                )
            if response.get("error"):
                raise SamTransportError(f"SAM stream error: {response['error']}",
                                        retryable=True)
            if response.get("completed") is False:
                raise SamTransportError(
                    "SAM stream ended before response.completed", retryable=True)
            break
        if response is None:
            raise SamTransportError("no response received", retryable=True)
        objects = normalise_response(response, label or prompt)
        usage = response.get("usage") or {}
        if not isinstance(usage, dict):
            usage = {}
        return SamResult(
            objects=objects,
            usage=usage,
            model=str(response.get("model") or self.model_id),
            calls=self._calls - start_calls,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
