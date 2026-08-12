import json
from pathlib import Path

from exam_prep.analytics.models import MasterySnapshot
from exam_prep.repositories.quiz_store import QuizStore
from exam_prep.schemas.quiz import QuestionGradeResult, RetryHistoryEntry, StoredQuizSession


class LocalQuizStore(QuizStore):
    def __init__(self, base_path: Path) -> None:
        self.base_path = base_path / "_quiz"
        self.quiz_path = self.base_path / "sessions"
        self.progress_path = self.base_path / "progress"
        self.results_path = self.base_path / "results"
        self.retry_path = self.base_path / "retry"
        self.quiz_path.mkdir(parents=True, exist_ok=True)
        self.progress_path.mkdir(parents=True, exist_ok=True)
        self.results_path.mkdir(parents=True, exist_ok=True)
        self.retry_path.mkdir(parents=True, exist_ok=True)

    def save_quiz_session(self, session: StoredQuizSession) -> None:
        session_path = self.quiz_path / f"{session.quiz.quiz_id}.json"
        session_path.write_text(session.model_dump_json(indent=2), encoding="utf-8")

    def get_quiz_session(self, quiz_id: str) -> StoredQuizSession | None:
        session_path = self.quiz_path / f"{quiz_id}.json"
        if not session_path.exists():
            return None
        return StoredQuizSession.model_validate_json(session_path.read_text(encoding="utf-8"))

    def delete_quiz_session(self, quiz_id: str) -> bool:
        session_path = self.quiz_path / f"{quiz_id}.json"
        if not session_path.exists():
            return False
        session_path.unlink()
        return True

    def list_quiz_sessions_by_course(
        self,
        course_id: str,
        module_id: str | None = None,
    ) -> list[StoredQuizSession]:
        sessions: list[StoredQuizSession] = []
        for session_path in self.quiz_path.glob("*.json"):
            session = StoredQuizSession.model_validate_json(session_path.read_text(encoding="utf-8"))
            if session.quiz.course_id == course_id and (
                module_id is None or session.quiz.module_id == module_id
            ):
                sessions.append(session)
        return sorted(sessions, key=lambda session: session.quiz.quiz_id)

    def get_mastery_snapshot(
        self,
        course_id: str,
        module_id: str | None = None,
    ) -> MasterySnapshot:
        progress_path = self.progress_path / f"{self._context_key(course_id, module_id)}.json"
        if not progress_path.exists():
            return MasterySnapshot(course_id=course_id, module_id=module_id, percent_mastery=0.0)
        return MasterySnapshot.model_validate_json(progress_path.read_text(encoding="utf-8"))

    def save_mastery_snapshot(self, snapshot: MasterySnapshot) -> None:
        progress_path = self.progress_path / f"{self._context_key(snapshot.course_id, snapshot.module_id)}.json"
        progress_path.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")

    def save_grade_results(self, quiz_id: str, results: list[QuestionGradeResult]) -> None:
        results_path = self.results_path / f"{quiz_id}.json"
        payload = [result.model_dump(mode="json") for result in results]
        results_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def get_grade_results(self, quiz_id: str) -> list[QuestionGradeResult]:
        results_path = self.results_path / f"{quiz_id}.json"
        if not results_path.exists():
            return []
        raw_results = json.loads(results_path.read_text(encoding="utf-8"))
        return [QuestionGradeResult.model_validate(raw_result) for raw_result in raw_results]

    def delete_grade_results(self, quiz_id: str) -> bool:
        results_path = self.results_path / f"{quiz_id}.json"
        if not results_path.exists():
            return False
        results_path.unlink()
        return True

    def save_retry_history(self, entry: RetryHistoryEntry) -> None:
        history = self.list_retry_history(entry.course_id, entry.module_id)
        history.append(entry)
        retry_path = self.retry_path / f"{self._context_key(entry.course_id, entry.module_id)}.json"
        payload = [item.model_dump(mode="json") for item in history]
        retry_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def list_retry_history(
        self,
        course_id: str,
        module_id: str | None = None,
    ) -> list[RetryHistoryEntry]:
        retry_path = self.retry_path / f"{self._context_key(course_id, module_id)}.json"
        if not retry_path.exists():
            return []
        raw_history = json.loads(retry_path.read_text(encoding="utf-8"))
        return [RetryHistoryEntry.model_validate(item) for item in raw_history]

    def _context_key(self, course_id: str, module_id: str | None) -> str:
        return f"{course_id}__{module_id}" if module_id else course_id
