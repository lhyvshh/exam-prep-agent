from typing import Protocol

from exam_prep.schemas.quiz import (
    QuestionGenerationAttempt,
    QuizGenerationAcceptedResponse,
    QuizGenerationJobResponse,
    QuizGenerationJobStatus,
    QuizGenerationRequest,
    QuizGenerationResultItem,
)


class QuizJobStore(Protocol):
    def create_job(
        self,
        *,
        job_id: str,
        dedupe_key: str,
        request: QuizGenerationRequest,
        provider: str,
        model: str,
    ) -> QuizGenerationAcceptedResponse:
        ...

    def find_active_job_by_dedupe_key(self, dedupe_key: str) -> QuizGenerationAcceptedResponse | None:
        ...

    def get_job(self, job_id: str) -> QuizGenerationJobResponse | None:
        ...

    def mark_running(self, job_id: str) -> None:
        ...

    def update_progress(
        self,
        job_id: str,
        *,
        completed_questions: int,
        fallback_questions: int,
        current_question_index: int,
    ) -> None:
        ...

    def append_result(self, result: QuizGenerationResultItem) -> None:
        ...

    def append_attempt(self, attempt: QuestionGenerationAttempt) -> None:
        ...

    def mark_completed(
        self,
        job_id: str,
        *,
        status: QuizGenerationJobStatus,
        failure_reason: str | None = None,
    ) -> None:
        ...

    def increment_error_count(self, job_id: str, *, failure_reason: str | None = None) -> None:
        ...

    def request_cancel(self, job_id: str) -> QuizGenerationJobStatus | None:
        ...

    def is_cancel_requested(self, job_id: str) -> bool:
        ...

    def list_incomplete_jobs(self) -> list[str]:
        ...
