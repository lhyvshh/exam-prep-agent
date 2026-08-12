import hashlib
import json
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Literal

from pydantic import Field, ValidationError, model_validator

from exam_prep.schemas.exam import MockExamGradeResponse

from .models import OfflineMockExam, PackageModel

class CompletedExamFormatError(ValueError):
    pass


class CompletedExamAttempt(PackageModel):
    schema_version: Literal["1"] = "1"
    attempt_id: str = Field(min_length=1, max_length=128)
    package_id: str = Field(min_length=1)
    package_version: int = Field(ge=1)
    file_id: str = Field(min_length=1)
    exam_id: str = Field(min_length=1)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    started_at: str = Field(min_length=1)
    completed_at: str = Field(min_length=1)
    remaining_seconds: int = Field(ge=0)
    answers: dict[str, int] = Field(default_factory=dict)
    flags: dict[str, bool] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_choice_indexes(self) -> "CompletedExamAttempt":
        if any(index < 0 or index > 3 for index in self.answers.values()):
            raise ValueError("Completed exam answers must use choice indexes from 0 to 3.")
        return self


class ImportedExamAttemptRecord(PackageModel):
    attempt: CompletedExamAttempt
    imported_at: str = Field(min_length=1)
    grade: MockExamGradeResponse


class CompletedExamImportResponse(PackageModel):
    record: ImportedExamAttemptRecord
    duplicate: bool = False


class ImportedExamAttemptListResponse(PackageModel):
    attempts: tuple[ImportedExamAttemptRecord, ...] = ()


class _CompletedExamHTMLParser(HTMLParser):
    target_ids = {"study-data", "attempt-data"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: dict[str, str] = {}
        self._current_id: str | None = None
        self._current_parts: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag.casefold() != "script":
            return
        attributes = {name.casefold(): value for name, value in attrs}
        script_id = attributes.get("id")
        script_type = attributes.get("type")
        if script_id in self.target_ids and script_type == "application/json":
            if script_id in self.blocks or self._current_id is not None:
                raise CompletedExamFormatError("Completed exam contains duplicate data blocks.")
            self._current_id = script_id
            self._current_parts = []

    def handle_data(self, data: str) -> None:
        if self._current_id is not None:
            self._current_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "script" and self._current_id is not None:
            self.blocks[self._current_id] = "".join(self._current_parts)
            self._current_id = None
            self._current_parts = []


def canonical_exam_fingerprint(exam: OfflineMockExam) -> str:
    canonical = json.dumps(
        exam.model_dump(mode="json"),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


class MockExamFileInput(PackageModel):
    package_id: str = Field(min_length=1)
    file_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    exam: OfflineMockExam
    content_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _populate_content_fingerprint(self) -> "MockExamFileInput":
        if self.content_sha256 is None:
            object.__setattr__(self, "content_sha256", canonical_exam_fingerprint(self.exam))
        return self


@dataclass(frozen=True)
class ParsedCompletedExam:
    document: MockExamFileInput
    attempt: CompletedExamAttempt


def _extract_json_blocks(content: bytes) -> dict[str, str]:
    try:
        source = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CompletedExamFormatError("Completed exam must be UTF-8 HTML.") from exc

    parser = _CompletedExamHTMLParser()
    try:
        parser.feed(source)
    except (CompletedExamFormatError, RecursionError) as exc:
        raise CompletedExamFormatError(str(exc)) from exc

    return parser.blocks


def parse_exam_document_html(content: bytes) -> MockExamFileInput:
    study_json = _extract_json_blocks(content).get("study-data")
    if not study_json:
        raise CompletedExamFormatError("Exam HTML is missing its study data.")
    try:
        document = MockExamFileInput.model_validate_json(study_json)
    except ValidationError as exc:
        raise CompletedExamFormatError("Exam study data is invalid.") from exc
    if document.content_sha256 != canonical_exam_fingerprint(document.exam):
        raise CompletedExamFormatError("Exam content fingerprint is invalid.")
    return document


def parse_completed_exam_html(content: bytes) -> ParsedCompletedExam:
    blocks = _extract_json_blocks(content)
    study_json = blocks.get("study-data")
    attempt_json = blocks.get("attempt-data")
    if not study_json or not attempt_json:
        raise CompletedExamFormatError(
            "Upload a completed exam HTML file saved after submitting the exam."
        )

    try:
        document = MockExamFileInput.model_validate_json(study_json)
        attempt = CompletedExamAttempt.model_validate_json(attempt_json)
    except ValidationError as exc:
        raise CompletedExamFormatError("Completed exam data is invalid.") from exc

    actual_fingerprint = canonical_exam_fingerprint(document.exam)
    if document.content_sha256 != actual_fingerprint:
        raise CompletedExamFormatError("Completed exam content fingerprint is invalid.")
    if attempt.content_sha256 != actual_fingerprint:
        raise CompletedExamFormatError("Completed exam attempt fingerprint is invalid.")
    if (
        attempt.package_id != document.package_id
        or attempt.package_version != document.version
        or attempt.file_id != document.file_id
        or attempt.exam_id != document.exam.exam_id
    ):
        raise CompletedExamFormatError("Completed exam metadata does not match its study data.")

    question_ids = {question.question_id for question in document.exam.questions}
    if not set(attempt.answers).issubset(question_ids) or not set(attempt.flags).issubset(
        question_ids
    ):
        raise CompletedExamFormatError("Completed exam contains unknown question IDs.")
    return ParsedCompletedExam(document=document, attempt=attempt)
