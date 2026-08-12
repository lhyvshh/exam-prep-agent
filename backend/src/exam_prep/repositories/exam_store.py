from typing import Protocol

from exam_prep.schemas.exam import MockExamSourceBank, MockExamSourceExam, StoredMockExamSession


class ExamStore(Protocol):
    def save_exam_session(self, session: StoredMockExamSession) -> None:
        ...

    def get_exam_session(self, exam_id: str) -> StoredMockExamSession | None:
        ...

    def list_exam_sessions_by_course(
        self,
        course_id: str,
        module_id: str | None = None,
    ) -> list[StoredMockExamSession]:
        ...

    def save_source_bank(self, bank: MockExamSourceBank) -> None:
        ...

    def get_source_bank(self, bank_id: str) -> MockExamSourceBank | None:
        ...

    def get_source_exam(self, source_exam_id: str) -> MockExamSourceExam | None:
        ...

    def list_source_banks_by_course(self, course_id: str) -> list[MockExamSourceBank]:
        ...

    def list_generated_question_signatures(self, course_id: str) -> set[str]:
        ...
