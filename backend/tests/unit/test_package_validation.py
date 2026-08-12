from exam_prep.packages.curriculum import (
    CurriculumBookSnapshot,
    CurriculumConceptSnapshot,
    CurriculumSnapshot,
)
from exam_prep.packages.models import (
    ExamBlueprintMode,
    OfflineExamQuestion,
    OfflineFlashcard,
    OfflineMockExam,
    PackageCreateRequest,
    PackageKind,
)
from exam_prep.packages.frm_policy import FRM_PART_I_POLICY
from exam_prep.packages.validation import (
    PackageBuildSnapshot,
    PackageValidator,
    SourceExamProfile,
    SourceExamQuestionProfile,
)


def _snapshot_fixture(
    *,
    cards_per_concept: int = 10,
    question_quality_passed: bool = True,
) -> PackageBuildSnapshot:
    cards = _cards("book-1", "concept-1", cards_per_concept)
    question = OfflineExamQuestion(
        question_id="question-1",
        question_number=1,
        domain="Foundations of Risk Management",
        subtopic="Corporate governance and risk-management frameworks",
        learning_objective="Explain risk governance",
        question_type="Applied conceptual",
        difficulty="Standard exam-level",
        prompt="Which action is most consistent with effective risk governance?",
        choices=(
            "Board oversight of risk appetite",
            "Elimination of all risk",
            "Delegation of every risk decision",
            "Removal of independent controls",
        ),
        correct_choice_index=0,
        explanation="Board oversight aligns risk taking with approved appetite.",
        source_reference="Foundations, page 10",
        source_excerpt="The board approves and oversees the firm's risk appetite.",
        quality_score=0.92 if question_quality_passed else 0.12,
        quality_confidence=0.88,
        quality_label="high_quality" if question_quality_passed else "low_quality",
        quality_accepted=question_quality_passed,
        quality_model_version="torch-fixture-1",
        quality_model_source="pytorch",
    )
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
            books=(
                CurriculumBookSnapshot(
                    material_id="book-1",
                    title="Foundations",
                    content_hash="book-hash-1",
                    concepts=(
                        CurriculumConceptSnapshot(
                            concept_id="concept-1",
                            title="Risk governance",
                            learning_outcome="Explain risk governance",
                            source_pages=(10,),
                            source_anchors=("chunk-1",),
                            flashcards=cards,
                        ),
                    ),
                    formulas=(),
                ),
            ),
        ),
        mock_exams=(
            OfflineMockExam(
                exam_id="exam-1",
                title="FRM Part I Mock Exam 1",
                questions=(question,),
            ),
        ),
    )


def _cards(book_id: str, concept_id: str, count: int) -> tuple[OfflineFlashcard, ...]:
    return tuple(
        OfflineFlashcard(
            card_id=f"card-{index}",
            book_id=book_id,
            learning_objective="Explain risk governance",
            concept_id=concept_id,
            prompt=f"Grounded prompt {index}",
            answer=f"Grounded answer {index}",
            source_page=10,
            source_reference="Foundations, page 10",
        )
        for index in range(count)
    )


def _alpha_code(value: int) -> str:
    letters: list[str] = []
    while value:
        value, remainder = divmod(value - 1, 26)
        letters.append(chr(ord("a") + remainder))
    return "".join(reversed(letters)) or "a"


def test_validation_rejects_concept_with_nine_cards() -> None:
    report = PackageValidator().validate(_snapshot_fixture(cards_per_concept=9))

    assert report.is_complete is False
    assert "concept_card_count" in {finding.code for finding in report.hard_failures}


def test_validation_accepts_selected_book_study_card_package_without_exams() -> None:
    snapshot = _snapshot_fixture().model_copy(
        update={
            "configuration": PackageCreateRequest(
                course_id="course-1",
                title="Book 1 study cards",
                package_kind=PackageKind.STUDY_CARDS,
                mock_exam_count=0,
                include_formula_review=False,
                material_ids=("book-1",),
            ),
            "mock_exams": (),
        }
    )

    report = PackageValidator().validate(snapshot)

    assert report.passed is True


