from exam_prep.schemas.materials import (
    MaterialRecord,
    MaterialStudyDocument,
    MaterialStudySection,
    StudyConceptCard,
    StudyFlashcard,
    StudyFormulaCard,
    StudyLearningOutcome,
)

from exam_prep.packages.curriculum import CurriculumSnapshotBuilder


def _study_document_fixture() -> MaterialStudyDocument:
    concept = StudyConceptCard(
        concept_id="concept-1",
        material_id="material-1",
        title="Capital asset pricing model",
        learning_outcome="Explain the assumptions and use of CAPM",
        source_pages=[12],
        source_excerpt="CAPM relates expected return to systematic risk.",
    )
    cards = [
        StudyFlashcard(
            flashcard_id=f"card-{index}",
            material_id="material-1",
            learning_outcome_id="lo-1",
            concept_id="concept-1",
            front=f"CAPM prompt {index}",
            back=f"CAPM answer {index}",
            card_type="short_answer_recall",
            source_page=12,
            source_excerpt="CAPM relates expected return to systematic risk.",
        )
        for index in range(1, 11)
    ]
    cards.append(
        StudyFlashcard(
            flashcard_id="card-without-page",
            material_id="material-1",
            concept_id="concept-1",
            front="Ungrounded prompt",
            back="Ungrounded answer",
            card_type="short_answer_recall",
        )
    )
    formula = StudyFormulaCard(
        formula_id="formula-1",
        material_id="material-1",
        concept_id="concept-1",
        formula_name="CAPM expected return",
        formula_text="E(Ri) = Rf + beta_i(E(Rm) - Rf)",
        variables_json={"Rf": "risk-free rate", "beta_i": "asset beta"},
        source_page=12,
        source_excerpt="The expected return equals the risk-free rate plus beta times the premium.",
        usage_note="Estimate the required return for a risky asset.",
    )
    section = MaterialStudySection(
        section_id="section-1",
        material_id="material-1",
        title="Capital Asset Pricing Model",
        normalized_title="capital asset pricing model",
        page_start=12,
        page_end=14,
        source_anchor="Book 1, pages 12-14",
        summary="CAPM assumptions and applications.",
        learning_outcomes=[
            StudyLearningOutcome(
                outcome_id="lo-1",
                outcome_title="Explain the assumptions and use of CAPM",
                concepts=[concept],
            )
        ],
        concepts=[concept],
        formulas=[formula],
        flashcards=cards,
        source_ids=["chunk-1"],
    )
    return MaterialStudyDocument(material_id="material-1", sections=[section])


def test_curriculum_builder_groups_cards_and_formulas_by_material() -> None:
    snapshot = CurriculumSnapshotBuilder().build(
        course_id="course-1",
        materials=[
            MaterialRecord(
                material_id="material-1",
                course_id="course-1",
                file_name="FRM Book 1.pdf",
                content_type="application/pdf",
                content_hash="book-hash-1",
            )
        ],
        study_documents=[_study_document_fixture()],
    )

    assert snapshot.books[0].material_id == "material-1"
    assert snapshot.books[0].concepts[0].source_pages == (12,)
    assert len(snapshot.books[0].concepts[0].flashcards) == 10
    assert snapshot.books[0].formulas[0].source_page == 12
    assert snapshot.rejected_flashcard_count == 1


def test_curriculum_builder_publishes_ten_cards_per_learning_outcome() -> None:
    document = _study_document_fixture()
    section = document.sections[0]
    second_concept = StudyConceptCard(
        concept_id="concept-2",
        material_id="material-1",
        title="CAPM applications",
        learning_outcome="Explain the assumptions and use of CAPM",
        source_pages=[13],
        source_excerpt="CAPM can be used to estimate a required return.",
    )
    extra_cards = [
        StudyFlashcard(
            flashcard_id=f"extra-card-{index}",
            material_id="material-1",
            learning_outcome_id="lo-1",
            concept_id="concept-2",
            front=f"CAPM application prompt {index}",
            back=f"CAPM application answer {index}",
            card_type="short_answer_recall",
            source_page=13,
            source_excerpt="CAPM can be used to estimate a required return.",
        )
        for index in range(1, 9)
    ]
    outcome = section.learning_outcomes[0].model_copy(
        update={"concepts": [*section.learning_outcomes[0].concepts, second_concept]}
    )
    document = document.model_copy(
        update={
            "sections": [
                section.model_copy(
                    update={
                        "learning_outcomes": [outcome],
                        "concepts": [*section.concepts, second_concept],
                        "flashcards": [*section.flashcards, *extra_cards],
                    }
                )
            ]
        }
    )

    snapshot = CurriculumSnapshotBuilder().build(
        course_id="course-1",
        materials=[
            MaterialRecord(
                material_id="material-1",
                course_id="course-1",
                file_name="FRM Book 1.pdf",
                content_type="application/pdf",
            )
        ],
        study_documents=[document],
    )

    assert len(snapshot.books[0].concepts) == 1
    assert len(snapshot.books[0].concepts[0].flashcards) == 10
    assert snapshot.books[0].concepts[0].learning_outcome == (
        "Explain the assumptions and use of CAPM"
    )
