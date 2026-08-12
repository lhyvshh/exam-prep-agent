from datetime import UTC, datetime

from exam_prep.repositories.exam_store import ExamStore
from exam_prep.repositories.package_store import PackageStore
from exam_prep.schemas.exam import MockExamGradeRequest
from exam_prep.schemas.quiz import QuizSubmissionAnswer
from exam_prep.services.exam_service import ExamService

from .completed_exam import (
    CompletedExamFormatError,
    CompletedExamImportResponse,
    ImportedExamAttemptRecord,
    parse_completed_exam_html,
    parse_exam_document_html,
)
from .models import PackageFileKind
from .service import PackageBuildError, PackageNotFoundError, PackageService

MAX_COMPLETED_EXAM_BYTES = 12 * 1024 * 1024


class CompletedExamImportError(ValueError):
    pass


class CompletedExamImportService:
    def __init__(
        self,
        *,
        package_service: PackageService,
        package_store: PackageStore,
        exam_store: ExamStore,
        exam_service: ExamService,
    ) -> None:
        self.package_service = package_service
        self.package_store = package_store
        self.exam_store = exam_store
        self.exam_service = exam_service

    def import_completed_exam(
        self,
        package_id: str,
        file_name: str,
        content: bytes,
    ) -> CompletedExamImportResponse:
        if not file_name.casefold().endswith(".html"):
            raise CompletedExamImportError("Upload the completed exam as an HTML file.")
        if not content or len(content) > MAX_COMPLETED_EXAM_BYTES:
            raise CompletedExamImportError("Completed exam HTML must be 12 MB or smaller.")

        try:
            parsed = parse_completed_exam_html(content)
        except CompletedExamFormatError as exc:
            raise CompletedExamImportError(str(exc)) from exc
        attempt = parsed.attempt
        if attempt.package_id != package_id:
            raise CompletedExamImportError("This completed exam belongs to another package.")

        existing = self.package_store.get_exam_attempt(attempt.attempt_id)
        if existing is not None:
            if existing.attempt.package_id != package_id:
                raise CompletedExamImportError("Attempt ID is already used by another package.")
            return CompletedExamImportResponse(record=existing, duplicate=True)

        try:
            package = self.package_service.get(package_id)
            self.package_service.get_version_number(package_id, attempt.package_version)
        except (PackageBuildError, PackageNotFoundError) as exc:
            raise CompletedExamImportError(str(exc)) from exc

        original = None
        for package_file in self.package_store.list_files(package_id, attempt.package_version):
            if package_file.kind != PackageFileKind.MOCK_EXAM:
                continue
            try:
                _, original_path = self.package_service.resolve_version_file(
                    package_id,
                    attempt.package_version,
                    package_file.file_id,
                )
                candidate = parse_exam_document_html(original_path.read_bytes())
            except (CompletedExamFormatError, OSError, PackageBuildError, PackageNotFoundError):
                continue
            if candidate.file_id == attempt.file_id:
                original = candidate
                break
        if original is None:
            raise CompletedExamImportError("The canonical package exam is unavailable.")
        if parsed.document != original:
            raise CompletedExamImportError("The completed exam was modified after download.")

        session = self.exam_store.get_exam_session(attempt.exam_id)
        if session is None or session.exam.course_id != package.course_id:
            raise CompletedExamImportError("The canonical exam session is unavailable.")
        canonical_questions = {question.question_id: question for question in session.exam.questions}
        if set(canonical_questions) != {
            question.question_id for question in original.exam.questions
        }:
            raise CompletedExamImportError("The completed exam does not match the canonical exam.")

        submissions: list[QuizSubmissionAnswer] = []
        for question_id, choice_index in attempt.answers.items():
            question = canonical_questions[question_id]
            options = question.options or question.answer_choices_json
            if choice_index >= len(options):
                raise CompletedExamImportError("A completed exam answer choice is invalid.")
            submissions.append(
                QuizSubmissionAnswer(
                    question_id=question_id,
                    selected_option_id=options[choice_index].option_id,
                )
            )

        grade = self.exam_service.grade_exam(
            MockExamGradeRequest(exam_id=attempt.exam_id, answers=submissions)
        )
        record = ImportedExamAttemptRecord(
            attempt=attempt,
            imported_at=datetime.now(UTC).isoformat(),
            grade=grade,
        )
        if self.package_store.save_exam_attempt(record):
            return CompletedExamImportResponse(record=record)
        concurrent = self.package_store.get_exam_attempt(attempt.attempt_id)
        if concurrent is None:
            raise CompletedExamImportError("Completed exam attempt could not be recorded.")
        return CompletedExamImportResponse(record=concurrent, duplicate=True)