def test_validation_cannot_override_failed_pytorch_quality_signal() -> None:
    report = PackageValidator().validate(_snapshot_fixture(question_quality_passed=False))

    assert report.is_complete is False
    assert "question_quality" in {finding.code for finding in report.hard_failures}


def test_validation_rejects_non_pytorch_quality_provenance() -> None:
    snapshot = _snapshot_fixture()
    exam = snapshot.mock_exams[0]
    question = exam.questions[0].model_copy(update={"quality_model_source": "heuristic"})
    report = PackageValidator().validate(
        snapshot.model_copy(
            update={"mock_exams": (exam.model_copy(update={"questions": (question,)}),)}
        )
    )

    assert report.is_complete is False
    assert "question_quality_source" in {finding.code for finding in report.hard_failures}


def test_validation_rejects_missing_question_source_evidence() -> None:
    snapshot = _snapshot_fixture()
    exam = snapshot.mock_exams[0]
    question = exam.questions[0].model_copy(update={"source_excerpt": None})

    report = PackageValidator().validate(
        snapshot.model_copy(
            update={"mock_exams": (exam.model_copy(update={"questions": (question,)}),)}
        )
    )

    assert "question_source_evidence" in {finding.code for finding in report.hard_failures}


def test_validation_rejects_number_reskinned_question_templates() -> None:
    snapshot = _snapshot_fixture()
    first = snapshot.mock_exams[0].questions[0].model_copy(
        update={"prompt": "Scenario 12: Which statement best applies duration to this bond?"}
    )
    second = first.model_copy(
        update={
            "question_id": "question-2",
            "question_number": 2,
            "prompt": "Scenario 84: Which statement best applies duration to this bond?",
            "choices": (
                "Choice one for the second question",
                "Choice two for the second question",
                "Choice three for the second question",
                "Choice four for the second question",
            ),
        }
    )
    exam = snapshot.mock_exams[0].model_copy(update={"questions": (first, second)})

    report = PackageValidator().validate(
        snapshot.model_copy(update={"mock_exams": (exam,)})
    )

    assert "question_template_duplicate" in {
        finding.code for finding in report.hard_failures
    }


def test_validation_rejects_toy_package_even_when_configuration_matches() -> None:
    report = PackageValidator().validate(_snapshot_fixture())

    assert report.is_complete is False
    assert {"source_book_count", "mock_exam_count", "exam_question_count"}.issubset(
        {finding.code for finding in report.hard_failures}
    )


