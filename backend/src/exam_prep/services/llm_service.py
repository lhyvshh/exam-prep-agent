import json
import logging
import re
from dataclasses import dataclass
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from exam_prep.core.exceptions import LLMProviderError, LLMResponseSchemaError
from exam_prep.llm.base import LLMClient
from exam_prep.llm.models import LLMRequest, LLMResponse
from exam_prep.schemas.quiz import (
    GeneratedExplanationPayload,
    GeneratedQuestionPayload,
    GeneratedShortAnswerGradePayload,
)

StructuredModel = TypeVar("StructuredModel", bound=BaseModel)
logger = logging.getLogger(__name__)


@dataclass(slots=True)
class StructuredLLMCallMetadata:
    normalization_applied: bool = False


class StructuredLLMService:
    def __init__(self, llm_client: LLMClient | None, model_name: str) -> None:
        self.llm_client = llm_client
        self.model_name = model_name
        self.last_call_metadata: StructuredLLMCallMetadata | None = None
        self.last_llm_response: LLMResponse | None = None

    def available(self) -> bool:
        return self.llm_client is not None

    def generate_model(
        self,
        response_model: type[StructuredModel],
        *,
        model_name: str | None = None,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 1200,
        allow_repair_with_llm: bool = False,
        request_name: str | None = None,
        request_context: dict[str, str] | None = None,
    ) -> StructuredModel:
        del allow_repair_with_llm
        if self.llm_client is None:
            raise LLMProviderError("No live LLM provider is configured for this request.")
        active_model_name = model_name or self.model_name
        self.last_call_metadata = StructuredLLMCallMetadata(normalization_applied=False)
        self.last_llm_response = None

        response = self.llm_client.generate(
            LLMRequest(
                model_name=active_model_name,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                request_name=request_name or response_model.__name__,
                response_format=self._response_format_for_model(response_model),
                request_context=request_context or {},
            )
        )
        self.last_llm_response = response
        payload = self._extract_json_object(response.raw_text)
        try:
            return response_model.model_validate(payload)
        except ValidationError as exc:
            logger.warning(
                "LLM schema validation failed model=%s response_model=%s validation_errors=%s raw_payload=%s",
                active_model_name,
                response_model.__name__,
                self._serialize_validation_errors(exc),
                payload,
            )

        try:
            normalized_payload, normalization_notes = self._normalize_payload(response_model, payload)
        except LLMResponseSchemaError as exc:
            logger.warning(
                "LLM payload normalization failed model=%s response_model=%s error=%s raw_payload=%s",
                active_model_name,
                response_model.__name__,
                str(exc),
                payload,
            )
            raise

        if normalized_payload is None:
            raise LLMResponseSchemaError(
                "The provider returned a response that could not be normalized into the expected schema."
            )

        try:
            validated = response_model.model_validate(normalized_payload)
        except ValidationError as exc:
            logger.warning(
                "LLM normalized payload validation failed model=%s response_model=%s validation_errors=%s "
                "normalized_payload=%s normalization_notes=%s",
                active_model_name,
                response_model.__name__,
                self._serialize_validation_errors(exc),
                normalized_payload,
                normalization_notes,
            )
            raise LLMResponseSchemaError(
                "The provider returned a response that did not match the expected schema after normalization."
            ) from exc

        if normalization_notes:
            if self.last_call_metadata is not None:
                self.last_call_metadata.normalization_applied = True
            logger.info(
                "LLM payload normalization succeeded model=%s response_model=%s notes=%s",
                active_model_name,
                response_model.__name__,
                normalization_notes,
            )
        return validated

    def _response_format_for_model(
        self,
        response_model: type[StructuredModel],
    ) -> dict[str, object] | None:
        if self.llm_client is None:
            return None
        if getattr(self.llm_client, "supports_json_schema_response_format", False):
            if not getattr(self.llm_client, "enable_response_format", True):
                return None
            return {
                "type": "json_schema",
                "json_schema": {
                    "name": response_model.__name__,
                    "schema": response_model.model_json_schema(),
                    "strict": True,
                },
            }
        return None

    def _extract_json_object(self, raw_text: str) -> dict[str, object]:
        stripped = raw_text.strip()
        candidates = [stripped]

        fenced_start = stripped.find("{")
        fenced_end = stripped.rfind("}")
        if fenced_start != -1 and fenced_end != -1 and fenced_end > fenced_start:
            candidates.append(stripped[fenced_start : fenced_end + 1])

        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
            if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                return parsed[0]

        raise LLMResponseSchemaError("The provider did not return valid JSON.")

    def _normalize_payload(
        self,
        response_model: type[StructuredModel],
        payload: dict[str, object],
    ) -> tuple[dict[str, object] | None, list[str]]:
        if response_model is GeneratedExplanationPayload:
            explanation = self._first_string(payload, ["explanation", "feedback", "rationale"])
            if not explanation:
                raise LLMResponseSchemaError("Missing required field: explanation.")
            notes = ["mapped feedback/rationale -> explanation"] if "explanation" not in payload else []
            return {"explanation": explanation}, notes

        if response_model is GeneratedShortAnswerGradePayload:
            explanation = self._first_string(payload, ["explanation", "feedback", "rationale"])
            raw_is_correct = payload.get("is_correct")
            raw_score = payload.get("score")
            grade_notes: list[str] = []
            if isinstance(raw_is_correct, str):
                raw_is_correct = raw_is_correct.strip().lower() in {"true", "yes", "correct", "1"}
                grade_notes.append("coerced string is_correct -> bool")
            if not isinstance(raw_is_correct, bool):
                raise LLMResponseSchemaError("Missing required field: is_correct.")
            if not isinstance(raw_score, (int, float)):
                raw_score = 1.0 if raw_is_correct else 0.0
                grade_notes.append("filled missing score from is_correct")
            if not explanation:
                explanation = "Graded against the grounded source excerpt."
                grade_notes.append("filled missing explanation with default")
            return {
                "is_correct": raw_is_correct,
                "score": float(raw_score),
                "explanation": explanation,
            }, grade_notes

        if response_model is GeneratedQuestionPayload:
            return self._normalize_generated_question_payload(payload)

        return None, []

    def _normalize_generated_question_payload(
        self,
        payload: dict[str, object],
    ) -> tuple[dict[str, object], list[str]]:
        notes: list[str] = []
        prompt = self._first_string(payload, ["prompt", "question", "instruction"])
        if not prompt:
            raise LLMResponseSchemaError("Missing required field: prompt or question.")
        if "prompt" not in payload:
            notes.append("mapped question/instruction -> prompt")

        correct_answer = self._first_string(
            payload,
            ["correct_answer", "answer", "expected_answer", "correct_option_text"],
        )
        if correct_answer and "correct_answer" not in payload:
            notes.append("mapped answer/expected_answer -> correct_answer")

        rationale = self._first_string(payload, ["rationale", "reasoning", "explanation"])
        if rationale and "rationale" not in payload:
            notes.append("mapped reasoning/explanation -> rationale")
        if not rationale:
            rationale = "Grounded in the retrieved material."
            notes.append("filled missing rationale with default")

        normalized_options = self._normalize_options(payload.get("options"))
        if payload.get("options") is not None and "options" in payload and normalized_options != payload.get("options"):
            notes.append("normalized options payload")

        correct_option_id = self._first_string(
            payload,
            ["correct_option_id", "correct_option", "answer_option", "correct_choice"],
        )
        if correct_option_id:
            normalized_option_id = self._normalize_option_id(correct_option_id)
            if normalized_option_id is None:
                raise LLMResponseSchemaError(
                    f'Invalid correct_option_id value: "{correct_option_id}". Expected A-D.'
                )
            if normalized_option_id != correct_option_id.strip():
                notes.append("normalized correct_option_id casing/format")
            correct_option_id = normalized_option_id

        if normalized_options and correct_answer and not correct_option_id:
            derived_option_id = self._normalize_option_id(correct_answer)
            if derived_option_id is not None:
                correct_option_id = derived_option_id
                notes.append("derived correct_option_id from correct_answer label")

        if normalized_options and not correct_option_id and correct_answer:
            for option in normalized_options:
                option_text = str(option.get("text", "")).strip().lower()
                if option_text == correct_answer.strip().lower():
                    correct_option_id = str(option["option_id"])
                    notes.append("derived correct_option_id from option text match")
                    break

        if normalized_options and correct_option_id and not correct_answer:
            for option in normalized_options:
                if str(option["option_id"]) == correct_option_id:
                    correct_answer = str(option["text"])
                    notes.append("derived correct_answer from correct_option_id")
                    break

        if normalized_options and correct_option_id and correct_answer:
            normalized_correct_answer_option = self._normalize_option_id(correct_answer)
            if normalized_correct_answer_option is not None and normalized_correct_answer_option == correct_option_id:
                for option in normalized_options:
                    if str(option["option_id"]) == correct_option_id:
                        correct_answer = str(option["text"])
                        notes.append("expanded correct_answer from option id to option text")
                        break

        if normalized_options and correct_option_id:
            valid_option_ids = {str(option["option_id"]) for option in normalized_options}
            if correct_option_id not in valid_option_ids:
                raise LLMResponseSchemaError(
                    f"correct_option_id {correct_option_id} does not match any option_id in options."
                )

        if not correct_answer:
            raise LLMResponseSchemaError("Missing required field: correct_answer.")

        return {
            "prompt": prompt.strip(),
            "correct_answer": correct_answer.strip(),
            "rationale": rationale.strip(),
            "options": normalized_options,
            "correct_option_id": correct_option_id,
        }, notes

    def _normalize_options(self, raw_options: object) -> list[dict[str, object]]:
        if raw_options is None:
            return []

        normalized: list[dict[str, object]] = []
        if isinstance(raw_options, dict):
            for key, value in raw_options.items():
                if not isinstance(value, str) or not value.strip():
                    raise LLMResponseSchemaError(
                        f'Invalid option value for option "{key}". Expected a non-empty string.'
                    )
                option_id = self._normalize_option_id(str(key)) or chr(ord("A") + len(normalized))
                normalized.append({"option_id": option_id, "text": self._strip_option_prefix(value)})
            return normalized

        if not isinstance(raw_options, list):
            raise LLMResponseSchemaError("Field options must be a list or object mapping.")

        for index, item in enumerate(raw_options):
            default_option_id = chr(ord("A") + index)
            if isinstance(item, str):
                parsed_option_id = self._normalize_option_id(item)
                normalized.append(
                    {
                        "option_id": parsed_option_id or default_option_id,
                        "text": self._strip_option_prefix(item),
                    }
                )
                continue
            if not isinstance(item, dict):
                raise LLMResponseSchemaError(
                    f"Invalid option at index {index}. Expected an object or string."
                )

            text = self._first_string(item, ["text", "value", "option", "label", "content"])
            if not text:
                raise LLMResponseSchemaError(
                    f"Invalid option at index {index}. Missing text/value/option field."
                )
            explicit_id = self._first_string(item, ["option_id", "id", "label"])
            normalized_option_id = (
                self._normalize_option_id(explicit_id) if explicit_id is not None else None
            )
            normalized.append(
                {
                    "option_id": normalized_option_id or default_option_id,
                    "text": self._strip_option_prefix(text),
                }
            )
        return normalized

    def _first_string(self, payload: dict[str, object], keys: list[str]) -> str | None:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _normalize_option_id(self, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip().upper()
        if stripped in {"A", "B", "C", "D"}:
            return stripped

        match = re.search(r"\b([A-D])\b", stripped)
        if match:
            return match.group(1)

        match = re.match(r"^\(?([A-D])[\)\.\:\-]?\s+", stripped)
        if match:
            return match.group(1)

        return None

    def _strip_option_prefix(self, value: str) -> str:
        return re.sub(r"^\s*\(?[A-D]\)?[\.\:\-]?\s+", "", value).strip()

    def _serialize_validation_errors(self, exc: ValidationError) -> str:
        return json.dumps(exc.errors(include_url=False), ensure_ascii=True)
