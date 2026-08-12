import json
import time
from typing import cast

from fastapi import FastAPI
from fastapi.testclient import TestClient

from exam_prep.packages.frm_policy import FRM_PART_I_POLICY
from exam_prep.packages.completed_exam import MockExamFileInput, parse_exam_document_html
from exam_prep.schemas.exam import (
    ExamBlueprint,
    MockExamBundle,
    MockExamSourceBank,
    MockExamSourceExam,
    StoredMockExamSession,
)
from exam_prep.schemas.materials import (
    MaterialRecord,
    MaterialStudyDocument,
    MaterialStudySection,
    StudyConceptCard,
    StudyFlashcard,
    StudyLearningOutcome,
)
from exam_prep.schemas.ml import QuestionQualityLabel, QuestionQualityValidation
from exam_prep.packages.models import (
    PackageValidationReport,
    ValidationFinding,
    ValidationSeverity,
)
from exam_prep.schemas.quiz import (
    ExamQuestionCategory,
    QuestionStyle,
    QuestionType,
    QuizQuestion,
    QuizQuestionOption,
    StoredQuestionKey,
)


def _seed_package_sources(client: TestClient) -> None:
    app = cast(FastAPI, client.app)
    material_store = app.state.material_store
    exam_store = app.state.exam_store
    for book_number in range(1, 5):
        record = MaterialRecord(
            material_id=f"material-{book_number}",
            course_id="course-1",
            file_name=f"Book-{book_number}.pdf",
            content_type="application/pdf",
            content_hash=f"book-hash-{book_number}",
        )
        material_store.save_record(record)
        concept = StudyConceptCard(
            concept_id=f"concept-{book_number}",
            material_id=record.material_id,
            title=f"Risk concept {book_number}",
            learning_outcome=f"Explain risk concept {book_number}",
            source_pages=[10],
        )
        cards = [
            StudyFlashcard(
                flashcard_id=f"card-{book_number}-{index}",
                material_id=record.material_id,
                concept_id=concept.concept_id,
                front=f"Grounded prompt {book_number}.{index}",
                back=f"Grounded answer {book_number}.{index}",
                card_type="short_answer_recall",
                source_page=10,
                source_excerpt="Risk governance aligns risk taking with approved appetite.",
            )
            for index in range(10)
        ]
        material_store.save_study_document(
            MaterialStudyDocument(
                material_id=record.material_id,
                sections=[
                    MaterialStudySection(
                        section_id=f"section-{book_number}",
                        material_id=record.material_id,
                        title=f"Risk Governance {book_number}",
                        normalized_title=f"risk governance {book_number}",
                        page_start=10,
                        page_end=11,
                        source_anchor=f"Book {book_number}, pages 10-11",
                        summary="Risk governance responsibilities.",
                        learning_outcomes=[
                            StudyLearningOutcome(
                                outcome_id=f"lo-{book_number}",
                                outcome_title=f"Explain risk concept {book_number}",
                                concepts=[concept],
                            )
                        ],
                        concepts=[concept],
                        flashcards=cards,
                        source_ids=[f"chunk-{book_number}"],
                    )
                ],
            )
        )
    for exam_number in range(1, 4):
        questions = _exam_questions(exam_number)
        exam_store.save_exam_session(
            StoredMockExamSession(
                exam=MockExamBundle(
                    exam_id=f"exam-{exam_number}",
                    course_id="course-1",
                    created_at="2026-07-13T12:00:00Z",
                    blueprint=ExamBlueprint(
                        title=f"Fixture exam {exam_number}",
                        instructions="Choose the best answer.",
                        style_example="Applied FRM question",
                    ),
                    questions=questions,
                ),
                answer_keys=[
                    StoredQuestionKey(
                        question_id=question.question_id,
                        question_type=QuestionType.MCQ,
                        concept=question.concept,
                        source_page=10,
                        source_evidence=question.source_evidence,
                        correct_answer=question.options[0].text,
                        correct_option_id="A",
                    )
                    for question in questions
                ],
            )
        )
    exam_store.save_source_bank(
        MockExamSourceBank(
            bank_id="source-bank-1",
            course_id="course-1",
            file_name="FRM-practice-exams.pdf",
            uploaded_at="2026-07-13T12:00:00Z",
            exams=[
                MockExamSourceExam(
                    source_exam_id="source-exam-1",
                    title="FRM Practice Exam 1",
                    question_count=100,
                    answer_count=100,
                )
            ],
        )
    )


