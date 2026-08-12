from pathlib import Path

import fitz

from exam_prep.ingestion.pipeline import IngestionPipeline
from exam_prep.repositories.local.exam_store import LocalExamStore
from exam_prep.repositories.local.material_store import LocalMaterialStore
from exam_prep.services.mock_exam_source_service import MockExamSourceService


def _pdf_bytes(pages: list[str]) -> bytes:
    document = fitz.open()
    for text in pages:
        page = document.new_page(width=612, height=792)
        page.insert_textbox(fitz.Rect(48, 48, 564, 744), text, fontsize=11, lineheight=1.25)
    data = document.tobytes()
    document.close()
    return data


def test_non_frm_pdf_book_and_exam_produce_grounded_course_assets(tmp_path: Path) -> None:
    material_store = LocalMaterialStore(tmp_path / "materials")
    exam_store = LocalExamStore(tmp_path / "materials")
    course_id = "biology-course"
    book = _pdf_bytes(
        [
            "CELL BIOLOGY\n"
            "Learning Objective: Explain how membrane structure controls transport.\n"
            "Cell membranes consist primarily of a phospholipid bilayer. The hydrophilic "
            "phosphate heads face water while hydrophobic fatty-acid tails face inward. "
            "Membrane proteins act as channels, carriers, receptors, and enzymes. Simple "
            "diffusion moves small nonpolar molecules down their concentration gradient. "
            "Facilitated diffusion uses proteins but does not require metabolic energy. "
            "Active transport moves substances against a gradient and requires energy. "
            "Osmosis is the net movement of water across a selectively permeable membrane."
        ]
    )
    record = IngestionPipeline(store=material_store).ingest(
        course_id=course_id,
        file_name="Biology Foundations.pdf",
        content_type="application/pdf",
        data=book,
    )

    study_document = material_store.get_study_document(record.material_id)
    assert record.processing_status.value == "ready"
    assert study_document is not None
    assert study_document.sections
    assert study_document.sections[0].concepts
    assert len(study_document.sections[0].flashcards) >= 10
    assert all(card.source_page >= 1 for card in study_document.sections[0].flashcards)

    exam = _pdf_bytes(
        [
            "Biology Practice Exam 1\n"
            "1. Which membrane region forms the hydrophobic interior?\n"
            "A. Phospholipid fatty-acid tails.\n"
            "B. Phosphate heads.\n"
            "C. Ribosomal subunits.\n"
            "2. Which transport mechanism requires metabolic energy?\n"
            "A. Simple diffusion.\n"
            "B. Active transport.\n"
            "C. Facilitated diffusion.\n"
            "3. What does osmosis describe?\n"
            "A. Protein synthesis.\n"
            "B. Lipid digestion.\n"
            "C. Net water movement across a selectively permeable membrane.\n",
            "Answer Key for Biology Practice Exam 1\n"
            "1. A. The nonpolar fatty-acid tails face inward.\n"
            "2. B. Active transport uses energy to move substances against a gradient.\n"
            "3. C. Osmosis is net water movement across a selectively permeable membrane.\n",
        ]
    )
    bank = MockExamSourceService(
        material_store=material_store,
        exam_store=exam_store,
    ).ingest_source_bank(
        course_id=course_id,
        file_name="Biology Practice Exams.pdf",
        content_type="application/pdf",
        data=exam,
        enable_ocr=False,
    )

    parsed_exam = bank.exams[0]
    assert parsed_exam.title == "Biology Practice Exam 1"
    assert parsed_exam.question_count == 3
    assert parsed_exam.answer_count == 3
    assert all(len(question.options) == 3 for question in parsed_exam.questions)
    assert all(question.matched_material_id == record.material_id for question in parsed_exam.questions)
    assert not any("FRM" in warning for warning in bank.warnings)
