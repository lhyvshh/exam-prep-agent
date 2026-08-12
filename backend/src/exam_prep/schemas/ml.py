from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class QuestionQualityLabel(StrEnum):
    LOW_QUALITY = "low_quality"
    NEEDS_REVIEW = "needs_review"
    HIGH_QUALITY = "high_quality"


class QuestionQualityValidation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    label: QuestionQualityLabel
    accepted_for_delivery: bool
    model_version: str
    model_source: str
    notes: list[str] = Field(default_factory=list)


class QuestionQualityInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str | None = None
    prompt: str = Field(min_length=1)
    question_type: str = Field(min_length=1)
    concept: str = ""
    section_title: str = ""
    difficulty: float = Field(default=0.5, ge=0.0, le=1.0)
    options: list[str] = Field(default_factory=list)
    rationale: str | None = None
    citation_count: int = Field(default=0, ge=0)


class QuestionQualityScoreResult(QuestionQualityValidation):
    model_config = ConfigDict(extra="forbid")

    question_id: str | None = None


class QuestionQualityScoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    questions: list[QuestionQualityInput] = Field(default_factory=list, min_length=1)


class QuestionQualityScoreResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    results: list[QuestionQualityScoreResult] = Field(default_factory=list)
