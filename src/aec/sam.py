"""Minimal SAM 3.1 /responses client.

The live endpoint streams one ``output_text`` line of token records per frame
(``<Nf>id<|box;x1=..;y1=..;x2=..;y2=..;w=..;h=..|><|mask;x=..;y=..;data=H,W,payload|>``).
Boxes are plain text; masks use Meta's range-coded payload and are decoded only
when the official ``meta-sam-parser`` package is installed (SAM License, an
OPTIONAL extra - this repository stays MIT-only at runtime).

Without that package a record still yields a usable object: its box becomes a
rectangle polygon and ``mask_available`` is False.
"""
from __future__ import annotations

import base64
import json
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Literal, cast

DEFAULT_BASE = "https://api.meta.ai/v1"
Transport = Callable[[str, dict[str, str], dict[str, Any], float], dict[str, Any]]

FRAME_RE = re.compile(r"<0f>(\d+)")
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
        canvas[y0:y1, x0:x1] = raster.reshape(int(height), int(width))[
            : y1 - y0, : x1 - x0]
    return canvas


def _polygon_from_mask(canvas: Any,
                       tolerance_px: float = 1.0) -> list[list[float]] | None:
    try:
        from aec.masks import mask_to_polygon
        return [[float(px), float(py)] for px, py in mask_to_polygon(canvas, tolerance_px)]
    except Exception:  # noqa: BLE001 - fall back to the box rectangle
        return None


def parse_output_text(text: str, label: str = "object") -> list[dict[str, Any]]:
    """Objects from one streamed token line; boxes always, masks when decodable."""
    objects: list[dict[str, Any]] = []
    for match in RECORD_RE.finditer(text):
        if match.group("box") is not None:
            fields = _fields(match.group("box"))
            try:
                x1 = int(float(fields["x1"]))
                y1 = int(float(fields["y1"]))
                x2 = int(float(fields["x2"]))
                y2 = int(float(fields["y2"]))
                image_w = int(float(fields.get("w", 0) or 0))
                image_h = int(float(fields.get("h", 0) or 0))
            except (KeyError, ValueError):
                continue
            objects.append({
                "object_id": str(len(objects) + 1),
                "label": label,
                "bbox": [min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)],
                "polygon": [[x1, y1], [x2, y1], [x2, y2], [x1, y2], [x1, y1]],
                "score": None,
                "mask_available": False,
                "_image": (image_w, image_h),
            })
            continue
        fields = _fields(match.group("mask"))
        try:
            x = int(float(fields.get("x", 0) or 0))
            y = int(float(fields.get("y", 0) or 0))
            height, width, payload = fields["data"].split(",", 2)
            height_i, width_i = int(height), int(width)
        except (KeyError, ValueError):
            continue
        target = objects[-1] if objects else None
        image_w, image_h = (target or {}).get("_image", (0, 0))
        # A mask token's x/y are relative to its box; the box carries the
        # image-space origin, so add it when the mask belongs to a box record.
        offset_x = x + (int(target["bbox"][0]) if target else 0)
        offset_y = y + (int(target["bbox"][1]) if target else 0)
        canvas = None
        if image_w and image_h:
            canvas = _decode_mask(offset_x, offset_y, height_i, width_i, payload,
                                  image_w, image_h)
        if target is None:
            target = {
                "object_id": str(len(objects) + 1),
                "label": label,
                "bbox": [x, y, x + width_i, y + height_i],
                "polygon": None,
                "score": None,
                "mask_available": False,
                "_image": (0, 0),
            }
            objects.append(target)
        if canvas is not None:
            polygon = _polygon_from_mask(canvas)
            if polygon:
                target["polygon"] = polygon
                target["mask_available"] = True
                xs = [point[0] for point in polygon]
                ys = [point[1] for point in polygon]
                target["bbox"] = [min(xs), min(ys), max(xs), max(ys)]
    for obj in objects:
        obj.pop("_image", None)
    return objects


def _join_sse(lines: Iterable[bytes | str]) -> dict[str, Any]:
    """Join a Responses event stream into one output-text + model + usage dict."""
    parts: list[str] = []
    model: str | None = None
    usage: dict[str, Any] = {}
    for raw in lines:
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
            response = event.get("response") or {}
            model = str(response.get("model") or model or "")
            usage = response.get("usage") or usage
    return {"output_text": "".join(parts), "model": model, "usage": usage}


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
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content_type = response.headers.get("Content-Type", "")
            if "text/event-stream" in content_type:
                return _join_sse(response)
            return cast(dict[str, Any], json.loads(response.read().decode("utf-8")))
    except urllib.error.HTTPError as error:
        return {"status": error.code, "body": error.read().decode("utf-8", "replace")}


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

    def segment(self, image: bytes, prompt: str, page: int = 0) -> SamResult:
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
        response: dict[str, Any] | None = None
        for attempt in range(self.max_attempts):
            self._calls += 1
            try:
                response = self.transport(self._url(), headers, payload, self.timeout)
            except OSError as error:
                if attempt + 1 >= self.max_attempts:
                    raise SamTransportError(
                        f"transport failed after {self._calls} call(s): "
                        f"{type(error).__name__}",
                        retryable=True,
                    ) from error
                self.sleep(0.5 * (2**attempt))
                continue
            status = response.get("status")
            if isinstance(status, int) and status >= 400:
                retryable = status in {429, 500, 502, 503, 504}
                if retryable and attempt + 1 < self.max_attempts:
                    self.sleep(0.5 * (2**attempt))
                    continue
                raise SamTransportError(
                    f"HTTP {status} after {self._calls} call(s)",
                    status_code=status,
                    retryable=retryable,
                )
            break
        if response is None:
            raise SamTransportError("no response received", retryable=True)
        objects = normalise_response(response, prompt)
        usage = response.get("usage") or {}
        if not isinstance(usage, dict):
            usage = {}
        return SamResult(
            objects=objects,
            usage=usage,
            model=str(response.get("model") or self.model_id),
            calls=self._calls,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
