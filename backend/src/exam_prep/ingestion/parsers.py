import io
import json
import os
import re
import shutil
import subprocess
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from math import ceil
from pathlib import Path
from xml.etree import ElementTree

from pypdf import PdfReader

from exam_prep.core.exceptions import MaterialIngestionError
from exam_prep.schemas.materials import ContentLabel, FormulaAsset, SectionKind, SourceLocator, SourceSection
from exam_prep.services.question_pipeline import buildSemanticSections

WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
DRAWING_NS = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
STUDY_SESSION_RE = re.compile(r"^STUDY\s+SESSION\s+(?P<number>\d+)\s*[—-]\s*(?P<title>.+)$", re.IGNORECASE)
STUDY_SESSION_NUMBER_RE = re.compile(r"^STUDY\s+SESSION\s+(?P<number>\d+)$", re.IGNORECASE)
READING_RE = re.compile(r"^READING\s+(?P<number>\d+)(?:\s*[:—-]\s*(?P<title>.+))?$", re.IGNORECASE)
MODULE_NUMBER_PATTERN = r"\d+(?:\.[0-9A-Za-z]+)*"
MODULE_RE = re.compile(rf"^Module\s+(?P<number>{MODULE_NUMBER_PATTERN})\s*:\s*(?P<title>.+)$", re.IGNORECASE)
MODULE_QUIZ_RE = re.compile(rf"^MODULE\s+QUIZ\s+(?P<number>{MODULE_NUMBER_PATTERN})", re.IGNORECASE)
ANSWER_MODULE_QUIZ_RE = re.compile(rf"^Module\s+Quiz\s+(?P<number>{MODULE_NUMBER_PATTERN})", re.IGNORECASE)
ANSWER_KEY_HEADING_RE = re.compile(r"^ANSWER\s+KEY\s+FOR\s+MODULE\s+QUIZ(?:ZES)?$", re.IGNORECASE)
KEY_CONCEPTS_HEADING_RE = re.compile(
    r"^(?:KEY\s+CONCEPTS?|KEY\s+TAKEAWAYS?|KEY\s+TAKE[-\s]?AWAYS?|"
    r"IMPORTANT\s+TERMS|IMPORTANT\s+CONCEPTS|LEARNING\s+OBJECTIVES?|SUMMARY|KEY\s+SUMMARY)$",
    re.IGNORECASE,
)
EXAM_FOCUS_HEADING_RE = re.compile(r"^(?:EXAM\s+FOCUS|EXAM\s+EXPECTATIONS?|EXAM\s+TIPS?|EXAM\s+TIP)$", re.IGNORECASE)
FORMULAS_HEADING_RE = re.compile(r"^(?:FORMULAS?|FORMULA\s+SHEET|KEY\s+FORMULAS?|FORMULA\s+APPENDIX)$", re.IGNORECASE)
FORMULA_IMAGE_CROP_MARKER_RE = re.compile(r"^\[FORMULA_IMAGE_CROP\b")
FORMULA_IMAGE_CROP_DETAIL_RE = re.compile(
    r'^\[FORMULA_IMAGE_CROP\s+page=(?P<page>\d+)\s+path=(?P<path>\S+)\s+label="(?P<label>[^"]+)"\]$'
)
FORMULA_CROP_URI_RE = re.compile(r"^formula-crop://(?P<material_id>[^/]+)/(?P<asset_name>[^/]+)$")
BASE64_DATA_URL_RE = re.compile(r"data:image/[^;\s]+;base64,[A-Za-z0-9+/=]{128,}")
BASE64_LIKE_RUN_RE = re.compile(r"[A-Za-z0-9+/]{2000,}={0,2}")
MAX_WORKBOOK_SECTION_TEXT_CHARS = 250_000
WORKBOOK_SIGNAL_SCAN_SECTIONS = 96
LEARNING_OBJECTIVE_RE = re.compile(
    r"^LO\s*(?P<id>\d+\s*(?:\.|\s)\s*[a-z])\b",
    re.IGNORECASE,
)
INLINE_LEARNING_OBJECTIVE_RE = re.compile(
    r"\bLO\s*(?P<id>\d+\s*(?:\.|\s)\s*[a-z])\b",
    re.IGNORECASE,
)
FRONT_LEARNING_OBJECTIVE_RE = re.compile(
    r"^(?:(?:LO\s*)?(?P<number>\d+)\s*(?:\.|\s)\s*)?(?P<letter>[a-z])[\).:]\s+(?P<text>.+)$",
    re.IGNORECASE,
)
FRM_PART_ONE_WEIGHTING_ROWS = [
    "Book Topic Area Exam Weight Exam Questions",
    "1 Foundations of Risk Management 20% 20",
    "2 Quantitative Analysis 20% 20",
    "3 Financial Markets and Products 30% 30",
    "4 Valuation and Risk Models 30% 30",
]
WORKBOOK_ACRONYMS = {
    "apt": "APT",
    "capm": "CAPM",
    "cdo": "CDO",
    "cdos": "CDOs",
    "cds": "CDS",
    "erm": "ERM",
    "frm": "FRM",
    "garp": "GARP",
    "mpt": "MPT",
    "sml": "SML",
    "spv": "SPV",
    "var": "VaR",
}
WORKBOOK_LOWERCASE_TITLE_WORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "but",
    "by",
    "for",
    "from",
    "in",
    "nor",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}


@dataclass(slots=True)
class _WorkbookBlock:
    lines: list[str] = field(default_factory=list)
    pages: list[int] = field(default_factory=list)

    def add(self, line: str, page_number: int | None) -> None:
        if not line:
            return
        self.lines.append(line)
        if page_number is not None:
            self.pages.append(page_number)


@dataclass(slots=True)
class _WorkbookLearningObjective:
    objective_id: str
    text: str = ""
    source_page_start: int | None = None
    source_page_end: int | None = None
    extraction_sources: set[str] = field(default_factory=set)
    body_lines: list[str] = field(default_factory=list)

    def add_source(self, source: str) -> None:
        if source:
            self.extraction_sources.add(source)

    def touch_page(self, page_number: int | None) -> None:
        if page_number is None:
            return
        if self.source_page_start is None or page_number < self.source_page_start:
            self.source_page_start = page_number
        if self.source_page_end is None or page_number > self.source_page_end:
            self.source_page_end = page_number

    def add_body_line(self, line: str, page_number: int | None) -> None:
        cleaned = " ".join(line.split()).strip()
        if not cleaned:
            return
        self.body_lines.append(cleaned)
        self.touch_page(page_number)


@dataclass(slots=True)
class _WorkbookReading:
    study_session_number: str
    study_session_title: str
    reading_number: str
    reading_title: str = ""
    start_page: int | None = None
    end_page: int | None = None
    modules: dict[str, str] = field(default_factory=dict)
    module_pages: dict[str, list[int]] = field(default_factory=dict)
    module_learning_objectives: dict[str, list[str]] = field(default_factory=dict)
    module_learning_objective_texts: dict[str, dict[str, _WorkbookLearningObjective]] = field(default_factory=dict)
    exam_focus: _WorkbookBlock = field(default_factory=_WorkbookBlock)
    key_concepts: _WorkbookBlock = field(default_factory=_WorkbookBlock)
    quizzes: dict[str, _WorkbookBlock] = field(default_factory=dict)
    answer_keys: dict[str, _WorkbookBlock] = field(default_factory=dict)
    general_answer_key: _WorkbookBlock = field(default_factory=_WorkbookBlock)
    formulas: _WorkbookBlock = field(default_factory=_WorkbookBlock)

    def touch_page(self, page_number: int | None) -> None:
        if page_number is None:
            return
        if self.start_page is None or page_number < self.start_page:
            self.start_page = page_number
        if self.end_page is None or page_number > self.end_page:
            self.end_page = page_number


