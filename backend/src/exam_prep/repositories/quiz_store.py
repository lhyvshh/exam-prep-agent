from typing import Protocol

from exam_prep.analytics.models import MasterySnapshot
from exam_prep.schemas.quiz import QuestionGradeResult, RetryHistoryEntry, StoredQuizSession


class QuizStore(Protocol):
    def save_quiz_session(self, session: StoredQuizSession) -> None:
        ...

    def get_quiz_session(self, quiz_id: str) -> StoredQuizSession | None:
        ...

    def list_quiz_sessions_by_course(
        self,
        course_id: str,
        module_id: str | None = None,
    ) -> list[StoredQuizSession]:
        ...

    def delete_quiz_session(self, quiz_id: str) -> bool:
        ...

    def get_mastery_snapshot(
        self,
        course_id: str,
        module_id: str | None = None,
    ) -> MasterySnapshot:
        ...

    def save_mastery_snapshot(self, snapshot: MasterySnapshot) -> None:
        ...

    def save_grade_results(self, quiz_id: str, results: list[QuestionGradeResult]) -> None:
        ...

    def get_grade_results(self, quiz_id: str) -> list[QuestionGradeResult]:
        ...

    def delete_grade_results(self, quiz_id: str) -> bool:
        ...

    def save_retry_history(self, entry: RetryHistoryEntry) -> None:
        ...

    def list_retry_history(
        self,
        course_id: str,
        module_id: str | None = None,
    ) -> list[RetryHistoryEntry]:
        ...
