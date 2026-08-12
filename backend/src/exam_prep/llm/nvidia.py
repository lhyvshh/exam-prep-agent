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


class NvidiaOpenAICompatibleClient:
    provider_name = "nvidia"
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
    ) -> None:
        self.api_key = api_key
        self.default_model_name = model_name
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.timeout = httpx.Timeout(
            timeout=timeout_seconds,
            connect=connect_timeout_seconds,
            read=read_timeout_seconds,
            write=write_timeout_seconds,
            pool=pool_timeout_seconds,
        )
        self.max_retries = max(0, max_retries)
        self.enable_response_format = enable_response_format
        self._response_format_supported = enable_response_format
        self._client = httpx.Client(timeout=self.timeout, headers={"Connection": "keep-alive"})
        self._semaphore = threading.BoundedSemaphore(max(1, max_concurrent_requests))
        self._request_counter_lock = threading.Lock()
        self._request_counter = 0
        logger.info(
            "Initialized LLM provider client provider=%s model=%s base_url=%s "
            "connect_timeout=%.1f read_timeout=%.1f write_timeout=%.1f pool_timeout=%.1f "
            "max_retries=%s max_concurrency=%s response_format_enabled=%s",
            self.provider_name,
            self.default_model_name,
            self.base_url,
            connect_timeout_seconds,
            read_timeout_seconds,
            write_timeout_seconds,
            pool_timeout_seconds,
            self.max_retries,
            max(1, max_concurrent_requests),
            self.enable_response_format,
        )

    def close(self) -> None:
        self._client.close()

    def generate(self, request: LLMRequest) -> LLMResponse:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = self._build_payload(request)
        total_started = time.monotonic()
        attempt = 0
        total_attempts = self.max_retries + 1
        request_sequence = self._next_request_sequence()
        queue_wait_started = time.monotonic()

        with self._acquire_request_slot():
            queue_wait_ms = (time.monotonic() - queue_wait_started) * 1000.0
            while True:
                attempt += 1
                attempt_started = time.monotonic()
                response_phase = "before_headers"
                logger.info(
                    "LLM request start provider=%s model=%s request_name=%s attempt=%s/%s "
                    "queue_wait_ms=%.1f request_sequence=%s client_reuse_hint=%s "
                    "response_format=%s context=%s",
                    self.provider_name,
                    request.model_name,
                    request.request_name or "unspecified",
                    attempt,
                    total_attempts,
                    queue_wait_ms,
                    request_sequence,
                    request_sequence > 1,
                    "response_format" in payload,
                    request.request_context,
                )
                try:
                    with self._client.stream(
                        "POST",
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                    ) as response:
                        if response.status_code >= 300:
                            response.read()
                        response.raise_for_status()
                        response_phase = "body_read"
                        raw_body = response.read().decode("utf-8", errors="replace")
                        latency_ms = (time.monotonic() - attempt_started) * 1000.0
                        request_id = response.headers.get("Nvcf-Reqid")
                        logger.info(
                            "LLM request success provider=%s model=%s request_name=%s attempt=%s "
                            "latency_ms=%.1f total_elapsed_ms=%.1f request_sequence=%s request_id=%s "
                            "response_phase=%s context=%s",
                            self.provider_name,
                            request.model_name,
                            request.request_name or "unspecified",
                            attempt,
                            latency_ms,
                            (time.monotonic() - total_started) * 1000.0,
                            request_sequence,
                            request_id or "unknown",
                            response_phase,
                            request.request_context,
                        )
                        return self._build_response(
                            raw_body=raw_body,
                            request=request,
                            latency_ms=latency_ms,
                            request_id=request_id,
                            response_phase=response_phase,
                        )
                except httpx.HTTPStatusError as exc:
                    detail = exc.response.text.strip() or exc.response.reason_phrase
                    if (
                        "response_format" in payload
                        and exc.response.status_code == 400
                        and self._response_format_may_be_unsupported(detail)
                    ):
                        logger.warning(
                            "LLM response_format unsupported provider=%s model=%s request_name=%s "
                            "status=%s detail=%s request_sequence=%s",
                            self.provider_name,
                            request.model_name,
                            request.request_name or "unspecified",
                            exc.response.status_code,
                            detail,
                            request_sequence,
                        )
                        self._response_format_supported = False
                        payload = self._build_payload(request)
                        continue
                    logger.error(
                        "LLM request failed provider=%s model=%s request_name=%s status=%s detail=%s "
                        "response_phase=%s request_sequence=%s context=%s",
                        self.provider_name,
                        request.model_name,
                        request.request_name or "unspecified",
                        exc.response.status_code,
                        detail,
                        response_phase,
                        request_sequence,
                        request.request_context,
                    )
                    raise LLMProviderError(
                        f"NVIDIA provider request failed with status {exc.response.status_code}: {detail}"
                    ) from exc
                except (httpx.ReadTimeout, httpx.TransportError) as exc:
                    elapsed_ms = (time.monotonic() - attempt_started) * 1000.0
                    if attempt < total_attempts:
                        backoff_seconds = self._retry_backoff_seconds(attempt)
                        logger.warning(
                            "LLM transport retry provider=%s model=%s request_name=%s attempt=%s/%s "
                            "latency_ms=%.1f total_elapsed_ms=%.1f response_phase=%s "
                            "backoff_seconds=%.2f request_sequence=%s context=%s error=%s",
                            self.provider_name,
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
                        "LLM transport failure provider=%s model=%s request_name=%s attempts=%s "
                        "elapsed_ms=%.1f response_phase=%s request_sequence=%s context=%s error=%s",
                        self.provider_name,
                        request.model_name,
                        request.request_name or "unspecified",
                        attempt,
                        (time.monotonic() - total_started) * 1000.0,
                        response_phase,
                        request_sequence,
                        request.request_context,
                        str(exc),
                    )
                    raise LLMTransportError(f"NVIDIA provider request failed: {exc}") from exc

    def _build_payload(self, request: LLMRequest) -> dict[str, object]:
        payload: dict[str, object] = {
            "model": request.model_name,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if self.enable_response_format and self._response_format_supported and request.response_format is not None:
            payload["response_format"] = request.response_format
        return payload

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
            choice = data["choices"][0]
            message = choice["message"]
            raw_text = message.get("content")
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            logger.error(
                "LLM response parse failure provider=%s model=%s request_name=%s body=%s context=%s",
                self.provider_name,
                request.model_name,
                request.request_name or "unspecified",
                raw_body,
                request.request_context,
            )
            raise LLMProviderError("NVIDIA provider returned an unexpected response payload.") from exc

        if not isinstance(raw_text, str) or not raw_text.strip():
            if request.request_name == "ConfigValidationPing":
                finish_reason = choice.get("finish_reason")
                logger.warning(
                    "LLM validation ping returned no assistant text; accepting provider response as connectivity success "
                    "provider=%s model=%s request_name=%s finish_reason=%s context=%s",
                    self.provider_name,
                    request.model_name,
                    request.request_name or "unspecified",
                    finish_reason,
                    request.request_context,
                )
                raw_text = "OK"
            else:
                logger.error(
                    "LLM empty response provider=%s model=%s request_name=%s body=%s context=%s",
                    self.provider_name,
                    request.model_name,
                    request.request_name or "unspecified",
                    raw_body,
                    request.request_context,
                )
                raise LLMProviderError("NVIDIA provider returned an empty completion.")

        return LLMResponse(
            model_name=request.model_name,
            raw_text=raw_text,
            provider_name=self.provider_name,
            latency_ms=latency_ms,
            request_id=request_id,
            response_phase=response_phase,
        )

    def _next_request_sequence(self) -> int:
        with self._request_counter_lock:
            self._request_counter += 1
            return self._request_counter

    def _retry_backoff_seconds(self, attempt: int) -> float:
        base_delay = 0.5 * (2 ** (attempt - 1))
        jitter = random.uniform(0.0, 0.25)
        return float(round(base_delay + jitter, 2))

    def _response_format_may_be_unsupported(self, detail: str) -> bool:
        lowered = detail.lower()
        return "response_format" in lowered or "json_schema" in lowered

    @contextmanager
    def _acquire_request_slot(self) -> Iterator[None]:
        self._semaphore.acquire()
        try:
            yield
        finally:
            self._semaphore.release()
