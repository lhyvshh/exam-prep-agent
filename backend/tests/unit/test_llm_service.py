import json

import pytest

from exam_prep.core.exceptions import LLMResponseSchemaError
from exam_prep.llm.models import LLMResponse
from exam_prep.schemas.quiz import GeneratedQuestionPayload
from exam_prep.services.llm_service import StructuredLLMService


class FakeLLMClient:
    def __init__(self, raw_payload: dict[str, object]) -> None:
        self.raw_payload = raw_payload

    def generate(self, request):  # type: ignore[no-untyped-def]
        return LLMResponse(
            model_name=request.model_name,
            provider_name="nvidia",
            raw_text=json.dumps(self.raw_payload),
        )


def test_structured_llm_service_normalizes_prompt_and_option_aliases() -> None:
    service = StructuredLLMService(
        FakeLLMClient(
            {
                "question": "Which statement is supported by the source excerpt?",
                "answer": "Option B",
                "reasoning": "The cited excerpt explicitly describes the learning-rate update.",
                "options": [
                    {"option_id": "A", "option": "Gradient descent removes all parameters from the model."},
                    {
                        "option_id": "B",
                        "option": "Gradient descent updates parameters using the learning rate.",
                    },
                    {"option_id": "C", "option": "Gradient descent skips the objective function entirely."},
                    {"option_id": "D", "option": "Gradient descent guarantees one-step convergence."},
                ],
            }
        ),
        "meta/llama-3.1-70b-instruct",
    )

    payload = service.generate_model(
        GeneratedQuestionPayload,
        system_prompt="Return JSON only.",
        user_prompt="Create a grounded question.",
    )

    assert payload.prompt == "Which statement is supported by the source excerpt?"
    assert payload.correct_option_id == "B"
    assert payload.correct_answer == "Gradient descent updates parameters using the learning rate."
    assert [option.option_id for option in payload.options] == ["A", "B", "C", "D"]
    assert payload.options[1].text == "Gradient descent updates parameters using the learning rate."


def test_structured_llm_service_normalizes_logged_nvidia_payload_shape() -> None:
    service = StructuredLLMService(
        FakeLLMClient(
            {
                "prompt": "What is the result of the expression x = 5 % 2?",
                "correct_answer": "1",
                "rationale": "The % operator returns the remainder after integer division.",
                "options": [
                    {"option_id": "A", "option": "0"},
                    {"option_id": "B", "option": "1"},
                    {"option_id": "C", "option": "2"},
                    {"option_id": "D", "option": "3"},
                ],
                "correct_option_id": "B",
            }
        ),
        "meta/llama-3.1-70b-instruct",
    )

    payload = service.generate_model(
        GeneratedQuestionPayload,
        system_prompt="Return JSON only.",
        user_prompt="Create a grounded question.",
    )

    assert payload.prompt == "What is the result of the expression x = 5 % 2?"
    assert payload.correct_option_id == "B"
    assert payload.correct_answer == "1"
    assert payload.options[1].text == "1"


def test_structured_llm_service_raises_explicit_schema_error_for_missing_fields() -> None:
    service = StructuredLLMService(
        FakeLLMClient(
            {
                "prompt": "Which statement is supported by the excerpt?",
                "options": [{"option_id": "A", "option": "Only option"}],
            }
        ),
        "meta/llama-3.1-70b-instruct",
    )

    with pytest.raises(LLMResponseSchemaError, match="correct_answer"):
        service.generate_model(
            GeneratedQuestionPayload,
            system_prompt="Return JSON only.",
            user_prompt="Create a grounded question.",
        )
