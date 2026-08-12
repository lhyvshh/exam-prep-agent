from pathlib import Path
from unittest.mock import patch

from exam_prep.repositories.local.exam_store import LocalExamStore
from exam_prep.repositories.local.material_store import LocalMaterialStore
from exam_prep.services.mock_exam_source_service import MockExamSourceService
from backend.tests.unit.mock_exam_source_fixtures import exam_source_text, ingest_book_material


def test_ingest_source_bank_splits_exams_answers_and_classifies_topics(tmp_path: Path) -> None:
    material_store = LocalMaterialStore(tmp_path / "materials")
    exam_store = LocalExamStore(tmp_path / "materials")
    ingest_book_material(material_store)
    service = MockExamSourceService(material_store=material_store, exam_store=exam_store)

    with patch.object(
        material_store,
        "list_parsed_documents_by_course",
        wraps=material_store.list_parsed_documents_by_course,
    ) as list_documents:
        bank = service.ingest_source_bank(
            course_id="frm-course",
            file_name="frm-practice-exams.txt",
            content_type="text/plain",
            data=(
                exam_source_text(2)
                + "\n\nFRM Practice Exam 2\n"
                + "1. A risk manager buys insurance for a loss exposure. What does this represent?\n"
                + "A. Retaining risk.\nB. Transferring risk.\nC. Creating basis risk.\nD. Eliminating governance.\n"
                + "\nAnswer Key for FRM Practice Exam 2\n1. B. Insurance transfers downside risk."
            ).encode("utf-8"),
        )

    assert bank.course_id == "frm-course"
    assert len(bank.exams) == 2
    assert bank.exams[0].question_count == 2
    assert bank.exams[0].questions[0].correct_option_id == "C"
    assert bank.exams[0].questions[0].topic == "Module 1.1: Risk Governance"
    assert bank.exams[0].questions[0].learning_objective == "LO 1.a"
    assert bank.exams[0].questions[1].topic == "Module 1.2: Hedging Decisions"
    assert all(0.0 <= question.difficulty <= 1.0 for exam in bank.exams for question in exam.questions)
    assert bank.exams[1].questions[0].correct_answer == "Insurance transfers downside risk."
    assert list_documents.call_count == 1

    persisted = exam_store.get_source_bank(bank.bank_id)
    assert persisted is not None
    assert persisted.exams[0].questions[0].matched_material_id is not None


def test_ingest_source_bank_accepts_complete_non_frm_exam_shape(tmp_path: Path) -> None:
    material_store = LocalMaterialStore(tmp_path / "materials")
    exam_store = LocalExamStore(tmp_path / "materials")
    ingest_book_material(material_store)
    service = MockExamSourceService(material_store=material_store, exam_store=exam_store)

    bank = service.ingest_source_bank(
        course_id="frm-course",
        file_name="biology-placement-exam.txt",
        content_type="text/plain",
        data=(
            "Practice Exam 1\n"
            "1. Which membrane component creates a hydrophobic interior?\n"
            "A. Phospholipids.\nB. Ribosomes.\nC. Chromosomes.\n"
            "2. Which organelle produces most aerobic ATP?\n"
            "A. Lysosome.\nB. Mitochondrion.\nC. Golgi apparatus.\n"
            "3. Which process copies DNA before cell division?\n"
            "A. Translation.\nB. Transcription.\nC. Replication.\n"
            "Answer Key for Practice Exam 1\n"
            "1. A. Phospholipids form the membrane bilayer.\n"
            "2. B. Mitochondria generate most aerobic ATP.\n"
            "3. C. Replication copies DNA before division.\n"
        ).encode("utf-8"),
    )

    assert bank.exams[0].question_count == 3
    assert bank.exams[0].answer_count == 3
    assert len(bank.exams[0].questions[0].options) == 3
    assert "FRM" not in bank.exams[0].title
    assert not any("expected 100" in warning for warning in bank.warnings)


