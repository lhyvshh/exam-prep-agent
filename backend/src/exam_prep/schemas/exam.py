from pydantic import BaseModel, ConfigDict, Field, model_validator

from exam_prep.schemas.quiz import (
    ExamQuestionCategory,
    QuestionGradeResult,
    QuestionType,
    QuizQuestion,
    QuizSubmissionAnswer,
    StoredQuestionKey,
    mcq_only_question_types,
)
from exam_prep.schemas.scope import StudyScope


class ExamTopicCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str
    question_count: int = Field(default=1, ge=1, le=10)
    question_types: list[QuestionType] = Field(default_factory=mcq_only_question_types)

    @model_validator(mode="after")
    def _force_mcq_only(self) -> "ExamTopicCoverage":
        self.question_types = mcq_only_question_types()
        return self


class ExamBlueprint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    instructions: str
    topic_coverage: list[ExamTopicCoverage] = Field(default_factory=list)
    target_difficulty: float = Field(default=0.5, ge=0.0, le=1.0)
    style_example: str = Field(min_length=1)


class MockExamSourceOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    option_id: str
    text: str


class MockExamSourceQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_question_id: str
    source_exam_id: str
    question_number: int = Field(ge=1, le=200)
    prompt: str
    options: list[MockExamSourceOption] = Field(default_factory=list)
    correct_option_id: str | None = None
    correct_answer: str = ""
    explanation: str = ""
    topic: str = "Unclassified topic"
    learning_objective: str | None = None
    frm_question_type: ExamQuestionCategory | None = None
    difficulty: float = Field(default=0.6, ge=0.0, le=1.0)
    source_page: int | None = None
    matched_material_id: str | None = None
    matched_source_id: str | None = None
    matched_chunk_id: str | None = None
    matched_citation_label: str | None = None
    source_evidence: str | None = None


class MockExamSourceExam(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_exam_id: str
    title: str
    question_count: int = 0
    answer_count: int = 0
    questions: list[MockExamSourceQuestion] = Field(default_factory=list)


class MockExamSourceBank(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bank_id: str
    course_id: str
    file_name: str
    content_type: str | None = None
    uploaded_at: str
    extraction_mode: str = "text"
    exams: list[MockExamSourceExam] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class MockExamSourceIngestResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bank: MockExamSourceBank


class MockExamSourceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_exam_id: str
    title: str
    question_count: int
    answer_count: int
    average_difficulty: float = Field(ge=0.0, le=1.0)


class MockExamSourceBankSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bank_id: str
    course_id: str
    file_name: str
    uploaded_at: str
    exam_count: int
    question_count: int
    exams: list[MockExamSourceSummary] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class MockExamSourceListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sources: list[MockExamSourceBankSummary] = Field(default_factory=list)


class MockExamBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exam_id: str
    course_id: str
    module_id: str | None = None
    module_ids: list[str] = Field(default_factory=list)
    created_at: str | None = None
    blueprint: ExamBlueprint
    questions: list[QuizQuestion] = Field(default_factory=list)

    @model_validator(mode="after")
    def _normalize_scope(self) -> "MockExamBundle":
        normalized = [module_id for module_id in self.module_ids if module_id]
        if not normalized and self.module_id:
            normalized = [self.module_id]
        self.module_ids = list(dict.fromkeys(normalized))
        self.module_id = self.module_ids[0] if len(self.module_ids) == 1 else None
        return self


class MockExamGenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    course_id: str
    module_id: str | None = None
    module_ids: list[str] = Field(default_factory=list)
    scope: StudyScope | None = None
    source_exam_id: str | None = None
    blueprint: ExamBlueprint
    retrieval_top_k: int = Field(default=8, ge=1, le=20)

    @model_validator(mode="after")
    def _normalize_scope(self) -> "MockExamGenerationRequest":
        normalized = [module_id for module_id in self.module_ids if module_id]
        if self.scope and self.scope.module_ids:
            normalized = [*normalized, *self.scope.module_ids]
        if not normalized and self.module_id:
            normalized = [self.module_id]
        self.module_ids = list(dict.fromkeys(normalized))
        self.module_id = self.module_ids[0] if len(self.module_ids) == 1 else None
        return self


class MockExamGenerationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exam: MockExamBundle


class MockExamGradeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exam_id: str
    answers: list[QuizSubmissionAnswer] = Field(default_factory=list)


class ConceptAnalytics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    concept: str
    question_count: int
    correct_count: int
    average_score: float


class MockExamGradeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exam_id: str
    course_id: str
    module_id: str | None = None
    module_ids: list[str] = Field(default_factory=list)
    completed_at: str | None = None
    overall_score: float
    analytics_by_concept: list[ConceptAnalytics] = Field(default_factory=list)
    results: list[QuestionGradeResult] = Field(default_factory=list)

    @model_validator(mode="after")
    def _normalize_scope(self) -> "MockExamGradeResponse":
        normalized = [module_id for module_id in self.module_ids if module_id]
        if not normalized and self.module_id:
            normalized = [self.module_id]
        self.module_ids = list(dict.fromkeys(normalized))
        self.module_id = self.module_ids[0] if len(self.module_ids) == 1 else None
        return self


class MockExamReviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exam: MockExamBundle
    grade_result: MockExamGradeResponse | None = None


class StoredMockExamSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exam: MockExamBundle
    answer_keys: list[StoredQuestionKey] = Field(default_factory=list)
    grade_result: MockExamGradeResponse | None = None
