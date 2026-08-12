import re
from datetime import datetime, timezone
from pathlib import Path

from exam_prep.repositories.exam_store import ExamStore
from exam_prep.schemas.exam import MockExamSourceBank, MockExamSourceExam, StoredMockExamSession


class LocalExamStore(ExamStore):
    def __init__(self, base_path: Path) -> None:
        self.base_path = base_path / "_exam"
        self.session_path = self.base_path / "sessions"
        self.source_bank_path = self.base_path / "source_banks"
        self.session_path.mkdir(parents=True, exist_ok=True)
        self.source_bank_path.mkdir(parents=True, exist_ok=True)

    def save_exam_session(self, session: StoredMockExamSession) -> None:
        session_file = self.session_path / f"{session.exam.exam_id}.json"
        session_file.write_text(session.model_dump_json(indent=2), encoding="utf-8")

    def get_exam_session(self, exam_id: str) -> StoredMockExamSession | None:
        session_file = self.session_path / f"{exam_id}.json"
        if not session_file.exists():
            return None
        return self._load_session(session_file)

    def list_exam_sessions_by_course(
        self,
        course_id: str,
        module_id: str | None = None,
    ) -> list[StoredMockExamSession]:
        sessions: list[StoredMockExamSession] = []
        for session_file in self.session_path.glob("*.json"):
            session = self._load_session(session_file)
            exam_module_ids = session.exam.module_ids or (
                [session.exam.module_id] if session.exam.module_id else []
            )
            if session.exam.course_id == course_id and (
                module_id is None or module_id in exam_module_ids
            ):
                sessions.append(session)
        return sorted(
            sessions,
            key=lambda session: (
                session.grade_result.completed_at
                if session.grade_result and session.grade_result.completed_at
                else session.exam.created_at or session.exam.exam_id
            ),
            reverse=True,
        )

    def save_source_bank(self, bank: MockExamSourceBank) -> None:
        bank_file = self.source_bank_path / f"{bank.bank_id}.json"
        bank_file.write_text(bank.model_dump_json(indent=2), encoding="utf-8")

    def get_source_bank(self, bank_id: str) -> MockExamSourceBank | None:
        bank_file = self.source_bank_path / f"{bank_id}.json"
        if not bank_file.exists():
            return None
        return MockExamSourceBank.model_validate_json(bank_file.read_text(encoding="utf-8"))

    def get_source_exam(self, source_exam_id: str) -> MockExamSourceExam | None:
        for bank_file in self.source_bank_path.glob("*.json"):
            bank = MockExamSourceBank.model_validate_json(bank_file.read_text(encoding="utf-8"))
            for exam in bank.exams:
                if exam.source_exam_id == source_exam_id:
                    return exam
        return None

    def list_source_banks_by_course(self, course_id: str) -> list[MockExamSourceBank]:
        banks: list[MockExamSourceBank] = []
        for bank_file in self.source_bank_path.glob("*.json"):
            bank = MockExamSourceBank.model_validate_json(bank_file.read_text(encoding="utf-8"))
            if bank.course_id == course_id:
                banks.append(bank)
        return sorted(banks, key=lambda bank: bank.uploaded_at, reverse=True)

    def list_generated_question_signatures(self, course_id: str) -> set[str]:
        signatures: set[str] = set()
        for session in self.list_exam_sessions_by_course(course_id):
            for question in session.exam.questions:
                signatures.add(_question_signature(question.question_id, question.prompt))
        return signatures

    def _load_session(self, session_file: Path) -> StoredMockExamSession:
        session = StoredMockExamSession.model_validate_json(session_file.read_text(encoding="utf-8"))
        if session.exam.created_at:
            return session
        created_at = datetime.fromtimestamp(session_file.stat().st_mtime, timezone.utc).isoformat()
        return session.model_copy(
            update={"exam": session.exam.model_copy(update={"created_at": created_at})}
        )


def _question_signature(question_id: str, prompt: str) -> str:
    question_number = _question_number(question_id)
    prompt_signature = _prompt_signature(prompt)
    if question_number is None:
        return prompt_signature
    return f"source-q{question_number}:{prompt_signature}"


def _question_number(question_id: str) -> int | None:
    match = re.search(r"-q(?P<number>\d+)$", question_id)
    if match is None:
        return None
    return int(match.group("number"))


def _prompt_signature(prompt: str) -> str:
    normalized = prompt.casefold()
    normalized = re.sub(r"\bcase\s+\d+(?:\.\d+)*\b", " ", normalized)
    normalized = re.sub(
        r"\bsource\s+question\s+\d+(?:'s)?\b",
        "source question",
        normalized,
    )
    normalized = re.sub(r"\d+(?:\.\d+)?", " number ", normalized)
    return " ".join(re.sub(r"[^a-z0-9\s]", " ", normalized).split())
