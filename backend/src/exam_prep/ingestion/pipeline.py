import mimetypes
from datetime import UTC, datetime
from hashlib import sha256
import io
import json
import logging
from pathlib import Path
import re
from uuid import uuid4

from pypdf import PdfReader

from exam_prep.core.exceptions import MaterialIngestionError
from exam_prep.repositories.material_store import MaterialStore
from exam_prep.repositories.vector_store import VectorStore
from exam_prep.retrieval.chunking import ChunkingService
from exam_prep.retrieval.grounding import GroundingService
from exam_prep.schemas.materials import (
    MaterialParseStatus,
    MaterialProcessingStage,
    MaterialRecord,
    MaterialStudyDocument,
    MaterialStageStatus,
    ParsedMaterialDocument,
    SourceSection,
)
from exam_prep.ingestion.parsers import DocumentParser
from exam_prep.services.section_study_service import SectionStudyService


logger = logging.getLogger(__name__)


class IngestionPipeline:
    def __init__(
        self,
        *,
        store: MaterialStore,
        vector_store: VectorStore | None = None,
        parser: DocumentParser | None = None,
        chunking_service: ChunkingService | None = None,
    ) -> None:
        self.store = store
        self.vector_store = vector_store
        formula_asset_base_path = getattr(store, "base_path", None)
        self.parser = parser or DocumentParser(
            formula_asset_base_path=Path(formula_asset_base_path) if formula_asset_base_path else None
        )
        self.chunking_service = chunking_service or ChunkingService()
        self.grounding_service = (
            GroundingService(material_store=store, vector_store=vector_store)
            if vector_store is not None
            else None
        )

    def ingest(
        self,
        *,
        course_id: str,
        module_id: str | None = None,
        file_name: str,
        content_type: str | None,
        data: bytes,
    ) -> MaterialRecord:
        record = self.register_upload(
            course_id=course_id,
            module_id=module_id,
            file_name=file_name,
            content_type=content_type,
            data=data,
        )
        return self.process_registered_material(record.material_id)

    def register_upload(
        self,
        *,
        course_id: str,
        module_id: str | None = None,
        file_name: str,
        content_type: str | None,
        data: bytes,
    ) -> MaterialRecord:
        if not data:
            raise MaterialIngestionError("Uploaded file is empty.")

        normalized_name = Path(file_name).name
        if not normalized_name:
            raise MaterialIngestionError("A file name is required.")

        resolved_content_type = content_type or mimetypes.guess_type(normalized_name)[0] or "application/octet-stream"
        material_id = uuid4().hex
        registered_record = MaterialRecord(
            material_id=material_id,
            course_id=course_id,
            module_id=module_id,
            file_name=normalized_name,
            display_name=normalized_name,
            uploaded_at=datetime.now(UTC).isoformat(),
            content_type=resolved_content_type,
            status=MaterialParseStatus.PENDING,
            page_count=self._estimate_page_count(normalized_name, data),
            processing_status=MaterialProcessingStage.REGISTERED,
            processing_progress=5,
            outline_status=MaterialStageStatus.PENDING,
            enrichment_status=MaterialStageStatus.PENDING,
            content_hash=sha256(data).hexdigest(),
        )
        return self.store.save_raw_material(registered_record, data)

    def process_registered_material(self, material_id: str) -> MaterialRecord:
        processing_record = self.store.get_record(material_id)
        if processing_record is None:
            raise MaterialIngestionError("Material not found.")
        data = self.store.get_raw_material(material_id)
        if data is None:
            raise MaterialIngestionError("Uploaded source file not found.")

        self.store.save_record(
            processing_record.model_copy(
                update={
                    "status": MaterialParseStatus.PROCESSING,
                    "processing_status": MaterialProcessingStage.EXTRACTING,
                    "processing_progress": 20,
                    "outline_status": MaterialStageStatus.PROCESSING,
                    "error_message": None,
                }
            )
        )

        try:
            sections = self.parser.parse(
                material_id=processing_record.material_id,
                course_id=processing_record.course_id,
                module_id=processing_record.module_id,
                file_name=processing_record.file_name,
                content_type=processing_record.content_type,
                data=data,
            )
            page_count = self._page_count_from_sections(sections) or processing_record.page_count
            self.store.save_record(
                processing_record.model_copy(
                    update={
                        "status": MaterialParseStatus.PROCESSING,
                        "page_count": page_count,
                        "processing_status": MaterialProcessingStage.NORMALIZING,
                        "processing_progress": 55,
                        "outline_status": MaterialStageStatus.COMPLETED,
                        "enrichment_status": MaterialStageStatus.PROCESSING,
                        "error_message": None,
                    }
                )
            )
            chunks = self.chunking_service.chunk_sections(sections)
            completed_record = processing_record.model_copy(
                update={
                    "status": MaterialParseStatus.COMPLETED,
                    "page_count": page_count,
                    "processing_status": MaterialProcessingStage.ENRICHING,
                    "processing_progress": 85,
                    "outline_status": MaterialStageStatus.COMPLETED,
                    "enrichment_status": MaterialStageStatus.PROCESSING,
                    "section_count": len(sections),
                    "chunk_count": len(chunks),
                    "last_processed_at": datetime.now(UTC).isoformat(),
                    "error_message": None,
                }
            )
            self.store.save_parsed_document(
                ParsedMaterialDocument(
                    record=completed_record,
                    sections=sections,
                    chunks=chunks,
                ),
                raw_bytes=data,
            )
            study_document = SectionStudyService(self.store).ensure_study_document(material_id, force=True)
            parse_debug_report = self._build_parse_debug_report(
                book=processing_record.file_name,
                sections=sections,
                study_document=study_document,
            )
            logger.info(
                "Material ingestion debug report: %s",
                json.dumps(parse_debug_report, sort_keys=True),
            )
            persisted_record = self.store.get_record(material_id) or completed_record
            ready_record = persisted_record.model_copy(
                update={
                    "processing_status": MaterialProcessingStage.READY,
                    "processing_progress": 100,
                    "enrichment_status": MaterialStageStatus.COMPLETED,
                    "last_processed_at": datetime.now(UTC).isoformat(),
                    "parse_debug_report": parse_debug_report,
                }
            )
            self.store.save_record(ready_record)
            if self.grounding_service is not None:
                self.grounding_service.refresh_course_index(processing_record.course_id)
            return ready_record
        except MaterialIngestionError as exc:
            failed_record = processing_record.model_copy(
                update={
                    "status": MaterialParseStatus.FAILED,
                    "processing_status": MaterialProcessingStage.FAILED,
                    "outline_status": MaterialStageStatus.FAILED,
                    "enrichment_status": MaterialStageStatus.FAILED,
                    "last_processed_at": datetime.now(UTC).isoformat(),
                    "error_message": str(exc),
                }
            )
            self.store.save_record(failed_record)
            raise

    def _estimate_page_count(self, file_name: str, data: bytes) -> int | None:
        if Path(file_name).suffix.lower() != ".pdf":
            return None
        try:
            return len(PdfReader(io.BytesIO(data)).pages)
        except Exception:  # noqa: BLE001
            return None

    def _page_count_from_sections(self, sections) -> int | None:  # noqa: ANN001
        page_numbers = [
            section.locator.page_number
            for section in sections
            if section.locator.page_number is not None
        ]
        return max(page_numbers) if page_numbers else None

    def _build_parse_debug_report(
        self,
        *,
        book: str,
        sections: list[SourceSection],
        study_document: MaterialStudyDocument,
    ) -> dict[str, object]:
        reading_numbers: set[int] = set()
        module_numbers: set[str] = set()
        formula_pages: set[int] = set()

        for section in sections:
            if section.section_title != "Formulas":
                reading_numbers.update(self._reading_numbers_from_text(section.section_title))
                module_numbers.update(self._module_numbers_from_text(section.section_title))
            if section.section_title == "Formulas" or section.formula_assets:
                if section.locator.page_number is not None:
                    formula_pages.add(section.locator.page_number)
                if section.page_end is not None:
                    formula_pages.add(section.page_end)
                for asset in section.formula_assets:
                    formula_pages.add(asset.source_page)
                    if asset.reading_number is not None:
                        reading_numbers.add(asset.reading_number)

        for group in study_document.groups:
            if group.title != "Formulas":
                reading_numbers.update(self._reading_numbers_from_text(group.title))
                module_numbers.update(self._module_numbers_from_text(group.title))
            if group.title == "Formulas":
                if group.page_start is not None:
                    formula_pages.add(group.page_start)
                if group.page_end is not None:
                    formula_pages.add(group.page_end)

        cards_generated = sum(len(section.flashcards) for section in study_document.sections)
        formula_cards = sum(len(section.formulas) for section in study_document.sections)

        return {
            "book": book,
            "readingsDetected": len(reading_numbers),
            "readingNumbersDetected": sorted(reading_numbers),
            "modulesDetected": len(module_numbers),
            "moduleNumbersDetected": sorted(module_numbers, key=self._module_sort_key),
            "missingExpectedReadings": [],
            "missingExpectedModules": [],
            "missingExpectedLOs": [],
            "orphanPages": [],
            "formulaPagesDetected": sorted(formula_pages),
            "sectionsDetected": len(sections),
            "studyGroupsDetected": len(study_document.groups),
            "cardsGenerated": cards_generated,
            "formulaCardsDetected": formula_cards,
            "cardsRejectedByQualityGate": 0,
            "sampleRejectedReasons": [],
        }

    def _reading_numbers_from_text(self, text: str) -> set[int]:
        return {int(match) for match in re.findall(r"\bReading\s+(\d{1,3})\b", text, flags=re.IGNORECASE)}

    def _module_numbers_from_text(self, text: str) -> set[str]:
        return {
            match.upper()
            for match in re.findall(
                r"\bModule\s+(\d+(?:\.[0-9A-Za-z]+)*)\b",
                text,
                flags=re.IGNORECASE,
            )
        }

    def _module_sort_key(self, module_number: str) -> tuple[tuple[int, str], ...]:
        parts: list[tuple[int, str]] = []
        for raw_part in module_number.split("."):
            if raw_part.isdigit():
                parts.append((int(raw_part), ""))
            else:
                alpha_match = re.match(r"(\d+)?([A-Z]+)", raw_part)
                if alpha_match is None:
                    parts.append((0, raw_part))
                else:
                    numeric = int(alpha_match.group(1) or 0)
                    parts.append((numeric, alpha_match.group(2)))
        return tuple(parts)