def test_validation_accepts_the_three_frm_profiles_in_persisted_exam_order() -> None:
    base = _snapshot_fixture()
    exams: list[OfflineMockExam] = []
    for exam_index in range(3):
        domains = [
            domain
            for domain, count in FRM_PART_I_POLICY.exam_domain_counts[exam_index].items()
            for _ in range(count)
        ]
        question_types = [
            question_type
            for question_type, count in FRM_PART_I_POLICY.question_type_counts.items()
            for _ in range(count)
        ]
        difficulties = [
            difficulty
            for difficulty, count in FRM_PART_I_POLICY.difficulty_counts[exam_index].items()
            for _ in range(count)
        ]
        questions = tuple(
            OfflineExamQuestion(
                question_id=f"exam-{exam_index + 1}-question-{number}",
                question_number=number,
                domain=domain,
                subtopic=f"Subtopic {number}",
                learning_objective=f"LO {number}",
                question_type=question_type,
                difficulty=difficulty,
                prompt=(
                    "Which FRM interpretation best applies to principle "
                    f"{_alpha_code(exam_index * 100 + number)}?"
                ),
                choices=(
                    f"Supported conclusion {_alpha_code(exam_index * 400 + number)}",
                    f"Alternative {_alpha_code(exam_index * 400 + 100 + number)}",
                    f"Alternative {_alpha_code(exam_index * 400 + 200 + number)}",
                    f"Alternative {_alpha_code(exam_index * 400 + 300 + number)}",
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
                quality_model_source="pytorch_checkpoint",
            )
            for number, (domain, question_type, difficulty) in enumerate(
                zip(domains, question_types, difficulties, strict=True),
                start=1,
            )
        )
        exams.append(
            OfflineMockExam(
                exam_id=f"exam-{exam_index + 1}",
                title=f"FRM Part I Mock Exam {exam_index + 1}",
                questions=questions,
            )
        )
    reordered = (exams[0], exams[2], exams[1])
    snapshot = base.model_copy(
        update={
            "configuration": PackageCreateRequest(
                course_id="course-1",
                title="FRM Part I Offline Package",
                include_formula_review=False,
            ),
            "curriculum": CurriculumSnapshot(
                course_id="course-1",
                books=tuple(
                    CurriculumBookSnapshot(
                        material_id=f"book-{book_number}",
                        title=f"Book {book_number}",
                        content_hash=f"book-hash-{book_number}",
                        concepts=(
                            CurriculumConceptSnapshot(
                                concept_id=f"concept-{book_number}",
                                title=f"Concept {book_number}",
                                learning_outcome=f"Learning outcome {book_number}",
                                source_pages=(10,),
                                source_anchors=(f"chunk-{book_number}",),
                                flashcards=_cards(
                                    f"book-{book_number}",
                                    f"concept-{book_number}",
                                    10,
                                ),
                            ),
                        ),
                        formulas=(),
                    )
                    for book_number in range(1, 5)
                ),
            ),
            "mock_exams": reordered,
        }
    )

    report = PackageValidator().validate(snapshot)

    assert report.passed is True


def test_validation_rejects_needs_review_or_low_confidence_quality() -> None:
    base = _snapshot_fixture()
    question = base.mock_exams[0].questions[0].model_copy(
        update={
            "quality_label": "needs_review",
            "quality_confidence": 0.49,
            "quality_model_source": "pytorch_checkpoint",
        }
    )
    exam = base.mock_exams[0].model_copy(update={"questions": (question,)})

    report = PackageValidator().validate(base.model_copy(update={"mock_exams": (exam,)}))

    codes = {finding.code for finding in report.hard_failures}
    assert "question_quality_label" in codes
    assert "question_quality_confidence" in codes


def test_source_exam_validation_preserves_each_question_blueprint() -> None:
    base = _snapshot_fixture()
    configuration = PackageCreateRequest(
        course_id="course-1",
        title="Governance practice exam",
        package_kind=PackageKind.MOCK_EXAM,
        exam_blueprint_mode=ExamBlueprintMode.SOURCE_EXAM,
        exam_name="Governance certification",
        exam_part="Practice Exam 1",
        mock_exam_count=1,
        questions_per_exam=1,
        include_formula_review=False,
        material_ids=("book-1",),
        source_exam_id="source-exam-1",
        generated_exam_ids=("exam-1",),
    )
    profile = SourceExamProfile(
        source_exam_id="source-exam-1",
        title="Practice Exam 1",
        questions=(
            SourceExamQuestionProfile(
                question_number=1,
                choice_count=4,
                topic="Foundations of Risk Management",
                learning_objective="Explain risk governance",
                question_type="Applied conceptual",
                difficulty="Standard exam-level",
            ),
        ),
    )
    snapshot = base.model_copy(
        update={
            "configuration": configuration,
            "source_exam_profile": profile,
        }
    )

    assert PackageValidator().validate(snapshot).passed is True

    changed = snapshot.mock_exams[0].questions[0].model_copy(update={"difficulty": "Difficult"})
    report = PackageValidator().validate(
        snapshot.model_copy(
            update={
                "mock_exams": (
                    snapshot.mock_exams[0].model_copy(update={"questions": (changed,)}),
                )
            }
        )
    )

    assert "source_exam_question_profile" in {
        finding.code for finding in report.hard_failures
    }
