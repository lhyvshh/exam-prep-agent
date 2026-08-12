import json

import httpx

from exam_prep.core.config import Settings
from exam_prep.llm.anthropic import AnthropicMessagesClient
from exam_prep.llm.factory import create_llm_client
from exam_prep.llm.models import LLMRequest
from exam_prep.schemas.config import LLMProvider, UserLLMConfig


def test_anthropic_messages_client_sends_messages_payload_and_parses_text_block() -> None:
    captured_payloads: list[dict[str, object]] = []
    captured_headers: list[httpx.Headers] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_payloads.append(json.loads(request.content.decode("utf-8")))
        captured_headers.append(request.headers)
        return httpx.Response(
            200,
            json={
                "id": "msg_test",
                "content": [{"type": "text", "text": '{"answer":"OK"}'}],
            },
            headers={"request-id": "req_test"},
        )

    client = AnthropicMessagesClient(
        api_key="test-key",
        model_name="claude-sonnet-4-5",
        base_url="https://api.anthropic.test/v1",
        timeout_seconds=10.0,
        connect_timeout_seconds=2.0,
        read_timeout_seconds=5.0,
        write_timeout_seconds=5.0,
        pool_timeout_seconds=5.0,
        max_retries=0,
        max_concurrent_requests=1,
    )
    client._client = httpx.Client(transport=httpx.MockTransport(handler))  # noqa: SLF001

    response = client.generate(
        LLMRequest(
            model_name="claude-sonnet-4-5",
            system_prompt="Return JSON.",
            user_prompt="Ping",
            max_tokens=128,
            request_name="unit-test",
            temperature=0.2,
        )
    )

    assert response.raw_text == '{"answer":"OK"}'
    assert response.request_id == "req_test"
    assert response.provider_name == "anthropic"
    assert captured_headers[0]["x-api-key"] == "test-key"
    assert captured_headers[0]["anthropic-version"] == "2023-06-01"
    assert captured_payloads[0] == {
        "model": "claude-sonnet-4-5",
        "system": "Return JSON.",
        "messages": [{"role": "user", "content": "Ping"}],
        "max_tokens": 128,
        "temperature": 0.2,
    }


def test_factory_creates_anthropic_client() -> None:
    client = create_llm_client(
        Settings(anthropic_api_base_url="https://api.anthropic.test/v1"),
        UserLLMConfig(
            provider=LLMProvider.ANTHROPIC,
            model="claude-sonnet-4-5",
            api_key="test-key",
            demo_mode=False,
        ),
    )

    assert isinstance(client, AnthropicMessagesClient)
    assert client.base_url == "https://api.anthropic.test/v1"
