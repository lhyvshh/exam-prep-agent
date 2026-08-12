from typing import Protocol

from exam_prep.llm.models import LLMRequest, LLMResponse


class LLMClient(Protocol):
    def generate(self, request: LLMRequest) -> LLMResponse:
        ...
