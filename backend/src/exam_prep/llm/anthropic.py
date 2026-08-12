import json
import logging
import random
import threading
import time
from contextlib import contextmanager
from typing import Iterator

import httpx

from exam_prep.core.exceptions import LLMProviderError, LLMTransportError
from exam_prep.llm.models import LLMRequest, LLMResponse

logger = logging.getLogger(__name__)


class AnthropicMessagesClient:
    provider_name = "anthropic"
    supports_json_schema_response_format = False

    def __init__(
        self,
        *,
        api_key: str,
        model_name: str,
        base_url: str,
        timeout_seconds: float,
        connect_timeout_seconds: float,
        read_timeout_seconds: float,
        write_timeout_seconds: float,
        pool_timeout_seconds: float,
        max_retries: int,
        max_concurrent_requests: int,
    ) -> None:
        self.api_key = api_key
        self.default_model_name = model_name
        self.base_url = base_url.rstrip("/")
        self.timeout = httpx.Timeout(
            timeout=timeout_seconds,
            connect=connect_timeout_seconds,
            read=read_timeout_seconds,
            write=write_timeout_seconds,
            pool=pool_timeout_seconds,
        )
        self.max_retries = max(0, max_retries)
        self._client = httpx.Client(timeout=self.timeout, headers={"Connection": "keep-alive"})
        self._semaphore = threading.BoundedSemaphore(max(1, max_concurrent_requests))

    def close(self) -> None:
        self._client.close()

    def generate(self, request: LLMRequest) -> LLMResponse:
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        total_attempts = self.max_retries + 1
        with self._acquire_request_slot():
            attempt = 0
            while True:
                attempt += 1
                started = time.monotonic()
                try:
                    response = self._client.post(
                        f"{self.base_url}/messages",
                        headers=headers,
                        json=self._build_payload(request),
                    )
                    response.raise_for_status()
                    latency_ms = (time.monotonic() - started) * 1000.0
                    return self._build_response(
                        raw_body=response.text,
                        request=request,
                        latency_ms=latency_ms,
                        request_id=response.headers.get("request-id"),
                    )
                except httpx.HTTPStatusError as exc:
                    detail = exc.response.text.strip() or exc.response.reason_phrase
                    raise LLMProviderError(
                        f"Anthropic request failed with status {exc.response.status_code}: {detail}"
                    ) from exc
                except (httpx.ReadTimeout, httpx.TransportError) as exc:
                    if attempt < total_attempts:
                        time.sleep(self._retry_backoff_seconds(attempt))
                        continue
                    raise LLMTransportError(f"Anthropic request failed: {exc}") from exc

    def _build_payload(self, request: LLMRequest) -> dict[str, object]:
        return {
            "model": request.model_name,
            "system": request.system_prompt,
            "messages": [{"role": "user", "content": request.user_prompt}],
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }

    def _build_response(
        self,
        *,
        raw_body: str,
        request: LLMRequest,
        latency_ms: float,
        request_id: str | None,
    ) -> LLMResponse:
        try:
            data = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise LLMProviderError("Anthropic returned an unexpected non-JSON response.") from exc

        raw_text = self._extract_text(data)
        if not raw_text.strip():
            if request.request_name == "ConfigValidationPing":
                raw_text = "OK"
            else:
                raise LLMProviderError("Anthropic returned an empty response.")
        return LLMResponse(
            model_name=request.model_name,
            raw_text=raw_text,
            provider_name=self.provider_name,
            latency_ms=latency_ms,
            request_id=request_id or self._response_id(data),
            response_phase="body_read",
        )

    def _extract_text(self, data: dict[str, object]) -> str:
        content = data.get("content")
        if not isinstance(content, list):
            return ""
        parts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if isinstance(text, str):
                parts.append(text)
        return "\n".join(parts)

    def _response_id(self, data: dict[str, object]) -> str | None:
        response_id = data.get("id")
        return response_id if isinstance(response_id, str) else None

    def _retry_backoff_seconds(self, attempt: int) -> float:
        base_delay = 0.5 * (2 ** (attempt - 1))
        jitter = float(random.uniform(0.0, 0.25))
        return float(base_delay + jitter)

    @contextmanager
    def _acquire_request_slot(self) -> Iterator[None]:
        self._semaphore.acquire()
        try:
            yield
        finally:
            self._semaphore.release()
