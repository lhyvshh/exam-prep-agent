from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from exam_prep.schemas.materials import SourceChunk
from exam_prep.schemas.scope import StudyScope
from exam_prep.schemas.ml import QuestionQualityValidation


class QuestionType(StrEnum):
    MCQ = "mcq"
    SHORT_ANSWER = "short_answer"


def mcq_only_question_types() -> list[QuestionType]:
    return [QuestionType.MCQ]


class QuestionStyle(StrEnum):
    DEFINITION = "definition"
    CONCEPT_CHECK = "concept_check"
    SCENARIO = "scenario"
    CALCULATION = "calculation"
    CASE_BASED = "case_based"
    MULTIPLE_SELECT = "multiple_select"
    TRUE_FALSE_WITH_EXPLANATION = "true_false_with_explanation"
    APPLICATION = "application"
    COMPARISON = "comparison"
    EXAM_STYLE_MIXED = "exam_style_mixed"


class ExamQuestionCategory(StrEnum):
    APPLIED_CONCEPTUAL = "Applied conceptual"
    CALCULATION = "Numerical calculation"
    SCENARIO = "Scenario or mini-case"
    MODEL_INTERPRETATION = "Model interpretation and limitations"
    ETHICS = "Ethics and professional conduct"


class QuizGenerationJobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class QuestionGenerationMode(StrEnum):
    LIVE = "live"
    NORMALIZED_LIVE = "normalized_live"
    FALLBACK = "fallback"


class StudyRecordType(StrEnum):
    QUIZ = "quiz"
    CONCEPT_PRACTICE = "concept_practice"


class QuizQuestionOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    option_id: str
    text: str


class GeneratedQuestionOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    option_id: str
    text: str


class GeneratedQuestionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str
    correct_answer: str
    rationale: str
    options: list[GeneratedQuestionOption] = Field(default_factory=list)
    correct_option_id: str | None = None


class GeneratedShortAnswerGradePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_correct: bool
    score: float = Field(ge=0.0, le=1.0)
    explanation: str


class GeneratedExplanationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    explanation: str


class QuizQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    quiz_id: str | None = None
    course_id: str | None = None
    module_id: str | None = None
    material_id: str | None = None
    section_id: str | None = None
    concept_id: str | None = None
    source_page: int | None = None
    question_id: str
    question_type: QuestionType
    question_style: QuestionStyle = QuestionStyle.EXAM_STYLE_MIXED
    frm_question_type: ExamQuestionCategory | None = None
    concept: str
    section_title: str
    difficulty: float = 0.5
    prompt: str
    question_text: str | None = None
    options: list[QuizQuestionOption] = Field(default_factory=list)
    answer_choices_json: list[QuizQuestionOption] = Field(default_factory=list)
    correct_answer: str | None = None
    explanation: str | None = None
    source_evidence: str | None = None
    created_at: str | None = None
    citations: list[SourceChunk] = Field(default_factory=list)
    rationale: str | None = None
    quality_validation: QuestionQualityValidation | None = None


class QuizBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quiz_id: str
    course_id: str
    module_id: str | None = None
    query: str
    created_at: str | None = None
    record_type: StudyRecordType = StudyRecordType.QUIZ
    questions: list[QuizQuestion] = Field(default_factory=list)


class QuizGenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = "demo-user"
    course_id: str
    module_id: str | None = None
    material_id: str | None = None
    section_id: str | None = None
    concept_id: str | None = None
    weak_area_id: str | None = None
    query: str = Field(min_length=1)
    question_count: int = Field(default=2, ge=1, le=10)
    question_types: list[QuestionType] = Field(
        default_factory=mcq_only_question_types,
        min_length=1,
    )
    question_styles: list[QuestionStyle] = Field(
        default_factory=lambda: [QuestionStyle.EXAM_STYLE_MIXED],
        min_length=1,
    )
    retrieval_top_k: int = Field(default=6, ge=1, le=20)
    selected_source_ids: list[str] = Field(default_factory=list)
    missed_question_ids: list[str] = Field(default_factory=list)
    scope: StudyScope | None = None
    client_request_id: str | None = None

    @model_validator(mode="after")
    def _force_mcq_only(self) -> "QuizGenerationRequest":
        self.question_types = mcq_only_question_types()
        return self


class StructuredQuizGenerationRequestBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = "demo-user"
    question_count: int = Field(default=3, ge=1, le=10)
    question_types: list[QuestionType] = Field(
        default_factory=mcq_only_question_types,
        min_length=1,
    )
    question_styles: list[QuestionStyle] = Field(
        default_factory=lambda: [QuestionStyle.EXAM_STYLE_MIXED],
        min_length=1,
    )
    query: str | None = None
    client_request_id: str | None = None

    @model_validator(mode="after")
    def _force_mcq_only(self) -> "StructuredQuizGenerationRequestBase":
        self.question_types = mcq_only_question_types()
        return self


class QuizFromCourseRequest(StructuredQuizGenerationRequestBase):
    course_id: str
    module_ids: list[str] = Field(default_factory=list)


class QuizFromModuleRequest(StructuredQuizGenerationRequestBase):
    course_id: str
    module_id: str


class QuizFromMaterialRequest(StructuredQuizGenerationRequestBase):
    material_id: str
    course_id: str | None = None


