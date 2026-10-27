"""Minimal SAM 3.1 /responses client with an injectable transport."""

from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

DEFAULT_BASE = "https://api.meta.ai/v1"
Transport = Callable[[str, dict[str, str], dict[str, Any], float], dict[str, Any]]


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
            return cast(dict[str, Any], json.loads(response.read().decode("utf-8")))
    except urllib.error.HTTPError as error:
        return {"status": error.code, "body": error.read().decode("utf-8", "replace")}


def build_request(model: str, image: bytes, prompt: str) -> dict[str, Any]:
    encoded = base64.b64encode(image).decode("ascii")
    return {
        "model": model,
        "input": [
            {
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
    }


def normalise_response(response: dict[str, Any]) -> list[dict[str, Any]]:
    objects = response.get("objects")
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
            "Accept": "application/json",
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
        objects = normalise_response(response)
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