def _exam_questions(exam_number: int) -> list[QuizQuestion]:
    domains = [
        domain
        for domain, count in FRM_PART_I_POLICY.exam_domain_counts[exam_number - 1].items()
        for _ in range(count)
    ]
    question_types = [
        question_type
        for question_type, count in FRM_PART_I_POLICY.question_type_counts.items()
        for _ in range(count)
    ]
    difficulties = [
        difficulty
        for difficulty, count in FRM_PART_I_POLICY.difficulty_counts[exam_number - 1].items()
        for _ in range(count)
    ]
    questions: list[QuizQuestion] = []
    for number, (domain, question_type, difficulty) in enumerate(
        zip(domains, question_types, difficulties, strict=True),
        start=1,
    ):
        options = [
            QuizQuestionOption(
                option_id="A",
                text=f"Supported conclusion {_alpha_code((exam_number - 1) * 400 + number)}",
            ),
            QuizQuestionOption(
                option_id="B",
                text=f"Alternative {_alpha_code((exam_number - 1) * 400 + 100 + number)}",
            ),
            QuizQuestionOption(
                option_id="C",
                text=f"Alternative {_alpha_code((exam_number - 1) * 400 + 200 + number)}",
            ),
            QuizQuestionOption(
                option_id="D",
                text=f"Alternative {_alpha_code((exam_number - 1) * 400 + 300 + number)}",
            ),
        ]
        questions.append(
            QuizQuestion(
                question_id=f"exam-{exam_number}-question-{number}",
                question_type=QuestionType.MCQ,
                question_style=QuestionStyle.APPLICATION,
                concept=f"Learning objective {number}",
                section_title=domain,
                difficulty=_difficulty_value(difficulty),
                frm_question_type=ExamQuestionCategory(question_type),
                prompt=(
                    "Which FRM interpretation best applies to principle "
                    f"{_alpha_code((exam_number - 1) * 100 + number)}?"
                ),
                options=options,
                correct_answer=options[0].text,
                explanation="Grounded explanation.",
                source_page=10,
                source_evidence="The board approves and oversees the firm's risk appetite.",
                quality_validation=QuestionQualityValidation(
                    score=0.92,
                    confidence=0.88,
                    label=QuestionQualityLabel.HIGH_QUALITY,
                    accepted_for_delivery=True,
                    model_version="torch-fixture-1",
                    model_source="pytorch_checkpoint",
                ),
            )
        )
    return questions


def _difficulty_value(difficulty: str) -> float:
    if difficulty == "Foundational":
        return 0.2
    if difficulty == "Difficult":
        return 0.8
    return 0.5


def _alpha_code(value: int) -> str:
    letters: list[str] = []
    while value:
        value, remainder = divmod(value - 1, 26)
        letters.append(chr(ord("a") + remainder))
    return "".join(reversed(letters)) or "a"


