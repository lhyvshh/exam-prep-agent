from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from exam_prep.schemas.materials import MaterialRecord
from exam_prep.schemas.quiz import QuestionGradeResult, QuizAttemptSummary, RetryHistoryEntry


class QuizHistoryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quiz_id: str
    module_id: str | None = None
    record_type: str = "quiz"
    query: str
    question_count: int
    overall_score: float | None = None
    wrong_question_count: int = 0
    created_at: str | None = None
    attempts: list[QuizAttemptSummary] = Field(default_factory=list)


class MockExamHistoryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exam_id: str
    module_id: str | None = None
    module_ids: list[str] = Field(default_factory=list)
    title: str
    question_count: int
    target_difficulty: float
    created_at: str | None = None
    completed_at: str | None = None
    score_percent: float | None = None


class CourseDashboardResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    course_id: str
    module_id: str | None = None
    material_count: int = 0
    section_count: int = 0
    chunk_count: int = 0
    mastery_percent: float = 0.0
    mastery_by_concept: dict[str, float] = Field(default_factory=dict)
    wrong_concepts: list[str] = Field(default_factory=list)
    materials: list[MaterialRecord] = Field(default_factory=list)
    quizzes: list[QuizHistoryItem] = Field(default_factory=list)
    mock_exams: list[MockExamHistoryItem] = Field(default_factory=list)
    remediation_history: list[RetryHistoryEntry] = Field(default_factory=list)
    wrong_questions: list[QuestionGradeResult] = Field(default_factory=list)
    exam_readiness_score: float = 0.0
    weak_modules: list[dict[str, Any]] = Field(default_factory=list)
    weak_concepts_ranked: list[dict[str, Any]] = Field(default_factory=list)
    weak_question_types: list[dict[str, Any]] = Field(default_factory=list)
    study_recommendations: list[dict[str, Any]] = Field(default_factory=list)
