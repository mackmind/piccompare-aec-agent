"""Minimal OpenAI-compatible Meta Model API client with injected transport."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, cast

DEFAULT_BASE = "https://api.meta.ai/v1"
Transport = Callable[[str, dict[str, str], dict[str, Any], float], dict[str, Any]]


class MetaError(RuntimeError):
    pass


class MetaUnavailable(MetaError):
    pass


class MetaTransportError(MetaError):
    def __init__(self, message: str, *, status_code: int | None = None,
                 retryable: bool = False) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


class MetaSchemaError(MetaError):
    pass


@dataclass(frozen=True)
class MetaResult:
    content: dict[str, Any]
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


class MetaClient:
    def __init__(
        self,
        *,
        api_key: str,
        model_id: str,
        base_url: str = DEFAULT_BASE,
        transport: Transport | None = None,
        sleep: Callable[[float], None] | None = None,
        max_attempts: int = 2,
        timeout: float = 60.0,
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
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        return f"{self.base_url}/chat/completions"

    def chat_json(
        self,
        system: str,
        user: str,
        schema: dict[str, Any],
        *,
        schema_name: str = "aec_result",
        max_tokens: int = 2048,
    ) -> MetaResult:
        if not self.api_key:
            raise MetaUnavailable("META_API_KEY is not set; no request was made")
        if not self.model_id:
            raise MetaUnavailable("META_MODEL_ID is not set; no request was made")
        payload = {
            "model": self.model_id,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_completion_tokens": max_tokens,
            "temperature": 0,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                },
            },
        }
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
                    raise MetaTransportError(
                        f"transport failed after {self._calls} call(s): {type(error).__name__}",
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
                raise MetaTransportError(
                    f"HTTP {status} after {self._calls} call(s)",
                    status_code=status,
                    retryable=retryable,
                )
            break
        if response is None:
            raise MetaTransportError("no response received", retryable=True)
        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise MetaSchemaError("response has no choices[0].message.content") from error
        if isinstance(content, str):
            try:
                parsed = json.loads(content)
            except ValueError as error:
                raise MetaSchemaError("message content is not JSON") from error
        elif isinstance(content, Mapping):
            parsed = dict(content)
        else:
            raise MetaSchemaError("message content is not a JSON object")
        if not isinstance(parsed, dict):
            raise MetaSchemaError("message content must be a JSON object")
        usage = response.get("usage") or {}
        if not isinstance(usage, dict):
            usage = {}
        model = str(response.get("model") or self.model_id)
        latency_ms = int((time.perf_counter() - started) * 1000)
        return MetaResult(
            content=parsed,
            usage=usage,
            model=model,
            calls=self._calls,
            latency_ms=latency_ms,
        )
