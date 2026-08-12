import httpx

from exam_prep.llm.models import LLMRequest
from exam_prep.llm.nvidia import NvidiaOpenAICompatibleClient


def _stream_response(body: bytes, status_code: int) -> httpx.Response:
    request = httpx.Request("POST", "https://integrate.api.nvidia.com/v1/chat/completions")
    return httpx.Response(status_code, request=request, stream=httpx.ByteStream(body))


def _json_response(payload: dict[str, object]) -> httpx.Response:
    request = httpx.Request("POST", "https://integrate.api.nvidia.com/v1/chat/completions")
    return httpx.Response(200, request=request, json=payload)


class _FakeStreamResponse:
    def __init__(self, response: httpx.Response) -> None:
        self._response = response
        self.headers = response.headers
        self.status_code = response.status_code

    def __enter__(self) -> "_FakeStreamResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def raise_for_status(self) -> None:
        self._response.raise_for_status()

    def read(self) -> bytes:
        return self._response.read()


def test_nvidia_client_retries_streamed_response_format_error_without_masking_body(monkeypatch) -> None:
    outcomes = [
        _stream_response(b'{"error":{"message":"response_format json_schema is not supported"}}', 400),
        _json_response(
            {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"prompt":"Q","correct_answer":"A","rationale":"R",'
                                '"options":[],"correct_option_id":null}'
                            )
                        }
                    }
                ]
            }
        ),
    ]
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
        ) -> _FakeStreamResponse:
            del method, url, headers
            recorded_payloads.append(json)
            return _FakeStreamResponse(outcomes.pop(0))

    monkeypatch.setattr("exam_prep.llm.nvidia.httpx.Client", FakeClient)

    client = NvidiaOpenAICompatibleClient(
        api_key="test-key",
        model_name="qwen/qwen3.5-397b-a17b",
        base_url="https://integrate.api.nvidia.com/v1",
        timeout_seconds=60.0,
        connect_timeout_seconds=5.0,
        read_timeout_seconds=15.0,
        write_timeout_seconds=10.0,
        pool_timeout_seconds=5.0,
        max_retries=0,
        max_concurrent_requests=1,
        enable_response_format=True,
    )

    response = client.generate(
        LLMRequest(
            model_name="qwen/qwen3.5-397b-a17b",
            system_prompt="Return JSON only.",
            user_prompt="Create a question.",
            response_format={"type": "json_schema", "json_schema": {"name": "payload", "schema": {}}},
            request_name="GeneratedQuestionPayload",
        )
    )

    assert response.raw_text.startswith("{")
    assert "response_format" in recorded_payloads[0]
    assert "response_format" not in recorded_payloads[1]
