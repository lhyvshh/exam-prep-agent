from pathlib import Path
from zipfile import ZipFile

from exam_prep.packages.assembler import PackageAssembler
from exam_prep.packages.curriculum import (
    CurriculumBookSnapshot,
    CurriculumConceptSnapshot,
    CurriculumSnapshot,
)
from exam_prep.packages.models import (
    OfflineExamQuestion,
    OfflineFlashcard,
    OfflineMockExam,
    PackageCreateRequest,
    PackageKind,
)
from exam_prep.packages.frm_policy import FRM_PART_I_POLICY
from exam_prep.packages.validation import PackageBuildSnapshot


def _valid_snapshot_fixture() -> PackageBuildSnapshot:
    return PackageBuildSnapshot(
        package_id="package-1",
        version=1,
        title="FRM Part I Offline Package",
        created_at="2026-07-13T12:00:00Z",
        configuration=PackageCreateRequest(
            course_id="course-1",
            title="FRM Part I Offline Package",
            include_formula_review=False,
        ),
        curriculum=CurriculumSnapshot(
            course_id="course-1",
            books=tuple(_book(book_number) for book_number in range(1, 5)),
        ),
        mock_exams=tuple(_exam(exam_number) for exam_number in range(1, 4)),
        model_metadata={"question_quality_model_versions": "torch-fixture-1"},
        prompt_versions={"section-study": "section-study-v1"},
    )


def _book(book_number: int) -> CurriculumBookSnapshot:
    concept_id = f"concept-{book_number}"
    return CurriculumBookSnapshot(
        material_id=f"book-{book_number}",
        title=f"Book {book_number}",
        content_hash=f"book-hash-{book_number}",
        concepts=(
            CurriculumConceptSnapshot(
                concept_id=concept_id,
                title=f"Risk concept {book_number}",
                learning_outcome=f"Explain risk concept {book_number}",
                source_pages=(10,),
                source_anchors=(f"chunk-{book_number}",),
                flashcards=tuple(
                    OfflineFlashcard(
                        card_id=f"book-{book_number}-card-{index}",
                        book_id=f"book-{book_number}",
                        learning_objective=f"Explain risk concept {book_number}",
                        concept_id=concept_id,
                        prompt=f"Grounded prompt {book_number}.{index}",
                        answer=f"Grounded answer {book_number}.{index}",
                        source_page=10,
                        source_reference=f"Book {book_number}, page 10",
                    )
                    for index in range(10)
                ),
            ),
        ),
        formulas=(),
    )


def _exam(exam_number: int) -> OfflineMockExam:
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
    questions = tuple(
        OfflineExamQuestion(
            question_id=f"exam-{exam_number}-question-{number}",
            question_number=number,
            domain=domain,
            subtopic=f"Subtopic {number}",
            learning_objective=f"Learning objective {number}",
            question_type=question_type,
            difficulty=difficulty,
            prompt=(
                "Which FRM interpretation best applies to principle "
                f"{_alpha_code((exam_number - 1) * 100 + number)}?"
            ),
            choices=(
                f"Supported conclusion {_alpha_code((exam_number - 1) * 400 + number)}",
                f"Alternative {_alpha_code((exam_number - 1) * 400 + 100 + number)}",
                f"Alternative {_alpha_code((exam_number - 1) * 400 + 200 + number)}",
                f"Alternative {_alpha_code((exam_number - 1) * 400 + 300 + number)}",
            ),
            correct_choice_index=0,
            explanation="Grounded explanation.",
            source_reference="FRM source, page 10",
            source_excerpt="The cited FRM reading supports this grounded answer.",
            quality_score=0.92,
            quality_confidence=0.88,
            quality_label="high_quality",
            quality_accepted=True,
            quality_model_version="torch-fixture-1",
            quality_model_source="pytorch",
        )
        for number, (domain, question_type, difficulty) in enumerate(
            zip(domains, question_types, difficulties, strict=True),
            start=1,
        )
    )
    return OfflineMockExam(
        exam_id=f"exam-{exam_number}",
        title=f"FRM Part I Mock Exam {exam_number}",
        questions=questions,
    )


def _alpha_code(value: int) -> str:
    letters: list[str] = []
    while value:
        value, remainder = divmod(value - 1, 26)
        letters.append(chr(ord("a") + remainder))
    return "".join(reversed(letters)) or "a"


def test_assembler_creates_hash_verified_zip(tmp_path: Path) -> None:
    result = PackageAssembler(tmp_path).assemble(_valid_snapshot_fixture())

    assert result.manifest.content_counts.flashcards == 40
    assert result.manifest.content_counts.exam_questions == 300
    assert result.zip_path.exists()
    with ZipFile(result.zip_path) as archive:
        names = archive.namelist()
        assert "package-manifest.json" not in names
        assert not any("validation" in name.casefold() for name in names)
        assert "01-Book-1-Flashcards.html" in names
        assert "Mock-Exam-1.html" in names
        assert all(".." not in name and not name.startswith("/") for name in names)


def test_assembler_creates_focused_study_card_package(tmp_path: Path) -> None:
    complete = _valid_snapshot_fixture()
    snapshot = complete.model_copy(
        update={
            "configuration": PackageCreateRequest(
                course_id="course-1",
                title="Book 1 study cards",
                package_kind=PackageKind.STUDY_CARDS,
                mock_exam_count=0,
                include_formula_review=False,
                material_ids=("book-1",),
            ),
            "curriculum": complete.curriculum.model_copy(
                update={"books": (complete.curriculum.books[0],)}
            ),
            "mock_exams": (),
        }
    )

    result = PackageAssembler(tmp_path).assemble(snapshot)

    with ZipFile(result.zip_path) as archive:
        names = archive.namelist()
        assert names == ["01-Book-1-Flashcards.html"]
        assert not any("manifest" in name.casefold() for name in names)
        assert not any("validation" in name.casefold() for name in names)
    zip_file = next(file for file in result.files if file.kind.value == "zip")
    assert zip_file.content_count == 1