def test_package_create_build_list_and_download(client: TestClient) -> None:
    _seed_package_sources(client)
    create = client.post(
        "/api/v1/packages",
        json={
            "course_id": "course-1",
            "title": "FRM Part I 2026",
            "timer_minutes": 90,
            "include_formula_review": False,
        },
    )
    assert create.status_code == 201
    package_id = create.json()["package_id"]

    no_job = client.get(f"/api/v1/packages/{package_id}/jobs/latest")
    assert no_job.status_code == 200
    assert no_job.json() is None

    build = client.post(f"/api/v1/packages/{package_id}/build")
    assert build.status_code == 202
    job_id = build.json()["job_id"]
    job: dict[str, object] = {}
    for _ in range(50):
        response = client.get(f"/api/v1/packages/jobs/{job_id}")
        assert response.status_code == 200
        job = response.json()
        if job["status"] not in {"queued", "running"}:
            break
        time.sleep(0.02)
    assert job["status"] == "complete"

    latest_job = client.get(f"/api/v1/packages/{package_id}/jobs/latest")
    assert latest_job.status_code == 200
    assert latest_job.json()["job_id"] == job_id
    assert latest_job.json()["accepted_flashcards"] == 40
    assert latest_job.json()["accepted_questions"] == 300

    listed = client.get("/api/v1/packages", params={"course_id": "course-1"})
    assert listed.status_code == 200
    assert listed.json()["packages"][0]["package_id"] == package_id
    files = client.get(f"/api/v1/packages/{package_id}/files").json()["files"]
    assert files
    mock_exam_file = next(file for file in files if file["kind"] == "mock_exam")
    mock_exam_download = client.get(
        f"/api/v1/packages/{package_id}/files/{mock_exam_file['file_id']}"
    )
    assert mock_exam_download.status_code == 200
    assert '"timer_minutes":90' in mock_exam_download.text
    document = parse_exam_document_html(mock_exam_download.content)
    attempt = {
        "schema_version": "1",
        "attempt_id": "imported-attempt-1",
        "package_id": package_id,
        "package_version": 1,
        "file_id": document.file_id,
        "exam_id": document.exam.exam_id,
        "content_sha256": document.content_sha256,
        "started_at": "2026-08-06T12:00:00Z",
        "completed_at": "2026-08-06T13:00:00Z",
        "remaining_seconds": 1800,
        "answers": {
            question.question_id: question.correct_choice_index
            for question in document.exam.questions
        },
        "flags": {},
    }
    completed_html = mock_exam_download.text.replace(
        "</body>",
        (
            '<script type="application/json" id="attempt-data">'
            f"{json.dumps(attempt)}"
            "</script></body>"
        ),
    )
    imported = client.post(
        f"/api/v1/packages/{package_id}/attempts/import",
        files={"file": ("completed-exam.html", completed_html, "text/html")},
    )
    assert imported.status_code == 201, imported.text
    assert imported.json()["duplicate"] is False
    assert imported.json()["record"]["grade"]["overall_score"] == 100.0

    duplicate = client.post(
        f"/api/v1/packages/{package_id}/attempts/import",
        files={"file": ("completed-exam.html", completed_html, "text/html")},
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["duplicate"] is True

    first_question = document.exam.questions[0]
    tampered_document = MockExamFileInput(
        package_id=document.package_id,
        file_id=document.file_id,
        version=document.version,
        exam=document.exam.model_copy(
            update={
                "questions": (
                    first_question.model_copy(update={"prompt": "Tampered question"}),
                    *document.exam.questions[1:],
                )
            }
        ),
    )
    tampered_attempt = {
        **attempt,
        "attempt_id": "imported-attempt-2",
        "content_sha256": tampered_document.content_sha256,
    }
    tampered_html = (
        "<!doctype html><html><body>"
        '<script type="application/json" id="study-data">'
        f"{tampered_document.model_dump_json()}"
        "</script>"
        '<script type="application/json" id="attempt-data">'
        f"{json.dumps(tampered_attempt)}"
        "</script></body></html>"
    )
    tampered = client.post(
        f"/api/v1/packages/{package_id}/attempts/import",
        files={"file": ("tampered-completed-exam.html", tampered_html, "text/html")},
    )
    assert tampered.status_code == 400
    assert tampered.json()["detail"] == "The completed exam was modified after download."

    attempts = client.get(f"/api/v1/packages/{package_id}/attempts")
    assert attempts.status_code == 200
    assert [item["attempt"]["attempt_id"] for item in attempts.json()["attempts"]] == [
        "imported-attempt-1"
    ]
    download = client.get(f"/api/v1/packages/{package_id}/files/{files[0]['file_id']}")
    assert download.status_code == 200
    assert download.content

    versions = client.get(f"/api/v1/packages/{package_id}/versions")
    assert versions.status_code == 200
    assert [item["version"] for item in versions.json()["versions"]] == [1]
    version_detail = client.get(f"/api/v1/packages/{package_id}/versions/1")
    assert version_detail.status_code == 200
    assert version_detail.json()["validation"]["passed"] is True
    historical_download = client.get(
        f"/api/v1/packages/{package_id}/versions/1/files/{files[0]['file_id']}"
    )
    assert historical_download.status_code == 200
    assert historical_download.content == download.content

    app = cast(FastAPI, client.app)
    app.state.package_store.save_validation(
        PackageValidationReport(
            package_id=package_id,
            version=1,
            passed=False,
            created_at="2026-07-13T12:05:00Z",
            findings=(
                ValidationFinding(
                    code="qa.blocked",
                    severity=ValidationSeverity.ERROR,
                    message="Release validation failed.",
                ),
            ),
        )
    )
    blocked = client.get(f"/api/v1/packages/{package_id}/files/{files[0]['file_id']}")
    assert blocked.status_code == 409


def test_study_card_package_builds_only_the_selected_book(client: TestClient) -> None:
    _seed_package_sources(client)
    create = client.post(
        "/api/v1/packages",
        json={
            "course_id": "course-1",
            "title": "Book 2 study cards",
            "package_kind": "study_cards",
            "mock_exam_count": 0,
            "include_formula_review": False,
            "material_ids": ["material-2"],
        },
    )
    assert create.status_code == 201, create.text
    package_id = create.json()["package_id"]

    job = _wait_for_package_job(client, package_id)

    assert job["status"] == "complete"
    assert job["accepted_flashcards"] == 10
    assert job["expected_questions"] == 0
    files = client.get(f"/api/v1/packages/{package_id}/files").json()["files"]
    assert [file["kind"] for file in files].count("flashcards") == 1
    assert not any(file["kind"] == "mock_exam" for file in files)


def test_mock_exam_package_exports_the_bound_new_exam(client: TestClient) -> None:
    _seed_package_sources(client)
    create = client.post(
        "/api/v1/packages",
        json={
            "course_id": "course-1",
            "title": "Fresh mock exam",
            "package_kind": "mock_exam",
            "mock_exam_count": 1,
            "include_formula_review": False,
            "material_ids": [f"material-{index}" for index in range(1, 5)],
            "source_exam_id": "source-exam-1",
            "generated_exam_ids": ["exam-2"],
        },
    )
    assert create.status_code == 201, create.text
    package_id = create.json()["package_id"]

    job = _wait_for_package_job(client, package_id)

    assert job["status"] == "complete"
    assert job["accepted_questions"] == 100
    files = client.get(f"/api/v1/packages/{package_id}/files").json()["files"]
    mock_file = next(file for file in files if file["kind"] == "mock_exam")
    document = parse_exam_document_html(
        client.get(f"/api/v1/packages/{package_id}/files/{mock_file['file_id']}").content
    )
    assert document.exam.exam_id == "exam-2"


def _wait_for_package_job(client: TestClient, package_id: str) -> dict[str, object]:
    build = client.post(f"/api/v1/packages/{package_id}/build")
    assert build.status_code == 202, build.text
    job_id = build.json()["job_id"]
    job: dict[str, object] = {}
    for _ in range(50):
        response = client.get(f"/api/v1/packages/jobs/{job_id}")
        assert response.status_code == 200
        job = response.json()
        if job["status"] not in {"queued", "running"}:
            return job
        time.sleep(0.02)
    return job