def test_ingest_source_bank_parses_scanned_frm_exam_ocr_layout(tmp_path: Path) -> None:
    material_store = LocalMaterialStore(tmp_path / "materials")
    exam_store = LocalExamStore(tmp_path / "materials")
    ingest_book_material(material_store)
    service = MockExamSourceService(material_store=material_store, exam_store=exam_store)

    bank = service.ingest_source_bank(
        course_id="frm-course",
        file_name="frm-scanned-ocr.txt",
        content_type="text/plain",
        data=(
            "Question #1 of 100\n"
            "Question ID: 1357794\n"
            "A board sets a risk appetite limit. Which statement best describes this action?\n"
            "A) It eliminates all risk without cost.\n"
            "B) It identifies basis risk from imperfect hedges.\n"
            "C) It translates tolerance for retained risk into limits.\n"
            "D)\n"
            "It replaces governance with insurance.\n"
            "Explanation\n"
            "Risk appetite defines the amount and type of risk the firm is willing to retain.\n"
            "(Book 1, Module 1.1, LO 1.a)\n"
            "Question #2 of 100\n"
            "Question ID.' 1512492\n"
            "A firm hedges exposure with a related futures contract. What concern remains?\n"
            "A) It eliminates all uncertainty.\n"
            "B} Basis risk can remain when the hedge and exposure are not perfectly matched.\n"
            "C) It replaces all governance.\n"
            "•) It guarantees profit.\n"
            "Explanatlon\n"
            "Basis risk can remain when the hedge and exposure are not perfectly matched.\n"
            "(Book 1, Module 1.2, LO 1.b)\n"
            "Question #3 of 100\n"
            "Which statement best handles a split OCR option marker?\n"
            "АA) First option remains normal.\n"
            "Second option text appears before its marker.\n"
            "B)\n"
            "C) Third option remains normal.\n"
            "Fourth option text appears before its marker.\n"
            "D)\n"
            "Question #4 of 100\n"
            "This scanned OCR block is incomplete and should not enter the source bank.\n"
            "A) First option.\n"
            "B) Second option.\n"
            "C) Third option.\n"
        ).encode("utf-8"),
    )

    assert len(bank.exams) == 1
    assert bank.exams[0].question_count == 3
    assert bank.exams[0].answer_count == 2
    assert bank.exams[0].questions[0].question_number == 1
    assert bank.exams[0].questions[0].options[2].option_id == "C"
    assert bank.exams[0].questions[0].options[3].text == "It replaces governance with insurance."
    assert bank.exams[0].questions[0].correct_answer.startswith("Risk appetite defines")
    assert bank.exams[0].questions[0].learning_objective == "LO 1.a"
    assert bank.exams[0].questions[1].options[1].option_id == "B"
    assert bank.exams[0].questions[1].options[3].option_id == "D"
    assert "Question ID" not in bank.exams[0].questions[1].prompt
    assert bank.exams[0].questions[1].topic == "Module 1.2: Hedging Decisions"
    assert bank.exams[0].questions[2].options[0].option_id == "A"
    assert bank.exams[0].questions[2].options[1].text == "Second option text appears before its marker."
    assert bank.exams[0].questions[2].options[3].text == "Fourth option text appears before its marker."


def test_ingest_source_bank_merges_scanned_question_and_answer_sections(tmp_path: Path) -> None:
    material_store = LocalMaterialStore(tmp_path / "materials")
    exam_store = LocalExamStore(tmp_path / "materials")
    ingest_book_material(material_store)
    service = MockExamSourceService(material_store=material_store, exam_store=exam_store)

    bank = service.ingest_source_bank(
        course_id="frm-course",
        file_name="frm-scanned-paired-ocr.txt",
        content_type="text/plain",
        data=(
            "Question #1 of 100\n"
            "A board sets a risk appetite limit. Which statement best describes this action?\n"
            "A) It eliminates all risk without cost.\n"
            "B) It identifies basis risk from imperfect hedges.\n"
            "C) It translates tolerance for retained risk into limits.\n"
            "D) It replaces governance with insurance.\n"
            "Question #2 of 100\n"
            "A firm hedges exposure with a related futures contract. What concern remains?\n"
            "A) It eliminates all uncertainty.\n"
            "B) Basis risk can remain when the hedge and exposure are not perfectly matched.\n"
            "C) It replaces all governance.\n"
            "D) It guarantees profit.\n"
            "Question #1 of 100\n"
            "A board sets a risk appetite limit. Which statement best describes this action?\n"
            "A) It eliminates all risk without cost.\n"
            "B) It identifies basis risk from imperfect hedges.\n"
            "C) It translates tolerance for retained risk into limits.\n"
            "D) It replaces governance with insurance.\n"
            "Explanation\n"
            "Risk appetite defines the amount and type of risk the firm is willing to retain.\n"
            "(Book 1, Module 1.1, LO 1.a)\n"
            "Question #2 of 100\n"
            "A firm hedges exposure with a related futures contract. What concern remains?\n"
            "A) It eliminates all uncertainty.\n"
            "B) Basis risk can remain when the hedge and exposure are not perfectly matched.\n"
            "C) It replaces all governance.\n"
            "D) It guarantees profit.\n"
            "Explanation\n"
            "Basis risk can remain when the hedge and exposure are not perfectly matched.\n"
            "(Book 1, Module 1.2, LO 1.b)\n"
        ).encode("utf-8"),
    )

    assert len(bank.exams) == 1
    assert bank.exams[0].question_count == 2
    assert bank.exams[0].answer_count == 2
    assert bank.exams[0].questions[0].correct_answer.startswith("Risk appetite defines")
    assert bank.exams[0].questions[1].correct_answer.startswith("Basis risk can remain")


