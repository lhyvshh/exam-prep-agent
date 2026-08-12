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


class OpenAIResponsesClient:
    provider_name = "openai"
    supports_json_schema_response_format = True

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
        enable_response_format: bool,
        reasoning_effort: str,
        text_verbosity: str,
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
        self.enable_response_format = enable_response_format
        self.reasoning_effort = reasoning_effort
        self.text_verbosity = text_verbosity
        self._client = httpx.Client(timeout=self.timeout, headers={"Connection": "keep-alive"})
        self._semaphore = threading.BoundedSemaphore(max(1, max_concurrent_requests))
        self._request_counter_lock = threading.Lock()
        self._request_counter = 0
        logger.info(
            "Initialized OpenAI Responses client model=%s base_url=%s max_retries=%s max_concurrency=%s",
            self.default_model_name,
            self.base_url,
            self.max_retries,
            max(1, max_concurrent_requests),
        )

    def close(self) -> None:
        self._client.close()

    def generate(self, request: LLMRequest) -> LLMResponse:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        total_started = time.monotonic()
        total_attempts = self.max_retries + 1
        request_sequence = self._next_request_sequence()
        queue_wait_started = time.monotonic()

        with self._acquire_request_slot():
            queue_wait_ms = (time.monotonic() - queue_wait_started) * 1000.0
            attempt = 0
            while True:
                attempt += 1
                attempt_started = time.monotonic()
                response_phase = "before_headers"
                payload = self._build_payload(request)
                logger.info(
                    "OpenAI request start model=%s request_name=%s attempt=%s/%s "
                    "queue_wait_ms=%.1f request_sequence=%s context=%s",
                    request.model_name,
                    request.request_name or "unspecified",
                    attempt,
                    total_attempts,
                    queue_wait_ms,
                    request_sequence,
                    request.request_context,
                )
                try:
                    response = self._client.post(
                        f"{self.base_url}/responses",
                        headers=headers,
                        json=payload,
                    )
                    response.raise_for_status()
                    response_phase = "body_read"
                    latency_ms = (time.monotonic() - attempt_started) * 1000.0
                    request_id = response.headers.get("x-request-id")
                    return self._build_response(
                        raw_body=response.text,
                        request=request,
                        latency_ms=latency_ms,
                        request_id=request_id,
                        response_phase=response_phase,
                    )
                except httpx.HTTPStatusError as exc:
                    detail = exc.response.text.strip() or exc.response.reason_phrase
                    logger.error(
                        "OpenAI request failed model=%s request_name=%s status=%s detail=%s "
                        "response_phase=%s request_sequence=%s context=%s",
                        request.model_name,
                        request.request_name or "unspecified",
                        exc.response.status_code,
                        detail,
                        response_phase,
                        request_sequence,
                        request.request_context,
                    )
                    raise LLMProviderError(
                        f"OpenAI request failed with status {exc.response.status_code}: {detail}"
                    ) from exc
                except (httpx.ReadTimeout, httpx.TransportError) as exc:
                    elapsed_ms = (time.monotonic() - attempt_started) * 1000.0
                    if attempt < total_attempts:
                        backoff_seconds = self._retry_backoff_seconds(attempt)
                        logger.warning(
                            "OpenAI transport retry model=%s request_name=%s attempt=%s/%s "
                            "latency_ms=%.1f total_elapsed_ms=%.1f response_phase=%s "
                            "backoff_seconds=%.2f request_sequence=%s context=%s error=%s",
                            request.model_name,
                            request.request_name or "unspecified",
                            attempt,
                            total_attempts,
                            elapsed_ms,
                            (time.monotonic() - total_started) * 1000.0,
                            response_phase,
                            backoff_seconds,
                            request_sequence,
                            request.request_context,
                            str(exc),
                        )
                        time.sleep(backoff_seconds)
                        continue

                    logger.error(
                        "OpenAI transport failure model=%s request_name=%s attempts=%s "
                        "elapsed_ms=%.1f response_phase=%s request_sequence=%s context=%s error=%s",
                        request.model_name,
                        request.request_name or "unspecified",
                        attempt,
                        (time.monotonic() - total_started) * 1000.0,
                        response_phase,
                        request_sequence,
                        request.request_context,
                        str(exc),
                    )
                    raise LLMTransportError(f"OpenAI request failed: {exc}") from exc

    def _build_payload(self, request: LLMRequest) -> dict[str, object]:
        payload: dict[str, object] = {
            "model": request.model_name,
            "instructions": request.system_prompt,
            "input": request.user_prompt,
            "max_output_tokens": request.max_tokens,
        }
        if self._supports_reasoning_controls(request.model_name):
            payload["reasoning"] = {"effort": self.reasoning_effort}

        text_options: dict[str, object] = {}
        if self.text_verbosity:
            text_options["verbosity"] = self.text_verbosity
        text_format = self._response_text_format(request.response_format)
        if text_format is not None:
            text_options["format"] = text_format
        if text_options:
            payload["text"] = text_options
        return payload

    def _response_text_format(self, response_format: dict[str, object] | None) -> dict[str, object] | None:
        if not self.enable_response_format or response_format is None:
            return None
        if response_format.get("type") != "json_schema":
            return response_format
        json_schema = response_format.get("json_schema")
        if not isinstance(json_schema, dict):
            return response_format
        return {
            "type": "json_schema",
            "name": str(json_schema.get("name", "StructuredOutput")),
            "schema": json_schema.get("schema", {}),
            "strict": bool(json_schema.get("strict", True)),
        }

    def _build_response(
        self,
        *,
        raw_body: str,
        request: LLMRequest,
        latency_ms: float,
        request_id: str | None,
        response_phase: str,
    ) -> LLMResponse:
        try:
            data = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise LLMProviderError("OpenAI returned an unexpected non-JSON response.") from exc

        raw_text = data.get("output_text")
        if not isinstance(raw_text, str) or not raw_text.strip():
            raw_text = self._extract_output_text(data)
        if not raw_text.strip():
            if request.request_name == "ConfigValidationPing":
                raw_text = "OK"
            else:
                raise LLMProviderError("OpenAI returned an empty response.")

        logger.info(
            "OpenAI request success model=%s request_name=%s latency_ms=%.1f request_id=%s",
            request.model_name,
            request.request_name or "unspecified",
            latency_ms,
            request_id or data.get("id") or "unknown",
        )
        return LLMResponse(
            model_name=request.model_name,
            raw_text=raw_text,
            provider_name=self.provider_name,
            latency_ms=latency_ms,
            request_id=request_id or data.get("id"),
            response_phase=response_phase,
        )

    def _extract_output_text(self, data: dict[str, object]) -> str:
        output = data.get("output")
        if not isinstance(output, list):
            return ""
        parts: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for content_item in content:
                if not isinstance(content_item, dict):
                    continue
                text = content_item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)

    def _supports_reasoning_controls(self, model_name: str) -> bool:
        normalized = model_name.lower()
        return normalized.startswith("gpt-5") or normalized.startswith("o")

    def _next_request_sequence(self) -> int:
        with self._request_counter_lock:
            self._request_counter += 1
            return self._request_counter

    def _retry_backoff_seconds(self, attempt: int) -> float:
        base_delay = 0.5 * (2.0 ** (attempt - 1))
        jitter = random.uniform(0.0, 0.25)
        return round(base_delay + jitter, 2)

    @contextmanager
    def _acquire_request_slot(self) -> Iterator[None]:
        self._semaphore.acquire()
        try:
            yield
        finally:
            self._semaphore.release()
