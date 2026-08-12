import json

import httpx

from exam_prep.llm.models import LLMRequest
from exam_prep.llm.openai import OpenAIResponsesClient


def test_openai_responses_client_sends_responses_payload_and_parses_output_text() -> None:
    captured_payloads: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_payloads.append(json.loads(request.content.decode("utf-8")))
        return httpx.Response(
            200,
            json={
                "id": "resp_test",
                "output_text": '{"answer":"OK"}',
            },
            headers={"x-request-id": "req_test"},
        )

    client = OpenAIResponsesClient(
        api_key="test-key",
        model_name="gpt-5.4-mini",
        base_url="https://api.openai.test/v1",
        timeout_seconds=10.0,
        connect_timeout_seconds=2.0,
        read_timeout_seconds=5.0,
        write_timeout_seconds=5.0,
        pool_timeout_seconds=5.0,
        max_retries=0,
        max_concurrent_requests=1,
        enable_response_format=True,
        reasoning_effort="none",
        text_verbosity="low",
    )
    client._client = httpx.Client(transport=httpx.MockTransport(handler))  # noqa: SLF001

    response = client.generate(
        LLMRequest(
            model_name="gpt-5.4-mini",
            system_prompt="Return JSON.",
            user_prompt="Ping",
            max_tokens=128,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "PingResult",
                    "schema": {
                        "type": "object",
                        "properties": {"answer": {"type": "string"}},
                        "required": ["answer"],
                        "additionalProperties": False,
                    },
                    "strict": True,
                },
            },
            request_name="unit-test",
        )
    )

    assert response.raw_text == '{"answer":"OK"}'
    assert response.request_id == "req_test"
    assert captured_payloads[0]["model"] == "gpt-5.4-mini"
    assert captured_payloads[0]["instructions"] == "Return JSON."
    assert captured_payloads[0]["input"] == "Ping"
    assert captured_payloads[0]["reasoning"] == {"effort": "none"}
    assert captured_payloads[0]["text"] == {
        "verbosity": "low",
        "format": {
            "type": "json_schema",
            "name": "PingResult",
            "schema": {
                "type": "object",
                "properties": {"answer": {"type": "string"}},
                "required": ["answer"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    }
