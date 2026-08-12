import httpx

from exam_prep.core.config import Settings
from exam_prep.llm.models import LLMRequest
from exam_prep.llm.nvidia import NvidiaOpenAICompatibleClient
from exam_prep.llm.registry import LLMClientRegistry
from exam_prep.schemas.config import LLMProvider, UserLLMConfig


def _json_response(payload: dict[str, object], status_code: int = 200) -> httpx.Response:
    request = httpx.Request("POST", "https://integrate.api.nvidia.com/v1/chat/completions")
    return httpx.Response(status_code, request=request, json=payload)


class FakeStreamResponse:
    def __init__(self, response: httpx.Response) -> None:
        self._response = response
        self.headers = response.headers
        self.status_code = response.status_code
        self.reason_phrase = response.reason_phrase
        self.text = response.text

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def raise_for_status(self) -> None:
        self._response.raise_for_status()

    def read(self) -> bytes:
        return self._response.read()


def test_nvidia_client_retries_transport_failures_then_succeeds(monkeypatch) -> None:
    outcomes: list[object] = [
        httpx.ReadTimeout("timed out"),
        httpx.ReadTimeout("timed out again"),
        _json_response(
            {
                "choices": [
                    {
                        "message": {
                            "content": '{"prompt":"Q","correct_answer":"A","rationale":"R","options":[],"correct_option_id":null}'
                        }
                    }
                ]
            }
        ),
    ]
    recorded_payloads: list[dict[str, object]] = []
    recorded_timeouts: list[httpx.Timeout] = []

    class FakeClient:
        def __init__(self, *, timeout, headers) -> None:
            del headers
            recorded_timeouts.append(timeout)

        def close(self) -> None:
            return None

        def stream(
            self,
            method: str,
            url: str,
            *,
            headers: dict[str, str],
            json: dict[str, object],
        ) -> FakeStreamResponse:
            del method, url, headers
            recorded_payloads.append(json)
            outcome = outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return FakeStreamResponse(outcome)

    monkeypatch.setattr("exam_prep.llm.nvidia.httpx.Client", FakeClient)
    monkeypatch.setattr("exam_prep.llm.nvidia.time.sleep", lambda seconds: None)

    client = NvidiaOpenAICompatibleClient(
        api_key="test-key",
        model_name="meta/llama-3.1-70b-instruct",
        base_url="https://integrate.api.nvidia.com/v1",
        timeout_seconds=60.0,
        connect_timeout_seconds=5.0,
        read_timeout_seconds=15.0,
        write_timeout_seconds=10.0,
        pool_timeout_seconds=5.0,
        max_retries=2,
        max_concurrent_requests=1,
        enable_response_format=True,
    )

    response = client.generate(
        LLMRequest(
            model_name="meta/llama-3.1-70b-instruct",
            system_prompt="Return JSON only.",
            user_prompt="Create a question.",
            response_format={"type": "json_object"},
            request_name="GeneratedQuestionPayload",
        )
    )

    assert response.raw_text.startswith("{")
    assert len(recorded_payloads) == 3
    assert recorded_payloads[0]["response_format"] == {"type": "json_object"}
    assert recorded_timeouts[0].connect == 5.0
    assert recorded_timeouts[0].read == 15.0


def test_nvidia_client_retries_without_response_format_when_unsupported(monkeypatch) -> None:
    unsupported_response = _json_response(
        {"error": {"message": "response_format json_schema is not supported"}},
        status_code=400,
    )
    success_response = _json_response(
        {
            "choices": [
                {
                    "message": {
                        "content": '{"prompt":"Q","correct_answer":"A","rationale":"R","options":[],"correct_option_id":null}'
                    }
                }
            ]
        }
    )
    outcomes: list[httpx.Response] = [unsupported_response, success_response]
    recorded_payloads: list[dict[str, object]] = []

    class FakeClient:
        def __init__(self, *, timeout, headers) -> None:
            del timeout, headers

        def close(self) -> None:
            return None

        def stream(
            self,
            method: str,
            url: str,
            *,
            headers: dict[str, str],
            json: dict[str, object],
        ) -> FakeStreamResponse:
            del method, url, headers
            recorded_payloads.append(json)
            return FakeStreamResponse(outcomes.pop(0))

    monkeypatch.setattr("exam_prep.llm.nvidia.httpx.Client", FakeClient)

    client = NvidiaOpenAICompatibleClient(
        api_key="test-key",
        model_name="meta/llama-3.1-70b-instruct",
        base_url="https://integrate.api.nvidia.com/v1",
        timeout_seconds=60.0,
        connect_timeout_seconds=5.0,
        read_timeout_seconds=15.0,
        write_timeout_seconds=10.0,
        pool_timeout_seconds=5.0,
        max_retries=2,
        max_concurrent_requests=1,
        enable_response_format=True,
    )

    response = client.generate(
        LLMRequest(
            model_name="meta/llama-3.1-70b-instruct",
            system_prompt="Return JSON only.",
            user_prompt="Create a question.",
            response_format={"type": "json_schema", "json_schema": {"name": "payload", "schema": {}}},
            request_name="GeneratedQuestionPayload",
        )
    )

    assert response.raw_text.startswith("{")
    assert "response_format" in recorded_payloads[0]
    assert "response_format" not in recorded_payloads[1]


def test_llm_client_registry_reuses_cached_client() -> None:
    created_clients: list[object] = []

    class DummyClient:
        def close(self) -> None:
            return None

    def fake_factory(settings, config, *, profile):  # type: ignore[no-untyped-def]
        del settings, config, profile
        client = DummyClient()
        created_clients.append(client)
        return client

    registry = LLMClientRegistry(
        settings=Settings(nvidia_api_base_url="https://base"),
        factory=fake_factory,
    )
    config = UserLLMConfig(
        provider=LLMProvider.NVIDIA,
        model="meta/llama-3.1-70b-instruct",
        api_key="test-key",
        demo_mode=False,
    )

    first = registry.get_or_create(config)
    second = registry.get_or_create(config)

    assert first is second
    assert len(created_clients) == 1


def test_nvidia_client_accepts_reasoning_only_connectivity_ping(monkeypatch) -> None:
    class FakeClient:
        def __init__(self, *, timeout, headers) -> None:
            del timeout, headers

        def close(self) -> None:
            return None

        def stream(
            self,
            method: str,
            url: str,
            *,
            headers: dict[str, str],
            json: dict[str, object],
        ) -> FakeStreamResponse:
            del method, url, headers, json
            return FakeStreamResponse(
                _json_response(
                    {
                        "choices": [
                            {
                                "message": {
                                    "content": None,
                                    "reasoning": " The user wants OK.",
                                },
                                "finish_reason": "length",
                            }
                        ]
                    }
                )
            )

    monkeypatch.setattr("exam_prep.llm.nvidia.httpx.Client", FakeClient)

    client = NvidiaOpenAICompatibleClient(
        api_key="test-key",
        model_name="moonshotai/kimi-k2.5",
        base_url="https://integrate.api.nvidia.com/v1",
        timeout_seconds=15.0,
        connect_timeout_seconds=5.0,
        read_timeout_seconds=12.0,
        write_timeout_seconds=10.0,
        pool_timeout_seconds=5.0,
        max_retries=0,
        max_concurrent_requests=1,
        enable_response_format=True,
    )

    response = client.generate(
        LLMRequest(
            model_name="moonshotai/kimi-k2.5",
            system_prompt="Reply with OK.",
            user_prompt="Reply with OK.",
            max_tokens=32,
            request_name="ConfigValidationPing",
        )
    )

    assert response.raw_text == "OK"
