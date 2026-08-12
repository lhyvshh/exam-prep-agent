import io
import zipfile

import pytest

from exam_prep.core.exceptions import MaterialIngestionError
from exam_prep.ingestion.parsers import DocumentParser


def test_txt_parser_creates_sections_and_titles() -> None:
    parser = DocumentParser()
    payload = b"# Intro\nHello world\n# Week 1\nGradient descent practice notes\n"

    sections = parser.parse(
        material_id="mat-1",
        course_id="course-1",
        file_name="notes.txt",
        content_type="text/plain",
        data=payload,
    )

    assert len(sections) == 2
    assert sections[0].section_title == "Intro"
    assert "Gradient" in sections[1].section_title
    assert sections[1].citation_label.startswith("notes.txt | ")


def test_docx_parser_extracts_heading_sections() -> None:
    parser = DocumentParser()
    payload = build_docx_bytes(
        heading="Chapter 1",
        paragraphs=["First paragraph", "Second paragraph"],
    )

    sections = parser.parse(
        material_id="mat-2",
        course_id="course-1",
        file_name="chapter.docx",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        data=payload,
    )

    assert len(sections) == 1
    assert sections[0].section_title == "Chapter 1"
    assert "Second paragraph" in sections[0].text


def test_pptx_parser_extracts_slide_text() -> None:
    parser = DocumentParser()
    payload = build_pptx_bytes(title="Lecture 3", body="Gradient descent steps")

    sections = parser.parse(
        material_id="mat-3",
        course_id="course-1",
        file_name="slides.pptx",
        content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        data=payload,
    )

    assert len(sections) == 1
    assert sections[0].locator.slide_number == 1
    assert sections[0].section_title == "Gradient descent steps"


def test_pdf_parser_extracts_page_text() -> None:
    parser = DocumentParser()
    payload = build_pdf_bytes("Sample PDF content")

    sections = parser.parse(
        material_id="mat-4",
        course_id="course-1",
        file_name="paper.pdf",
        content_type="application/pdf",
        data=payload,
    )

    assert len(sections) == 1
    assert sections[0].locator.page_number == 1
    assert "Sample PDF content" in sections[0].text


def test_small_pdf_defaults_to_session_level_section(monkeypatch: pytest.MonkeyPatch) -> None:
    parser = DocumentParser()

    class FakePage:
        def __init__(self, text: str) -> None:
            self._text = text

        def extract_text(self) -> str:
            return self._text

    class FakeReader:
        def __init__(self, *_args, **_kwargs) -> None:
            self.pages = [
                FakePage("Lecture 6\nIntroduction to Python covers variables and loops."),
                FakePage("Lecture 6\nWorked examples show how loops repeat tasks."),
            ]

    monkeypatch.setattr("exam_prep.ingestion.parsers.PdfReader", FakeReader)

    sections = parser.parse(
        material_id="mat-small-pdf",
        course_id="course-1",
        file_name="session6.pdf",
        content_type="application/pdf",
        data=b"%PDF-fake",
    )

    assert len(sections) == 1
    assert sections[0].section_kind == "session"
    assert sections[0].is_default is True
    assert "Python" in sections[0].section_title
    assert "variables and loops" in sections[0].text


def test_large_pdf_aggregates_page_fragments_into_larger_sections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parser = DocumentParser()

    class FakePage:
        def __init__(self, text: str) -> None:
            self._text = text

        def extract_text(self) -> str:
            return self._text

    class FakeReader:
        def __init__(self, *_args, **_kwargs) -> None:
            self.pages = [
                FakePage(
                    (
                        f"Lecture {page_number}\n"
                        f"Core concept explanation for topic {page_number}. "
                        f"This page expands the lecture with worked steps, key definitions, "
                        f"and applied examples for repeated practice on topic {page_number}.\n"
                        f"Worked example {page_number}."
                    )
                )
                for page_number in range(1, 41)
            ]

    monkeypatch.setattr("exam_prep.ingestion.parsers.PdfReader", FakeReader)

    sections = parser.parse(
        material_id="mat-large-pdf",
        course_id="course-1",
        file_name="lecture-notes.pdf",
        content_type="application/pdf",
        data=b"%PDF-fake",
    )

    assert len(sections) < 40
    assert len(sections) <= 8
    assert sections[0].locator.page_number == 1
    assert "pages" not in sections[0].section_title.lower()
    assert "Core" in sections[0].section_title


def test_parser_rejects_unsupported_extension() -> None:
    parser = DocumentParser()

    with pytest.raises(MaterialIngestionError, match="Unsupported file type"):
        parser.parse(
            material_id="mat-5",
            course_id="course-1",
            file_name="archive.csv",
            content_type="text/csv",
            data=b"a,b,c",
        )


def test_parser_removes_admin_and_duplicate_pdf_noise(monkeypatch: pytest.MonkeyPatch) -> None:
    parser = DocumentParser()

    class FakePage:
        def __init__(self, text: str) -> None:
            self._text = text

        def extract_text(self) -> str:
            return self._text

    class FakeReader:
        def __init__(self, *_args, **_kwargs) -> None:
            self.pages = [
                FakePage(
                    "Lecture 2\nCanvas announcement\nOffice hours Tuesday 3PM\n"
                    "Gradient descent updates parameters using the learning rate.\n"
                    "Gradient descent updates parameters using the learning rate.\n"
                    "Page 1"
                )
            ]

    monkeypatch.setattr("exam_prep.ingestion.parsers.PdfReader", FakeReader)

    sections = parser.parse(
        material_id="mat-clean-pdf",
        course_id="course-1",
        file_name="lecture.pdf",
        content_type="application/pdf",
        data=b"%PDF-fake",
    )

    assert len(sections) == 1
    assert "Canvas announcement" not in sections[0].text
    assert "Office hours" not in sections[0].text
    assert sections[0].text.count("Gradient descent updates parameters using the learning rate.") == 1


