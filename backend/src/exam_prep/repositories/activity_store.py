from typing import Protocol

from exam_prep.schemas.activity import (
    ActivityEventCreate,
    ActivityEventRecord,
    ActivityEventType,
    FlashcardReviewCreate,
    FlashcardReviewRecord,
    GeneratedContentQualityFlagCreate,
    GeneratedContentQualityFlagRecord,
    GeneratedContentQualityFlagType,
    QuestionAttemptCreate,
    QuestionAttemptRecord,
    StudySessionEndRequest,
    StudySessionRecord,
    StudySessionStartRequest,
)


class ActivityStore(Protocol):
    def record_event(self, event: ActivityEventCreate) -> ActivityEventRecord:
        ...

    def list_events(
        self,
        *,
        user_id: str | None = None,
        course_id: str | None = None,
        quiz_id: str | None = None,
        event_type: ActivityEventType | None = None,
    ) -> list[ActivityEventRecord]:
        ...

    def start_study_session(self, request: StudySessionStartRequest) -> StudySessionRecord:
        ...

    def end_study_session(
        self,
        session_id: str,
        request: StudySessionEndRequest,
    ) -> StudySessionRecord | None:
        ...

    def list_study_sessions(
        self,
        *,
        user_id: str | None = None,
        course_id: str | None = None,
    ) -> list[StudySessionRecord]:
        ...

    def record_question_attempt(self, attempt: QuestionAttemptCreate) -> QuestionAttemptRecord:
        ...

    def list_question_attempts(
        self,
        *,
        user_id: str | None = None,
        course_id: str | None = None,
        quiz_id: str | None = None,
    ) -> list[QuestionAttemptRecord]:
        ...

    def record_flashcard_review(self, review: FlashcardReviewCreate) -> FlashcardReviewRecord:
        ...

    def list_flashcard_reviews(
        self,
        *,
        user_id: str | None = None,
        course_id: str | None = None,
        material_id: str | None = None,
        concept_id: str | None = None,
        flashcard_id: str | None = None,
    ) -> list[FlashcardReviewRecord]:
        ...

    def record_generated_content_quality_flag(
        self,
        flag: GeneratedContentQualityFlagCreate,
    ) -> GeneratedContentQualityFlagRecord:
        ...

    def list_generated_content_quality_flags(
        self,
        *,
        course_id: str | None = None,
        material_id: str | None = None,
        section_id: str | None = None,
        concept_id: str | None = None,
        content_id: str | None = None,
        flag_type: GeneratedContentQualityFlagType | None = None,
    ) -> list[GeneratedContentQualityFlagRecord]:
        ...