def test_ingest_source_bank_handles_ocr_question_prefix_and_missed_section_start(
    tmp_path: Path,
) -> None:
    material_store = LocalMaterialStore(tmp_path / "materials")
    exam_store = LocalExamStore(tmp_path / "materials")
    ingest_book_material(material_store)
    service = MockExamSourceService(material_store=material_store, exam_store=exam_store)

    question = (
        "A board sets a risk appetite limit. Which statement best describes this action?\n"
        "A) It eliminates all risk without cost.\n"
        "B) It identifies basis risk from imperfect hedges.\n"
        "C) It translates tolerance for retained risk into limits.\n"
        "D) It replaces governance with insurance.\n"
    )
    bank = service.ingest_source_bank(
        course_id="frm-course",
        file_name="frm-scanned-reset-ocr.txt",
        content_type="text/plain",
        data=(
            "Que5tion #1 of 100\n"
            + question
            + "Question #8S of 100\n"
            + question
            + "Question #100 of 100\n"
            + question
            + "Question #2 of 100\n"
            + question
            + "Explanation\n"
            + "Risk appetite defines the amount and type of risk the firm is willing to retain.\n"
            + "Question #100 of 100\n"
            + question
            + "Explanation\n"
            + "Risk appetite defines the amount and type of risk the firm is willing to retain.\n"
        ).encode("utf-8"),
    )

    assert len(bank.exams) == 1
    assert [question.question_number for question in bank.exams[0].questions] == [1, 2, 85, 100]
    assert bank.exams[0].answer_count == 2


def test_ingest_scanned_pdf_recovers_only_incomplete_question_pages(tmp_path: Path) -> None:
    material_store = LocalMaterialStore(tmp_path / "materials")
    exam_store = LocalExamStore(tmp_path / "materials")
    ingest_book_material(material_store)
    service = MockExamSourceService(material_store=material_store, exam_store=exam_store)
    incomplete_pages = [
        (
            1,
            "Question #1 of 100\nWhich action best applies risk appetite?\n"
            "A) Remove every limit.\nB) Ignore retained risk.\nC) Set measurable limits.\n",
        )
    ]
    recovered_pages = [
        (
            1,
            "Question #1 of 100\nWhich action best applies risk appetite?\n"
            "A) Remove every limit.\nB) Ignore retained risk.\nC) Set measurable limits.\n"
            "D) Replace governance.\nExplanation\nThe board translates risk appetite into limits.\n",
        )
    ]

    with (
        patch(
            "exam_prep.services.mock_exam_source_service.extract_exam_source_pages",
            return_value=incomplete_pages,
        ),
        patch(
            "exam_prep.services.mock_exam_source_service.recover_exam_source_pages",
            return_value=recovered_pages,
        ) as recover_pages,
    ):
        bank = service.ingest_source_bank(
            course_id="frm-course",
            file_name="scanned-exams.pdf",
            content_type="application/pdf",
            data=b"pdf",
            enable_ocr=True,
        )

    assert bank.exams[0].question_count == 1
    assert bank.exams[0].answer_count == 1
    assert recover_pages.call_args.args[2] == {1, 2}
