import json

import pytest

from exam_prep.packages.completed_exam import (
    CompletedExamFormatError,
    canonical_exam_fingerprint,
    parse_completed_exam_html,
)
from exam_prep.packages.models import OfflineExamQuestion, OfflineMockExam
from exam_prep.packages.rendering import MockExamFileInput


def _document() -> MockExamFileInput:
    return MockExamFileInput(
        package_id="package-1",
        file_id="mock-exam-1",
        version=1,
        exam=OfflineMockExam(
            exam_id="exam-1",
            title="FRM Part I Mock Exam 1",
            questions=(
                OfflineExamQuestion(
                    question_id="question-1",
                    question_number=1,
                    domain="Quantitative Analysis",
                    subtopic="Regression",
                    learning_objective="Interpret regression output",
                    question_type="Model interpretation and limitations",
                    difficulty="Standard exam-level",
                    prompt="Which conclusion is most appropriate?",
                    choices=("A", "B", "C", "D"),
                    correct_choice_index=2,
                    explanation="Choice C is supported by the source.",
                    source_reference="FRM Book 1, page 120",
                    quality_score=0.92,
                    quality_confidence=0.88,
                    quality_label="high_quality",
                    quality_accepted=True,
                    quality_model_version="torch-1",
                    quality_model_source="pytorch",
                ),
            ),
        ),
    )


def _completed_html(document: MockExamFileInput) -> str:
    attempt = {
        "schema_version": "1",
        "attempt_id": "attempt-1",
        "package_id": document.package_id,
        "package_version": document.version,
        "file_id": document.file_id,
        "exam_id": document.exam.exam_id,
        "content_sha256": document.content_sha256,
        "started_at": "2026-08-06T12:00:00Z",
        "completed_at": "2026-08-06T13:00:00Z",
        "remaining_seconds": 10800,
        "answers": {"question-1": 2},
        "flags": {"question-1": False},
    }
    return (
        "<!doctype html><html><body>"
        f'<script type="application/json" id="study-data">{document.model_dump_json()}</script>'
        f'<script type="application/json" id="attempt-data">{json.dumps(attempt)}</script>'
        '<script>throw new Error("must never execute")</script>'
        "</body></html>"
    )


def test_completed_exam_parser_extracts_only_inert_json_blocks() -> None:
    document = _document()

    parsed = parse_completed_exam_html(_completed_html(document).encode())

    assert parsed.document == document
    assert parsed.attempt.attempt_id == "attempt-1"
    assert parsed.attempt.answers == {"question-1": 2}
    assert document.content_sha256 == canonical_exam_fingerprint(document.exam)


def test_completed_exam_parser_rejects_a_tampered_fingerprint() -> None:
    document = _document()
    html = _completed_html(document).replace(document.content_sha256, "0" * 64, 1)

    with pytest.raises(CompletedExamFormatError, match="fingerprint"):
        parse_completed_exam_html(html.encode())


@pytest.mark.parametrize(
    "html",
    [
        b"<html></html>",
        b'<script type="application/json" id="study-data">{}</script>',
    ],
)
def test_completed_exam_parser_requires_both_payloads(html: bytes) -> None:
    with pytest.raises(CompletedExamFormatError, match="completed exam"):
        parse_completed_exam_html(html)