class QuizFromSectionRequest(StructuredQuizGenerationRequestBase):
    section_id: str
    course_id: str | None = None


class QuizFromConceptRequest(StructuredQuizGenerationRequestBase):
    concept_id: str


class QuizFromWeakAreaRequest(StructuredQuizGenerationRequestBase):
    course_id: str
    module_id: str | None = None
    weak_area_id: str
    prefer_question_type: QuestionType | None = None

    @model_validator(mode="after")
    def _force_preferred_mcq(self) -> "QuizFromWeakAreaRequest":
        self.question_types = mcq_only_question_types()
        self.prefer_question_type = QuestionType.MCQ
        return self


class QuizFromMissedQuestionsRequest(StructuredQuizGenerationRequestBase):
    course_id: str
    module_id: str | None = None
    quiz_id: str | None = None
    question_ids: list[str] = Field(default_factory=list)


class QuizGenerationAcceptedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    status: QuizGenerationJobStatus
    created_at: str
    dedupe_key: str


class QuizGenerationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quiz: QuizBundle


class QuizGenerationJobProgress(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_questions: int
    completed_questions: int
    fallback_questions: int
    current_question_index: int = 0


class QuizGenerationResultItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    question_id: str
    ordinal: int
    source_id: str
    section_title: str
    generation_mode: QuestionGenerationMode
    question: QuizQuestion
    answer_key: "StoredQuestionKey"
    created_at: str


class QuestionGenerationAttempt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    question_id: str
    attempt_number: int
    provider: str
    model: str
    latency_ms: float | None = None
    response_phase: str | None = None
    timeout_hit: bool = False
    error_type: str | None = None
    request_id: str | None = None
    created_at: str


class QuizGenerationJobResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    dedupe_key: str
    status: QuizGenerationJobStatus
    provider: str
    model: str
    request_payload: QuizGenerationRequest
    progress: QuizGenerationJobProgress
    quiz: QuizBundle | None = None
    partial_results: list[QuizGenerationResultItem] = Field(default_factory=list)
    error_summary: str | None = None
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    last_heartbeat_at: str | None = None


class QuizGenerationCancelResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    status: QuizGenerationJobStatus


class QuizSubmissionAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str
    selected_option_id: str | None = None
    answer_text: str | None = None


class QuizGradeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = "demo-user"
    quiz_id: str
    answers: list[QuizSubmissionAnswer] = Field(default_factory=list)


class QuestionGradeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str
    question_type: QuestionType
    concept: str
    is_correct: bool
    grading_label: str
    score: float
    submitted_option_id: str | None = None
    submitted_answer: str
    correct_option_id: str | None = None
    correct_answer: str
    explanation: str
    citations: list[SourceChunk] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def populate_canonical_fields(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data

        normalized = dict(data)
        if "grading_label" not in normalized and "is_correct" in normalized:
            normalized["grading_label"] = "correct" if normalized["is_correct"] else "incorrect"
        normalized.setdefault("submitted_option_id", None)
        normalized.setdefault("correct_option_id", None)
        return normalized


class QuizGradeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quiz_id: str
    course_id: str
    module_id: str | None = None
    overall_score: float
    mastery_by_concept: dict[str, float] = Field(default_factory=dict)
    wrong_concepts: list[str] = Field(default_factory=list)
    results: list[QuestionGradeResult] = Field(default_factory=list)


class QuizAttemptSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quiz_id: str
    created_at: str | None = None
    question_count: int
    overall_score: float | None = None
    wrong_question_count: int = 0
    module_id: str | None = None


class QuizReviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quiz: QuizBundle
    results: list[QuestionGradeResult] = Field(default_factory=list)


class RemediationConceptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    concept: str
    question_count: int = Field(default=3, ge=1, le=5)


class RemediationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    course_id: str
    module_id: str | None = None
    concepts: list[RemediationConceptRequest] = Field(default_factory=list)
    default_question_count: int = Field(default=3, ge=1, le=5)
    retrieval_top_k: int = Field(default=8, ge=1, le=20)


class RemediationConceptBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    concept: str
    questions: list[QuizQuestion] = Field(default_factory=list)


class RemediationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    remediation_id: str
    course_id: str
    module_id: str | None = None
    mastery_by_concept: dict[str, float] = Field(default_factory=dict)
    wrong_concepts: list[str] = Field(default_factory=list)
    concept_bundles: list[RemediationConceptBundle] = Field(default_factory=list)


class RetryHistoryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    remediation_id: str
    course_id: str
    module_id: str | None = None
    concept: str
    generated_question_ids: list[str] = Field(default_factory=list)
    prompt_signatures: list[str] = Field(default_factory=list)
    original_question_ids: list[str] = Field(default_factory=list)


class StoredQuestionKey(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str
    question_type: QuestionType
    concept: str
    course_id: str | None = None
    module_id: str | None = None
    material_id: str | None = None
    section_id: str | None = None
    concept_id: str | None = None
    source_page: int | None = None
    source_evidence: str | None = None
    correct_answer: str
    correct_option_id: str | None = None
    expected_keywords: list[str] = Field(default_factory=list)
    difficulty: float = 0.5
    citations: list[SourceChunk] = Field(default_factory=list)


class StoredQuizSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quiz: QuizBundle
    answer_keys: list[StoredQuestionKey] = Field(default_factory=list)


QuizGenerationResultItem.model_rebuild()
