import pytest

from exam_prep.ingestion.parsers import DocumentParser


def test_detects_reading_11(monkeypatch: pytest.MonkeyPatch) -> None:
    sections = _parse_part6_book_fixture(monkeypatch)

    assert any("Reading 11" in section.section_title for section in sections)


def test_detects_module_11_1(monkeypatch: pytest.MonkeyPatch) -> None:
    sections = _parse_part6_book_fixture(monkeypatch)

    assert _find_section(sections, "Module 11.1").section_title.endswith("Module 11.1: GARP Code of Conduct")


def test_detects_lo_11_a_and_11_b(monkeypatch: pytest.MonkeyPatch) -> None:
    sections = _parse_part6_book_fixture(monkeypatch)

    module_111 = _find_section(sections, "Module 11.1")
    assert "LO 11.a: Describe the responsibility of GARP members." in module_111.text
    assert "LO 11.b: Describe the potential consequences of violating the GARP Code of Conduct." in module_111.text


def test_detects_reading_5_modules_5_1_5_2_5_3(monkeypatch: pytest.MonkeyPatch) -> None:
    sections = _parse_part6_book_fixture(monkeypatch)
    titles = [section.section_title for section in sections]

    assert any("Reading 5" in title and "Module 5.1" in title for title in titles)
    assert any("Reading 5" in title and "Module 5.2" in title for title in titles)
    assert any("Reading 5" in title and "Module 5.3" in title for title in titles)


def test_detects_lo_5_a(monkeypatch: pytest.MonkeyPatch) -> None:
    sections = _parse_part6_book_fixture(monkeypatch)

    module_51 = _find_section(sections, "Module 5.1")
    assert "LO 5.a: Explain Modern Portfolio Theory and the Markowitz efficient frontier." in module_51.text


def test_does_not_skip_single_module_reading(monkeypatch: pytest.MonkeyPatch) -> None:
    sections = _parse_part6_book_fixture(monkeypatch)

    module_111 = _find_section(sections, "Module 11.1")
    assert "MODULE QUIZ 11.1" in module_111.text


def test_does_not_require_key_concepts_to_create_module(monkeypatch: pytest.MonkeyPatch) -> None:
    sections = _parse_part6_book_fixture(monkeypatch)

    module_53 = _find_section(sections, "Module 5.3")
    assert "Module 5.3: Performance Evaluation Measures" in module_53.section_title
    assert "LO 5.g: Explain risk-adjusted performance measures." in module_53.text


def test_detects_formula_appendix(monkeypatch: pytest.MonkeyPatch) -> None:
    sections = _parse_part6_book_fixture(monkeypatch)

    formula_section = sections[-1]
    assert formula_section.section_title == "Formulas"
    assert formula_section.locator.page_number == 7
    assert "Reading 5" in formula_section.text
    assert formula_section.formula_assets
    assert formula_section.formula_assets[0].source_page == 7


def _parse_part6_book_fixture(monkeypatch: pytest.MonkeyPatch):
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
                    "READING 5 Modern Portfolio Theory (MPT) and the Capital Asset Pricing Model (CAPM) ..... 71\n"
                    "MODULE 5.1: Modern Portfolio Theory and the Capital Market Line ..... 71\n"
                    "MODULE 5.2: Deriving and Applying the Capital Asset Pricing Model ..... 80\n"
                    "MODULE 5.3: Performance Evaluation Measures ..... 86\n"
                    "READING 11 GARP Code of Conduct ..... 153\n"
                    "MODULE 11.1: GARP Code of Conduct ..... 153\n"
                    "FORMULAS ..... 160\n"
                ),
                FakePage(
                    "Readings and Learning Objectives\n"
                    "STUDY SESSION 2\n"
                    "READING 5\n"
                    "Modern Portfolio Theory (MPT) and the Capital Asset Pricing Model (CAPM)\n"
                    "MODULE 5.1: Modern Portfolio Theory and the Capital Market Line\n"
                    "LO 5.a: Explain Modern Portfolio Theory and the Markowitz efficient frontier.\n"
                    "MODULE 5.2: Deriving and Applying the Capital Asset Pricing Model\n"
                    "LO 5.c: Explain the capital asset pricing model.\n"
                    "MODULE 5.3: Performance Evaluation Measures\n"
                    "LO 5.g: Explain risk-adjusted performance measures.\n"
                    "STUDY SESSION 3\n"
                    "READING 11\n"
                    "GARP Code of Conduct\n"
                    "MODULE 11.1: GARP Code of Conduct\n"
                    "LO 11.a: Describe the responsibility of GARP members.\n"
                    "LO 11.b: Describe the potential consequences of violating the GARP Code of Conduct.\n"
                ),
                FakePage(
                    "READING 5\n"
                    "Modern Portfolio Theory (MPT) and the Capital Asset Pricing Model (CAPM)\n"
                    "STUDY SESSION 2\n"
                    "MODULE 5.1: MODERN PORTFOLIO THEORY AND THE CAPITAL MARKET LINE\n"
                    "LO 5.a: Explain Modern Portfolio Theory and the Markowitz efficient frontier.\n"
                    "Modern Portfolio Theory explains how investors combine risky assets."
                ),
                FakePage(
                    "MODULE 5.2: DERIVING AND APPLYING THE CAPITAL ASSET PRICING MODEL\n"
                    "LO 5.c: Explain the capital asset pricing model.\n"
                    "The CAPM links expected return to market beta.\n"
                    "MODULE 5.3: PERFORMANCE EVALUATION MEASURES\n"
                    "LO 5.g: Explain risk-adjusted performance measures.\n"
                    "Sharpe, Treynor, and Jensen measures evaluate performance."
                ),
                FakePage(
                    "READING 11\n"
                    "GARP Code of Conduct\n"
                    "STUDY SESSION 3\n"
                    "MODULE 11.1: GARP CODE OF CONDUCT\n"
                    "LO 11.a: Describe the responsibility of GARP members.\n"
                    "GARP members should act with integrity, competence, and respect.\n"
                    "LO 11.b: Describe the potential consequences of violating the GARP Code of Conduct.\n"
                    "Violations may lead to disciplinary review and sanctions.\n"
                    "MODULE QUIZ 11.1\n"
                    "1. Which action is consistent with the GARP Code?\n"
                    "A. Preserve confidentiality.\n"
                ),
                FakePage(
                    "ANSWER KEY FOR MODULE QUIZZES\n"
                    "Module Quiz 11.1\n"
                    "1. A Members must protect confidential information and maintain integrity."
                ),
                FakePage(
                    "FORMULAS\n"
                    "Reading 5\n"
                    "capital market line:\n"
                    "[FORMULA_IMAGE_CROP page=7 path=formula-crop://mat-part6/page-7-full-1.png label=\"Formula page crop\"]"
                ),
            ]

    monkeypatch.setattr("exam_prep.ingestion.parsers.PdfReader", FakeReader)

    return parser.parse(
        material_id="mat-part6",
        course_id="course-frm",
        file_name="frm-book.pdf",
        content_type="application/pdf",
        data=b"%PDF-fake",
    )


def _find_section(sections, needle: str):  # noqa: ANN001
    return next(section for section in sections if needle in section.section_title)
