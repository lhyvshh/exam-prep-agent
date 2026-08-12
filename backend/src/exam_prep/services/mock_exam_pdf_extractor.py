import io
import importlib
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Final

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from exam_prep.core.exceptions import MaterialIngestionError
from exam_prep.ingestion.parsers import DocumentParser

OCR_RENDER_SCALE: Final = 2.0


def extract_exam_source_pages(*, file_name: str, data: bytes, enable_ocr: bool) -> list[tuple[int, str]]:
    suffix = Path(file_name).suffix.lower()
    if suffix == ".txt":
        text = data.decode("utf-8", errors="replace").strip()
        return [(1, text)] if text else []
    if suffix != ".pdf":
        raise MaterialIngestionError("Exam source upload must be a TXT or PDF file.")

    pages = _extract_pdf_text_pages(data)
    if pages:
        return pages
    if enable_ocr:
        pages = _extract_pdf_ocr_pages(data)
        if pages:
            return pages
    raise MaterialIngestionError(
        "The exam PDF is image-only. Upload a searchable PDF/TXT, or enable OCR for scanned exams."
    )


def _extract_pdf_text_pages(data: bytes) -> list[tuple[int, str]]:
    pages = _extract_pdf_text_pages_with_pymupdf(data)
    if pages:
        return pages
    try:
        reader = PdfReader(io.BytesIO(data))
    except (PdfReadError, ValueError) as exc:
        raise MaterialIngestionError("Unable to parse exam PDF content.") from exc
    extracted: list[tuple[int, str]] = []
    for page_number, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            extracted.append((page_number, text))
    return extracted


def _extract_pdf_text_pages_with_pymupdf(data: bytes) -> list[tuple[int, str]]:
    fitz = _load_fitz()
    if fitz is None:
        return []
    try:
        document = getattr(fitz, "open")(stream=data, filetype="pdf")
    except RuntimeError:
        return []
    extracted: list[tuple[int, str]] = []
    with document:
        for page_number, page in enumerate(document, start=1):
            text = (page.get_text("text") or "").strip()
            if text:
                extracted.append((page_number, text))
    return extracted


def _extract_pdf_ocr_pages(data: bytes) -> list[tuple[int, str]]:
    fitz = _load_fitz()
    if fitz is None:
        return []
    parser = DocumentParser()
    extracted: list[tuple[int, str]] = []
    try:
        document = getattr(fitz, "open")(stream=data, filetype="pdf")
    except RuntimeError:
        return []
    with tempfile.TemporaryDirectory(prefix="mock-exam-ocr-") as temp_dir:
        temp_path = Path(temp_dir)
        with document:
            for page_number, page in enumerate(document, start=1):
                image_path = temp_path / f"page-{page_number}.png"
                page.get_pixmap(
                    matrix=getattr(fitz, "Matrix")(OCR_RENDER_SCALE, OCR_RENDER_SCALE),
                    alpha=False,
                ).save(image_path)
                result = parser._ocr_formula_crop_with_vision(image_path, fast=True)
                text = str(result.get("text") or "").strip()
                if not text:
                    result = parser._ocr_formula_crop_with_tesseract(image_path)
                    text = str(result.get("text") or "").strip()
                if text:
                    extracted.append((page_number, text))
    return extracted


def recover_exam_source_pages(
    data: bytes,
    pages: list[tuple[int, str]],
    page_numbers: set[int],
) -> list[tuple[int, str]]:
    fitz = _load_fitz()
    if fitz is None or not page_numbers:
        return pages
    by_page = dict(pages)
    try:
        document = getattr(fitz, "open")(stream=data, filetype="pdf")
    except RuntimeError:
        return pages
    parser = DocumentParser()
    with tempfile.TemporaryDirectory(prefix="mock-exam-recovery-") as temp_dir:
        temp_path = Path(temp_dir)
        with document:
            for page_number in sorted(page_numbers):
                if page_number < 1 or page_number > len(document):
                    continue
                image_path = temp_path / f"page-{page_number}.png"
                document[page_number - 1].get_pixmap(
                    matrix=getattr(fitz, "Matrix")(OCR_RENDER_SCALE, OCR_RENDER_SCALE),
                    alpha=False,
                ).save(image_path)
                result = parser._ocr_formula_crop_with_vision(image_path)
                text = str(result.get("text") or "").strip()
                if text:
                    by_page[page_number] = text
    return sorted(by_page.items())


def _load_fitz() -> ModuleType | None:
    try:
        return importlib.import_module("fitz")
    except ImportError:
        return None