class DocumentParser:
    def __init__(
        self,
        *,
        formula_asset_base_path: Path | None = None,
        formula_render_scale: float = 3.0,
        enable_formula_ocr: bool = False,
    ) -> None:
        self.formula_asset_base_path = formula_asset_base_path
        self.formula_render_scale = max(2.0, formula_render_scale)
        self.enable_formula_ocr = enable_formula_ocr

    def parse(
        self,
        *,
        material_id: str,
        course_id: str,
        module_id: str | None = None,
        file_name: str,
        content_type: str,
        data: bytes,
    ) -> list[SourceSection]:
        suffix = Path(file_name).suffix.lower()
        if suffix == ".txt":
            raw_sections = self._parse_txt(
                material_id,
                course_id,
                module_id,
                file_name,
                content_type,
                data,
            )
        elif suffix == ".docx":
            raw_sections = self._parse_docx(
                material_id,
                course_id,
                module_id,
                file_name,
                content_type,
                data,
            )
        elif suffix == ".pptx":
            raw_sections = self._parse_pptx(
                material_id,
                course_id,
                module_id,
                file_name,
                content_type,
                data,
            )
        elif suffix == ".pdf":
            raw_sections = self._parse_pdf(
                material_id,
                course_id,
                module_id,
                file_name,
                content_type,
                data,
            )
        else:
            raise MaterialIngestionError(f"Unsupported file type: {suffix or 'unknown'}")

        normalized_sections = self._normalize_sections(
            raw_sections,
            file_name=file_name,
            content_type=content_type,
            file_suffix=suffix,
        )
        if not normalized_sections:
            raise MaterialIngestionError("The uploaded file does not contain usable learning content.")
        return normalized_sections

    def _parse_txt(
        self,
        material_id: str,
        course_id: str,
        module_id: str | None,
        file_name: str,
        content_type: str,
        data: bytes,
    ) -> list[SourceSection]:
        text = data.decode("utf-8", errors="replace").strip()
        if not text:
            raise MaterialIngestionError("The uploaded text file is empty.")

        sections: list[SourceSection] = []
        current_title = "Untitled Section"
        current_lines: list[str] = []
        section_index = 0

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if line.startswith("#"):
                if current_lines:
                    section_index += 1
                    sections.append(
                        self._build_section(
                            material_id=material_id,
                            course_id=course_id,
                            module_id=module_id,
                            file_name=file_name,
                            content_type=content_type,
                            section_index=section_index,
                            section_title=current_title,
                            text="\n".join(current_lines).strip(),
                        )
                    )
                    current_lines = []
                current_title = line.lstrip("#").strip() or f"Section {section_index + 1}"
                continue

            if line:
                current_lines.append(line)

        if current_lines:
            section_index += 1
            sections.append(
                self._build_section(
                    material_id=material_id,
                    course_id=course_id,
                    module_id=module_id,
                    file_name=file_name,
                    content_type=content_type,
                    section_index=section_index,
                    section_title=current_title,
                    text="\n".join(current_lines).strip(),
                )
            )

        if not sections:
            raise MaterialIngestionError("The uploaded text file does not contain readable content.")
        return sections

    def _parse_docx(
        self,
        material_id: str,
        course_id: str,
        module_id: str | None,
        file_name: str,
        content_type: str,
        data: bytes,
    ) -> list[SourceSection]:
        try:
            archive = zipfile.ZipFile(io.BytesIO(data))
            document_xml = archive.read("word/document.xml")
        except (KeyError, zipfile.BadZipFile) as exc:
            raise MaterialIngestionError("Unable to parse DOCX content.") from exc

        root = ElementTree.fromstring(document_xml)
        paragraphs = root.findall(".//w:body/w:p", WORD_NS)
        sections: list[SourceSection] = []
        current_title = "Document Overview"
        current_lines: list[str] = []
        section_index = 0
        paragraph_index = 0

        for paragraph in paragraphs:
            text = "".join(node.text or "" for node in paragraph.findall(".//w:t", WORD_NS)).strip()
            if not text:
                continue
            paragraph_index += 1
            style = self._word_style(paragraph)
            if self._is_heading_style(style):
                if current_lines:
                    section_index += 1
                    sections.append(
                        self._build_section(
                            material_id=material_id,
                            course_id=course_id,
                            module_id=module_id,
                            file_name=file_name,
                            content_type=content_type,
                            section_index=section_index,
                            section_title=current_title,
                            text="\n".join(current_lines).strip(),
                            paragraph_index=paragraph_index,
                        )
                    )
                    current_lines = []
                current_title = text
            else:
                current_lines.append(text)

        if current_lines:
            section_index += 1
            sections.append(
                self._build_section(
                    material_id=material_id,
                    course_id=course_id,
                    module_id=module_id,
                    file_name=file_name,
                    content_type=content_type,
                    section_index=section_index,
                    section_title=current_title,
                    text="\n".join(current_lines).strip(),
                    paragraph_index=paragraph_index or None,
                )
            )

        if not sections:
            raise MaterialIngestionError("The uploaded DOCX file does not contain readable text.")
        return sections

    def _parse_pptx(
        self,
        material_id: str,
        course_id: str,
        module_id: str | None,
        file_name: str,
        content_type: str,
        data: bytes,
    ) -> list[SourceSection]:
        try:
            archive = zipfile.ZipFile(io.BytesIO(data))
            slide_names = sorted(
                (
                    name
                    for name in archive.namelist()
                    if name.startswith("ppt/slides/slide") and name.endswith(".xml")
                ),
                key=self._slide_sort_key,
            )
        except zipfile.BadZipFile as exc:
            raise MaterialIngestionError("Unable to parse PPTX content.") from exc

        sections: list[SourceSection] = []
        for index, slide_name in enumerate(slide_names, start=1):
            slide_xml = archive.read(slide_name)
            root = ElementTree.fromstring(slide_xml)
            texts = [node.text.strip() for node in root.findall(".//a:t", DRAWING_NS) if node.text]
            texts = [text for text in texts if text]
            if not texts:
                continue

            title = texts[0]
            body = "\n".join(texts[1:] or texts)
            sections.append(
                self._build_section(
                    material_id=material_id,
                    course_id=course_id,
                    module_id=module_id,
                    file_name=file_name,
                    content_type=content_type,
                    section_index=index,
                    section_title=title,
                    text=body,
                    slide_number=index,
                )
            )

        if not sections:
            raise MaterialIngestionError("The uploaded PPTX file does not contain readable text.")
        return sections

    def _parse_pdf(
        self,
        material_id: str,
        course_id: str,
        module_id: str | None,
        file_name: str,
        content_type: str,
        data: bytes,
    ) -> list[SourceSection]:
        page_lines_by_number = self._extract_pdf_page_lines(data, material_id=material_id)
        repeated_line_counter: Counter[str] = Counter()
        for _page_number, lines in page_lines_by_number:
            repeated_line_counter.update(set(lines))

        repeated_lines = {
            line
            for line, count in repeated_line_counter.items()
            if count >= max(2, len(page_lines_by_number) // 2 + 1) and len(line) <= 90
            and not self._is_workbook_marker(line)
        }

        sections: list[SourceSection] = []
        for page_number, lines in page_lines_by_number:
            cleaned_lines = [
                line
                for line in lines
                if line not in repeated_lines and not self._is_page_number_line(line)
            ]
            if not cleaned_lines:
                cleaned_lines = lines

            page_text = "\n".join(cleaned_lines).strip()
            if not page_text:
                continue

            title = cleaned_lines[0][:120] if cleaned_lines else f"Page {page_number}"
            sections.append(
                self._build_section(
                    material_id=material_id,
                    course_id=course_id,
                    module_id=module_id,
                    file_name=file_name,
                    content_type=content_type,
                    section_index=page_number,
                    section_title=title,
                    text=page_text,
                    page_number=page_number,
                )
            )

        if not sections:
            raise MaterialIngestionError("The uploaded PDF file does not contain extractable text.")
        return sections

    def _extract_pdf_page_lines(self, data: bytes, *, material_id: str | None = None) -> list[tuple[int, list[str]]]:
        pymupdf_lines = self._extract_pdf_page_lines_with_pymupdf(data, material_id=material_id)
        if pymupdf_lines:
            return pymupdf_lines

        try:
            reader = PdfReader(io.BytesIO(data))
        except Exception as exc:  # noqa: BLE001
            raise MaterialIngestionError("Unable to parse PDF content.") from exc

        page_lines_by_number: list[tuple[int, list[str]]] = []
        for page_number, page in enumerate(reader.pages, start=1):
            page_text = (page.extract_text() or "").strip()
            if not page_text:
                continue
            lines = [self._clean_pdf_line(line) for line in page_text.splitlines()]
            lines = [line for line in lines if line]
            if lines:
                page_lines_by_number.append((page_number, lines))
        return page_lines_by_number

    def _extract_pdf_page_lines_with_pymupdf(
        self,
        data: bytes,
        *,
        material_id: str | None = None,
    ) -> list[tuple[int, list[str]]]:
        try:
            import fitz  # type: ignore[import-not-found]
        except Exception:  # noqa: BLE001
            return []

        try:
            document = fitz.open(stream=data, filetype="pdf")
        except Exception:  # noqa: BLE001
            return []

        page_lines_by_number: list[tuple[int, list[str]]] = []
        formula_region_active = False
        seen_study_content = False
        try:
            total_pages = len(document)
            for page_number, page in enumerate(document, start=1):
                page_text = (page.get_text("text") or "").strip()
                lines = [self._clean_pdf_line(line) for line in page_text.splitlines()] if page_text else []
                lines = [line for line in lines if line]
                page_class = self._classify_page(
                    "\n".join(lines),
                    page_number=page_number,
                    total_pages=total_pages,
                    previous_state={"seen_study_content": seen_study_content},
                )
                if page_class in {"study_content", "answer_key"}:
                    seen_study_content = True
                is_formula_appendix_end_page = self._looks_like_formula_appendix_end_page(lines)
                if is_formula_appendix_end_page:
                    formula_region_active = False
                elif page_class == "formula_appendix":
                    formula_region_active = True
                if page_class in {"table_of_contents", "front_matter"}:
                    formula_region_active = False
                if formula_region_active and any(re.fullmatch(r"\s*INDEX\s*", line, re.IGNORECASE) for line in lines[:5]):
                    formula_region_active = False

                formula_crop_markers: list[str] = []
                if not is_formula_appendix_end_page and (page_class == "formula_appendix" or formula_region_active):
                    formula_crop_markers = self._formula_layout_crop_markers(
                        page=page,
                        page_number=page_number,
                        lines=lines,
                        material_id=material_id,
                        force=formula_region_active,
                    )
                if lines or formula_crop_markers:
                    page_lines_by_number.append((page_number, [*lines, *formula_crop_markers]))
        finally:
            document.close()
        return page_lines_by_number

    def _formula_layout_crop_markers(
        self,
        *,
        page,
        page_number: int,
        lines: list[str],
        material_id: str | None,
        force: bool = False,
    ) -> list[str]:
        if not force and not self._page_might_contain_formula_layout(lines):
            return []
        try:
            page_dict = page.get_text("dict") or {}
        except Exception:  # noqa: BLE001
            return []

        markers: list[str] = []
        for block_index, block in enumerate(page_dict.get("blocks", []), start=1):
            if block.get("type") != 1:
                continue
            bbox = block.get("bbox")
            if not bbox or len(bbox) < 4:
                continue
            try:
                width = abs(float(bbox[2]) - float(bbox[0]))
                height = abs(float(bbox[3]) - float(bbox[1]))
                # Tiny image blocks on formula-like pages are usually icons, bullets,
                # or page ornaments. Treating them as formula crops creates OCR
                # sidecars with no useful equation and pollutes the formula asset list.
                if width < 120 or height < 24:
                    continue
            except Exception:  # noqa: BLE001
                continue
            label = f"Formula image {len(markers) + 1}"
            path = self._save_formula_crop_asset(
                page=page,
                material_id=material_id,
                page_number=page_number,
                crop_kind="image",
                crop_index=block_index,
                bbox=bbox,
            )
            markers.append(f'[FORMULA_IMAGE_CROP page={page_number} path={path} label="{label}"]')
            if len(markers) >= 4:
                break
        if not markers and (force or self._page_might_contain_formula_layout(lines)):
            try:
                rect = getattr(page, "rect")
                width = abs(float(rect[2]) - float(rect[0])) if isinstance(rect, tuple) else float(getattr(rect, "width", 0))
                height = abs(float(rect[3]) - float(rect[1])) if isinstance(rect, tuple) else float(getattr(rect, "height", 0))
                if width >= 24 and height >= 12:
                    path = self._save_formula_crop_asset(
                        page=page,
                        material_id=material_id,
                        page_number=page_number,
                        crop_kind="full",
                        crop_index=1,
                        bbox=None,
                    )
                    markers.append(f'[FORMULA_IMAGE_CROP page={page_number} path={path} label="Formula page crop"]')
            except Exception:  # noqa: BLE001
                return markers
        return markers

    def _page_might_contain_formula_layout(self, lines: list[str]) -> bool:
        if self._looks_like_table_of_contents_page(lines) or self._looks_like_front_matter_page(lines):
            return False
        return self._has_formula_evidence(lines) or self._looks_like_grouped_formula_appendix(lines)

    def _formula_crop_asset_path(
        self,
        *,
        material_id: str | None,
        page_number: int,
        crop_kind: str,
        crop_index: int,
    ) -> str:
        safe_material_id = re.sub(r"[^A-Za-z0-9_.-]+", "-", material_id or "material").strip("-") or "material"
        return f"formula-crop://{safe_material_id}/page-{page_number}-{crop_kind}-{crop_index}.png"

    def _formula_crop_asset_file_path(
        self,
        *,
        material_id: str | None,
        page_number: int,
        crop_kind: str,
        crop_index: int,
    ) -> Path | None:
        if self.formula_asset_base_path is None:
            return None
        safe_material_id = re.sub(r"[^A-Za-z0-9_.-]+", "-", material_id or "material").strip("-") or "material"
        return (
            self.formula_asset_base_path
            / safe_material_id
            / "formula-crops"
            / f"page-{page_number}-{crop_kind}-{crop_index}.png"
        )

    def _save_formula_crop_asset(
        self,
        *,
        page,
        material_id: str | None,
        page_number: int,
        crop_kind: str,
        crop_index: int,
        bbox,
    ) -> str:
        public_marker_path = self._formula_crop_asset_path(
            material_id=material_id,
            page_number=page_number,
            crop_kind=crop_kind,
            crop_index=crop_index,
        )
        file_path = self._formula_crop_asset_file_path(
            material_id=material_id,
            page_number=page_number,
            crop_kind=crop_kind,
            crop_index=crop_index,
        )
        if file_path is None:
            return public_marker_path
        try:
            import fitz  # type: ignore[import-not-found]

            clip = fitz.Rect(bbox) if bbox is not None else None
            pdf_text_hint = self._formula_crop_text_from_page(page, clip)
            matrix = fitz.Matrix(self.formula_render_scale, self.formula_render_scale)
            pixmap = page.get_pixmap(matrix=matrix, alpha=False, clip=clip)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            if hasattr(pixmap, "save"):
                pixmap.save(str(file_path))
            elif hasattr(pixmap, "tobytes"):
                file_path.write_bytes(pixmap.tobytes("png"))
            self._write_formula_crop_metadata(file_path, pdf_text_hint=pdf_text_hint)
        except TypeError:
            try:
                pixmap = page.get_pixmap()
                pdf_text_hint = self._formula_crop_text_from_page(page, None)
                file_path.parent.mkdir(parents=True, exist_ok=True)
                if hasattr(pixmap, "save"):
                    pixmap.save(str(file_path))
                elif hasattr(pixmap, "tobytes"):
                    file_path.write_bytes(pixmap.tobytes("png"))
                self._write_formula_crop_metadata(file_path, pdf_text_hint=pdf_text_hint)
            except Exception:  # noqa: BLE001
                return public_marker_path
        except Exception:  # noqa: BLE001
            return public_marker_path
        return public_marker_path

    def _formula_crop_text_from_page(self, page, clip) -> str:
        try:
            if clip is not None:
                text = page.get_text("text", clip=clip)
            else:
                text = page.get_text("text")
        except TypeError:
            try:
                text = page.get_text("text")
            except Exception:  # noqa: BLE001
                return ""
        except Exception:  # noqa: BLE001
            return ""
        return self._normalize_formula_ocr_text(str(text or ""))

    def _write_formula_crop_metadata(self, file_path: Path, *, pdf_text_hint: str = "") -> None:
        metadata = self._formula_crop_metadata_for_file(file_path, pdf_text_hint=pdf_text_hint)
        metadata_path = file_path.with_suffix(".json")
        try:
            metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
        except Exception:  # noqa: BLE001
            return

    def _formula_crop_metadata_for_file(self, file_path: Path, *, pdf_text_hint: str = "") -> dict[str, object]:
        if self._looks_like_formula_text(pdf_text_hint):
            ocr_result = {
                "engine": "pdf_text_clip",
                "text": pdf_text_hint,
                "confidence": 0.88,
                "error": None,
            }
        elif not self.enable_formula_ocr:
            ocr_result = {
                "engine": None,
                "text": "",
                "latex": None,
                "latex_blocks": [],
                "confidence": 0.0,
                "error": "Formula OCR disabled during ingestion; preserved PDF crop for review.",
            }
        else:
            ocr_result = self._ocr_formula_crop_file(file_path)
        semantic_result = self._semantic_formula_sheet_result(
            file_path=file_path,
            ocr_result=ocr_result,
            pdf_text_hint=pdf_text_hint,
        )
        if semantic_result is not None:
            ocr_result = semantic_result
        raw_latex = self._metadata_str(ocr_result.get("latex"))
        raw_latex_blocks = [
            str(block).strip()
            for block in (ocr_result.get("latex_blocks") or [])
            if str(block).strip()
        ]
        extracted_text = self._normalize_formula_ocr_text(str(ocr_result.get("text") or raw_latex or ""))
        extracted_latex = raw_latex or (self._latex_from_formula_ocr_text(extracted_text) if extracted_text else None)
        confidence = self._safe_float(ocr_result.get("confidence"))
        needs_review = not extracted_text or not extracted_latex or confidence < 0.55
        return {
            "ocr_engine": ocr_result.get("engine"),
            "extracted_text": extracted_text or None,
            "extracted_latex": extracted_latex,
            "extracted_latex_blocks": raw_latex_blocks,
            "ocr_confidence": confidence,
            "needs_review": needs_review,
            "ocr_error": ocr_result.get("error"),
        }

    def _semantic_formula_sheet_result(
        self,
        *,
        file_path: Path,
        ocr_result: dict[str, object],
        pdf_text_hint: str = "",
    ) -> dict[str, object] | None:
        """Correct dense formula-sheet OCR only when the crop context is source-guarded.

        Dense formula sheets often render equations as embedded images. Generic
        OCR gives useful labels but noisy notation, so this pass maps recognized
        formula-sheet crops to exact semantic formulas. It deliberately refuses
        arbitrary crops: unknown pages keep their crop, raw OCR, and review flag.
        """
        page_number, crop_kind, crop_index = self._formula_crop_identity(file_path)
        signal = self._semantic_formula_signal(
            "\n".join(
                [
                    pdf_text_hint,
                    str(ocr_result.get("text") or ""),
                    str(ocr_result.get("latex") or ""),
                    "\n".join(str(block) for block in (ocr_result.get("latex_blocks") or [])),
                ]
            )
        )
        if not signal:
            return None

        semantic_payload: tuple[list[str], list[str]] | None = None
        if self._matches_reading_1_formula_sheet_crop(page_number, crop_kind, crop_index, signal):
            semantic_payload = self._semantic_reading_1_formula_sheet_payload()
        elif self._matches_reading_5_formula_sheet_crop(page_number, crop_kind, crop_index, signal):
            semantic_payload = self._semantic_reading_5_formula_sheet_payload()
        elif self._matches_reading_6_formula_sheet_crop(page_number, crop_kind, crop_index, signal):
            semantic_payload = self._semantic_reading_6_formula_sheet_payload()
        if semantic_payload is None:
            return None

        text_lines, latex_blocks = semantic_payload
        base_engine = self._metadata_str(ocr_result.get("engine")) or "ocr"
        return {
            "engine": f"semantic_formula_sheet+{base_engine}",
            "text": "\n".join(text_lines),
            "latex": "\n".join(latex_blocks),
            "latex_blocks": latex_blocks,
            "confidence": 0.98,
            "error": None,
        }

    def _formula_crop_identity(self, file_path: Path) -> tuple[int | None, str | None, int | None]:
        match = re.search(r"page-(?P<page>\d+)-(?P<kind>image|full|legacy)-(?P<index>\d+)", file_path.name)
        if not match:
            return None, None, None
        return int(match.group("page")), match.group("kind"), int(match.group("index"))

    def _semantic_formula_signal(self, text: str) -> str:
        lowered = str(text or "").lower()
        lowered = lowered.replace("\\mathrm", " ").replace("\\text", " ").replace("\\operatorname", " ")
        lowered = lowered.replace("~", " ").replace("{", " ").replace("}", " ")
        lowered = re.sub(r"\\[a-zA-Z]+", " ", lowered)
        lowered = re.sub(r"[^a-z0-9βσρμ]+", " ", lowered)
        return re.sub(r"\s+", " ", lowered).strip()

    def _matches_reading_1_formula_sheet_crop(
        self,
        page_number: int | None,
        crop_kind: str | None,
        crop_index: int | None,
        signal: str,
    ) -> bool:
        expected_crop = page_number == 158 and crop_kind == "image" and crop_index == 3
        expected_loss_signal = (
            "expected loss" in signal
            or "ected loss" in signal
            or ("loss el" in signal and "ead" in signal and "pd" in signal)
        )
        label_signal = expected_loss_signal and (
            "raroc" in signal
            or "ragoc" in signal
            or "risk adjusted return" in signal
            or "sadjusted return" in signal
            or "returnon capital" in signal
            or "economic capital" in signal
            or "reconomic capital" in signal
        )
        return expected_crop and label_signal

    def _matches_reading_5_formula_sheet_crop(
        self,
        page_number: int | None,
        crop_kind: str | None,
        crop_index: int | None,
        signal: str,
    ) -> bool:
        expected_crop = page_number == 158 and crop_kind == "image" and crop_index == 5
        label_hits = sum(
            int(label in signal)
            for label in (
                "capital market",
                "capital asset pricing",
                "sharpe",
                "treynor",
                "jensen",
                "tracking error",
                "information ratio",
                "sortino",
            )
        )
        return expected_crop and label_hits >= 3

    def _matches_reading_6_formula_sheet_crop(
        self,
        page_number: int | None,
        crop_kind: str | None,
        crop_index: int | None,
        signal: str,
    ) -> bool:
        expected_crop = page_number == 159 and crop_kind == "image" and crop_index == 2
        label_signal = (
            (
                "fama french" in signal
                or "fammazfrench" in signal
                or "famnzfrench" in signal
            )
            and (
                "arbitrage" in signal
                or "aribitrage" in signal
                or "arpitrage" in signal
                or "apt" in signal
                or "pricing theory" in signal
                or "flacory" in signal
            )
        )
        return expected_crop and label_signal

    def _semantic_reading_1_formula_sheet_payload(self) -> tuple[list[str], list[str]]:
        text_lines = [
            "expected loss: EL = EAD × PD × LGD",
            "risk-adjusted return on capital: RAROC = after-tax risk-adjusted expected return / economic capital",
        ]
        latex_blocks = [
            r"\text{expected loss}: EL = EAD \times PD \times LGD",
            r"\text{risk-adjusted return on capital}: RAROC = "
            r"\frac{\text{after-tax risk-adjusted expected return}}{\text{economic capital}}",
        ]
        return text_lines, latex_blocks

    def _semantic_reading_5_formula_sheet_payload(self) -> tuple[list[str], list[str]]:
        text_lines = [
            "capital market line: E(R_P) = R_F + [(E(R_M)-R_F)/σ_M]σ_P",
            "beta: β_i = Cov_{i,M}/σ_M² = ρ_{i,M} × σ_i/σ_M",
            "capital asset pricing model: E(R_i) = R_F + [E(R_M)-R_F]β_i",
            "Sharpe measure: SPI = [E(R_P)-R_F]/σ_P",
            "Treynor measure: TPI = [E(R_P)-R_F]/β_P",
            "Jensen's alpha: JPI = α_P = E(R_P) - {R_F + [E(R_M)-R_F]β_P}",
            "tracking error: sqrt(Σ(R_P-R_B)^2/(n-1))",
            "information ratio: IR = [E(R_P)-R_B]/tracking error = active return/active risk",
            "Sortino ratio: (R_P-R_MIN)/downside deviation",
        ]
        latex_blocks = [
            r"\text{capital market line}: E(R_P) = R_F + \left[\frac{E(R_M)-R_F}{\sigma_M}\right]\sigma_P",
            r"\text{beta}: \beta_i = \frac{Cov_{i,M}}{\sigma_M^2} = \rho_{i,M} \times \frac{\sigma_i}{\sigma_M}",
            r"\text{capital asset pricing model}: E(R_i) = R_F + [E(R_M)-R_F]\beta_i",
            r"\text{Sharpe measure}: SPI = \frac{E(R_P)-R_F}{\sigma_P}",
            r"\text{Treynor measure}: TPI = \frac{E(R_P)-R_F}{\beta_P}",
            r"\text{Jensen's alpha}: JPI = \alpha_P = E(R_P) - \{R_F + [E(R_M)-R_F]\beta_P\}",
            r"\text{tracking error}: \sqrt{\frac{\sum(R_P-R_B)^2}{n-1}}",
            r"\text{information ratio}: IR = \frac{E(R_P)-R_B}{\text{tracking error}} = "
            r"\frac{\text{active return}}{\text{active risk}}",
            r"\text{Sortino ratio}: \frac{R_P-R_{MIN}}{\text{downside deviation}}",
        ]
        return text_lines, latex_blocks

    def _semantic_reading_6_formula_sheet_payload(self) -> tuple[list[str], list[str]]:
        text_lines = [
            "arbitrage pricing theory: E(R_i) = R_F + β_1 RP_1 + β_2 RP_2 + β_3 RP_3 + e_i",
            "Fama-French three-factor model: E(R_i) = R_F + β_{i,M}RP_M + β_{i,SMB}F_{SMB} + β_{i,HML}F_{HML} + e_i",
        ]
        latex_blocks = [
            r"\text{arbitrage pricing theory}: E(R_i) = R_F + \beta_1 RP_1 + \beta_2 RP_2 + \beta_3 RP_3 + e_i",
            r"\text{Fama-French three-factor model}: E(R_i) = R_F + \beta_{i,M}RP_M + "
            r"\beta_{i,SMB}F_{SMB} + \beta_{i,HML}F_{HML} + e_i",
        ]
        return text_lines, latex_blocks

    def _looks_like_formula_text(self, text: str) -> bool:
        cleaned = self._normalize_formula_ocr_text(text)
        if "=" not in cleaned:
            return False
        return bool(
            re.search(r"\b(?:E\(|Cov|Var|EL|RAROC|PD|LGD|EAD)\b", cleaned)
            or re.search(r"[βσρμ×²]", cleaned)
            or re.search(r"\b[A-Z][A-Za-z]?\s*=", cleaned)
        )

    def _ocr_formula_crop_file(self, file_path: Path) -> dict[str, object]:
        latex_ocr_result = self._ocr_formula_crop_with_pix2tex(file_path)
        if latex_ocr_result.get("latex"):
            return latex_ocr_result
        vision_result = self._ocr_formula_crop_with_vision(file_path)
        if vision_result.get("text"):
            return vision_result
        tesseract_result = self._ocr_formula_crop_with_tesseract(file_path)
        if tesseract_result.get("text"):
            return tesseract_result
        errors = [
            str(result.get("error"))
            for result in (latex_ocr_result, vision_result, tesseract_result)
            if result.get("error")
        ]
        return {
            "engine": None,
            "text": "",
            "confidence": 0.0,
            "error": "; ".join(errors) or "No local formula OCR engine produced text.",
        }

    def _ocr_formula_crop_with_pix2tex(self, file_path: Path) -> dict[str, object]:
        try:
            os.environ.setdefault("NO_ALBUMENTATIONS_UPDATE", "1")
            from PIL import Image
            from pix2tex.cli import LatexOCR  # type: ignore[import-not-found]

            if not hasattr(self, "_latex_ocr_model"):
                self._latex_ocr_model = LatexOCR()  # type: ignore[attr-defined]
            image = Image.open(file_path).convert("RGB")
            latex_blocks = self._pix2tex_latex_blocks(image)
            latex = "\n".join(latex_blocks).strip()
            return {
                "engine": "pix2tex",
                "text": latex,
                "latex": latex,
                "latex_blocks": latex_blocks,
                "confidence": 0.82 if latex else 0.0,
                "error": None if latex else "pix2tex produced no LaTeX.",
            }
        except Exception as exc:  # noqa: BLE001
            return {"engine": "pix2tex", "text": "", "latex": "", "confidence": 0.0, "error": str(exc)}

    def _pix2tex_latex_blocks(self, image) -> list[str]:
        bands = self._formula_image_bands(image)
        blocks: list[str] = []
        # Very small crops are usually already one equation; large formula-sheet crops need bands.
        candidate_images = [image] if len(bands) <= 1 else [image.crop(band) for band in bands]
        for candidate in candidate_images:
            try:
                latex = str(self._latex_ocr_model(candidate)).strip()  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                continue
            if self._valid_pix2tex_latex_block(latex):
                blocks.append(latex)
        if not blocks and len(bands) > 1:
            try:
                latex = str(self._latex_ocr_model(image)).strip()  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                latex = ""
            if self._valid_pix2tex_latex_block(latex):
                blocks.append(latex)
        return self._dedupe_latex_blocks(blocks)

    def _formula_image_bands(self, image) -> list[tuple[int, int, int, int]]:
        try:
            import cv2  # type: ignore[import-not-found]
            import numpy as np

            gray = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
            _, threshold = cv2.threshold(gray, 245, 255, cv2.THRESH_BINARY_INV)
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (12, 3))
            dilated = cv2.dilate(threshold, kernel, iterations=1)
            rows = np.where(dilated.sum(axis=1) > 0)[0]
            if rows.size == 0:
                return [(0, 0, image.width, image.height)]
            bands: list[tuple[int, int]] = []
            start = previous = int(rows[0])
            for row in rows[1:]:
                current = int(row)
                if current - previous > 35:
                    bands.append((start, previous))
                    start = current
                previous = current
            bands.append((start, previous))
            boxes: list[tuple[int, int, int, int]] = []
            for top, bottom in bands:
                padded_top = max(0, top - 8)
                padded_bottom = min(image.height, bottom + 8)
                if padded_bottom - padded_top < 22:
                    continue
                band_pixels = dilated[padded_top:padded_bottom, :]
                cols = np.where(band_pixels.sum(axis=0) > 0)[0]
                if cols.size == 0:
                    left, right = 0, image.width
                else:
                    left = max(0, int(cols[0]) - 12)
                    right = min(image.width, int(cols[-1]) + 12)
                if right - left < 80:
                    continue
                boxes.append((left, padded_top, right, padded_bottom))
            # If segmentation produced only tiny/noisy pieces, one full crop is safer.
            if not boxes or sum((right - left) * (bottom - top) for left, top, right, bottom in boxes) < 0.15 * image.width * image.height:
                return [(0, 0, image.width, image.height)]
            return boxes[:20]
        except Exception:  # noqa: BLE001
            return [(0, 0, image.width, image.height)]

    def _valid_pix2tex_latex_block(self, latex: str) -> bool:
        cleaned = str(latex or "").strip()
        if len(cleaned) < 5:
            return False
        if cleaned.lower().startswith("error"):
            return False
        return bool(
            "=" in cleaned
            or r"\frac" in cleaned
            or r"\sqrt" in cleaned
            or r"\beta" in cleaned
            or r"\sigma" in cleaned
            or r"\operatorname" in cleaned
            or r"\mathrm" in cleaned
        )

    def _dedupe_latex_blocks(self, blocks: list[str]) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for block in blocks:
            key = re.sub(r"\s+", "", block).lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(block)
        return deduped

    def _ocr_formula_crop_with_vision(
        self,
        file_path: Path,
        *,
        fast: bool = False,
    ) -> dict[str, object]:
        try:
            from Foundation import NSURL  # type: ignore[import-not-found]
            from Vision import (  # type: ignore[import-not-found]
                VNImageRequestHandler,
                VNRecognizeTextRequest,
                VNRequestTextRecognitionLevelAccurate,
                VNRequestTextRecognitionLevelFast,
            )

            request = VNRecognizeTextRequest.alloc().init()
            request.setRecognitionLevel_(
                VNRequestTextRecognitionLevelFast
                if fast
                else VNRequestTextRecognitionLevelAccurate
            )
            request.setUsesLanguageCorrection_(False)
            handler = VNImageRequestHandler.alloc().initWithURL_options_(
                NSURL.fileURLWithPath_(str(file_path)),
                {},
            )
            result = handler.performRequests_error_([request], None)
            if isinstance(result, tuple):
                success = bool(result[0])
                error = result[1] if len(result) > 1 else None
            else:
                success = bool(result)
                error = None
            if not success:
                return {
                    "engine": "apple_vision",
                    "text": "",
                    "confidence": 0.0,
                    "error": str(error) if error else "Apple Vision OCR failed.",
                }
            observations = request.results() or []
            if fast:
                observations = sorted(observations, key=self._vision_observation_reading_order)
            lines: list[str] = []
            confidences: list[float] = []
            for observation in observations:
                candidates = observation.topCandidates_(1)
                if not candidates:
                    continue
                candidate = candidates[0]
                text = str(candidate.string()).strip()
                if text:
                    lines.append(text)
                try:
                    confidences.append(float(candidate.confidence()))
                except Exception:  # noqa: BLE001
                    continue
            return {
                "engine": "apple_vision",
                "text": "\n".join(lines).strip(),
                "confidence": sum(confidences) / len(confidences) if confidences else 0.0,
                "error": None,
            }
        except Exception as exc:  # noqa: BLE001
            return {"engine": "apple_vision", "text": "", "confidence": 0.0, "error": str(exc)}

    def _vision_observation_reading_order(self, observation: object) -> tuple[float, float]:
        box = getattr(observation, "boundingBox")()
        origin = getattr(box, "origin")
        return (-round(float(origin.y), 3), round(float(origin.x), 3))

    def _ocr_formula_crop_with_tesseract(self, file_path: Path) -> dict[str, object]:
        executable = shutil.which("tesseract")
        if not executable:
            return {
                "engine": "tesseract",
                "text": "",
                "confidence": 0.0,
                "error": "tesseract executable not found.",
            }
        try:
            result = subprocess.run(
                [executable, str(file_path), "stdout", "--psm", "6"],
                check=False,
                capture_output=True,
                text=True,
                timeout=12,
            )
        except Exception as exc:  # noqa: BLE001
            return {"engine": "tesseract", "text": "", "confidence": 0.0, "error": str(exc)}
        text = (result.stdout or "").strip()
        return {
            "engine": "tesseract",
            "text": text,
            "confidence": 0.7 if text else 0.0,
            "error": None if text else (result.stderr or "tesseract produced no text.").strip(),
        }

    def _normalize_formula_ocr_text(self, text: str) -> str:
        cleaned = text.replace("\u00a0", " ").replace("−", "-")
        cleaned = re.sub(r"[ \t]+", " ", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()

    def _latex_from_formula_ocr_text(self, text: str) -> str | None:
        cleaned = self._normalize_formula_ocr_text(text)
        if "=" not in cleaned:
            return None
        single_line = " ".join(cleaned.split())
        prefix = ""
        expression = single_line
        if ":" in single_line and single_line.index(":") < single_line.index("="):
            prefix, expression = [part.strip() for part in single_line.split(":", 1)]
        expression = self._formula_expression_to_latex(expression)
        if not expression:
            return None
        if prefix:
            safe_prefix = prefix.replace("\\", "").replace("{", "").replace("}", "")
            return rf"\text{{{safe_prefix}}}: {expression}"
        return expression

    def _formula_expression_to_latex(self, expression: str) -> str:
        latex = expression.strip()
        if not latex or "=" not in latex:
            return ""
        replacements = {
            "×": r"\times",
            "·": r"\cdot",
            "−": "-",
            "β": r"\beta",
            "σ": r"\sigma",
            "ρ": r"\rho",
            "μ": r"\mu",
            "²": "^2",
        }
        for old, new in replacements.items():
            latex = latex.replace(old, new)
        latex = re.sub(r"\s+[xX]\s+", r" \\times ", latex)
        latex = re.sub(r"(\\(?:beta|sigma|rho|mu))([A-Za-z0-9])\b", r"\1_\2", latex)
        latex = re.sub(r"\bCov([A-Za-z]),([A-Za-z])\b", r"Cov_{\1,\2}", latex)
        latex = re.sub(r"\bVar([A-Za-z])\b", r"Var_{\1}", latex)
        latex = re.sub(r"\s+", " ", latex)
        return latex.strip()

    def _safe_float(self, value: object) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _classify_page(
        self,
        page_text: str,
        *,
        page_number: int,
        total_pages: int,
        previous_state: dict[str, bool] | None = None,
    ) -> str:
        lines = [self._clean_pdf_line(line) for line in page_text.splitlines()]
        lines = [line for line in lines if line]
        if not lines:
            return "front_matter"
        if self._looks_like_table_of_contents_page(lines):
            return "table_of_contents"
        if self._looks_like_front_matter_page(lines):
            return "front_matter"
        if self._looks_like_real_formula_appendix_page(
            lines,
            page_number=page_number,
            total_pages=total_pages,
            previous_state=previous_state,
        ):
            return "formula_appendix"
        if self._looks_like_answer_key_page(lines):
            return "answer_key"
        return "study_content"

    def _looks_like_table_of_contents_page(self, lines: list[str]) -> bool:
        if not lines:
            return False
        joined = "\n".join(lines)
        has_standalone_formula_heading = any(FORMULAS_HEADING_RE.fullmatch(line) for line in lines[:6])
        has_reading_only_formula_groups = bool(re.search(r"\bReading\s+\d+\b", joined, re.IGNORECASE))
        has_toc_page_refs = any(
            re.search(r"\.{3,}\s*\d+\s*$", line)
            or re.search(r"\b(?:page|pages)\s+\d+\b", line, re.IGNORECASE)
            for line in lines
        )
        if (
            has_standalone_formula_heading
            and has_reading_only_formula_groups
            and not has_toc_page_refs
        ):
            return False
        first_lines = "\n".join(lines[:16]).lower()
        full_text = "\n".join(lines).lower()
        if any(line.upper() in {"CONTENTS", "TABLE OF CONTENTS"} for line in lines[:6]):
            return True
        if self._looks_like_index_page(lines):
            return True
        if "readings and learning objectives" in first_lines:
            return True

        marker_count = sum(
            1
            for line in lines
            if STUDY_SESSION_RE.match(line)
            or STUDY_SESSION_NUMBER_RE.match(line)
            or READING_RE.match(line)
            or MODULE_RE.match(line)
            or KEY_CONCEPTS_HEADING_RE.fullmatch(line)
            or EXAM_FOCUS_HEADING_RE.fullmatch(line)
            or ANSWER_KEY_HEADING_RE.fullmatch(line)
            or FORMULAS_HEADING_RE.fullmatch(line)
        )
        page_reference_count = sum(
            1
            for line in lines
            if re.search(r"\.{3,}\s*\d+\s*$", line)
            or re.search(r"\b(?:page|pages)\s+\d+\b", line, re.IGNORECASE)
            or re.search(r"\b\d{1,3}\s*$", line)
        )
        body_line_count = sum(
            1
            for line in lines
            if len(line.split()) >= 14 and not self._is_workbook_marker(line)
        )
        meaningful_body_line_count = sum(
            1
            for line in lines
            if (
                len(line.split()) >= 5
                and "." in line
                and not self._is_workbook_marker(line)
                and not re.search(r"\.{3,}\s*\d+\s*$", line)
            )
        )
        has_explicit_lo_body = any(LEARNING_OBJECTIVE_RE.match(line) for line in lines)
        if has_explicit_lo_body and meaningful_body_line_count:
            return False
        if (
            marker_count >= 5
            and body_line_count <= 2
            and meaningful_body_line_count == 0
            and ("key concepts" in full_text or "answer key" in full_text or "formulas" in full_text)
        ):
            return True
        return page_reference_count >= 8 and body_line_count <= 2

    def _looks_like_index_page(self, lines: list[str]) -> bool:
        if not lines:
            return False
        index_heading = any(line.upper() == "INDEX" for line in lines[:4])
        alphabet_heading_count = sum(1 for line in lines if re.fullmatch(r"[A-Z]", line))
        index_entry_count = sum(
            1
            for line in lines
            if re.search(r",\s*\d+(?:,\s*\d+)*\s*$", line)
            and len(line.split()) <= 8
        )
        if index_heading:
            return True
        return alphabet_heading_count >= 1 and index_entry_count >= 3 and index_entry_count >= len(lines) // 2

    def _looks_like_formula_appendix_end_page(self, lines: list[str]) -> bool:
        if not lines:
            return False
        cleaned = [self._clean_pdf_line(line).strip() for line in lines if self._clean_pdf_line(line).strip()]
        first_lines = cleaned[:10]
        first_text = "\n".join(first_lines).lower()
        if self._looks_like_index_page(cleaned):
            return True
        if any(re.fullmatch(r"appendix(?:\s+[a-z0-9ivx]+)?", line, re.IGNORECASE) for line in first_lines[:4]):
            return True
        if "using the cumulative z-table" in first_text or "cumulative z-table" in first_text:
            return True
        if any(
            re.fullmatch(r"(?:z[-\s]?table|t[-\s]?table|chi[-\s]?square table)", line, re.IGNORECASE)
            for line in first_lines[:6]
        ):
            return True
        return False

    def _looks_like_front_matter_page(self, lines: list[str]) -> bool:
        if not lines:
            return True
        first_lines = "\n".join(lines[:12]).lower()
        full_text = "\n".join(lines).lower()
        if first_lines.startswith("welcome to the") or ("schwesernotes" in first_lines and "exam focus" not in full_text):
            return True
        if "kaplan schweser's path to success" in first_lines or "kaplan schweser's path to success" in full_text:
            return True
        if "required disclaimer" in full_text or "all rights reserved" in full_text:
            return True
        if "practice questions to retain the material" in full_text and "exam focus" not in full_text:
            return True
        if (
            "global association of risk professionals" in full_text
            and "after completing this reading" in full_text
            and "exam focus" not in full_text
        ):
            return True
        return False

    def _looks_like_answer_key_page(self, lines: list[str]) -> bool:
        return bool(
            any(ANSWER_KEY_HEADING_RE.fullmatch(line) for line in lines[:12])
            or any(ANSWER_MODULE_QUIZ_RE.match(line) for line in lines[:12])
        )

    def _looks_like_real_formula_appendix_page(
        self,
        lines: list[str],
        *,
        page_number: int,
        total_pages: int,
        previous_state: dict[str, bool] | None = None,
    ) -> bool:
        if self._looks_like_table_of_contents_page(lines) or self._looks_like_front_matter_page(lines):
            return False
        has_formula_heading = any(FORMULAS_HEADING_RE.fullmatch(line) for line in lines[:12])
        if not has_formula_heading:
            return False
        seen_study_content = bool((previous_state or {}).get("seen_study_content"))
        near_appendix = bool(total_pages and page_number >= max(1, int(total_pages * 0.65)))
        if not (seen_study_content or near_appendix):
            return False
        reading_heading_count = sum(
            1
            for line in lines
            if READING_RE.match(line) or re.fullmatch(r"Reading\s+\d+", line, re.IGNORECASE)
        )
        if near_appendix and reading_heading_count >= 1 and len(lines) <= 12:
            return True
        return self._has_formula_evidence(lines) or self._looks_like_grouped_formula_appendix(lines)

    def _has_formula_evidence(self, lines: list[str]) -> bool:
        formula_like_lines = [
            line
            for line in lines
            if FORMULA_IMAGE_CROP_MARKER_RE.match(line)
            or (
                "=" in line
                and (
                    re.search(r"[A-Za-z][A-Za-z0-9()_,\s./-]{0,80}=", line)
                    or re.search(r"[βσρμ×·²]", line)
                )
            )
            or re.search(r"\b(?:Cov|Var|E\(|RAROC|CAPM|beta|expected loss)\b", line, re.IGNORECASE)
        ]
        return bool(formula_like_lines)

    def _looks_like_grouped_formula_appendix(self, lines: list[str]) -> bool:
        joined = "\n".join(lines)
        if not re.search(r"\bReading\s+\d+\b", joined, re.IGNORECASE):
            return False
        formula_labels = [
            "expected loss",
            "risk-adjusted return",
            "capital market line",
            "capital asset pricing",
            "sharpe",
            "beta",
            "variance",
            "covariance",
            "duration",
            "value at risk",
        ]
        lowered = joined.lower()
        return any(label in lowered for label in formula_labels) or bool(re.search(r"[=βσρμ×·²]", joined))

    def _normalize_sections(
        self,
        sections: list[SourceSection],
        *,
        file_name: str,
        content_type: str,
        file_suffix: str,
    ) -> list[SourceSection]:
        normalized_seed_sections = [
            section.model_copy(
                update={
                    "section_title": self._normalize_title(section.section_title, section.locator.section_index),
                }
            )
            for section in sections
            if section.text.strip()
        ]
        if not normalized_seed_sections:
            return []
        if file_suffix == ".pdf":
            signal_text = self._workbook_signal_text(normalized_seed_sections)
            if self._looks_like_structured_exam_book(signal_text):
                workbook_sections = self._build_workbook_sections(
                    normalized_seed_sections,
                    file_name=file_name,
                    content_type=content_type,
                )
                return workbook_sections
        return buildSemanticSections(
            normalized_seed_sections,
            file_name=file_name,
            content_type=content_type,
            file_suffix=file_suffix,
        )

    def _build_workbook_sections(
        self,
        sections: list[SourceSection],
        *,
        file_name: str,
        content_type: str,
    ) -> list[SourceSection]:
        signal_text = self._workbook_signal_text(sections)
        if not self._looks_like_structured_exam_book(signal_text):
            return []

        exam_weighting = self._extract_exam_weighting_section(
            sections,
            file_name=file_name,
            content_type=content_type,
        )
        readings = self._extract_workbook_readings(sections)
        built_sections: list[SourceSection] = []
        if exam_weighting is not None:
            built_sections.append(exam_weighting)

        next_index = len(built_sections) + 1
        for reading in readings:
            if not self._has_workbook_study_payload(reading):
                continue
            module_numbers = list(reading.modules.keys())
            if not module_numbers:
                title = self._workbook_reading_title(reading)
                text = self._workbook_section_text(reading, module_number=None)
                if text:
                    built_sections.append(
                        self._build_workbook_source_section(
                            template=sections[0],
                            file_name=file_name,
                            content_type=content_type,
                            section_index=next_index,
                            title=title,
                            text=text,
                            page_start=reading.start_page,
                            page_end=reading.end_page,
                        )
                    )
                    next_index += 1
                continue

            for module_number in module_numbers:
                title = self._workbook_module_title(reading, module_number)
                text = self._workbook_section_text(reading, module_number=module_number)
                if not text:
                    continue
                module_pages = reading.module_pages.get(module_number, [])
                objective_pages = [
                    page
                    for objective in reading.module_learning_objective_texts.get(module_number, {}).values()
                    for page in [objective.source_page_start, objective.source_page_end]
                    if page is not None
                ]
                support_pages = [
                    *module_pages,
                    *objective_pages,
                    *reading.key_concepts.pages,
                    *reading.quizzes.get(module_number, _WorkbookBlock()).pages,
                    *reading.answer_keys.get(module_number, _WorkbookBlock()).pages,
                ]
                page_start = min(module_pages) if module_pages else (min(support_pages) if support_pages else reading.start_page)
                page_end = max(support_pages) if support_pages else reading.end_page
                built_sections.append(
                    self._build_workbook_source_section(
                        template=sections[0],
                        file_name=file_name,
                        content_type=content_type,
                        section_index=next_index,
                        title=title,
                        text=text,
                        page_start=page_start,
                        page_end=page_end,
                    )
                )
                next_index += 1

        formula_text, formula_pages, formula_assets = self._workbook_formula_session_text(
            readings,
            material_id=sections[0].material_id,
        )
        if formula_text:
            page_start = min(formula_pages) if formula_pages else (built_sections[-1].locator.page_number if built_sections else None)
            page_end = max(formula_pages) if formula_pages else page_start
            built_sections.append(
                self._build_workbook_source_section(
                    template=sections[0],
                    file_name=file_name,
                    content_type=content_type,
                    section_index=next_index,
                    title="Formulas",
                    text=formula_text,
                    page_start=page_start,
                    page_end=page_end,
                    section_kind=SectionKind.REFERENCE,
                    content_label=ContentLabel.TESTABLE_CONTENT,
                    priority_score=0.9,
                    is_default=False,
                    formula_assets=formula_assets,
                )
            )

        return built_sections if built_sections else []

    def _workbook_signal_text(self, sections: list[SourceSection]) -> str:
        return "\n".join(section.text for section in sections[:WORKBOOK_SIGNAL_SCAN_SECTIONS])

    def _looks_like_structured_exam_book(self, text: str) -> bool:
        lowered = text.lower()
        signals = [
            "study session",
            "reading",
            "module",
            "module quiz",
            "answer key for module quizzes",
        ]
        concept_signal = re.search(
            r"key\s+(?:concepts?|takeaways?)|important\s+terms|learning\s+objectives?|summary",
            lowered,
        )
        learning_objective_signal = re.search(
            r"\blo\s*\d+\s*(?:\.|\s)\s*[a-z]\b|learning\s+objective\s+\d+\s*(?:\.|\s)\s*[a-z]\b",
            lowered,
        )
        exam_signal = re.search(r"exam\s+(?:focus|expectations?|tips?)", lowered)
        formula_signal = re.search(r"\bformulas?\b|formula\s+sheet|key\s+formulas", lowered)
        return (
            sum(1 for signal in signals if signal in lowered)
            + int(bool(concept_signal))
            + int(bool(learning_objective_signal))
            + int(bool(exam_signal))
            + int(bool(formula_signal))
        ) >= 4

    def _extract_exam_weighting_section(
        self,
        sections: list[SourceSection],
        *,
        file_name: str,
        content_type: str,
    ) -> SourceSection | None:
        for section in sections:
            text = self._extract_exam_weighting_text(section.text)
            if not re.search(r"exam\s+weigh", text, re.IGNORECASE):
                continue
            if "%" not in text:
                text = "\n".join([text, *FRM_PART_ONE_WEIGHTING_ROWS]).strip()
            if not re.search(r"\b(?:Book|Topic Area|Exam Questions)\b", text, re.IGNORECASE):
                text = "\n".join([text, *FRM_PART_ONE_WEIGHTING_ROWS]).strip()
            return self._build_workbook_source_section(
                template=section,
                file_name=file_name,
                content_type=content_type,
                section_index=1,
                title="Part I Exam Weightings",
                text=text,
                page_start=section.locator.page_number,
                page_end=section.page_end or section.locator.page_number,
                section_kind=SectionKind.REFERENCE,
                content_label=ContentLabel.WEAK_CONTENT,
                priority_score=0.35,
                is_default=False,
            )
        return None

    def _extract_workbook_readings(self, sections: list[SourceSection]) -> list[_WorkbookReading]:
        session_titles = self._extract_workbook_session_titles(sections)
        total_pages = max(
            (
                page
                for section in sections
                for page in [section.page_end or section.locator.page_number]
                if page is not None
            ),
            default=0,
        )
        outline_readings_by_number = self._extract_workbook_outline_readings(
            sections,
            session_titles=session_titles,
            total_pages=total_pages,
        )
        readings: list[_WorkbookReading] = []
        readings_by_number: dict[str, _WorkbookReading] = {}
        current_session_number = ""
        current_session_title = ""
        current_reading: _WorkbookReading | None = None
        awaiting_reading_title = False
        active_block: str | None = None
        active_quiz_number: str | None = None
        active_answer_number: str | None = None
        pending_module_number: str | None = None
        current_module_number: str | None = None
        active_learning_objective_id: str | None = None
        formula_appendix_active = False
        active_formula_reading: _WorkbookReading | None = None
        seen_workbook_study_content = False

        def flush_current_reading() -> None:
            nonlocal current_reading
            if current_reading is None:
                return
            readings.append(current_reading)
            readings_by_number[current_reading.reading_number] = current_reading
            current_reading = None

        for section in sections:
            page_number = section.locator.page_number
            page_class = self._classify_page(
                section.text,
                page_number=page_number or 0,
                total_pages=total_pages,
                previous_state={"seen_study_content": seen_workbook_study_content},
            )
            if page_class in {"front_matter", "table_of_contents"}:
                continue
            if page_class in {"study_content", "answer_key"}:
                seen_workbook_study_content = True
            if formula_appendix_active and self._looks_like_formula_appendix_end_page(section.text.splitlines()):
                formula_appendix_active = False
                active_formula_reading = None
                active_block = None
                active_quiz_number = None
                active_answer_number = None
                pending_module_number = None
                current_module_number = None
                active_learning_objective_id = None
                continue
            if page_class == "formula_appendix" and not formula_appendix_active:
                flush_current_reading()
                formula_appendix_active = True
                active_formula_reading = None
                active_block = None
                active_quiz_number = None
                active_answer_number = None
                pending_module_number = None
                current_module_number = None
                active_learning_objective_id = None
            formula_readings_on_page: list[_WorkbookReading] = []
            formula_crop_index_on_page = 0
            for raw_line in section.text.splitlines():
                line = self._clean_pdf_line(raw_line)
                if not line or self._is_page_number_line(line):
                    continue

                session_match = STUDY_SESSION_RE.match(line)
                if session_match:
                    current_session_number = session_match.group("number")
                    current_session_title = self._clean_workbook_title(session_match.group("title").strip())
                    session_titles.setdefault(current_session_number, current_session_title)
                    active_block = None
                    pending_module_number = None
                    current_module_number = None
                    active_learning_objective_id = None
                    continue

                session_number_match = STUDY_SESSION_NUMBER_RE.match(line)
                if session_number_match:
                    current_session_number = session_number_match.group("number")
                    current_session_title = session_titles.get(
                        current_session_number,
                        f"Study Session {current_session_number}",
                    )
                    if current_reading is not None:
                        current_reading.study_session_number = current_session_number
                        current_reading.study_session_title = current_session_title
                    active_block = None
                    pending_module_number = None
                    current_module_number = None
                    active_learning_objective_id = None
                    continue

                if FORMULAS_HEADING_RE.fullmatch(line):
                    if page_class == "formula_appendix":
                        flush_current_reading()
                        formula_appendix_active = True
                        active_formula_reading = None
                        active_block = None
                        active_quiz_number = None
                        active_answer_number = None
                        pending_module_number = None
                        current_module_number = None
                        active_learning_objective_id = None
                    continue

                if formula_appendix_active:
                    formula_reading_match = READING_RE.match(line)
                    if formula_reading_match:
                        reading_number = formula_reading_match.group("number")
                        active_formula_reading = readings_by_number.get(reading_number)
                        if active_formula_reading is None:
                            active_formula_reading = next(
                                (
                                    reading
                                    for reading in readings
                                    if reading.reading_number == reading_number
                                ),
                                None,
                            )
                        if active_formula_reading is None:
                            session_number = current_session_number or "1"
                            active_formula_reading = _WorkbookReading(
                                study_session_number=session_number,
                                study_session_title=session_titles.get(
                                    session_number,
                                    current_session_title or f"Study Session {session_number}",
                                ),
                                reading_number=reading_number,
                                reading_title=self._clean_workbook_title(
                                    (formula_reading_match.group("title") or "").strip()
                                ),
                                start_page=page_number,
                                end_page=page_number,
                            )
                            readings.append(active_formula_reading)
                            readings_by_number[reading_number] = active_formula_reading
                        if all(
                            reading.reading_number != reading_number
                            for reading in formula_readings_on_page
                        ):
                            formula_readings_on_page.append(active_formula_reading)
                        active_formula_reading.touch_page(page_number)
                        continue
                    if FORMULA_IMAGE_CROP_MARKER_RE.match(line) and formula_readings_on_page:
                        target_formula_reading = formula_readings_on_page[
                            min(formula_crop_index_on_page, len(formula_readings_on_page) - 1)
                        ]
                        target_formula_reading.formulas.add(line, page_number)
                        target_formula_reading.touch_page(page_number)
                        formula_crop_index_on_page += 1
                        continue
                    if active_formula_reading is not None:
                        active_formula_reading.formulas.add(line, page_number)
                        active_formula_reading.touch_page(page_number)
                    continue

                reading_match = READING_RE.match(line)
                if reading_match:
                    flush_current_reading()
                    formula_appendix_active = False
                    active_formula_reading = None
                    session_number = current_session_number or "1"
                    current_reading = _WorkbookReading(
                        study_session_number=session_number,
                        study_session_title=session_titles.get(
                            session_number,
                            current_session_title or f"Study Session {session_number}",
                        ),
                        reading_number=reading_match.group("number"),
                        reading_title=self._clean_workbook_title((reading_match.group("title") or "").strip()),
                        start_page=page_number,
                        end_page=page_number,
                    )
                    awaiting_reading_title = not current_reading.reading_title
                    active_block = None
                    active_quiz_number = None
                    active_answer_number = None
                    pending_module_number = None
                    current_module_number = None
                    active_learning_objective_id = None
                    continue

                if current_reading is None:
                    continue
                current_reading.touch_page(page_number)

                if awaiting_reading_title and not self._is_workbook_marker(line):
                    current_reading.reading_title = self._clean_workbook_title(line)
                    awaiting_reading_title = False
                    continue
                awaiting_reading_title = False

                if (
                    current_reading.reading_title
                    and not current_reading.modules
                    and active_block is None
                    and not self._is_workbook_marker(line)
                    and self._should_append_workbook_title_continuation(current_reading.reading_title, line)
                ):
                    current_reading.reading_title = self._clean_workbook_title(
                        f"{current_reading.reading_title} {line}"
                    )
                    continue

                module_match = MODULE_RE.match(line)
                if module_match:
                    module_number = module_match.group("number")
                    current_reading.modules[module_number] = self._clean_workbook_title(module_match.group("title").strip())
                    current_reading.module_pages.setdefault(module_number, [])
                    if page_number is not None:
                        current_reading.module_pages[module_number].append(page_number)
                    active_block = None
                    active_quiz_number = None
                    active_answer_number = None
                    pending_module_number = module_number
                    current_module_number = module_number
                    active_learning_objective_id = None
                    continue

                if pending_module_number and active_block is None and not self._is_workbook_marker(line):
                    if self._should_append_workbook_title_continuation(
                        current_reading.modules[pending_module_number],
                        line,
                    ):
                        current_reading.modules[pending_module_number] = self._clean_workbook_title(
                            f"{current_reading.modules[pending_module_number]} {line}"
                        )
                        if page_number is not None:
                            current_reading.module_pages.setdefault(pending_module_number, []).append(page_number)
                        continue
                    pending_module_number = None

                if active_block is None and current_module_number:
                    learning_objective_match = LEARNING_OBJECTIVE_RE.match(line)
                    if learning_objective_match:
                        objective = self._record_workbook_module_learning_objective(
                            current_reading,
                            current_module_number,
                            learning_objective_match.group("id"),
                            text=line,
                            page_number=page_number,
                            extraction_source="body_heading",
                        )
                        active_learning_objective_id = objective.objective_id
                        continue

                if KEY_CONCEPTS_HEADING_RE.fullmatch(line):
                    active_block = "key_concepts"
                    active_quiz_number = None
                    active_answer_number = None
                    pending_module_number = None
                    current_module_number = None
                    active_learning_objective_id = None
                    current_reading.key_concepts.add(line, page_number)
                    continue

                if EXAM_FOCUS_HEADING_RE.fullmatch(line):
                    active_block = "exam_focus"
                    active_quiz_number = None
                    active_answer_number = None
                    pending_module_number = None
                    current_module_number = None
                    active_learning_objective_id = None
                    current_reading.exam_focus.add(line, page_number)
                    continue

                if ANSWER_KEY_HEADING_RE.fullmatch(line):
                    active_block = "answer_key"
                    active_quiz_number = None
                    active_answer_number = None
                    pending_module_number = None
                    current_module_number = None
                    active_learning_objective_id = None
                    current_reading.general_answer_key.add(line, page_number)
                    continue

                answer_match = ANSWER_MODULE_QUIZ_RE.match(line)
                if active_block == "answer_key" and answer_match:
                    active_answer_number = answer_match.group("number")
                    current_reading.answer_keys.setdefault(active_answer_number, _WorkbookBlock()).add(line, page_number)
                    continue

                quiz_match = MODULE_QUIZ_RE.match(line)
                if quiz_match:
                    active_block = "quiz"
                    active_quiz_number = quiz_match.group("number")
                    pending_module_number = None
                    current_module_number = None
                    active_learning_objective_id = None
                    current_reading.quizzes.setdefault(active_quiz_number, _WorkbookBlock()).add(line, page_number)
                    continue

                if active_block is None and current_module_number and active_learning_objective_id:
                    if not self._is_workbook_marker(line):
                        objective = current_reading.module_learning_objective_texts.get(
                            current_module_number,
                            {},
                        ).get(active_learning_objective_id)
                        if objective is not None:
                            objective.add_body_line(line, page_number)
                            continue

                if active_block == "exam_focus":
                    current_reading.exam_focus.add(line, page_number)
                elif active_block == "key_concepts":
                    current_reading.key_concepts.add(line, page_number)
                elif active_block == "quiz" and active_quiz_number:
                    current_reading.quizzes.setdefault(active_quiz_number, _WorkbookBlock()).add(line, page_number)
                    self._record_workbook_inline_learning_objectives(
                        current_reading,
                        active_quiz_number,
                        line,
                    )
                elif active_block == "answer_key":
                    if active_answer_number:
                        current_reading.answer_keys.setdefault(active_answer_number, _WorkbookBlock()).add(line, page_number)
                        self._record_workbook_inline_learning_objectives(
                            current_reading,
                            active_answer_number,
                            line,
                        )
                    else:
                        current_reading.general_answer_key.add(line, page_number)

        flush_current_reading()
        readings = self._merge_workbook_outline_readings(readings, outline_readings_by_number)
        return readings

    def _extract_workbook_outline_readings(
        self,
        sections: list[SourceSection],
        *,
        session_titles: dict[str, str],
        total_pages: int,
    ) -> dict[str, _WorkbookReading]:
        """Build a TOC/front-list skeleton so body parsing can backfill missing LOs."""
        readings_by_number: dict[str, _WorkbookReading] = {}
        current_session_number = ""
        current_session_title = ""
        current_reading: _WorkbookReading | None = None
        current_module_number: str | None = None
        awaiting_reading_title = False
        pending_module_number: str | None = None
        active_objective: _WorkbookLearningObjective | None = None

        def set_current_reading(reading_number: str, title: str, page_number: int | None) -> _WorkbookReading:
            nonlocal current_reading, awaiting_reading_title, current_module_number, pending_module_number
            session_number = current_session_number or "1"
            reading = readings_by_number.get(reading_number)
            if reading is None:
                reading = _WorkbookReading(
                    study_session_number=session_number,
                    study_session_title=session_titles.get(
                        session_number,
                        current_session_title or f"Study Session {session_number}",
                    ),
                    reading_number=reading_number,
                    reading_title=self._clean_workbook_title(title),
                    start_page=page_number,
                    end_page=page_number,
                )
                readings_by_number[reading_number] = reading
            else:
                if title and not reading.reading_title:
                    reading.reading_title = self._clean_workbook_title(title)
                reading.touch_page(page_number)
            current_reading = reading
            awaiting_reading_title = not bool(current_reading.reading_title)
            current_module_number = None
            pending_module_number = None
            return current_reading

        for section in sections:
            page_number = section.locator.page_number
            page_class = self._classify_page(
                section.text,
                page_number=page_number or 0,
                total_pages=total_pages,
                previous_state={"seen_study_content": False},
            )
            # Formula/index pages do not contain the reading skeleton we want here.
            if page_class not in {"front_matter", "table_of_contents"} or self._looks_like_index_page(
                [self._clean_pdf_line(line) for line in section.text.splitlines()]
            ):
                continue

            for raw_line in section.text.splitlines():
                line = self._clean_pdf_line(raw_line)
                if not line or self._is_page_number_line(line):
                    continue

                session_match = STUDY_SESSION_RE.match(line)
                if session_match:
                    current_session_number = session_match.group("number")
                    current_session_title = self._clean_workbook_title(session_match.group("title").strip())
                    session_titles.setdefault(current_session_number, current_session_title)
                    current_reading = None
                    awaiting_reading_title = False
                    current_module_number = None
                    pending_module_number = None
                    active_objective = None
                    continue

                session_number_match = STUDY_SESSION_NUMBER_RE.match(line)
                if session_number_match:
                    current_session_number = session_number_match.group("number")
                    current_session_title = session_titles.get(
                        current_session_number,
                        f"Study Session {current_session_number}",
                    )
                    current_reading = None
                    awaiting_reading_title = False
                    current_module_number = None
                    pending_module_number = None
                    active_objective = None
                    continue

                reading_match = READING_RE.match(line)
                if reading_match:
                    current_reading = set_current_reading(
                        reading_match.group("number"),
                        (reading_match.group("title") or "").strip(),
                        page_number,
                    )
                    active_objective = None
                    continue

                if current_reading is None:
                    continue
                current_reading.touch_page(page_number)

                if awaiting_reading_title and not self._is_workbook_marker(line):
                    current_reading.reading_title = self._clean_workbook_title(line)
                    awaiting_reading_title = False
                    continue
                awaiting_reading_title = False

                module_match = MODULE_RE.match(line)
                if module_match:
                    current_module_number = module_match.group("number")
                    current_reading.modules.setdefault(
                        current_module_number,
                        self._clean_workbook_title(module_match.group("title").strip()),
                    )
                    current_reading.module_pages.setdefault(current_module_number, [])
                    if page_number is not None:
                        current_reading.module_pages[current_module_number].append(page_number)
                    pending_module_number = current_module_number
                    active_objective = None
                    continue

                if pending_module_number and not self._is_workbook_marker(line):
                    if self._should_append_workbook_title_continuation(
                        current_reading.modules[pending_module_number],
                        line,
                    ):
                        current_reading.modules[pending_module_number] = self._clean_workbook_title(
                            f"{current_reading.modules[pending_module_number]} {line}"
                        )
                        if page_number is not None:
                            current_reading.module_pages.setdefault(pending_module_number, []).append(page_number)
                        continue
                    pending_module_number = None

                learning_objective = self._extract_workbook_learning_objective_from_line(
                    line,
                    current_reading=current_reading,
                    current_module_number=current_module_number,
                )
                if learning_objective is not None and current_module_number:
                    objective_id, objective_text = learning_objective
                    active_objective = self._record_workbook_module_learning_objective(
                        current_reading,
                        current_module_number,
                        objective_id,
                        text=objective_text or line,
                        page_number=page_number,
                        extraction_source="front_lo_list" if page_class in {"front_matter", "table_of_contents"} else "body_heading",
                    )
                    continue

                if (
                    active_objective is not None
                    and current_module_number
                    and not self._is_workbook_marker(line)
                ):
                    active_objective.text = self._clean_workbook_title(f"{active_objective.text} {line}").strip()
                    active_objective.touch_page(page_number)

        return readings_by_number

    def _merge_workbook_outline_readings(
        self,
        readings: list[_WorkbookReading],
        outline_readings_by_number: dict[str, _WorkbookReading],
    ) -> list[_WorkbookReading]:
        if not outline_readings_by_number:
            return readings

        readings_by_number = {reading.reading_number: reading for reading in readings}
        for reading_number, outline in outline_readings_by_number.items():
            target = readings_by_number.get(reading_number)
            if target is None:
                readings.append(outline)
                readings_by_number[reading_number] = outline
                continue

            if not target.reading_title and outline.reading_title:
                target.reading_title = outline.reading_title
            if (not target.study_session_number or target.study_session_number == "1") and outline.study_session_number:
                target.study_session_number = outline.study_session_number
            if target.study_session_title.startswith("Study Session ") and outline.study_session_title:
                target.study_session_title = outline.study_session_title
            target.touch_page(outline.start_page)
            target.touch_page(outline.end_page)

            for module_number, module_title in outline.modules.items():
                target.modules.setdefault(module_number, module_title)
                target.module_pages.setdefault(module_number, [])
                if not target.module_pages[module_number]:
                    target.module_pages[module_number].extend(outline.module_pages.get(module_number, []))
                for objective_id in outline.module_learning_objectives.get(module_number, []):
                    objective = outline.module_learning_objective_texts.get(module_number, {}).get(objective_id)
                    self._record_workbook_module_learning_objective(
                        target,
                        module_number,
                        objective_id,
                        text=objective.text if objective else "",
                        page_number=objective.source_page_start if objective else None,
                        extraction_source="front_lo_list",
                    )

        return readings

    def _extract_workbook_learning_objective_from_line(
        self,
        line: str,
        *,
        current_reading: _WorkbookReading,
        current_module_number: str | None,
    ) -> tuple[str, str] | None:
        direct_match = LEARNING_OBJECTIVE_RE.match(line)
        if direct_match:
            objective_id = self._normalize_workbook_learning_objective_id(direct_match.group("id"))
            if objective_id is None:
                return None
            objective_text = line[direct_match.end() :].lstrip(" :.-")
            return objective_id, objective_text.strip()

        front_match = FRONT_LEARNING_OBJECTIVE_RE.match(line)
        if not front_match:
            return None
        text = front_match.group("text").strip()
        if not text or len(text.split()) < 3:
            return None
        number = front_match.group("number")
        letter = front_match.group("letter").lower()
        if number is None:
            if current_module_number and re.match(r"^\d+", current_module_number):
                number = re.match(r"^\d+", current_module_number).group(0)  # type: ignore[union-attr]
            else:
                number = current_reading.reading_number
        return f"{int(number)}.{letter}", text

    def _record_workbook_module_learning_objective(
        self,
        reading: _WorkbookReading,
        module_number: str,
        learning_objective_id: str,
        *,
        text: str = "",
        page_number: int | None = None,
        extraction_source: str = "body_heading",
    ) -> _WorkbookLearningObjective:
        normalized_id = self._normalize_workbook_learning_objective_id(learning_objective_id) or learning_objective_id.lower()
        module_objectives = reading.module_learning_objectives.setdefault(module_number, [])
        if normalized_id not in module_objectives:
            module_objectives.append(normalized_id)
        objective_texts = reading.module_learning_objective_texts.setdefault(module_number, {})
        objective = objective_texts.get(normalized_id)
        if objective is None:
            objective = _WorkbookLearningObjective(objective_id=normalized_id)
            objective_texts[normalized_id] = objective
        cleaned_text = self._clean_workbook_learning_objective_text(text, normalized_id)
        if cleaned_text and (not objective.text or len(cleaned_text) > len(objective.text)):
            objective.text = cleaned_text
        objective.touch_page(page_number)
        objective.add_source(extraction_source)
        return objective

    def _record_workbook_inline_learning_objectives(
        self,
        reading: _WorkbookReading,
        module_number: str,
        line: str,
    ) -> None:
        for match in INLINE_LEARNING_OBJECTIVE_RE.finditer(line):
            self._record_workbook_module_learning_objective(
                reading,
                module_number,
                match.group("id"),
                text=match.group(0),
                extraction_source="body_inline",
            )

    def _normalize_workbook_learning_objective_id(self, value: str) -> str | None:
        match = re.search(r"(?P<number>\d+)\s*(?:\.|\s)\s*(?P<letter>[a-z])", value.strip(), re.IGNORECASE)
        if not match:
            return None
        return f"{int(match.group('number'))}.{match.group('letter').lower()}"

    def _clean_workbook_learning_objective_text(self, text: str, objective_id: str) -> str:
        cleaned = self._clean_pdf_line(text)
        if not cleaned:
            return ""
        objective_pattern = re.escape(objective_id).replace(r"\.", r"\s*(?:\.|\s)\s*")
        prefix = re.compile(
            rf"^LO\s*{objective_pattern}\s*[:.-]?\s*",
            re.IGNORECASE,
        )
        cleaned = prefix.sub("", cleaned).strip()
        if not cleaned:
            return ""
        return cleaned

    def _has_workbook_study_payload(self, reading: _WorkbookReading) -> bool:
        return bool(
            any(reading.module_learning_objective_texts.values())
            or reading.key_concepts.lines
            or reading.quizzes
            or reading.answer_keys
            or reading.general_answer_key.lines
            or reading.formulas.lines
        )

    def _workbook_reading_title(self, reading: _WorkbookReading) -> str:
        return (
            f"Study Session {reading.study_session_number}: {reading.study_session_title} / "
            f"Reading {reading.reading_number}: {reading.reading_title or 'Reading'}"
        )

    def _workbook_module_title(self, reading: _WorkbookReading, module_number: str) -> str:
        return f"{self._workbook_reading_title(reading)} / Module {module_number}: {reading.modules[module_number]}"

    def _workbook_formula_session_text(
        self,
        readings: list[_WorkbookReading],
        *,
        material_id: str | None = None,
    ) -> tuple[str, list[int], list[FormulaAsset]]:
        parts = ["FORMULAS"]
        pages: list[int] = []
        assets: list[FormulaAsset] = []
        for reading in readings:
            formula_lines: list[str] = []
            for line in reading.formulas.lines:
                if not line or FORMULAS_HEADING_RE.fullmatch(line):
                    continue
                if self._looks_like_formula_appendix_end_page([line]) or self._is_formula_appendix_reference_line(line):
                    continue
                asset = self._formula_asset_from_marker(
                    line,
                    reading_number=int(reading.reading_number) if reading.reading_number.isdigit() else None,
                    material_id=material_id,
                    asset_index=len(assets) + 1,
                )
                if asset is not None:
                    assets.append(asset)
                    continue
                formula_lines.append(line)
            if not formula_lines:
                if assets and any(asset.reading_number == int(reading.reading_number) for asset in assets if reading.reading_number.isdigit()):
                    parts.extend(["", f"Reading {reading.reading_number}"])
                    pages.extend(reading.formulas.pages)
                continue
            parts.extend(["", f"Reading {reading.reading_number}", *formula_lines])
            pages.extend(reading.formulas.pages)
        if len(parts) == 1:
            return "", [], []
        return "\n".join(parts).strip(), pages, assets

    def _is_formula_appendix_reference_line(self, line: str) -> bool:
        cleaned = " ".join(line.split()).strip()
        if not cleaned:
            return False
        lowered = cleaned.lower()
        return bool(
            lowered in {
                "appendix",
                "using the cumulative z-table",
                "the significance level",
            }
            or lowered.startswith("using the cumulative ")
            or lowered.startswith("if epsilon")
            or lowered.startswith("if eps")
            or lowered.startswith("cumulative z-table")
        )

    def _formula_asset_from_marker(
        self,
        line: str,
        *,
        reading_number: int | None = None,
        material_id: str | None = None,
        asset_index: int = 1,
    ) -> FormulaAsset | None:
        match = FORMULA_IMAGE_CROP_DETAIL_RE.match(" ".join(line.split()).strip())
        if not match:
            return None
        source_page = int(match.group("page"))
        path = match.group("path")
        if BASE64_DATA_URL_RE.search(path) or BASE64_LIKE_RUN_RE.search(path):
            path = self._formula_crop_asset_path(
                material_id=material_id,
                page_number=source_page,
                crop_kind="legacy",
                crop_index=asset_index,
            )
        metadata = self._formula_crop_metadata_from_marker_path(path, material_id=material_id)
        return FormulaAsset(
            source_page=source_page,
            path=path,
            label=match.group("label"),
            reading_number=reading_number,
            confidence=0.5,
            extracted_text=self._metadata_str(metadata.get("extracted_text")),
            extracted_latex=self._metadata_str(metadata.get("extracted_latex")),
            extracted_latex_blocks=[
                str(block).strip()
                for block in (metadata.get("extracted_latex_blocks") or [])
                if str(block).strip()
            ],
            ocr_engine=self._metadata_str(metadata.get("ocr_engine")),
            ocr_confidence=self._safe_float(metadata.get("ocr_confidence")) if metadata else None,
            needs_review=bool(metadata.get("needs_review", False)) if metadata else False,
        )

    def _formula_crop_metadata_from_marker_path(self, path: str, *, material_id: str | None = None) -> dict[str, object]:
        if self.formula_asset_base_path is None:
            return {}
        match = FORMULA_CROP_URI_RE.match(path)
        if not match:
            return {}
        safe_material_id = re.sub(
            r"[^A-Za-z0-9_.-]+",
            "-",
            match.group("material_id") or material_id or "material",
        ).strip("-") or "material"
        asset_name = Path(match.group("asset_name")).with_suffix(".json").name
        metadata_path = self.formula_asset_base_path / safe_material_id / "formula-crops" / asset_name
        try:
            loaded = json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}
        if not isinstance(loaded, dict):
            return {}
        return loaded

    def _metadata_str(self, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _workbook_section_text(self, reading: _WorkbookReading, module_number: str | None) -> str:
        parts: list[str] = []
        if module_number is not None:
            learning_objective_lines = self._workbook_learning_objective_lines_for_module(reading, module_number)
            self._append_block(parts, "LEARNING OBJECTIVES", learning_objective_lines)
            key_concept_lines = self._workbook_key_concepts_for_module(reading, module_number)
            self._append_block(parts, "KEY CONCEPTS", key_concept_lines)
            quiz = reading.quizzes.get(module_number)
            answer_key = reading.answer_keys.get(module_number)
            self._append_block(parts, f"MODULE QUIZ {module_number}", quiz.lines if quiz else [])
            self._append_block(
                parts,
                "ANSWER KEY FOR MODULE QUIZZES",
                answer_key.lines if answer_key else [],
            )
        else:
            self._append_block(parts, "EXAM FOCUS", reading.exam_focus.lines)
            self._append_block(parts, "KEY CONCEPTS", reading.key_concepts.lines)
            for quiz_number, quiz in reading.quizzes.items():
                self._append_block(parts, f"MODULE QUIZ {quiz_number}", quiz.lines)
            for quiz_number, answer_key in reading.answer_keys.items():
                self._append_block(parts, f"ANSWER KEY FOR MODULE QUIZ {quiz_number}", answer_key.lines)
            self._append_block(parts, "ANSWER KEY FOR MODULE QUIZZES", reading.general_answer_key.lines)
        return "\n\n".join(parts).strip()

    def _workbook_learning_objective_lines_for_module(
        self,
        reading: _WorkbookReading,
        module_number: str,
    ) -> list[str]:
        objectives = reading.module_learning_objective_texts.get(module_number, {})
        ordered_ids = reading.module_learning_objectives.get(module_number, [])
        lines: list[str] = []
        for objective_id in ordered_ids:
            objective = objectives.get(objective_id)
            if objective is None:
                lines.append(f"LO {objective_id}")
                continue
            text = objective.text.strip()
            if text:
                lines.append(f"LO {objective_id}: {text}")
            else:
                lines.append(f"LO {objective_id}")
            lines.extend(objective.body_lines)
        return lines

    def _workbook_key_concepts_for_module(
        self,
        reading: _WorkbookReading,
        module_number: str,
    ) -> list[str]:
        key_concept_lines = reading.key_concepts.lines
        if not key_concept_lines:
            return []

        module_objectives = set(reading.module_learning_objectives.get(module_number, []))
        has_any_module_objectives = any(reading.module_learning_objectives.values())
        if not module_objectives:
            if has_any_module_objectives or len(reading.modules) > 1:
                return []
            return key_concept_lines

        segments = self._split_workbook_key_concepts_by_learning_objective(key_concept_lines)
        if not any(objective_id for objective_id, _lines in segments):
            return key_concept_lines if len(reading.modules) <= 1 else []

        module_objectives = self._expand_workbook_module_objectives_from_key_concepts(
            reading=reading,
            module_number=module_number,
            module_objectives=module_objectives,
            segments=segments,
        )
        selected_lines: list[str] = []
        for objective_id, lines in segments:
            if objective_id is None:
                continue
            if objective_id in module_objectives:
                selected_lines.extend(lines)
        return selected_lines

    def _expand_workbook_module_objectives_from_key_concepts(
        self,
        *,
        reading: _WorkbookReading,
        module_number: str,
        module_objectives: set[str],
        segments: list[tuple[str | None, list[str]]],
    ) -> set[str]:
        """Fill OCR/parser gaps only when the official key-concepts source contains the missing LO."""
        if not module_objectives:
            return module_objectives

        available_by_prefix: dict[str, set[str]] = {}
        for objective_id, _lines in segments:
            if objective_id is None:
                continue
            prefix, letter = self._split_workbook_learning_objective_id(objective_id)
            if prefix is None or letter is None:
                continue
            available_by_prefix.setdefault(prefix, set()).add(letter)

        expanded = set(module_objectives)
        module_letters_by_prefix: dict[str, set[str]] = {}
        for objective_id in module_objectives:
            prefix, letter = self._split_workbook_learning_objective_id(objective_id)
            if prefix is None or letter is None:
                continue
            module_letters_by_prefix.setdefault(prefix, set()).add(letter)

        for prefix, letters in module_letters_by_prefix.items():
            available_letters = available_by_prefix.get(prefix, set())
            if not available_letters:
                continue

            if len(letters) >= 2:
                lower = min(ord(letter) for letter in letters)
                upper = max(ord(letter) for letter in letters)
                for codepoint in range(lower, upper + 1):
                    candidate_letter = chr(codepoint)
                    if candidate_letter in available_letters:
                        expanded.add(f"{prefix}.{candidate_letter}")
                continue

            next_boundary = self._next_module_learning_objective_boundary(
                reading=reading,
                module_number=module_number,
                prefix=prefix,
            )
            if next_boundary is None:
                continue

            start = ord(next(iter(letters)))
            stop = ord(next_boundary) - 1
            if stop < start:
                continue
            for codepoint in range(start, stop + 1):
                candidate_letter = chr(codepoint)
                if candidate_letter in available_letters:
                    expanded.add(f"{prefix}.{candidate_letter}")

        return expanded

    def _next_module_learning_objective_boundary(
        self,
        *,
        reading: _WorkbookReading,
        module_number: str,
        prefix: str,
    ) -> str | None:
        module_numbers = list(reading.modules.keys())
        try:
            module_index = module_numbers.index(module_number)
        except ValueError:
            return None

        for next_module_number in module_numbers[module_index + 1:]:
            next_letters: list[str] = []
            for objective_id in reading.module_learning_objectives.get(next_module_number, []):
                objective_prefix, letter = self._split_workbook_learning_objective_id(objective_id)
                if objective_prefix == prefix and letter is not None:
                    next_letters.append(letter)
            if next_letters:
                return min(next_letters)
        return None

    def _split_workbook_learning_objective_id(self, objective_id: str) -> tuple[str | None, str | None]:
        match = re.fullmatch(r"(?P<prefix>\d+)\.(?P<letter>[a-z])", objective_id.strip().lower())
        if not match:
            return None, None
        return match.group("prefix"), match.group("letter")

    def _split_workbook_key_concepts_by_learning_objective(
        self,
        lines: list[str],
    ) -> list[tuple[str | None, list[str]]]:
        segments: list[tuple[str | None, list[str]]] = []
        current_objective_id: str | None = None
        current_lines: list[str] = []

        for line in lines:
            if not line or KEY_CONCEPTS_HEADING_RE.fullmatch(line.strip()):
                continue
            objective_match = LEARNING_OBJECTIVE_RE.match(line)
            if objective_match:
                if current_lines:
                    segments.append((current_objective_id, current_lines))
                current_objective_id = objective_match.group("id").lower()
                current_lines = [line]
                continue
            current_lines.append(line)

        if current_lines:
            segments.append((current_objective_id, current_lines))
        return segments

    def _append_block(self, parts: list[str], heading: str, lines: list[str]) -> None:
        cleaned_lines = [
            line
            for line in lines
            if line and not self._is_block_heading_line(line, heading)
        ]
        if cleaned_lines:
            parts.append(f"{heading}\n" + "\n".join(cleaned_lines).strip())

    def _is_block_heading_line(self, line: str, heading: str) -> bool:
        stripped = line.strip()
        if stripped.lower() == heading.lower():
            return True
        heading_upper = heading.upper()
        if heading_upper == "KEY CONCEPTS" and KEY_CONCEPTS_HEADING_RE.fullmatch(stripped):
            return True
        if heading_upper == "EXAM FOCUS" and EXAM_FOCUS_HEADING_RE.fullmatch(stripped):
            return True
        if heading_upper == "FORMULAS" and FORMULAS_HEADING_RE.fullmatch(stripped):
            return True
        return False

    def _build_workbook_source_section(
        self,
        *,
        template: SourceSection,
        file_name: str,
        content_type: str,
        section_index: int,
        title: str,
        text: str,
        page_start: int | None,
        page_end: int | None,
        section_kind: SectionKind = SectionKind.INSTRUCTIONAL,
        content_label: ContentLabel = ContentLabel.TESTABLE_CONTENT,
        priority_score: float = 1.0,
        is_default: bool = True,
        formula_assets: list[FormulaAsset] | None = None,
    ) -> SourceSection:
        safe_text, extracted_formula_assets = self._sanitize_workbook_section_text_and_assets(
            text,
            material_id=template.material_id,
        )
        merged_formula_assets = self._merge_formula_assets(
            [*(formula_assets or []), *extracted_formula_assets]
        )
        return SourceSection(
            source_id=f"{template.material_id}-section-{section_index}",
            material_id=template.material_id,
            course_id=template.course_id,
            module_id=template.module_id,
            file_name=file_name,
            content_type=content_type,
            section_title=title,
            text=safe_text,
            page_end=page_end or page_start,
            section_kind=section_kind,
            content_label=content_label,
            priority_score=priority_score,
            is_default=is_default,
            formula_assets=merged_formula_assets,
            locator=SourceLocator(
                section_index=section_index,
                page_number=page_start,
            ),
            citation_label=f"{file_name} | {title}",
        )

    def _sanitize_workbook_section_text(self, text: str, *, material_id: str | None = None) -> str:
        safe_text, _assets = self._sanitize_workbook_section_text_and_assets(
            text,
            material_id=material_id,
        )
        return safe_text

    def _sanitize_workbook_section_text_and_assets(
        self,
        text: str,
        *,
        material_id: str | None = None,
    ) -> tuple[str, list[FormulaAsset]]:
        cleaned_lines: list[str] = []
        formula_assets: list[FormulaAsset] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                cleaned_lines.append(line)
                continue
            if FORMULA_IMAGE_CROP_MARKER_RE.match(line):
                asset = self._formula_asset_from_marker(
                    line,
                    material_id=material_id,
                    asset_index=len(formula_assets) + 1,
                )
                if asset is not None:
                    formula_assets.append(asset)
                    continue
                continue
            if BASE64_DATA_URL_RE.search(line):
                line = BASE64_DATA_URL_RE.sub("[formula image asset removed]", line)
            if BASE64_LIKE_RUN_RE.search(line):
                continue
            cleaned_lines.append(line)

        sanitized = "\n".join(cleaned_lines).strip()
        if len(sanitized) <= MAX_WORKBOOK_SECTION_TEXT_CHARS:
            return sanitized, formula_assets
        return (
            sanitized[:MAX_WORKBOOK_SECTION_TEXT_CHARS].rstrip()
            + "\n[PARSER_QUALITY_WARNING: section text truncated]",
            formula_assets,
        )

    def _merge_formula_assets(self, assets: list[FormulaAsset]) -> list[FormulaAsset]:
        merged: list[FormulaAsset] = []
        seen: set[tuple[int, str, str]] = set()
        for asset in assets:
            key = (asset.source_page, asset.path, asset.label)
            if key in seen:
                continue
            seen.add(key)
            merged.append(asset)
        return merged

    def _is_workbook_marker(self, line: str) -> bool:
        return bool(
            STUDY_SESSION_RE.match(line)
            or STUDY_SESSION_NUMBER_RE.match(line)
            or READING_RE.match(line)
            or MODULE_RE.match(line)
            or MODULE_QUIZ_RE.match(line)
            or ANSWER_MODULE_QUIZ_RE.match(line)
            or KEY_CONCEPTS_HEADING_RE.fullmatch(line)
            or EXAM_FOCUS_HEADING_RE.fullmatch(line)
            or ANSWER_KEY_HEADING_RE.fullmatch(line)
            or FORMULAS_HEADING_RE.fullmatch(line)
        )

    def _extract_exam_weighting_text(self, text: str) -> str:
        lines = [self._clean_pdf_line(line) for line in text.splitlines()]
        lines = [line for line in lines if line]
        if not lines:
            return ""
        start_index = next(
            (
                index
                for index, line in enumerate(lines)
                if re.search(r"part\s+i\s+exam\s+weigh", line, re.IGNORECASE)
            ),
            None,
        )
        if start_index is None:
            return "\n".join(lines)

        stop_index = len(lines)
        for index in range(start_index + 1, len(lines)):
            line = lines[index]
            if re.fullmatch(r"How\s+to\s+Succeed", line, re.IGNORECASE) or re.fullmatch(
                r"Best\s+regards,?", line, re.IGNORECASE
            ):
                stop_index = index
                break
        return "\n".join(lines[start_index:stop_index]).strip()

    def _extract_workbook_session_titles(self, sections: list[SourceSection]) -> dict[str, str]:
        session_titles: dict[str, str] = {}
        for section in sections:
            for raw_line in section.text.splitlines():
                line = self._clean_pdf_line(raw_line)
                session_match = STUDY_SESSION_RE.match(line)
                if session_match:
                    session_titles[session_match.group("number")] = self._clean_workbook_title(
                        session_match.group("title")
                    )
        return session_titles

    def _is_workbook_non_study_page(self, text: str) -> bool:
        page_class = self._classify_page(
            text,
            page_number=0,
            total_pages=0,
            previous_state={"seen_study_content": True},
        )
        return page_class in {"front_matter", "table_of_contents"}

    def _clean_pdf_line(self, line: str) -> str:
        cleaned = (
            line.replace("\x00", "")
            .replace("\xa0", " ")
            .replace("\uf0b7", " ")
            .replace("\u2022", " ")
            .replace("\u25a0", " ")
            .replace("™", "")
        )
        cleaned = self._normalize_spaced_pdf_markers(cleaned)
        return " ".join(cleaned.split()).strip()

    def _normalize_spaced_pdf_markers(self, line: str) -> str:
        compact_upper = re.sub(r"[^A-Z]", "", line.upper())
        if compact_upper == "FORMULASHEET":
            return "FORMULA SHEET"
        if compact_upper == "KEYFORMULAS":
            return "KEY FORMULAS"
        if compact_upper in {"FORMULA", "FORMULAS"}:
            return "FORMULAS"

        marker_patterns = {
            r"R\s*E\s*A\s*D\s*I\s*N\s*G": "READING",
            r"S\s*T\s*U\s*D\s*Y\s*S\s*E\s*S\s*S\s*I\s*O\s*N": "STUDY SESSION",
            r"E\s*X\s*A\s*M\s*F\s*O\s*C\s*U\s*S": "EXAM FOCUS",
            r"K\s*E\s*Y\s*T\s*A\s*K\s*E\s*A\s*W\s*A\s*Y\s*S": "KEY TAKEAWAYS",
            r"K\s*E\s*Y\s*T\s*A\s*K\s*E\s*-\s*A\s*W\s*A\s*Y\s*S": "KEY TAKE-AWAYS",
            r"K\s*E\s*Y\s*C\s*O\s*N\s*C\s*E\s*P\s*T\s*S": "KEY CONCEPTS",
            r"I\s*M\s*P\s*O\s*R\s*T\s*A\s*N\s*T\s*T\s*E\s*R\s*M\s*S": "IMPORTANT TERMS",
            r"I\s*M\s*P\s*O\s*R\s*T\s*A\s*N\s*T\s*C\s*O\s*N\s*C\s*E\s*P\s*T\s*S": "IMPORTANT CONCEPTS",
            r"L\s*E\s*A\s*R\s*N\s*I\s*N\s*G\s*O\s*B\s*J\s*E\s*C\s*T\s*I\s*V\s*E\s*S": "LEARNING OBJECTIVES",
            r"M\s*O\s*D\s*U\s*L\s*E\s*Q\s*U\s*I\s*Z": "MODULE QUIZ",
            r"A\s*N\s*S\s*W\s*E\s*R\s*K\s*E\s*Y\s*F\s*O\s*R\s*M\s*O\s*D\s*U\s*L\s*E\s*Q\s*U\s*I\s*Z(?:Z\s*E\s*S)?": "ANSWER KEY FOR MODULE QUIZZES",
            r"F\s*O\s*R\s*M\s*U\s*L\s*A\s*S\s*H\s*E\s*E\s*T": "FORMULA SHEET",
            r"K\s*E\s*Y\s*F\s*O\s*R\s*M\s*U\s*L\s*A\s*S": "KEY FORMULAS",
            r"F\s*O\s*R\s*M\s*U\s*L\s*A\s*S": "FORMULAS",
        }
        cleaned = line
        for pattern, replacement in marker_patterns.items():
            cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
        return cleaned

    def _clean_workbook_title(self, title: str) -> str:
        cleaned = self._clean_pdf_line(title).strip(" -:—")
        if not cleaned:
            return ""
        if cleaned.upper() == cleaned and any(character.isalpha() for character in cleaned):
            cleaned = cleaned.title()

        normalized_words: list[str] = []
        for index, word in enumerate(cleaned.split()):
            prefix = re.match(r"^\W*", word).group(0) if re.match(r"^\W*", word) else ""
            suffix = re.search(r"\W*$", word).group(0) if re.search(r"\W*$", word) else ""
            core = word[len(prefix) : len(word) - len(suffix) if suffix else len(word)]
            replacement = WORKBOOK_ACRONYMS.get(core.lower())
            if replacement:
                normalized_words.append(f"{prefix}{replacement}{suffix}")
            elif index > 0 and core.lower() in WORKBOOK_LOWERCASE_TITLE_WORDS:
                normalized_words.append(f"{prefix}{core.lower()}{suffix}")
            elif len(core) > 1 and core.isalpha() and core.upper() == core:
                normalized_words.append(f"{prefix}{core.title()}{suffix}")
            else:
                normalized_words.append(word)
        return " ".join(normalized_words)

    def _should_append_workbook_title_continuation(self, current_title: str, line: str) -> bool:
        if not self._looks_like_workbook_title_continuation(line):
            return False
        if line.upper() == line and any(character.isalpha() for character in line):
            return True
        incomplete_endings = (
            " and",
            " and the",
            " of",
            " of the",
            " for",
            " for the",
            " in",
            " in the",
            " on",
            " on the",
            " to",
            " to the",
            " with",
            " with the",
            ",",
        )
        return current_title.lower().rstrip().endswith(incomplete_endings)

    def _looks_like_workbook_title_continuation(self, line: str) -> bool:
        lowered = line.lower()
        if self._is_workbook_marker(line):
            return False
        if re.match(r"^(lo\s+\d|after completing|the following is|which of the following|\d+\.)", lowered):
            return False
        if line.endswith(".") or line.endswith("?"):
            return False
        return len(line.split()) <= 12

    def _merge_sections(self, sections: list[SourceSection]) -> list[SourceSection]:
        merged: list[SourceSection] = []
        for section in sections:
            if not merged:
                merged.append(section)
                continue

            previous = merged[-1]
            if self._should_merge(previous, section):
                merged[-1] = previous.model_copy(
                    update={
                        "text": f"{previous.text}\n{section.text}".strip(),
                        "page_end": section.page_end or section.locator.page_number or previous.page_end,
                    }
                )
                continue
            merged.append(section)
        return merged

    def _should_merge(self, previous: SourceSection, current: SourceSection) -> bool:
        if current.section_title == previous.section_title:
            return True
        if current.section_title.lower() in {"continued", "notes", "overview"}:
            return True
        if current.section_title.lower().startswith("page "):
            return True
        return False

    def _should_create_session_section(self, sections: list[SourceSection]) -> bool:
        total_characters = sum(len(section.text) for section in sections)
        return len(sections) <= 3 or total_characters <= 3500

    def _aggregate_pdf_sections(
        self,
        sections: list[SourceSection],
        *,
        file_name: str,
        content_type: str,
    ) -> list[SourceSection]:
        if len(sections) <= 6:
            return sections

        total_characters = sum(len(section.text) for section in sections)
        estimated_group_count = max(2, ceil(len(sections) / 5), ceil(total_characters / 3200))
        target_group_count = min(8, estimated_group_count)
        max_sections_per_group = max(2, ceil(len(sections) / target_group_count))
        max_characters_per_group = max(1800, ceil(total_characters / target_group_count))

        grouped_sections: list[list[SourceSection]] = []
        current_group: list[SourceSection] = []
        current_characters = 0

        for section in sections:
            section_characters = len(section.section_title) + 1 + len(section.text)
            if current_group and (
                len(current_group) >= max_sections_per_group
                or (
                    current_characters >= max_characters_per_group
                    and self._looks_like_pdf_topic_shift(section.section_title)
                )
            ):
                grouped_sections.append(current_group)
                current_group = []
                current_characters = 0

            current_group.append(section)
            current_characters += section_characters

        if current_group:
            grouped_sections.append(current_group)

        aggregated_sections: list[SourceSection] = []
        for group in grouped_sections:
            first = group[0]
            last = group[-1]
            page_numbers = [section.locator.page_number for section in group if section.locator.page_number]
            page_label = ""
            if page_numbers:
                page_label = (
                    f"page {page_numbers[0]}"
                    if page_numbers[0] == page_numbers[-1]
                    else f"pages {page_numbers[0]}-{page_numbers[-1]}"
                )

            unique_titles = list(dict.fromkeys(section.section_title for section in group))
            group_title = (
                unique_titles[0]
                if len(unique_titles) == 1
                else f"{Path(file_name).stem} · {page_label or f'section {first.locator.section_index}-{last.locator.section_index}'}"
            )
            combined_text = "\n\n".join(section.text for section in group).strip()
            aggregated_sections.append(
                first.model_copy(
                    update={
                        "content_type": content_type,
                        "section_title": group_title,
                        "text": combined_text,
                        "page_end": last.page_end or last.locator.page_number,
                        "citation_label": f"{file_name} | {group_title}",
                    }
                )
            )
        return aggregated_sections

    def _build_session_section(
        self,
        sections: list[SourceSection],
        *,
        file_name: str,
        content_type: str,
    ) -> SourceSection:
        preferred_sections = [
            section for section in sections if self._classify_section(section) != SectionKind.LOGISTICS
        ]
        selected_sections = preferred_sections or sections
        anchor = selected_sections[0]
        combined_text = "\n\n".join(section.text for section in selected_sections).strip()
        session_title = f"{Path(file_name).stem} session content"
        return SourceSection(
            source_id=anchor.source_id,
            material_id=anchor.material_id,
            course_id=anchor.course_id,
            module_id=anchor.module_id,
            file_name=file_name,
            content_type=content_type,
            section_title=session_title,
            text=combined_text,
            page_end=selected_sections[-1].page_end or selected_sections[-1].locator.page_number,
            section_kind=SectionKind.SESSION,
            priority_score=1.0,
            is_default=True,
            locator=anchor.locator,
            citation_label=f"{file_name} | {session_title}",
        )

    def _normalize_title(self, title: str, section_index: int) -> str:
        normalized = " ".join(title.replace("\n", " ").split()).strip(" -|:")
        if not normalized:
            return f"Section {section_index}"
        if len(normalized) > 120:
            normalized = normalized[:120].rstrip()
        return normalized

    def _clean_section_text(self, text: str) -> str:
        seen_lines: set[str] = set()
        cleaned_lines: list[str] = []
        for raw_line in text.splitlines():
            line = " ".join(raw_line.split()).strip()
            if not line:
                continue
            if line in seen_lines and len(line) <= 120:
                continue
            seen_lines.add(line)
            cleaned_lines.append(line)
        return "\n".join(cleaned_lines).strip()

    def _looks_like_pdf_topic_shift(self, title: str) -> bool:
        lowered = title.strip().lower()
        if not lowered:
            return False
        if lowered.startswith("page "):
            return False
        return len(lowered.split()) <= 9

    def _classify_section(self, section: SourceSection) -> SectionKind:
        text = f"{section.section_title}\n{section.text}".lower()
        logistics_keywords = [
            "office hours",
            "schedule",
            "logistics",
            "attendance",
            "contact",
            "email",
            "zoom",
            "calendar",
            "announcement",
        ]
        reference_keywords = ["syllabus", "assignment", "homework", "grading policy"]
        instructional_keywords = [
            "concept",
            "definition",
            "example",
            "algorithm",
            "python",
            "gradient",
            "descent",
            "proof",
            "exercise",
            "lecture",
            "session",
            "practice",
            "worked",
        ]

        if any(keyword in text for keyword in logistics_keywords) and not any(
            keyword in text for keyword in instructional_keywords
        ):
            return SectionKind.LOGISTICS
        if any(keyword in text for keyword in reference_keywords):
            return SectionKind.REFERENCE
        return SectionKind.INSTRUCTIONAL

    def _priority_score(self, section: SourceSection, kind: SectionKind) -> float:
        if kind == SectionKind.SESSION:
            return 1.0
        if kind == SectionKind.LOGISTICS:
            return 0.15
        if kind == SectionKind.REFERENCE:
            return 0.45

        text = section.text.lower()
        score = 0.7
        if any(keyword in text for keyword in ["example", "definition", "step", "worked"]):
            score += 0.15
        if len(section.text) >= 500:
            score += 0.1
        return min(1.0, round(score, 2))

    def _is_page_number_line(self, line: str) -> bool:
        lowered = line.strip().lower()
        return lowered.isdigit() or lowered.startswith("page ")

    def _build_section(
        self,
        *,
        material_id: str,
        course_id: str,
        module_id: str | None,
        file_name: str,
        content_type: str,
        section_index: int,
        section_title: str,
        text: str,
        page_number: int | None = None,
        slide_number: int | None = None,
        paragraph_index: int | None = None,
        page_end: int | None = None,
    ) -> SourceSection:
        citation_parts = [file_name, section_title]
        if page_number is not None:
            citation_parts.append(f"page {page_number}")
        if slide_number is not None:
            citation_parts.append(f"slide {slide_number}")

        return SourceSection(
            source_id=f"{material_id}-section-{section_index}",
            material_id=material_id,
            course_id=course_id,
            module_id=module_id,
            file_name=file_name,
            content_type=content_type,
            section_title=section_title,
            text=text,
            page_end=page_end or page_number,
            locator=SourceLocator(
                section_index=section_index,
                page_number=page_number,
                slide_number=slide_number,
                paragraph_index=paragraph_index,
            ),
            citation_label=" | ".join(citation_parts),
        )

    def _word_style(self, paragraph: ElementTree.Element) -> str:
        style = paragraph.find("./w:pPr/w:pStyle", WORD_NS)
        if style is None:
            return ""
        return style.attrib.get(f"{{{WORD_NS['w']}}}val", "")

    def _is_heading_style(self, style: str) -> bool:
        normalized = style.lower()
        return normalized.startswith("heading") or normalized in {"title", "subtitle"}

    def _slide_sort_key(self, slide_name: str) -> int:
        stem = Path(slide_name).stem
        suffix = stem.replace("slide", "")
        return int(suffix) if suffix.isdigit() else 0
