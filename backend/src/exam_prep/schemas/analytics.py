from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ConceptMasteryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    user_id: str
    course_id: str
    module_id: str | None = None
    material_id: str | None = None
    section_id: str | None = None
    concept_id: str
    attempts: int
    correct_attempts: int
    accuracy: float
    repeat_misses: int
    average_time_seconds: float | None = None
    mastery_score: float
    last_attempt_at: str | None = None
    updated_at: str
    priority_score: float = 0.0
    weak_question_types: list[str] = Field(default_factory=list)


class QuestionTypeMasteryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    user_id: str
    course_id: str
    module_id: str | None = None
    concept_id: str | None = None
    question_type: str
    attempts: int
    correct_attempts: int
    accuracy: float
    average_time_seconds: float | None = None
    updated_at: str
    priority_score: float = 0.0


class ModuleMasteryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    user_id: str
    course_id: str
    module_id: str
    attempts: int
    correct_attempts: int
    accuracy: float
    average_time_seconds: float | None = None
    mastery_score: float
    weak_concepts: list[dict[str, Any]] = Field(default_factory=list)
    weak_question_types: list[dict[str, Any]] = Field(default_factory=list)
    updated_at: str
    priority_score: float = 0.0


class RecommendationHistoryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    user_id: str
    course_id: str
    recommendation_type: str
    title: str
    target_module_id: str | None = None
    target_section_id: str | None = None
    target_concept_id: str | None = None
    reason: str
    recommended_action: str
    priority_score: float
    clicked: bool = False
    completed: bool = False
    created_at: str


class AnalyticsOverviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    course_id: str
    accuracy_by_module: dict[str, float] = Field(default_factory=dict)
    accuracy_by_concept: dict[str, float] = Field(default_factory=dict)
    accuracy_by_question_type: dict[str, float] = Field(default_factory=dict)
    accuracy_by_difficulty: dict[str, float] = Field(default_factory=dict)
    average_time_per_question: float | None = None
    time_spent_per_material: dict[str, int] = Field(default_factory=dict)
    time_spent_per_section: dict[str, int] = Field(default_factory=dict)
    repeat_misses: int = 0
    recent_improvement_trend: float = 0.0
    quiz_completion_rate: float = 0.0
    most_clicked_materials: list[dict[str, Any]] = Field(default_factory=list)
    least_reviewed_weak_materials: list[dict[str, Any]] = Field(default_factory=list)
    weak_concept_clusters: list[dict[str, Any]] = Field(default_factory=list)
    exam_readiness_score: float = 0.0


class AnalyticsModulesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    course_id: str
    modules: list[ModuleMasteryRecord] = Field(default_factory=list)


class AnalyticsConceptsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    course_id: str
    concepts: list[ConceptMasteryRecord] = Field(default_factory=list)


class AnalyticsQuestionTypesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    course_id: str
    question_types: list[QuestionTypeMasteryRecord] = Field(default_factory=list)


class AnalyticsRecommendationsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    course_id: str
    recommendations: list[RecommendationHistoryRecord] = Field(default_factory=list)


class AgentAnalyticsContextResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    course_id: str
    overview: AnalyticsOverviewResponse
    weak_modules: list[ModuleMasteryRecord] = Field(default_factory=list)
    weak_concepts: list[ConceptMasteryRecord] = Field(default_factory=list)
    weak_question_types: list[QuestionTypeMasteryRecord] = Field(default_factory=list)
    recommendations: list[RecommendationHistoryRecord] = Field(default_factory=list)
