import pytest
from pydantic import ValidationError

from exam_prep.packages.models import (
    OfflineExamQuestion,
    PackageCreateRequest,
    PackageFile,
    PackageFileKind,
    PackageKind,
)


def test_package_create_request_defaults_to_frm_part_i() -> None:
    request = PackageCreateRequest(course_id="course-1", title="FRM Part I 2026")
    assert request.exam_name == "Financial Risk Manager"
    assert request.exam_part == "Part I"
    assert request.mock_exam_count == 3
    assert request.questions_per_exam == 100
    assert request.cards_per_concept == 10
    assert request.package_kind == PackageKind.COMPLETE


def test_package_create_request_rejects_non_production_counts() -> None:
    with pytest.raises(ValidationError):
        PackageCreateRequest.model_validate(
            {
                "course_id": "course-1",
                "title": "FRM Part I 2026",
                "mock_exam_count": 1,
                "questions_per_exam": 1,
            }
        )


def test_package_create_request_accepts_only_four_unique_ordered_materials() -> None:
    request = PackageCreateRequest(
        course_id="course-1",
        title="FRM Part I 2026",
        material_ids=("book-1", "book-2", "book-3", "book-4"),
        source_exam_id="source-exam-1",
    )

    assert request.material_ids == ("book-1", "book-2", "book-3", "book-4")
    assert request.source_exam_id == "source-exam-1"

    for material_ids in (("book-1",), ("book-1", "book-1", "book-2", "book-3")):
        with pytest.raises(ValidationError):
            PackageCreateRequest(
                course_id="course-1",
                title="FRM Part I 2026",
                material_ids=material_ids,
            )


def test_study_card_package_accepts_selected_ready_books_without_exam_inputs() -> None:
    request = PackageCreateRequest(
        course_id="course-1",
        title="Book 1 study cards",
        package_kind=PackageKind.STUDY_CARDS,
        mock_exam_count=0,
        include_formula_review=False,
        material_ids=("book-1",),
    )

    assert request.material_ids == ("book-1",)
    assert request.source_exam_id is None
    assert request.generated_exam_ids == ()


def test_mock_exam_package_requires_one_source_and_one_generated_exam() -> None:
    request = PackageCreateRequest(
        course_id="course-1",
        title="Fresh mock exam",
        package_kind=PackageKind.MOCK_EXAM,
        mock_exam_count=1,
        material_ids=("book-1", "book-2", "book-3", "book-4"),
        source_exam_id="source-exam-1",
        generated_exam_ids=("generated-exam-1",),
    )

    assert request.generated_exam_ids == ("generated-exam-1",)

    with pytest.raises(ValidationError):
        PackageCreateRequest(
            course_id="course-1",
            title="Incomplete mock exam",
            package_kind=PackageKind.MOCK_EXAM,
            mock_exam_count=1,
            material_ids=("book-1",),
            source_exam_id="source-exam-1",
        )


def test_package_file_rejects_parent_directory_paths() -> None:
    with pytest.raises(ValidationError):
        PackageFile(
            file_id="file-1",
            package_id="package-1",
            version=1,
            kind=PackageFileKind.FLASHCARDS,
            file_name="../unsafe.html",
            media_type="text/html",
            size_bytes=1,
            sha256="0" * 64,
        )


def test_package_file_rejects_non_sha256_hash() -> None:
    with pytest.raises(ValidationError):
        PackageFile(
            file_id="file-1",
            package_id="package-1",
            version=1,
            kind=PackageFileKind.MANIFEST,
            file_name="package-manifest.json",
            media_type="application/json",
            size_bytes=1,
            sha256="A" * 64,
        )


def test_source_exam_package_accepts_source_defined_counts_and_materials() -> None:
    request = PackageCreateRequest(
        course_id="course-1",
        title="Biology practice package",
        package_kind=PackageKind.MOCK_EXAM,
        exam_blueprint_mode="source_exam",
        exam_name="Biology placement exam",
        exam_part="Practice set A",
        mock_exam_count=1,
        questions_per_exam=3,
        material_ids=("book-1", "book-2", "book-3", "book-4", "book-5"),
        source_exam_id="source-exam-1",
        generated_exam_ids=("generated-exam-1",),
    )

    assert request.questions_per_exam == 3
    assert len(request.material_ids) == 5


def test_frm_part_i_mock_package_keeps_the_100_question_fixture() -> None:
    with pytest.raises(ValidationError, match="100 questions"):
        PackageCreateRequest(
            course_id="course-1",
            title="Malformed FRM mock",
            package_kind=PackageKind.MOCK_EXAM,
            exam_blueprint_mode="frm_part_i",
            mock_exam_count=1,
            questions_per_exam=80,
            material_ids=("book-1",),
            source_exam_id="source-exam-1",
            generated_exam_ids=("generated-exam-1",),
        )


def test_frm_part_i_complete_package_keeps_the_100_question_fixture() -> None:
    with pytest.raises(ValidationError, match="100 questions"):
        PackageCreateRequest(
            course_id="course-1",
            title="Malformed complete FRM package",
            package_kind=PackageKind.COMPLETE,
            exam_blueprint_mode="frm_part_i",
            mock_exam_count=3,
            questions_per_exam=80,
            material_ids=("book-1", "book-2", "book-3", "book-4"),
        )


def test_offline_exam_question_accepts_source_defined_choice_count() -> None:
    question = OfflineExamQuestion.model_validate(
        {
            "question_id": "question-1",
            "question_number": 1,
            "domain": "Cell biology",
            "subtopic": "Cell membranes",
            "learning_objective": "Explain selective permeability",
            "question_type": "Applied conceptual",
            "difficulty": "Standard exam-level",
            "prompt": "Which membrane property best explains selective permeability?",
            "choices": (
                "Its phospholipid bilayer has a hydrophobic interior.",
                "It permits every dissolved substance to cross freely.",
                "It is composed only of carbohydrate chains.",
            ),
            "correct_choice_index": 0,
            "explanation": "The hydrophobic interior limits passage by polar solutes.",
            "source_reference": "Biology, page 42",
            "quality_score": 0.92,
            "quality_confidence": 0.88,
            "quality_label": "high_quality",
            "quality_accepted": True,
            "quality_model_version": "torch-fixture-1",
            "quality_model_source": "pytorch",
        }
    )

    assert len(question.choices) == 3


def test_offline_exam_question_requires_trusted_quality_provenance() -> None:
    with pytest.raises(ValidationError):
        OfflineExamQuestion.model_validate(
            {
                "question_id": "question-1",
                "question_number": 1,
                "domain": "Quantitative Analysis",
                "subtopic": "Correlation and linear regression",
                "learning_objective": "Estimate a linear regression",
                "question_type": "Numerical calculation",
                "difficulty": "Standard exam-level",
                "prompt": "What is the slope estimate?",
                "choices": ("0.5", "1.0", "1.5", "2.0"),
                "correct_choice_index": 1,
                "explanation": "The slope is covariance divided by variance.",
                "source_reference": "Book 1, page 120",
            }
        )