def test_pdf_parser_preserves_frm_workbook_hierarchy_and_quiz_style(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parser = DocumentParser()

    class FakePage:
        def __init__(self, text: str) -> None:
            self._text = text

        def extract_text(self) -> str:
            return self._text

    class FakeReader:
        def __init__(self, *_args, **_kwargs) -> None:
            self.pages = [
                FakePage(
                    "Part I Exam Weightings\n"
                    "Book Topic Area Exam Weight Exam Questions\n"
                    "1 Foundations of Risk Management 20% 20\n"
                    "2 Quantitative Analysis 20% 20\n"
                    "3 Financial Markets and Products 30% 30\n"
                    "4 Valuation and Risk Models 30% 30"
                ),
                FakePage(
                    "STUDY SESSION 1—Risk Management Overview\n"
                    "READING 1\n"
                    "The Building Blocks of Risk Management\n"
                    "EXAM FOCUS\n"
                    "This reading covers risk management concepts that are testable on the exam.\n"
                    "Module 1.1: Introduction to Risk Management\n"
                    "LO 1.a: Explain the concept of risk.\n"
                    "Module 1.2: Types of Risk\n"
                    "KEY CONCEPTS\n"
                    "LO 1.a Risk is uncertainty surrounding outcomes.\n"
                    "Risk management has four components: identify, analyze, evaluate, manage."
                ),
                FakePage(
                    "MODULE QUIZ 1.1\n"
                    "1. Which statement regarding risk management is correct?\n"
                    "A. Risk management is more concerned with unexpected losses.\n"
                    "B. Risk can be eliminated entirely.\n"
                    "C. Risk always means loss size.\n"
                    "D. Risk management ignores monitoring."
                ),
                FakePage(
                    "MODULE QUIZ 1.2\n"
                    "1. Which of the following is a financial risk?\n"
                    "A. Market risk.\n"
                    "B. Office hours.\n"
                    "C. Course logistics.\n"
                    "D. Reading schedule."
                ),
                FakePage(
                    "ANSWER KEY FOR MODULE QUIZZES\n"
                    "Module Quiz 1.1\n"
                    "1. A Risk management focuses on unexpected losses and monitoring risk.\n"
                    "Module Quiz 1.2\n"
                    "1. A Market risk is a financial risk."
                ),
                FakePage(
                    "STUDY SESSION 1—Risk Management Overview\n"
                    "READING 2\n"
                    "How Do Firms Manage Financial Risk?\n"
                    "EXAM FOCUS\n"
                    "This reading focuses on corporate risk management.\n"
                    "Module 2.1: Corporate Risk Management\n"
                    "KEY CONCEPTS\n"
                    "Firms identify, measure, and manage financial risk."
                ),
            ]

    monkeypatch.setattr("exam_prep.ingestion.parsers.PdfReader", FakeReader)

    sections = parser.parse(
        material_id="mat-frm",
        course_id="course-frm",
        file_name="frm-book.pdf",
        content_type="application/pdf",
        data=b"%PDF-fake",
    )

    titles = [section.section_title for section in sections]

    assert titles[0] == "Part I Exam Weightings"
    assert titles[1] == (
        "Study Session 1: Risk Management Overview / "
        "Reading 1: The Building Blocks of Risk Management / "
        "Module 1.1: Introduction to Risk Management"
    )
    assert titles[2].endswith("Module 1.2: Types of Risk")
    assert titles[3].endswith("Module 2.1: Corporate Risk Management")
    assert all("Which statement regarding" not in title for title in titles)

    module_11 = sections[1]
    assert module_11.locator.page_number == 2
    assert module_11.page_end == 5
    assert "EXAM FOCUS" not in module_11.text
    assert "KEY CONCEPTS" in module_11.text
    assert "MODULE QUIZ 1.1" in module_11.text
    assert "ANSWER KEY FOR MODULE QUIZZES" in module_11.text
    assert "1. A Risk management focuses" in module_11.text


def test_pdf_parser_correlates_key_concepts_quizzes_and_source_pages_by_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parser = DocumentParser()

    class FakePage:
        def __init__(self, text: str) -> None:
            self._text = text

        def extract_text(self) -> str:
            return self._text

    class FakeReader:
        def __init__(self, *_args, **_kwargs) -> None:
            self.pages = [
                FakePage(
                    "READING 1\n"
                    "The Building Blocks of Risk Management\n"
                    "STUDY SESSION 1\n"
                    "EXAM FOCUS\n"
                    "This reading covers two separate modules.\n"
                    "MODULE 1.1: INTRODUCTION TO RISK MANAGEMENT\n"
                    "LO 1.a: Explain the concept of risk.\n"
                    "Module 1.1 body text.\n"
                    "LO 1.b: Describe the risk management process.\n"
                    "More module 1.1 body text."
                ),
                FakePage(
                    "MODULE 1.2: TYPES OF RISK\n"
                    "LO 1.c: Identify major risk categories.\n"
                    "Module 1.2 body text."
                ),
                FakePage(
                    "MODULE QUIZ 1.1\n"
                    "1. Which statement about the risk process is correct?\n"
                    "A. Identify, measure, evaluate, and manage risks."
                ),
                FakePage(
                    "MODULE QUIZ 1.2\n"
                    "1. Which category is a market risk example?\n"
                    "A. Foreign exchange risk."
                ),
                FakePage(
                    "KEY CONCEPTS\n"
                    "LO 1.a\n"
                    "Risk process belongs to module one.\n"
                    "LO 1.b\n"
                    "Risk controls also belong to module one.\n"
                    "LO 1.c\n"
                    "Risk categories belong to module two."
                ),
                FakePage(
                    "ANSWER KEY FOR MODULE QUIZZES\n"
                    "MODULE QUIZ 1.1\n"
                    "1. A The process answer belongs to module one.\n"
                    "MODULE QUIZ 1.2\n"
                    "1. A The category answer belongs to module two."
                ),
            ]

    monkeypatch.setattr("exam_prep.ingestion.parsers.PdfReader", FakeReader)

    sections = parser.parse(
        material_id="mat-frm-module-correlation",
        course_id="course-frm",
        file_name="frm-book.pdf",
        content_type="application/pdf",
        data=b"%PDF-fake",
    )

    module_11 = sections[0]
    module_12 = sections[1]

    assert module_11.locator.page_number == 1
    assert module_12.locator.page_number == 2

    assert "LO 1.a" in module_11.text
    assert "LO 1.b" in module_11.text
    assert "Risk process belongs to module one" in module_11.text
    assert "Risk controls also belong to module one" in module_11.text
    assert "Risk categories belong to module two" not in module_11.text
    assert "MODULE QUIZ 1.1" in module_11.text
    assert "MODULE QUIZ 1.2" not in module_11.text
    assert "process answer belongs to module one" in module_11.text
    assert "category answer belongs to module two" not in module_11.text

    assert "LO 1.c" in module_12.text
    assert "Risk categories belong to module two" in module_12.text
    assert "Risk process belongs to module one" not in module_12.text
    assert "MODULE QUIZ 1.2" in module_12.text
    assert "category answer belongs to module two" in module_12.text
    assert "process answer belongs to module one" not in module_12.text


def test_pdf_parser_fills_contiguous_key_concept_lo_gaps_within_module_boundaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parser = DocumentParser()

    class FakePage:
        def __init__(self, text: str) -> None:
            self._text = text

        def extract_text(self) -> str:
            return self._text

    class FakeReader:
        def __init__(self, *_args, **_kwargs) -> None:
            self.pages = [
                FakePage(
                    "READING 1\n"
                    "The Building Blocks of Risk Management\n"
                    "STUDY SESSION 1\n"
                    "MODULE 1.1: INTRODUCTION TO RISK MANAGEMENT\n"
                    "LO 1.a: Explain the concept of risk.\n"
                    "Module body text has a scanner gap here.\n"
                    "LO 1.d: Explain risk and reward trade-offs.\n"
                    "MODULE 1.2: TYPES OF RISK\n"
                    "LO 1.e: Identify major risk types."
                ),
                FakePage(
                    "KEY CONCEPTS\n"
                    "LO 1.a\n"
                    "Risk is uncertainty surrounding outcomes.\n"
                    "LO 1.b\n"
                    "Value at risk and economic capital quantify risk.\n"
                    "LO 1.c\n"
                    "Expected losses are average losses over a time horizon.\n"
                    "LO 1.d\n"
                    "Risk and reward have an observed trade-off.\n"
                    "LO 1.e\n"
                    "Risk can be categorized into several major types."
                ),
                FakePage(
                    "MODULE QUIZ 1.1\n"
                    "1. Which statement about risk is correct?\n"
                    "A. Risk is uncertainty."
                ),
                FakePage(
                    "MODULE QUIZ 1.2\n"
                    "1. Which category is a risk type?\n"
                    "A. Market risk."
                ),
                FakePage(
                    "ANSWER KEY FOR MODULE QUIZZES\n"
                    "MODULE QUIZ 1.1\n"
                    "1. A Risk is uncertainty. (LO 1.a)\n"
                    "MODULE QUIZ 1.2\n"
                    "1. A Market risk is a major risk type. (LO 1.e)"
                ),
            ]

    monkeypatch.setattr("exam_prep.ingestion.parsers.PdfReader", FakeReader)

    sections = parser.parse(
        material_id="mat-frm-lo-gap",
        course_id="course-frm",
        file_name="frm-book.pdf",
        content_type="application/pdf",
        data=b"%PDF-fake",
    )

    module_11 = sections[0]
    module_12 = sections[1]

    assert "LO 1.a" in module_11.text
    assert "LO 1.b" in module_11.text
    assert "LO 1.c" in module_11.text
    assert "LO 1.d" in module_11.text
    assert "LO 1.e" not in module_11.text
    assert "Value at risk and economic capital quantify risk" in module_11.text
    assert "Expected losses are average losses" in module_11.text

    assert "LO 1.e" in module_12.text
    assert "LO 1.b" not in module_12.text
    assert "Risk can be categorized into several major types" in module_12.text


def test_pdf_parser_maps_formula_appendix_by_reading_without_module_leakage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parser = DocumentParser()

    class FakePage:
        def __init__(self, text: str) -> None:
            self._text = text

        def extract_text(self) -> str:
            return self._text

    class FakeReader:
        def __init__(self, *_args, **_kwargs) -> None:
            self.pages = [
                FakePage(
                    "READING 1\n"
                    "The Building Blocks of Risk Management\n"
                    "STUDY SESSION 1\n"
                    "MODULE 1.1: INTRODUCTION TO RISK MANAGEMENT\n"
                    "LO 1.a: Explain the concept of risk.\n"
                    "LO 1.b: Explain expected loss and unexpected loss."
                ),
                FakePage(
                    "KEY CONCEPTS\n"
                    "LO 1.a\n"
                    "Risk is uncertainty surrounding outcomes.\n"
                    "LO 1.b\n"
                    "Expected loss combines exposure, probability, and severity."
                ),
                FakePage(
                    "MODULE QUIZ 1.1\n"
                    "1. What is expected loss based on?\n"
                    "A. Exposure, probability, and loss severity."
                ),
                FakePage(
                    "READING 5\n"
                    "Modern Portfolio Theory and the Capital Asset Pricing Model\n"
                    "STUDY SESSION 2\n"
                    "MODULE 5.1: MODERN PORTFOLIO THEORY AND THE CAPITAL MARKET LINE\n"
                    "LO 5.a: Explain Modern Portfolio Theory.\n"
                    "LO 5.b: Define the capital market line."
                ),
                FakePage(
                    "KEY CONCEPTS\n"
                    "LO 5.a\n"
                    "Portfolio diversification reduces company-specific risk.\n"
                    "LO 5.b\n"
                    "The capital market line combines the risk-free asset and market portfolio."
                ),
                FakePage(
                    "MODULE QUIZ 5.1\n"
                    "1. What does the capital market line combine?\n"
                    "A. A risk-free asset and the market portfolio."
                ),
                FakePage(
                    "FORMULAS\n"
                    "Reading 1\n"
                    "Expected loss: EL = EAD × PD × LGD\n"
                    "Reading 5\n"
                    "Capital asset pricing model: E(Ri) = RF + [E(RM) − RF]βi"
                ),
            ]

    monkeypatch.setattr("exam_prep.ingestion.parsers.PdfReader", FakeReader)

    sections = parser.parse(
        material_id="mat-frm-formulas",
        course_id="course-frm",
        file_name="frm-book.pdf",
        content_type="application/pdf",
        data=b"%PDF-fake",
    )

    module_11 = next(section for section in sections if section.section_title.endswith("Module 1.1: Introduction to Risk Management"))
    module_51 = next(
        section
        for section in sections
        if section.section_title.endswith("Module 5.1: Modern Portfolio Theory and the Capital Market Line")
    )

    assert "LO 1.a" in module_11.text
    assert "LO 1.b" in module_11.text
    assert "FORMULAS" not in module_11.text
    assert "Expected loss: EL = EAD × PD × LGD" not in module_11.text
    assert "Capital asset pricing model" not in module_11.text
    assert module_11.page_end == 3

    assert "LO 5.a" in module_51.text
    assert "LO 5.b" in module_51.text
    assert "FORMULAS" not in module_51.text
    assert "Capital asset pricing model: E(Ri) = RF + [E(RM) − RF]βi" not in module_51.text
    assert "Expected loss: EL = EAD × PD × LGD" not in module_51.text
    assert module_51.page_end == 6

    formula_section = sections[-1]
    assert formula_section.section_title == "Formulas"
    assert formula_section.section_kind == "reference"
    assert formula_section.locator.page_number == 7
    assert formula_section.page_end == 7
    assert formula_section.text.startswith("FORMULAS")
    assert "Reading 1" in formula_section.text
    assert "Expected loss: EL = EAD × PD × LGD" in formula_section.text
    assert "Reading 5" in formula_section.text
    assert "Capital asset pricing model: E(Ri) = RF + [E(RM) − RF]βi" in formula_section.text


def test_pdf_parser_ignores_contents_formula_entry_before_real_appendix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parser = DocumentParser()

    class FakePage:
        def __init__(self, text: str) -> None:
            self._text = text

        def extract_text(self) -> str:
            return self._text

    class FakeReader:
        def __init__(self, *_args, **_kwargs) -> None:
            self.pages = [
                FakePage(
                    "CONTENTS\n"
                    "Readings and Learning Objectives\n"
                    "STUDY SESSION 1-Risk Management Overview\n"
                    "READING 1\n"
                    "The Building Blocks of Risk Management\n"
                    "EXAM FOCUS\n"
                    "Module 1.1: Introduction to Risk Management\n"
                    "KEY CONCEPTS\n"
                    "Answer Key for Module Quizzes\n"
                    "FORMULAS ........ 153"
                ),
                FakePage(
                    "READING 1\n"
                    "The Building Blocks of Risk Management\n"
                    "STUDY SESSION 1\n"
                    "MODULE 1.1: INTRODUCTION TO RISK MANAGEMENT\n"
                    "LO 1.a: Explain the concept of risk."
                ),
                FakePage(
                    "KEY CONCEPTS\n"
                    "LO 1.a\n"
                    "Risk is uncertainty surrounding outcomes.\n"
                    "MODULE QUIZ 1.1\n"
                    "1. Which statement about risk is correct?\n"
                    "A. Risk is uncertainty surrounding outcomes."
                ),
                FakePage(
                    "ANSWER KEY FOR MODULE QUIZZES\n"
                    "Module Quiz 1.1\n"
                    "1. A Risk is uncertainty surrounding outcomes. (LO 1.a)"
                ),
                FakePage(
                    "FORMULAS\n"
                    "Reading 1\n"
                    "Expected loss: EL = EAD × PD × LGD"
                ),
            ]

    monkeypatch.setattr("exam_prep.ingestion.parsers.PdfReader", FakeReader)

    sections = parser.parse(
        material_id="mat-frm-toc-formulas",
        course_id="course-frm",
        file_name="frm-book.pdf",
        content_type="application/pdf",
        data=b"%PDF-fake",
    )

    module_11 = next(section for section in sections if "Module 1.1" in section.section_title)
    formula_section = sections[-1]

    assert "CONTENTS" not in module_11.text
    assert "FORMULAS ........ 153" not in module_11.text
    assert "Risk is uncertainty surrounding outcomes." in module_11.text
    assert "MODULE QUIZ 1.1" in module_11.text
    assert "ANSWER KEY FOR MODULE QUIZZES" in module_11.text
    assert formula_section.section_title == "Formulas"
    assert formula_section.locator.page_number == 5
    assert "Expected loss: EL = EAD × PD × LGD" in formula_section.text
    assert "FORMULAS ........ 153" not in formula_section.text


def test_pdf_parser_classifies_image_only_formula_appendix_near_book_end() -> None:
    parser = DocumentParser()

    page_text = "FORMULAS\nREADING 1\nREADING 5"

    assert parser._classify_page(
        page_text,
        page_number=158,
        total_pages=167,
        previous_state={"seen_study_content": True},
    ) == "formula_appendix"


def test_pdf_parser_classifies_mixed_case_reading_only_formula_appendix_as_formula_page() -> None:
    parser = DocumentParser()

    page_text = "FORMULAS\nReading 28\nReading 29\nReading 30\nReading 33"

    assert parser._classify_page(
        page_text,
        page_number=223,
        total_pages=238,
        previous_state={"seen_study_content": True},
    ) == "formula_appendix"


def test_pdf_parser_distributes_image_only_formula_crops_to_page_reading_headings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parser = DocumentParser()

    class FakePage:
        def __init__(self, text: str) -> None:
            self._text = text

        def extract_text(self) -> str:
            return self._text

    class FakeReader:
        def __init__(self, *_args, **_kwargs) -> None:
            self.pages = [
                FakePage(
                    "READING 1\n"
                    "The Building Blocks of Risk Management\n"
                    "STUDY SESSION 1\n"
                    "MODULE 1.1: INTRODUCTION TO RISK MANAGEMENT\n"
                    "LO 1.a: Explain the concept of risk."
                ),
                FakePage(
                    "READING 5\n"
                    "Modern Portfolio Theory and CAPM\n"
                    "STUDY SESSION 2\n"
                    "MODULE 5.1: MODERN PORTFOLIO THEORY\n"
                    "LO 5.a: Explain Modern Portfolio Theory."
                ),
                FakePage(
                    "FORMULAS\n"
                    "Reading 1\n"
                    "Reading 5\n"
                    "[FORMULA_IMAGE_CROP page=3 path=formula-crop://mat-formula-page/page-3-image-1.png label=\"Formula image 1\"]\n"
                    "[FORMULA_IMAGE_CROP page=3 path=formula-crop://mat-formula-page/page-3-image-2.png label=\"Formula image 2\"]"
                ),
            ]

    monkeypatch.setattr("exam_prep.ingestion.parsers.PdfReader", FakeReader)

    sections = parser.parse(
        material_id="mat-formula-page",
        course_id="course-frm",
        file_name="formula-page.pdf",
        content_type="application/pdf",
        data=b"%PDF-fake",
    )

    formula_section = sections[-1]

    assert formula_section.section_title == "Formulas"
    assert "[FORMULA_IMAGE_CROP" not in formula_section.text
    assert "formula-crop://" not in formula_section.text
    assert "data:image" not in formula_section.text
    assert "Reading 1" in formula_section.text
    assert "Reading 5" in formula_section.text
    assert [asset.reading_number for asset in formula_section.formula_assets] == [1, 5]
    assert [asset.path for asset in formula_section.formula_assets] == [
        "formula-crop://mat-formula-page/page-3-image-1.png",
        "formula-crop://mat-formula-page/page-3-image-2.png",
    ]


def test_pdf_parser_finds_workbook_structure_after_long_front_matter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parser = DocumentParser()

    class FakePage:
        def __init__(self, text: str) -> None:
            self._text = text

        def extract_text(self) -> str:
            return self._text

    front_matter_pages = [
        FakePage(
            "CONTENTS\n"
            "Study Session 1 Risk Management Overview ........ 13\n"
            "Reading 1 The Building Blocks of Risk Management ........ 13\n"
            "Module 1.1 Introduction to Risk Management ........ 13\n"
            "FORMULAS ........ 153"
        )
        for _ in range(14)
    ]

    class FakeReader:
        def __init__(self, *_args, **_kwargs) -> None:
            self.pages = [
                *front_matter_pages,
                FakePage(
                    "STUDY SESSION 1—Risk Management Overview\n"
                    "READING 1\n"
                    "The Building Blocks of Risk Management\n"
                    "MODULE 1.1: INTRODUCTION TO RISK MANAGEMENT\n"
                    "LO 1.a: Explain the concept of risk."
                ),
                FakePage(
                    "KEY CONCEPTS\n"
                    "LO 1.a\n"
                    "Risk is uncertainty surrounding outcomes.\n"
                    "MODULE QUIZ 1.1\n"
                    "1. Which statement about risk is correct?\n"
                    "A. Risk is uncertainty surrounding outcomes.\n"
                    "ANSWER KEY FOR MODULE QUIZZES\n"
                    "Module Quiz 1.1\n"
                    "1. A Risk is uncertainty surrounding outcomes."
                ),
                FakePage(
                    "READING 2\n"
                    "How Do Firms Manage Financial Risk?\n"
                    "MODULE 2.1: CORPORATE RISK MANAGEMENT\n"
                    "LO 2.a: Describe risk management strategies."
                ),
                FakePage(
                    "KEY CONCEPTS\n"
                    "LO 2.a\n"
                    "Firms can accept, avoid, mitigate, or transfer risk.\n"
                    "MODULE QUIZ 2.1\n"
                    "1. Which strategy uses a derivative to offset exposure?\n"
                    "A. Mitigate risk.\n"
                    "ANSWER KEY FOR MODULE QUIZZES\n"
                    "Module Quiz 2.1\n"
                    "1. A Derivatives can mitigate risk."
                ),
            ]

    monkeypatch.setattr("exam_prep.ingestion.parsers.PdfReader", FakeReader)

    sections = parser.parse(
        material_id="mat-long-front-matter",
        course_id="course-frm",
        file_name="frm-long-front-matter.pdf",
        content_type="application/pdf",
        data=b"%PDF-fake",
    )

    titles = [section.section_title for section in sections]
    assert any("Module 1.1: Introduction to Risk Management" in title for title in titles)
    assert any("Module 2.1: Corporate Risk Management" in title for title in titles)
    assert all(section.section_title != "Study sections" for section in sections)
    assert not any("FORMULAS ........ 153" in section.text for section in sections)


def test_pdf_parser_one_reading_excerpt_keeps_actual_module_card(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parser = DocumentParser()

    class FakePage:
        def __init__(self, text: str) -> None:
            self._text = text

        def extract_text(self) -> str:
            return self._text

    class FakeReader:
        def __init__(self, *_args, **_kwargs) -> None:
            self.pages = [
                FakePage(
                    "READING 5\n"
                    "Modern Portfolio Theory and CAPM\n"
                    "STUDY SESSION 2\n"
                    "MODULE 5.1: MODERN PORTFOLIO THEORY\n"
                    "LO 5.a: Explain Modern Portfolio Theory and diversification."
                ),
                FakePage(
                    "KEY CONCEPTS\n"
                    "LO 5.a\n"
                    "Diversification can reduce company-specific risk.\n"
                    "MODULE QUIZ 5.1\n"
                    "1. Which risk can diversification reduce?\n"
                    "A. Company-specific risk.\n"
                    "ANSWER KEY FOR MODULE QUIZZES\n"
                    "Module Quiz 5.1\n"
                    "1. A Diversification can reduce company-specific risk."
                ),
            ]

    monkeypatch.setattr("exam_prep.ingestion.parsers.PdfReader", FakeReader)

    sections = parser.parse(
        material_id="mat-one-reading",
        course_id="course-frm",
        file_name="frm-one-reading.pdf",
        content_type="application/pdf",
        data=b"%PDF-fake",
    )

    assert len(sections) == 1
    assert "Reading 5: Modern Portfolio Theory and CAPM" in sections[0].section_title
    assert "Module 5.1: Modern Portfolio Theory" in sections[0].section_title
    assert sections[0].section_title != "Study sections"
    assert "Diversification can reduce company-specific risk." in sections[0].text


def test_pdf_parser_moves_inline_base64_formula_markers_to_formula_assets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parser = DocumentParser()
    inline_payload = "data:image/png;base64," + ("A" * 180)

    class FakePage:
        def __init__(self, text: str) -> None:
            self._text = text

        def extract_text(self) -> str:
            return self._text

    class FakeReader:
        def __init__(self, *_args, **_kwargs) -> None:
            self.pages = [
                FakePage(
                    "READING 1\n"
                    "The Building Blocks of Risk Management\n"
                    "STUDY SESSION 1\n"
                    "MODULE 1.1: INTRODUCTION TO RISK MANAGEMENT\n"
                    "LO 1.a: Explain the concept of risk."
                ),
                FakePage(
                    "KEY CONCEPTS\n"
                    "LO 1.a\n"
                    "Risk is uncertainty surrounding outcomes."
                ),
                FakePage(
                    "FORMULAS\n"
                    "Reading 1\n"
                    f"[FORMULA_IMAGE_CROP page=3 path={inline_payload} label=\"Formula image 1\"]"
                ),
            ]

    monkeypatch.setattr("exam_prep.ingestion.parsers.PdfReader", FakeReader)

    sections = parser.parse(
        material_id="mat-inline-formula",
        course_id="course-frm",
        file_name="inline-formula.pdf",
        content_type="application/pdf",
        data=b"%PDF-fake",
    )

    formula_section = sections[-1]
    assert formula_section.section_title == "Formulas"
    assert inline_payload not in formula_section.text
    assert not any("data:image" in asset.path for asset in formula_section.formula_assets)
    assert formula_section.formula_assets[0].path.startswith("formula-crop://mat-inline-formula/")


def test_pdf_parser_detects_book_agnostic_concept_aliases_and_alpha_modules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parser = DocumentParser()

    class FakePage:
        def __init__(self, text: str) -> None:
            self._text = text

        def extract_text(self) -> str:
            return self._text

    class FakeReader:
        def __init__(self, *_args, **_kwargs) -> None:
            self.pages = [
                FakePage(
                    "READING 11\n"
                    "GARP Code of Conduct\n"
                    "STUDY SESSION 3\n"
                    "MODULE 11.a: PROFESSIONAL STANDARDS\n"
                    "LO 11.a: Explain the GARP Code of Conduct."
                ),
                FakePage(
                    "KEY TAKEAWAYS\n"
                    "LO 11.a\n"
                    "GARP members should act with integrity.\n"
                    "IMPORTANT TERMS\n"
                    "Code of Conduct: a professional standard for risk managers."
                ),
                FakePage(
                    "MODULE 11.b: VIOLATIONS OF THE CODE OF CONDUCT\n"
                    "LO 11.b: Describe consequences of violating the GARP Code of Conduct."
                ),
                FakePage(
                    "SUMMARY\n"
                    "LO 11.b\n"
                    "Violations can lead to disciplinary consequences.\n"
                    "MODULE QUIZ 11.b\n"
                    "1. Which consequence can follow a code violation?\n"
                    "A. Disciplinary action.\n"
                    "ANSWER KEY FOR MODULE QUIZZES\n"
                    "Module Quiz 11.b\n"
                    "1. A Violations can result in disciplinary action."
                ),
            ]

    monkeypatch.setattr("exam_prep.ingestion.parsers.PdfReader", FakeReader)

    sections = parser.parse(
        material_id="mat-alpha-modules",
        course_id="course-frm",
        file_name="frm-code.pdf",
        content_type="application/pdf",
        data=b"%PDF-fake",
    )

    module_11a = next(section for section in sections if "Module 11.a: Professional Standards" in section.section_title)
    module_11b = next(
        section
        for section in sections
        if "Module 11.b: Violations of the Code of Conduct" in section.section_title
    )

    assert "KEY CONCEPTS" in module_11a.text
    assert "LO 11.a" in module_11a.text
    assert "GARP members should act with integrity." in module_11a.text
    assert "Code of Conduct: a professional standard for risk managers." in module_11a.text
    assert "LO 11.b" not in module_11a.text

    assert "KEY CONCEPTS" in module_11b.text
    assert "LO 11.b" in module_11b.text
    assert "Violations can lead to disciplinary consequences." in module_11b.text
    assert "MODULE QUIZ 11.b" in module_11b.text
    assert "ANSWER KEY FOR MODULE QUIZZES" in module_11b.text
    assert "LO 11.a" not in module_11b.text


def test_pdf_parser_backfills_front_learning_objectives_into_reading_modules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parser = DocumentParser()

    class FakePage:
        def __init__(self, text: str) -> None:
            self._text = text

        def extract_text(self) -> str:
            return self._text

    class FakeReader:
        def __init__(self, *_args, **_kwargs) -> None:
            self.pages = [
                FakePage(
                    "Readings and Learning Objectives\n"
                    "STUDY SESSION 2\n"
                    "READING 5\n"
                    "Modern Portfolio Theory and the Capital Asset Pricing Model\n"
                    "MODULE 5.1: MODERN PORTFOLIO THEORY AND THE CAPITAL MARKET LINE\n"
                    "LO 5.a: Explain Modern Portfolio Theory and the Markowitz efficient frontier.\n"
                    "LO 5.b: Define the capital market line.\n"
                    "MODULE 5.2: DERIVING AND APPLYING THE CAPITAL ASSET PRICING MODEL\n"
                    "LO 5.c: Explain the capital asset pricing model.\n"
                    "LO 5.d: Describe the security market line.\n"
                    "MODULE 5.3: PERFORMANCE EVALUATION MEASURES\n"
                    "LO 5.g: Explain risk-adjusted performance measures."
                ),
                FakePage(
                    "READING 5\n"
                    "Modern Portfolio Theory and the Capital Asset Pricing Model\n"
                    "STUDY SESSION 2\n"
                    "MODULE 5.1: MODERN PORTFOLIO THEORY AND THE CAPITAL MARKET LINE\n"
                    "LO 5.b: Define the capital market line."
                ),
                FakePage(
                    "KEY CONCEPTS\n"
                    "LO 5.a\n"
                    "Modern Portfolio Theory explains efficient combinations of risky assets.\n"
                    "LO 5.b\n"
                    "The capital market line combines the risk-free asset with the market portfolio.\n"
                    "LO 5.c\n"
                    "The capital asset pricing model links expected return to beta.\n"
                    "LO 5.d\n"
                    "The security market line plots expected return against systematic risk.\n"
                    "LO 5.g\n"
                    "Performance evaluation measures compare return with risk taken."
                ),
                FakePage(
                    "MODULE 5.2: DERIVING AND APPLYING THE CAPITAL ASSET PRICING MODEL\n"
                    "LO 5.c: Explain the capital asset pricing model."
                ),
                FakePage(
                    "MODULE 5.3: PERFORMANCE EVALUATION MEASURES\n"
                    "LO 5.g: Explain risk-adjusted performance measures."
                ),
            ]

    monkeypatch.setattr("exam_prep.ingestion.parsers.PdfReader", FakeReader)

    sections = parser.parse(
        material_id="mat-front-lo-backfill",
        course_id="course-frm",
        file_name="frm-book.pdf",
        content_type="application/pdf",
        data=b"%PDF-fake",
    )

    module_51 = next(
        section
        for section in sections
        if section.section_title.endswith("Module 5.1: Modern Portfolio Theory and the Capital Market Line")
    )
    module_52 = next(
        section
        for section in sections
        if section.section_title.endswith("Module 5.2: Deriving and Applying the Capital Asset Pricing Model")
    )
    module_53 = next(
        section
        for section in sections
        if section.section_title.endswith("Module 5.3: Performance Evaluation Measures")
    )

    assert "LEARNING OBJECTIVES" in module_51.text
    assert "LO 5.a: Explain Modern Portfolio Theory and the Markowitz efficient frontier." in module_51.text
    assert "LO 5.b: Define the capital market line." in module_51.text
    assert "LO 5.a" in module_51.text
    assert "Modern Portfolio Theory explains efficient combinations of risky assets." in module_51.text

    assert "LO 5.c: Explain the capital asset pricing model." in module_52.text
    assert "LO 5.d: Describe the security market line." in module_52.text
    assert "LO 5.g" not in module_52.text

    assert "LO 5.g: Explain risk-adjusted performance measures." in module_53.text


def test_pdf_parser_keeps_single_module_reading_with_front_learning_objectives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parser = DocumentParser()

    class FakePage:
        def __init__(self, text: str) -> None:
            self._text = text

        def extract_text(self) -> str:
            return self._text

    class FakeReader:
        def __init__(self, *_args, **_kwargs) -> None:
            self.pages = [
                FakePage(
                    "Readings and Learning Objectives\n"
                    "STUDY SESSION 3\n"
                    "READING 11\n"
                    "GARP Code of Conduct\n"
                    "MODULE 11.1: GARP CODE OF CONDUCT\n"
                    "LO 11.a: Describe the responsibility of GARP members.\n"
                    "LO 11.b: Describe the potential consequences of violating the GARP Code of Conduct."
                ),
                FakePage(
                    "READING 11\n"
                    "GARP Code of Conduct\n"
                    "STUDY SESSION 3\n"
                    "MODULE 11.1: GARP CODE OF CONDUCT\n"
                    "MODULE QUIZ 11.1\n"
                    "1. Which behavior is required by the GARP Code?\n"
                    "A. Acting with integrity."
                ),
                FakePage(
                    "ANSWER KEY FOR MODULE QUIZZES\n"
                    "Module Quiz 11.1\n"
                    "1. A GARP members must act honestly and professionally."
                ),
            ]

    monkeypatch.setattr("exam_prep.ingestion.parsers.PdfReader", FakeReader)

    sections = parser.parse(
        material_id="mat-reading-11-front-lo",
        course_id="course-frm",
        file_name="frm-book.pdf",
        content_type="application/pdf",
        data=b"%PDF-fake",
    )

    module_111 = next(section for section in sections if "Module 11.1: GARP Code of Conduct" in section.section_title)

    assert "LEARNING OBJECTIVES" in module_111.text
    assert "LO 11.a: Describe the responsibility of GARP members." in module_111.text
    assert (
        "LO 11.b: Describe the potential consequences of violating the GARP Code of Conduct."
        in module_111.text
    )
    assert "MODULE QUIZ 11.1" in module_111.text
    assert "ANSWER KEY FOR MODULE QUIZZES" in module_111.text


def test_pdf_parser_preserves_body_learning_objective_content_for_single_module_reading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parser = DocumentParser()

    class FakePage:
        def __init__(self, text: str) -> None:
            self._text = text

        def extract_text(self) -> str:
            return self._text

    class FakeReader:
        def __init__(self, *_args, **_kwargs) -> None:
            self.pages = [
                FakePage(
                    "READING 11\n"
                    "GARP Code of Conduct\n"
                    "STUDY SESSION 3\n"
                    "MODULE 11.1: GARP CODE OF CONDUCT\n"
                    "The Code of Conduct contains principles for financial risk management practices.\n"
                    "LO 11.a: Describe the responsibility of each GARP Member with respect to "
                    "professional integrity, ethical conduct, conflicts of interest, confidentiality.\n"
                    "Members must act with integrity, competence, diligence, respect, and in an ethical manner.\n"
                    "Members must maintain confidentiality and disclose conflicts of interest."
                ),
                FakePage(
                    "Violations of the Code of Conduct\n"
                    "LO 11.b: Describe the potential consequences of violating the GARP Code of Conduct.\n"
                    "Violations may lead to sanctions, suspension, revocation of membership, or referral to regulators.\n"
                ),
            ]

    monkeypatch.setattr("exam_prep.ingestion.parsers.PdfReader", FakeReader)

    sections = parser.parse(
        material_id="mat-reading-11-body-lo",
        course_id="course-frm",
        file_name="frm-book.pdf",
        content_type="application/pdf",
        data=b"%PDF-fake",
    )

    module_111 = next(section for section in sections if "Module 11.1: GARP Code of Conduct" in section.section_title)

    assert "LO 11.a: Describe the responsibility of each GARP Member" in module_111.text
    assert "Members must act with integrity, competence, diligence, respect" in module_111.text
    assert "Members must maintain confidentiality and disclose conflicts of interest." in module_111.text
    assert "LO 11.b: Describe the potential consequences of violating the GARP Code of Conduct." in module_111.text
    assert "Violations may lead to sanctions, suspension, revocation of membership" in module_111.text


def test_pdf_parser_creates_final_formula_session_from_formula_image_markers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parser = DocumentParser()

    class FakePage:
        def __init__(self, text: str) -> None:
            self._text = text

        def extract_text(self) -> str:
            return self._text

    class FakeReader:
        def __init__(self, *_args, **_kwargs) -> None:
            self.pages = [
                FakePage(
                    "READING 1\n"
                    "The Building Blocks of Risk Management\n"
                    "STUDY SESSION 1\n"
                    "MODULE 1.1: INTRODUCTION TO RISK MANAGEMENT\n"
                    "LO 1.a: Explain the concept of risk."
                ),
                FakePage(
                    "KEY CONCEPTS\n"
                    "LO 1.a\n"
                    "Risk is uncertainty surrounding outcomes."
                ),
                FakePage(
                    "FORMULA SHEET\n"
                    "Reading 1\n"
                    "[FORMULA_IMAGE_CROP page=3 path=formula-crop://mat-formula-crop/page-3-image-1.png label=\"Formula image 1\"]"
                ),
            ]

    monkeypatch.setattr("exam_prep.ingestion.parsers.PdfReader", FakeReader)

    sections = parser.parse(
        material_id="mat-formula-crop",
        course_id="course-frm",
        file_name="formula-crop.pdf",
        content_type="application/pdf",
        data=b"%PDF-fake",
    )

    module_11 = next(section for section in sections if "Module 1.1" in section.section_title)
    assert "FORMULA SHEET" not in module_11.text
    assert "[FORMULA_IMAGE_CROP" not in module_11.text

    formula_section = sections[-1]
    assert formula_section.section_title == "Formulas"
    assert formula_section.locator.page_number == 3
    assert formula_section.text.startswith("FORMULAS")
    assert "Reading 1" in formula_section.text
    assert "[FORMULA_IMAGE_CROP" not in formula_section.text
    assert "formula-crop://" not in formula_section.text
    assert len(formula_section.formula_assets) == 1
    assert formula_section.formula_assets[0].source_page == 3
    assert formula_section.formula_assets[0].path == "formula-crop://mat-formula-crop/page-3-image-1.png"
    assert formula_section.formula_assets[0].label == "Formula image 1"
    assert formula_section.formula_assets[0].reading_number == 1


def test_pdf_parser_stops_formula_appendix_before_appendix_reference_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parser = DocumentParser()

    class FakePage:
        def __init__(self, text: str) -> None:
            self._text = text

        def extract_text(self) -> str:
            return self._text

    class FakeReader:
        def __init__(self, *_args, **_kwargs) -> None:
            self.pages = [
                FakePage(
                    "READING 12\n"
                    "Hypothesis Testing\n"
                    "STUDY SESSION 4\n"
                    "MODULE 12.1: HYPOTHESIS TESTS AND CONFIDENCE INTERVALS\n"
                    "LO 12.a: Explain hypothesis testing."
                ),
                FakePage(
                    "FORMULAS\n"
                    "Reading 12\n"
                    "test statistic: t = (sample mean - hypothesized mean) / standard error\n"
                    "[FORMULA_IMAGE_CROP page=2 path=formula-crop://mat-formula-end/page-2-image-1.png label=\"Formula image 1\"]"
                ),
                FakePage(
                    "APPENDIX\n"
                    "USING THE CUMULATIVE Z-TABLE\n"
                    "The Significance Level\n"
                    "If Epsilon is selected from the table, use the normal distribution reference."
                ),
                FakePage("INDEX\nHypothesis testing, 12\nSignificance level, 14"),
            ]

    monkeypatch.setattr("exam_prep.ingestion.parsers.PdfReader", FakeReader)

    sections = parser.parse(
        material_id="mat-formula-end",
        course_id="course-frm",
        file_name="formula-end.pdf",
        content_type="application/pdf",
        data=b"%PDF-fake",
    )

    formula_section = sections[-1]
    assert formula_section.section_title == "Formulas"
    assert formula_section.locator.page_number == 2
    assert formula_section.text.startswith("FORMULAS")
    assert "Reading 12" in formula_section.text
    assert "test statistic" in formula_section.text
    assert "APPENDIX" not in formula_section.text
    assert "USING THE CUMULATIVE Z-TABLE" not in formula_section.text
    assert "The Significance Level" not in formula_section.text
    assert "If Epsilon" not in formula_section.text
    assert len(formula_section.formula_assets) == 1
    assert formula_section.formula_assets[0].source_page == 2


def test_pdf_parser_moves_formula_crop_markers_out_of_module_section_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parser = DocumentParser()

    class FakePage:
        def __init__(self, text: str) -> None:
            self._text = text

        def extract_text(self) -> str:
            return self._text

    class FakeReader:
        def __init__(self, *_args, **_kwargs) -> None:
            self.pages = [
                FakePage(
                    "READING 1\n"
                    "The Building Blocks of Risk Management\n"
                    "STUDY SESSION 1\n"
                    "MODULE 1.1: INTRODUCTION TO RISK MANAGEMENT\n"
                    "LO 1.a: Explain the concept of risk."
                ),
                FakePage(
                    "KEY CONCEPTS\n"
                    "LO 1.a\n"
                    "Risk is uncertainty surrounding outcomes.\n"
                    "[FORMULA_IMAGE_CROP page=2 path=formula-crop://mat-module-crop/page-2-image-1.png label=\"Formula image 1\"]"
                ),
            ]

    monkeypatch.setattr("exam_prep.ingestion.parsers.PdfReader", FakeReader)

    sections = parser.parse(
        material_id="mat-module-crop",
        course_id="course-frm",
        file_name="module-crop.pdf",
        content_type="application/pdf",
        data=b"%PDF-fake",
    )

    module_11 = next(section for section in sections if "Module 1.1" in section.section_title)

    assert "Risk is uncertainty surrounding outcomes." in module_11.text
    assert "[FORMULA_IMAGE_CROP" not in module_11.text
    assert "formula-crop://" not in module_11.text
    assert len(module_11.formula_assets) == 1
    assert module_11.formula_assets[0].source_page == 2
    assert module_11.formula_assets[0].path == "formula-crop://mat-module-crop/page-2-image-1.png"
    assert module_11.formula_assets[0].label == "Formula image 1"


def test_pdf_parser_preserves_formula_page_crop_when_layout_has_no_image_blocks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    parser = DocumentParser(formula_asset_base_path=tmp_path)

    class FakePixmap:
        def save(self, path: str) -> None:
            with open(path, "wb") as handle:
                handle.write(b"formula-page-png")

    class FakePage:
        rect = (0, 0, 612, 792)
        pixmap_kwargs = None

        def get_text(self, _format: str = "text"):
            if _format == "dict":
                return {
                    "blocks": [
                        {
                            "type": 0,
                            "bbox": (72, 80, 540, 260),
                            "lines": [
                                {
                                    "spans": [
                                        {"text": "FORMULAS"},
                                        {"text": "Reading 5"},
                                        {"text": "capital market line"},
                                    ]
                                }
                            ],
                        }
                    ]
                }
            return "FORMULAS\nReading 5\ncapital market line"

        def get_pixmap(self, **kwargs):
            self.pixmap_kwargs = kwargs
            return FakePixmap()

    fake_page = FakePage()
    markers = parser._formula_layout_crop_markers(
        page=fake_page,
        page_number=153,
        lines=["FORMULAS", "Reading 5", "capital market line"],
        material_id="mat-formulas",
        force=True,
    )

    assert len(markers) == 1
    assert markers[0].startswith("[FORMULA_IMAGE_CROP page=153 path=formula-crop://mat-formulas/page-153-full-1.png")
    assert 'label="Formula page crop"' in markers[0]
    saved_crop = tmp_path / "mat-formulas" / "formula-crops" / "page-153-full-1.png"
    assert saved_crop.read_bytes() == b"formula-page-png"
    assert fake_page.pixmap_kwargs is not None
    assert "matrix" in fake_page.pixmap_kwargs


def test_pdf_parser_preserves_formula_crop_without_blocking_on_ocr(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    parser = DocumentParser(formula_asset_base_path=tmp_path)

    def fail_if_ocr_runs(_path):
        raise AssertionError("Formula OCR must not block ingestion by default.")

    monkeypatch.setattr(parser, "_ocr_formula_crop_file", fail_if_ocr_runs, raising=False)

    class FakePixmap:
        def save(self, path: str) -> None:
            with open(path, "wb") as handle:
                handle.write(b"formula-page-png")

    class FakePage:
        rect = (0, 0, 612, 792)

        def get_text(self, _format: str = "text", **_kwargs):
            if _format == "dict":
                return {"blocks": []}
            return "FORMULAS\nReading 5"

        def get_pixmap(self, **_kwargs):
            return FakePixmap()

    markers = parser._formula_layout_crop_markers(
        page=FakePage(),
        page_number=158,
        lines=["FORMULAS", "Reading 5"],
        material_id="mat-no-blocking-ocr",
        force=True,
    )

    assert markers == [
        '[FORMULA_IMAGE_CROP page=158 path=formula-crop://mat-no-blocking-ocr/page-158-full-1.png label="Formula page crop"]'
    ]
    metadata_path = tmp_path / "mat-no-blocking-ocr" / "formula-crops" / "page-158-full-1.json"
    assert metadata_path.exists()
    assert "OCR disabled during ingestion" in metadata_path.read_text(encoding="utf-8")


def test_pdf_parser_writes_formula_crop_ocr_latex_sidecar(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    parser = DocumentParser(formula_asset_base_path=tmp_path, enable_formula_ocr=True)

    monkeypatch.setattr(
        parser,
        "_ocr_formula_crop_file",
        lambda _path: {
            "engine": "test-ocr",
            "text": "expected loss: EL = EAD × PD × LGD",
            "latex_blocks": [r"EL = EAD \times PD \times LGD"],
            "confidence": 0.93,
            "error": None,
        },
        raising=False,
    )

    class FakePixmap:
        def save(self, path: str) -> None:
            with open(path, "wb") as handle:
                handle.write(b"formula-page-png")

    class FakePage:
        rect = (0, 0, 640, 480)

        def get_text(self, mode: str) -> dict[str, object] | str:
            if mode == "dict":
                return {"blocks": []}
            return "FORMULAS\nReading 1\nexpected loss"

        def get_pixmap(self, **_kwargs):
            return FakePixmap()

    markers = parser._formula_layout_crop_markers(
        page=FakePage(),
        page_number=153,
        lines=["FORMULAS", "Reading 1", "expected loss"],
        material_id="mat-formula-ocr",
        force=True,
    )

    assert len(markers) == 1
    metadata_path = tmp_path / "mat-formula-ocr" / "formula-crops" / "page-153-full-1.json"
    assert metadata_path.exists()

    asset = parser._formula_asset_from_marker(
        markers[0],
        material_id="mat-formula-ocr",
        reading_number=1,
    )

    assert asset is not None
    assert asset.extracted_text == "expected loss: EL = EAD × PD × LGD"
    assert asset.extracted_latex == r"\text{expected loss}: EL = EAD \times PD \times LGD"
    assert asset.extracted_latex_blocks == [r"EL = EAD \times PD \times LGD"]
    assert asset.ocr_engine == "test-ocr"
    assert asset.ocr_confidence == 0.93
    assert asset.needs_review is False


def test_formula_crop_metadata_semantically_corrects_reading_1_formula_sheet_crop(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    parser = DocumentParser(formula_asset_base_path=tmp_path, enable_formula_ocr=True)
    crop_path = tmp_path / "mat-formula-semantic" / "formula-crops" / "page-158-image-3.png"
    crop_path.parent.mkdir(parents=True)
    crop_path.write_bytes(b"fake-image")

    monkeypatch.setattr(
        parser,
        "_ocr_formula_crop_file",
        lambda _path: {
            "engine": "pix2tex",
            "text": (
                r"\begin{array}{l}{\exp\mathrm{expected~loss.~EL}=\mathrm{EAD}\times"
                r"\mathrm{PD}\times\mathrm{ED}}\\ {\mathrm{risk}\mathrm{stadjusted~return~on~capital}}\\"
                r"{\mathrm{RAROC=after.tax~risk.~alpusted~expected~recurn}\ /\mathrm{economic~capital}}\end{array}"
            ),
            "latex": (
                r"\begin{array}{l}{\exp\mathrm{expected~loss.~EL}=\mathrm{EAD}\times"
                r"\mathrm{PD}\times\mathrm{ED}}\\ {\mathrm{risk}\mathrm{stadjusted~return~on~capital}}\\"
                r"{\mathrm{RAROC=after.tax~risk.~alpusted~expected~recurn}\ /\mathrm{economic~capital}}\end{array}"
            ),
            "latex_blocks": [
                r"\begin{array}{l}{\exp\mathrm{expected~loss.~EL}=\mathrm{EAD}\times\mathrm{PD}\times\mathrm{ED}}\end{array}"
            ],
            "confidence": 0.82,
            "error": None,
        },
        raising=False,
    )

    metadata = parser._formula_crop_metadata_for_file(crop_path, pdf_text_hint="")

    assert metadata["ocr_engine"] == "semantic_formula_sheet+pix2tex"
    assert metadata["ocr_confidence"] == 0.98
    assert metadata["needs_review"] is False
    assert metadata["extracted_text"] == (
        "expected loss: EL = EAD × PD × LGD\n"
        "risk-adjusted return on capital: RAROC = after-tax risk-adjusted expected return / economic capital"
    )
    assert metadata["extracted_latex_blocks"] == [
        r"\text{expected loss}: EL = EAD \times PD \times LGD",
        r"\text{risk-adjusted return on capital}: RAROC = "
        r"\frac{\text{after-tax risk-adjusted expected return}}{\text{economic capital}}",
    ]


def test_formula_crop_metadata_semantically_corrects_observed_reading_1_ocr_noise(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    parser = DocumentParser(formula_asset_base_path=tmp_path, enable_formula_ocr=True)
    crop_path = tmp_path / "mat-formula-semantic" / "formula-crops" / "page-158-image-3.png"
    crop_path.parent.mkdir(parents=True)
    crop_path.write_bytes(b"fake-image")

    monkeypatch.setattr(
        parser,
        "_ocr_formula_crop_file",
        lambda _path: {
            "engine": "pix2tex",
            "text": (
                r"\begin{array}{l}{\exp\mathrm{\bf{expected~loss.~EL}}={\bf E A D}\times"
                r"{\bf P D}\times{\bf E D}}\\ {\mathrm{\bf{risk}}\mathrm{\bf{sked~returnon~capital}}.}\\"
                r"{\mathrm{\bf{RAGOC}}=\mathrm{\bf{after.tar~risk.}}\mathrm{\bf{expected~recturn~}}/"
                r"\mathrm{\bf{expected~recapral~reconomic~capital}}.}\end{array}"
            ),
            "latex": r"\mathrm{RAGOC}",
            "latex_blocks": [r"\mathrm{RAGOC}"],
            "confidence": 0.82,
            "error": None,
        },
        raising=False,
    )

    metadata = parser._formula_crop_metadata_for_file(crop_path, pdf_text_hint="")

    assert metadata["ocr_engine"] == "semantic_formula_sheet+pix2tex"
    assert metadata["extracted_latex_blocks"] == [
        r"\text{expected loss}: EL = EAD \times PD \times LGD",
        r"\text{risk-adjusted return on capital}: RAROC = "
        r"\frac{\text{after-tax risk-adjusted expected return}}{\text{economic capital}}",
    ]


def test_formula_crop_metadata_semantically_corrects_split_expected_reading_1_ocr_noise(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    parser = DocumentParser(formula_asset_base_path=tmp_path, enable_formula_ocr=True)
    crop_path = tmp_path / "mat-formula-semantic" / "formula-crops" / "page-158-image-3.png"
    crop_path.parent.mkdir(parents=True)
    crop_path.write_bytes(b"fake-image")

    monkeypatch.setattr(
        parser,
        "_ocr_formula_crop_file",
        lambda _path: {
            "engine": "pix2tex",
            "text": (
                r"\begin{array}{c}{{\exp\mathrm{ected~loss.~EL}=\mathrm{EAD}\times"
                r"\mathrm{PD}\times\mathrm{EOD}}}\\"
                r"{{\mathrm{risk}\mathrm{sadjusted~return~on~capital}\cdot\mathrm{}}}\\"
                r"{{\mathrm{RAROC=after.tax~risk.adjusted~expected~recurn~}/"
                r"\mathrm{economic~capital}}}\end{array}"
            ),
            "latex": r"\exp\mathrm{ected~loss}",
            "latex_blocks": [r"\exp\mathrm{ected~loss}"],
            "confidence": 0.82,
            "error": None,
        },
        raising=False,
    )

    metadata = parser._formula_crop_metadata_for_file(crop_path, pdf_text_hint="")

    assert metadata["ocr_engine"] == "semantic_formula_sheet+pix2tex"
    assert metadata["extracted_text"] == (
        "expected loss: EL = EAD × PD × LGD\n"
        "risk-adjusted return on capital: RAROC = after-tax risk-adjusted expected return / economic capital"
    )


def test_formula_crop_metadata_semantically_corrects_reading_5_dense_formula_sheet_crop(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    parser = DocumentParser(formula_asset_base_path=tmp_path, enable_formula_ocr=True)
    crop_path = tmp_path / "mat-formula-semantic" / "formula-crops" / "page-158-image-5.png"
    crop_path.parent.mkdir(parents=True)
    crop_path.write_bytes(b"fake-image")

    monkeypatch.setattr(
        parser,
        "_ocr_formula_crop_file",
        lambda _path: {
            "engine": "pix2tex",
            "text": (
                r"\begin{array}{r}{\mathrm{capital~market~ine;}}\\"
                r"{\mathrm{E}\left(\mathbf{R}_{\mathrm{p}}\right)=\mathrm{R}_{\mathrm{F}}"
                r"+\left[{\frac{E\left(\mathrm{R}_{\mathrm{M}}\right)-\mathrm{R}_{\mathrm{F}}}{\sigma_M}}\right]\sigma_P}\\"
                r"{\mathrm{capital~asset~pricing~model}}\\{\mathrm{Sharpe~measure}}\\"
                r"{\mathrm{Treynor~measure}}\\{\mathrm{Jensen's~alpha}}\\"
                r"{\mathrm{tracking~error}}\\{\mathrm{information~ratio}}\\{\mathrm{Sortino~ratio}}\end{array}"
            ),
            "latex": r"\mathrm{capital~market~ine}",
            "latex_blocks": [r"\mathrm{capital~market~ine}"],
            "confidence": 0.82,
            "error": None,
        },
        raising=False,
    )

    metadata = parser._formula_crop_metadata_for_file(crop_path, pdf_text_hint="")

    assert metadata["ocr_engine"] == "semantic_formula_sheet+pix2tex"
    assert metadata["ocr_confidence"] == 0.98
    assert metadata["needs_review"] is False
    latex_blocks = metadata["extracted_latex_blocks"]
    assert r"\text{capital market line}: E(R_P) = R_F + \left[\frac{E(R_M)-R_F}{\sigma_M}\right]\sigma_P" in latex_blocks
    assert r"\text{capital asset pricing model}: E(R_i) = R_F + [E(R_M)-R_F]\beta_i" in latex_blocks
    assert r"\text{Sortino ratio}: \frac{R_P-R_{MIN}}{\text{downside deviation}}" in latex_blocks
    assert len(latex_blocks) == 9


def test_formula_crop_metadata_semantically_corrects_reading_6_formula_sheet_crop(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    parser = DocumentParser(formula_asset_base_path=tmp_path, enable_formula_ocr=True)
    crop_path = tmp_path / "mat-formula-semantic" / "formula-crops" / "page-159-image-2.png"
    crop_path.parent.mkdir(parents=True)
    crop_path.write_bytes(b"fake-image")

    monkeypatch.setattr(
        parser,
        "_ocr_formula_crop_file",
        lambda _path: {
            "engine": "pix2tex",
            "text": (
                r"\begin{array}{c}{{\mathrm{aribitrage~prag.~flacory.}}}\\"
                r"{{\mathrm{E(R_{i})=R_{F}+\left|j_{1}R P_{1}+j_{2}R P_{2}+j_{3}R P_{3}+e_i}}}\\"
                r"{{\mathrm{Fama-French~three-factor~model}}}\end{array}"
            ),
            "latex": r"\mathrm{aribitrage~prag.~flacory}",
            "latex_blocks": [r"\mathrm{aribitrage~prag.~flacory}"],
            "confidence": 0.82,
            "error": None,
        },
        raising=False,
    )

    metadata = parser._formula_crop_metadata_for_file(crop_path, pdf_text_hint="")

    assert metadata["ocr_engine"] == "semantic_formula_sheet+pix2tex"
    assert metadata["ocr_confidence"] == 0.98
    assert metadata["needs_review"] is False
    latex_blocks = metadata["extracted_latex_blocks"]
    assert r"\text{arbitrage pricing theory}: E(R_i) = R_F + \beta_1 RP_1 + \beta_2 RP_2 + \beta_3 RP_3 + e_i" in latex_blocks
    assert r"\text{Fama-French three-factor model}: E(R_i) = R_F + \beta_{i,M}RP_M + \beta_{i,SMB}F_{SMB} + \beta_{i,HML}F_{HML} + e_i" in latex_blocks
    assert len(latex_blocks) == 2


def test_formula_crop_metadata_semantically_corrects_observed_reading_6_ocr_noise(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    parser = DocumentParser(formula_asset_base_path=tmp_path, enable_formula_ocr=True)
    crop_path = tmp_path / "mat-formula-semantic" / "formula-crops" / "page-159-image-2.png"
    crop_path.parent.mkdir(parents=True)
    crop_path.write_bytes(b"fake-image")

    monkeypatch.setattr(
        parser,
        "_ocr_formula_crop_file",
        lambda _path: {
            "engine": "pix2tex",
            "text": (
                r"\begin{array}{c}{{\mathrm{arpitrage~prag.~flacory:}}}\\"
                r"{{\mathrm{E(R_{i})=R_{F}+\left|j_{1}R P_{1}+\delta_{2}R P_{2}+\delta_{3}R P_{3}+\epsilon_{i}~}}}\\"
                r"{{\mathrm{wheres~prensitwmasitiwn~sitwetarator~i~factor~}i}}\\"
                r"{{\mathrm{Fammazfrench~rharee~ractor~inath~risk~factor~}i}}\\"
                r"{{\mathrm{FamnzFrench~flnee~ractor~inactor~isith~risk~factor~is}}}\end{array}"
            ),
            "latex": r"\mathrm{arpitrage~prag.~flacory}",
            "latex_blocks": [r"\mathrm{arpitrage~prag.~flacory}"],
            "confidence": 0.82,
            "error": None,
        },
        raising=False,
    )

    metadata = parser._formula_crop_metadata_for_file(crop_path, pdf_text_hint="")

    assert metadata["ocr_engine"] == "semantic_formula_sheet+pix2tex"
    latex_blocks = metadata["extracted_latex_blocks"]
    assert r"\text{arbitrage pricing theory}: E(R_i) = R_F + \beta_1 RP_1 + \beta_2 RP_2 + \beta_3 RP_3 + e_i" in latex_blocks
    assert r"\text{Fama-French three-factor model}: E(R_i) = R_F + \beta_{i,M}RP_M + \beta_{i,SMB}F_{SMB} + \beta_{i,HML}F_{HML} + e_i" in latex_blocks


def test_pdf_parser_builds_module_sections_from_only_exact_exam_blocks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parser = DocumentParser()

    class FakePage:
        def __init__(self, text: str) -> None:
            self._text = text

        def extract_text(self) -> str:
            return self._text

    class FakeReader:
        def __init__(self, *_args, **_kwargs) -> None:
            self.pages = [
                FakePage(
                    "READING 2\n"
                    "How Do Firms Manage Financial Risk?\n"
                    "STUDY SESSION 1\n"
                    "EXAM FOCUS\n"
                    "This reading-level focus paragraph should not become module source text.\n"
                    "MODULE 2.1: CORPORATE RISK MANAGEMENT\n"
                    "LO 2.a: Describe risk management strategies.\n"
                    "LO 2.b: Explain risk appetite.\n"
                    "MODULE 2.2: RISK MANAGEMENT METHODS AND INSTRUMENTS\n"
                    "LO 2.c: Describe hedging instruments."
                ),
                FakePage(
                    "KEY CONCEPTS\n"
                    "LO 2.a\n"
                    "Firms can accept, avoid, mitigate, or transfer risk.\n"
                    "LO 2.b\n"
                    "Risk appetite is the willingness to retain risk.\n"
                    "LO 2.c\n"
                    "Hedging instruments transfer specific financial risks."
                ),
                FakePage(
                    "MODULE QUIZ 2.1\n"
                    "1. Which risk strategy uses a derivative to offset exposure?\n"
                    "A. Transfer risk.\n"
                    "MODULE QUIZ 2.2\n"
                    "1. Which instrument is used to hedge currency exposure?\n"
                    "A. Forward contract."
                ),
                FakePage(
                    "ANSWER KEY FOR MODULE QUIZZES\n"
                    "MODULE QUIZ 2.1\n"
                    "1. A Using a derivative transfers risk to another counterparty. (LO 2.a)\n"
                    "MODULE QUIZ 2.2\n"
                    "1. A Forward contracts can hedge currency exposure. (LO 2.c)"
                ),
            ]

    monkeypatch.setattr("exam_prep.ingestion.parsers.PdfReader", FakeReader)

    sections = parser.parse(
        material_id="mat-frm-exact-blocks",
        course_id="course-frm",
        file_name="frm-book.pdf",
        content_type="application/pdf",
        data=b"%PDF-fake",
    )

    module_21 = sections[0]
    module_22 = sections[1]

    assert module_21.section_title.endswith("Module 2.1: Corporate Risk Management")
    assert "EXAM FOCUS" not in module_21.text
    assert "This reading-level focus paragraph" not in module_21.text
    assert "LO 2.a" in module_21.text
    assert "LO 2.b" in module_21.text
    assert "LO 2.c" not in module_21.text
    assert "MODULE QUIZ 2.1" in module_21.text
    assert "MODULE QUIZ 2.2" not in module_21.text
    assert "Using a derivative transfers risk" in module_21.text
    assert "Forward contracts can hedge currency exposure" not in module_21.text

    assert module_22.section_title.endswith("Module 2.2: Risk Management Methods and Instruments")
    assert "EXAM FOCUS" not in module_22.text
    assert "LO 2.c" in module_22.text
    assert "LO 2.a" not in module_22.text
    assert "MODULE QUIZ 2.2" in module_22.text
    assert "MODULE QUIZ 2.1" not in module_22.text
    assert "Forward contracts can hedge currency exposure" in module_22.text
    assert "Using a derivative transfers risk" not in module_22.text


def test_pdf_parser_accepts_singular_workbook_answer_key_heading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parser = DocumentParser()

    class FakePage:
        def __init__(self, text: str) -> None:
            self._text = text

        def extract_text(self) -> str:
            return self._text

    class FakeReader:
        def __init__(self, *_args, **_kwargs) -> None:
            self.pages = [
                FakePage(
                    "READING 10\n"
                    "Anatomy of the Great Financial Crisis of 2007-2009\n"
                    "STUDY SESSION 3\n"
                    "EXAM FOCUS\n"
                    "This reading covers the global financial crisis.\n"
                    "MODULE 10.1: GLOBAL FINANCIAL CRISIS\n"
                    "LO 10.a: Explain the buildup to the financial crisis.\n"
                    "KEY CONCEPTS\n"
                    "LO 10.a\n"
                    "Easy access to credit fueled a rapid increase in house prices.\n"
                    "MODULE QUIZ 10.1\n"
                    "1. Which factor contributed to the financial crisis?\n"
                    "A. Originate-to-distribute incentives."
                ),
                FakePage(
                    "ANSWER KEY FOR MODULE QUIZ\n"
                    "MODULE QUIZ 10.1\n"
                    "1. A The originate-to-distribute model relaxed lending standards. (LO 10.a)"
                ),
            ]

    monkeypatch.setattr("exam_prep.ingestion.parsers.PdfReader", FakeReader)

    sections = parser.parse(
        material_id="mat-frm-singular-answer-key",
        course_id="course-frm",
        file_name="frm-book.pdf",
        content_type="application/pdf",
        data=b"%PDF-fake",
    )

    assert len(sections) == 1
    assert sections[0].section_title.endswith("Module 10.1: Global Financial Crisis")
    assert "ANSWER KEY FOR MODULE QUIZZES" in sections[0].text
    assert "originate-to-distribute model relaxed lending standards" in sections[0].text.lower()


def test_pdf_parser_uses_quiz_lo_evidence_for_modules_without_body_lo_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parser = DocumentParser()

    class FakePage:
        def __init__(self, text: str) -> None:
            self._text = text

        def extract_text(self) -> str:
            return self._text

    class FakeReader:
        def __init__(self, *_args, **_kwargs) -> None:
            self.pages = [
                FakePage(
                    "READING 7\n"
                    "Principles for Effective Data Aggregation and Risk Reporting\n"
                    "STUDY SESSION 2\n"
                    "EXAM FOCUS\n"
                    "This reading covers risk data aggregation principles.\n"
                    "MODULE 7.1: DATA QUALITY, GOVERNANCE, AND INFRASTRUCTURE\n"
                    "LO 7.a: Describe benefits of effective risk data aggregation.\n"
                    "MODULE 7.2: RISK DATA AGGREGATION AND REPORTING CAPABILITIES\n"
                    "Principle 3 requires accuracy and integrity.\n"
                    "Principle 4 requires completeness."
                ),
                FakePage(
                    "MODULE QUIZ 7.2\n"
                    "1. Which principle requires adaptable data?\n"
                    "A. Principle 6.\n"
                    "ANSWER KEY FOR MODULE QUIZZES\n"
                    "MODULE QUIZ 7.2\n"
                    "1. A Principle 6 requires adaptable data capabilities. (LO 7.d)"
                ),
                FakePage(
                    "KEY CONCEPTS\n"
                    "LO 7.a\n"
                    "Effective risk data aggregation helps managers anticipate problems.\n"
                    "LO 7.d\n"
                    "Principles 3-6 specify standards for accurate, complete, timely, and adaptable data."
                ),
            ]

    monkeypatch.setattr("exam_prep.ingestion.parsers.PdfReader", FakeReader)

    sections = parser.parse(
        material_id="mat-frm-lo-evidence",
        course_id="course-frm",
        file_name="frm-book.pdf",
        content_type="application/pdf",
        data=b"%PDF-fake",
    )

    module_71 = sections[0]
    module_72 = sections[1]

    assert module_71.section_title.endswith("Module 7.1: Data Quality, Governance, and Infrastructure")
    assert module_72.section_title.endswith("Module 7.2: Risk Data Aggregation and Reporting Capabilities")
    assert "Effective risk data aggregation helps managers anticipate problems" in module_71.text
    assert "Principles 3-6 specify standards" not in module_71.text
    assert "Principles 3-6 specify standards" in module_72.text
    assert "Effective risk data aggregation helps managers anticipate problems" not in module_72.text


def test_pdf_parser_uses_hard_workbook_boundaries_not_contents_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parser = DocumentParser()

    class FakePage:
        def __init__(self, text: str) -> None:
            self._text = text

        def extract_text(self) -> str:
            return self._text

    class FakeReader:
        def __init__(self, *_args, **_kwargs) -> None:
            self.pages = [
                FakePage(
                    "WELCOME TO THE 2025 SCHWESERNOTES\n"
                    "This introduction explains the resources included with the SchweserNotes.\n"
                    "Practice Questions and Mock Exams are available online."
                ),
                FakePage(
                    "CONTENTS\n"
                    "Readings and Learning Objectives\n"
                    "STUDY SESSION 1-Risk Management Overview\n"
                    "READING 1\n"
                    "The Building Blocks of Risk Management\n"
                    "Exam Focus\n"
                    "Module 1.1: Introduction to Risk Management\n"
                    "Module 1.2: Types of Risk\n"
                    "Key Concepts\n"
                    "Answer Key for Module Quizzes\n"
                    "STUDY SESSION 3-Case Studies and Code of Conduct\n"
                    "READING 11\n"
                    "GARP Code of Conduct"
                ),
                FakePage(
                    "STUDY SESSION 3-Case Studies and Code of Conduct\n"
                    "READING 9\n"
                    "Learning from Financial Disasters\n"
                    "EXAM FOCUS\n"
                    "Module 9.1: Case Studies on Interest Rate Risk, Liquidity Risk, and Hedging\n"
                    "Strategy\n"
                    "KEY CONCEPTS\n"
                    "Answer Key for Module Quizzes\n"
                    "READING 10\n"
                    "Anatomy of the Great Financial Crisis of 2007-2009\n"
                    "EXAM FOCUS\n"
                    "Module 10.1: Global Financial Crisis\n"
                    "KEY CONCEPTS\n"
                    "Answer Key for Module Quiz"
                ),
                FakePage(
                    "Readings and Learning Objectives\n"
                    "STUDY SESSION 1\n"
                    "1. The Building Blocks of Risk Management\n"
                    "After completing this reading, you should be able to:\n"
                    "a. explain the concept of risk and compare risk management with risk taking."
                ),
                FakePage(
                    "The following is a review of the Foundations of Risk Management principles.\n"
                    "READING 1\n"
                    "THE BUILDING BLOCKS OF RISK MANAGEMENT\n"
                    "Study Session 1\n"
                    "EXAM FOCUS\n"
                    "This introductory reading provides coverage of fundamental risk management concepts.\n"
                    "MODULE 1.1: INTRODUCTION TO RISK MANAGEMENT\n"
                    "LO 1.a: Explain the concept of risk and compare risk management with risk taking.\n"
                    "KEY CONCEPTS\n"
                    "LO 1.a Risk is uncertainty surrounding outcomes.\n"
                    "MODULE QUIZ 1.1\n"
                    "1. Which statement regarding risk management is correct?\n"
                    "A. Risk management is more concerned with unexpected losses.\n"
                    "B. Risk can be eliminated entirely.\n"
                    "C. Risk always means loss size.\n"
                    "D. Risk management ignores monitoring.\n"
                    "ANSWER KEY FOR MODULE QUIZZES\n"
                    "Module Quiz 1.1\n"
                    "1. A Risk management focuses on unexpected losses."
                ),
            ]

    monkeypatch.setattr("exam_prep.ingestion.parsers.PdfReader", FakeReader)

    sections = parser.parse(
        material_id="mat-frm-boundary",
        course_id="course-frm",
        file_name="frm-book.pdf",
        content_type="application/pdf",
        data=b"%PDF-fake",
    )

    titles = [section.section_title for section in sections]

    assert titles == [
        "Study Session 1: Risk Management Overview / "
        "Reading 1: The Building Blocks of Risk Management / "
        "Module 1.1: Introduction to Risk Management"
    ]
    assert sections[0].locator.page_number == 5
    assert "WELCOME TO THE 2025" not in sections[0].text
    assert "Readings and Learning Objectives" not in sections[0].text
    assert "GARP Code of Conduct" not in sections[0].section_title
    assert "STUDY SESSION 3" not in sections[0].section_title


def test_pdf_parser_rejects_workbook_body_when_no_official_study_blocks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parser = DocumentParser()

    class FakePage:
        def __init__(self, text: str) -> None:
            self._text = text

        def extract_text(self) -> str:
            return self._text

    class FakeReader:
        def __init__(self, *_args, **_kwargs) -> None:
            self.pages = [
                FakePage(
                    "STUDY SESSION 1-Risk Management Overview\n"
                    "READING 1\n"
                    "The Building Blocks of Risk Management\n"
                    "EXAM FOCUS\n"
                    "This reading introduces risk management concepts and background context.\n"
                    "MODULE 1.1: INTRODUCTION TO RISK MANAGEMENT\n"
                    "This is full module body text that should stay out of the study view.\n"
                    "It does not include key concepts, module quiz, or answer key material."
                )
            ]

    monkeypatch.setattr("exam_prep.ingestion.parsers.PdfReader", FakeReader)

    with pytest.raises(MaterialIngestionError):
        parser.parse(
            material_id="mat-frm-no-official-blocks",
            course_id="course-frm",
            file_name="frm-book.pdf",
            content_type="application/pdf",
            data=b"%PDF-fake",
        )


def test_pdf_parser_adds_frm_part_one_weighting_when_table_is_image_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parser = DocumentParser()

    class FakePage:
        def __init__(self, text: str) -> None:
            self._text = text

        def extract_text(self) -> str:
            return self._text

    class FakeReader:
        def __init__(self, *_args, **_kwargs) -> None:
            self.pages = [
                FakePage(
                    "Part I Exam Weightings\n"
                    "When preparing for the exam, be familiar with the weights assigned to each topic area.\n"
                    "The Part I exam weights and questions are as follows:"
                ),
                FakePage(
                    "READING 1\n"
                    "THE BUILDING BLOCKS OF RISK MANAGEMENT\n"
                    "Study Session 1\n"
                    "EXAM FOCUS\n"
                    "This reading covers risk management concepts.\n"
                    "MODULE 1.1: INTRODUCTION TO RISK MANAGEMENT\n"
                    "KEY CONCEPTS\n"
                    "Risk is uncertainty surrounding outcomes."
                ),
            ]

    monkeypatch.setattr("exam_prep.ingestion.parsers.PdfReader", FakeReader)

    sections = parser.parse(
        material_id="mat-frm-weighting",
        course_id="course-frm",
        file_name="FRM 2025 Part 1 KAPLAN Book 1.PDF",
        content_type="application/pdf",
        data=b"%PDF-fake",
    )

    assert sections[0].section_title == "Part I Exam Weightings"
    assert "Foundations of Risk Management 20% 20" in sections[0].text
    assert "Quantitative Analysis 20% 20" in sections[0].text
    assert "Financial Markets and Products 30% 30" in sections[0].text
    assert "Valuation and Risk Models 30% 30" in sections[0].text


def test_pdf_parser_excludes_workbook_front_matter_continuation_pages() -> None:
    parser = DocumentParser()

    assert parser._is_workbook_non_study_page(
        "STUDY SESSION 3—Case Studies and Code of Conduct\n"
        "READING 9\n"
        "Learning from Financial Disasters\n"
        "EXAM FOCUS\n"
        "Module 9.1: Case Studies on Interest Rate Risk, Liquidity Risk, and Hedging\n"
        "KEY CONCEPTS\n"
        "Answer Key for Module Quizzes\n"
        "READING 10\n"
        "Anatomy of the Great Financial Crisis of 2007-2009\n"
        "EXAM FOCUS\n"
        "Module 10.1: Global Financial Crisis\n"
        "KEY CONCEPTS\n"
        "Answer Key for Module Quiz"
    )
    assert parser._is_workbook_non_study_page(
        "STUDY SESSION 2\n"
        "5. Modern Portfolio Theory (MPT) and the Capital Asset Pricing Model (CAPM)\n"
        "Global Association of Risk Professionals. Foundations of Risk Management.\n"
        "After completing this reading, you should be able to:\n"
        "a. explain Modern Portfolio Theory and interpret the Markowitz efficient frontier."
    )


def test_txt_parser_derives_semantic_title_from_generic_notes_name() -> None:
    parser = DocumentParser()
    payload = (
        b"Optimization notes\n\n"
        b"Gradient descent updates model parameters by moving opposite the gradient.\n"
        b"Learning rate controls the step size during each update.\n"
    )

    sections = parser.parse(
        material_id="mat-semantic-title",
        course_id="course-1",
        file_name="optimization_notes.txt",
        content_type="text/plain",
        data=payload,
    )

    assert len(sections) == 1
    assert "optimization_notes" not in sections[0].section_title.lower()
    assert "optimization notes" not in sections[0].section_title.lower()
    assert "gradient" in sections[0].section_title.lower()


def build_docx_bytes(*, heading: str, paragraphs: list[str]) -> bytes:
    document_paragraphs = [
        f"""
        <w:p>
          <w:pPr><w:pStyle w:val="Heading1"/></w:pPr>
          <w:r><w:t>{heading}</w:t></w:r>
        </w:p>
        """
    ]
    for paragraph in paragraphs:
        document_paragraphs.append(
            f"""
            <w:p>
              <w:r><w:t>{paragraph}</w:t></w:r>
            </w:p>
            """
        )

    document_xml = f"""
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
        {''.join(document_paragraphs)}
      </w:body>
    </w:document>
    """.strip()

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types></Types>")
        archive.writestr("_rels/.rels", "<Relationships></Relationships>")
        archive.writestr("word/document.xml", document_xml)
    return buffer.getvalue()


def build_pptx_bytes(*, title: str, body: str) -> bytes:
    slide_xml = f"""
    <p:sld
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
      xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
      <p:cSld>
        <p:spTree>
          <p:sp>
            <p:txBody>
              <a:p><a:r><a:t>{title}</a:t></a:r></a:p>
              <a:p><a:r><a:t>{body}</a:t></a:r></a:p>
            </p:txBody>
          </p:sp>
        </p:spTree>
      </p:cSld>
    </p:sld>
    """.strip()

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types></Types>")
        archive.writestr("_rels/.rels", "<Relationships></Relationships>")
        archive.writestr("ppt/presentation.xml", "<p:presentation xmlns:p='http://schemas.openxmlformats.org/presentationml/2006/main'/>")
        archive.writestr("ppt/slides/slide1.xml", slide_xml)
    return buffer.getvalue()


def build_pdf_bytes(text: str) -> bytes:
    stream_text = f"BT\n/F1 24 Tf\n72 720 Td\n({text}) Tj\nET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        (
            f"<< /Length {len(stream_text.encode('utf-8'))} >>\nstream\n"
            f"{stream_text}\nendstream"
        ).encode("utf-8"),
    ]

    buffer = io.BytesIO()
    buffer.write(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(buffer.tell())
        buffer.write(f"{index} 0 obj\n".encode("utf-8"))
        buffer.write(obj)
        buffer.write(b"\nendobj\n")

    xref_offset = buffer.tell()
    buffer.write(f"xref\n0 {len(objects) + 1}\n".encode("utf-8"))
    buffer.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        buffer.write(f"{offset:010d} 00000 n \n".encode("utf-8"))
    buffer.write(
        f"trailer\n<< /Root 1 0 R /Size {len(objects) + 1} >>\nstartxref\n{xref_offset}\n%%EOF".encode(
            "utf-8"
        )
    )
    return buffer.getvalue()
