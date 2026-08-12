from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ActivityEventType(StrEnum):
    MATERIAL_OPENED = "material_opened"
    MATERIAL_SECTION_VIEWED = "material_section_viewed"
    PDF_SOURCE_CLICKED = "pdf_source_clicked"
    QUIZ_GENERATED = "quiz_generated"
    QUIZ_STARTED = "quiz_started"
    QUESTION_ANSWERED = "question_answered"
    QUESTION_SUBMITTED = "question_submitted"
    ANSWER_EXPLANATION_VIEWED = "answer_explanation_viewed"
    MISSED_QUESTION_SAVED = "missed_question_saved"
    PRACTICE_CONCEPT_CLICKED = "practice_concept_clicked"
    REVIEW_MATERIAL_CLICKED = "review_material_clicked"
    QUIZ_COMPLETED = "quiz_completed"
    RECOMMENDATION_CLICKED = "recommendation_clicked"
    STUDY_SESSION_STARTED = "study_session_started"
    STUDY_SESSION_ENDED = "study_session_ended"


class ActivityContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = "demo-user"
    course_id: str | None = None
    module_id: str | None = None
    material_id: str | None = None
    section_id: str | None = None
    concept_id: str | None = None
    quiz_id: str | None = None
    question_id: str | None = None
    question_type: str | None = None
    difficulty: float | None = None


class ActivityEventCreate(ActivityContext):
    event_type: ActivityEventType
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ActivityEventRecord(ActivityEventCreate):
    id: str
    timestamp: str


class ActivityEventsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events: list[ActivityEventRecord] = Field(default_factory=list)


class StudySessionStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = "demo-user"
    course_id: str
    module_id: str | None = None
    material_id: str | None = None
    section_id: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class StudySessionEndRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata_json: dict[str, Any] = Field(default_factory=dict)


class StudySessionRecord(StudySessionStartRequest):
    id: str
    started_at: str
    ended_at: str | None = None
    duration_seconds: int | None = None


class StudySessionsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    study_sessions: list[StudySessionRecord] = Field(default_factory=list)


class QuestionAttemptCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = "demo-user"
    quiz_id: str
    question_id: str
    course_id: str
    module_id: str | None = None
    material_id: str | None = None
    section_id: str | None = None
    concept_id: str | None = None
    selected_answer: str
    correct_answer: str
    is_correct: bool
    time_spent_seconds: int | None = None
    question_type: str | None = None
    difficulty: float | None = None


class QuestionAttemptRecord(QuestionAttemptCreate):
    id: str
    attempt_number: int
    created_at: str


class QuestionAttemptsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_attempts: list[QuestionAttemptRecord] = Field(default_factory=list)


class FlashcardReviewRating(StrEnum):
    FORGOT = "forgot"
    HARD = "hard"
    GOOD = "good"
    EASY = "easy"


class FlashcardReviewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = "demo-user"
    course_id: str
    module_id: str | None = None
    material_id: str | None = None
    section_id: str | None = None
    concept_id: str | None = None
    flashcard_id: str
    rating: FlashcardReviewRating
    previous_interval_days: int
    new_interval_days: int
    previous_confidence_group: str
    new_confidence_group: str
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class FlashcardReviewRecord(FlashcardReviewCreate):
    id: str
    reviewed_at: str


class FlashcardReviewsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    flashcard_reviews: list[FlashcardReviewRecord] = Field(default_factory=list)


class GeneratedContentQualityFlagType(StrEnum):
    GENERIC_QUESTION = "generic_question"
    MISSING_SOURCE_PAGE = "missing_source_page"
    DUPLICATE_CARD = "duplicate_card"
    FORMULA_WITHOUT_FORMULA = "formula_without_formula"
    MISSING_CONCEPT_LINK = "missing_concept_link"
    LOW_PARSE_CONFIDENCE = "low_parse_confidence"


class GeneratedContentQualityFlagCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    course_id: str | None = None
    material_id: str | None = None
    section_id: str | None = None
    concept_id: str | None = None
    content_id: str
    content_type: str
    flag_type: GeneratedContentQualityFlagType
    reason: str


class GeneratedContentQualityFlagRecord(GeneratedContentQualityFlagCreate):
    id: str
    created_at: str


class GeneratedContentQualityFlagsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quality_flags: list[GeneratedContentQualityFlagRecord] = Field(default_factory=list)
