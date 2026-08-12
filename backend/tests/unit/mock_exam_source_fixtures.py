from exam_prep.ingestion.pipeline import IngestionPipeline
from exam_prep.repositories.local.material_store import LocalMaterialStore


def ingest_book_material(store: LocalMaterialStore) -> None:
    governance_text = "\n".join(
        [
            "# Module 1.1: Risk Governance",
            "LO 1.a Explain how a board sets risk appetite and delegates limits.",
            "Risk appetite is the amount and type of risk a firm is willing to retain.",
            "Limits translate risk appetite into measurable controls for business units.",
        ]
    )
    hedging_text = "\n".join(
        [
            "# Module 1.2: Hedging Decisions",
            "LO 1.b Compare hedging, insurance, and risk transfer decisions.",
            "A hedge offsets an exposure but can introduce basis risk and opportunity cost.",
            "Insurance transfers downside risk while leaving some upside exposure intact.",
        ]
    )
    IngestionPipeline(store=store).ingest(
        course_id="frm-course",
        module_id=None,
        file_name="frm-book-governance.txt",
        content_type="text/plain",
        data=governance_text.encode("utf-8"),
    )
    IngestionPipeline(store=store).ingest(
        course_id="frm-course",
        module_id=None,
        file_name="frm-book-hedging.txt",
        content_type="text/plain",
        data=hedging_text.encode("utf-8"),
    )


def exam_source_text(question_count: int = 100) -> str:
    question_lines = ["FRM Practice Exam 1"]
    answer_lines = ["Answer Key for FRM Practice Exam 1"]
    for index in range(1, question_count + 1):
        if index % 2 == 0:
            prompt = (
                f"{index}. A firm hedges exposure {index} with a closely related futures contract. "
                "Which statement best describes the remaining concern?"
            )
            correct = "B"
            explanation = "Basis risk can remain when the hedge and exposure are not perfectly matched."
        else:
            prompt = (
                f"{index}. A board sets a risk appetite limit for business unit {index}. "
                "Which statement best describes this governance action?"
            )
            correct = "C"
            explanation = "Risk appetite defines the amount and type of risk the firm is willing to retain."
        question_lines.extend(
            [
                prompt,
                "A. It eliminates all risk without cost.",
                "B. It identifies basis risk from imperfect hedges.",
                "C. It translates tolerance for retained risk into limits.",
                "D. It replaces governance with insurance.",
            ]
        )
        answer_lines.append(f"{index}. {correct}. {explanation}")
    return "\n".join([*question_lines, "", *answer_lines])
