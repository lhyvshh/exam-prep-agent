from hashlib import sha256
import logging
from datetime import UTC, datetime
from math import ceil
from pathlib import Path

from exam_prep.core.config import Settings, get_settings
from exam_prep.repositories.material_catalog import MaterialCatalog
from exam_prep.core.exceptions import MaterialIngestionError
from exam_prep.ingestion.pipeline import IngestionPipeline
from exam_prep.repositories.material_store import MaterialStore
from exam_prep.repositories.vector_store import VectorStore
from exam_prep.repositories.workflow_store import WorkflowStore
from exam_prep.retrieval.grounding import GroundingService
from exam_prep.schemas.materials import (
    ContentLabel,
    ConceptSourceResponse,
    CourseMaterialsResponse,
    MaterialParseStatus,
    MaterialProcessingStage,
    MaterialDeleteResponse,
    MaterialDetailResponse,
    MaterialListResponse,
    MaterialSectionsResponse,
    MaterialPreviewResponse,
    MaterialRecord,
    MaterialSectionSummary,
    MaterialStageStatus,
    MaterialStudyResponse,
    MaterialStudySectionResponse,
    MaterialStudySectionUpdateRequest,
    MaterialStatusResponse,
    MaterialUploadResponse,
    QuizSourceSummary,
    SectionChunksResponse,
    SectionDetailResponse,
    SectionKind,
    SourceLocator,
    SourceSection,
)
from exam_prep.services.material_job_runner import MaterialJobRunner
from exam_prep.services.section_study_service import SectionStudyService

logger = logging.getLogger(__name__)


class MaterialService:
    def __init__(
        self,
        store: MaterialStore,
        vector_store: VectorStore | None = None,
        workflow_store: WorkflowStore | None = None,
        material_catalog: MaterialCatalog | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.store = store
        self.vector_store = vector_store
        self.workflow_store = workflow_store
        self.material_catalog = material_catalog
        self.settings = settings or get_settings()
        self.pipeline = IngestionPipeline(store=store, vector_store=vector_store)

    def ingest_material(
        self,
        *,
        course_id: str,
        module_id: str | None,
        file_name: str,
        content_type: str | None,
        data: bytes,
        job_runner: MaterialJobRunner | None = None,
    ) -> MaterialUploadResponse:
        existing_record = (
            self._find_existing_upload(
                course_id=course_id,
                module_id=module_id,
                data=data,
            )
            if self.settings.enable_parse_cache
            else None
        )
        if existing_record is not None:
            if self.workflow_store is not None:
                self.workflow_store.set_current_selection(course_id, module_id)
            return MaterialUploadResponse(record=existing_record)

        registered_record = self.pipeline.register_upload(
            course_id=course_id,
            module_id=module_id,
            file_name=file_name,
            content_type=content_type,
            data=data,
        )
        if self._should_process_async(registered_record, len(data)):
            if job_runner is not None:
                job_runner.enqueue(registered_record.material_id)
            record = registered_record
        else:
            record = self.pipeline.process_registered_material(registered_record.material_id)
        if self.workflow_store is not None:
            self.workflow_store.set_current_selection(course_id, module_id)
        return MaterialUploadResponse(record=record)

    def list_materials(
        self,
        course_id: str | None = None,
        module_id: str | None = None,
    ) -> MaterialListResponse:
        if self.material_catalog is not None:
            return MaterialListResponse(
                records=self.material_catalog.list_records(course_id, module_id)
            )
        if course_id is None:
            raise MaterialIngestionError("Course ID is required when the material catalog is unavailable.")
        return MaterialListResponse(records=self.store.list_records_by_course(course_id, module_id))

    def get_material(self, material_id: str) -> MaterialDetailResponse:
        record = self.store.get_record(material_id)
        if record is None:
            raise MaterialIngestionError("Material not found.")
        return MaterialDetailResponse(record=record)

    def list_material_sections(self, material_id: str) -> MaterialSectionsResponse:
        record = self.store.get_record(material_id)
        if record is None:
            raise MaterialIngestionError("Material not found.")
        if self.material_catalog is None:
            raise MaterialIngestionError("Structured material catalog is unavailable.")
        return MaterialSectionsResponse(
            record=record,
            sections=self.material_catalog.list_structured_sections(material_id),
        )

    def get_section_detail(self, section_id: str) -> SectionDetailResponse:
        if self.material_catalog is None:
            raise MaterialIngestionError("Structured material catalog is unavailable.")
        section = self.material_catalog.get_structured_section(section_id)
        if section is None:
            raise MaterialIngestionError("Study section not found.")
        return SectionDetailResponse(section=section)

    def list_section_chunks(self, section_id: str) -> SectionChunksResponse:
        if self.material_catalog is None:
            raise MaterialIngestionError("Structured material catalog is unavailable.")
        if self.material_catalog.get_structured_section(section_id) is None:
            raise MaterialIngestionError("Study section not found.")
        return SectionChunksResponse(
            section_id=section_id,
            chunks=self.material_catalog.list_chunks_by_section(section_id),
        )

    def get_concept_source(self, concept_id: str) -> ConceptSourceResponse:
        if self.material_catalog is None:
            raise MaterialIngestionError("Structured material catalog is unavailable.")
        concept = self.material_catalog.get_concept(concept_id)
        if concept is None:
            raise MaterialIngestionError("Concept not found.")
        section = self.material_catalog.get_structured_section(concept.section_id)
        if section is None:
            raise MaterialIngestionError("Concept source section not found.")
        return ConceptSourceResponse(
            concept=concept,
            source={
                "material_id": section.material_id,
                "section_id": section.id,
                "page_number": concept.source_page or section.start_page,
                "page_start": section.start_page,
                "page_end": section.end_page,
                "source_text": section.source_text,
            },
        )

    def get_status(self, material_id: str) -> MaterialStatusResponse:
        record = self.store.get_record(material_id)
        if record is None:
            raise MaterialIngestionError("Material not found.")
        return MaterialStatusResponse(record=record)

    def get_preview(self, material_id: str, chunk_limit: int = 5) -> MaterialPreviewResponse:
        document = self.store.get_parsed_document(material_id)
        if document is None:
            raise MaterialIngestionError("Parsed material not found.")
        return MaterialPreviewResponse(
            record=document.record,
            sections=document.sections,
            chunks=document.chunks[:chunk_limit],
        )

    def get_study_material(
        self,
        material_id: str,
        *,
        group_id: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> MaterialStudyResponse:
        record = self.store.get_record(material_id)
        if record is None:
            raise MaterialIngestionError("Material not found.")

        document = SectionStudyService(self.store).ensure_study_document(material_id)
        if document is None:
            return MaterialStudyResponse(
                record=record,
                groups=[],
                sections=[],
                total_sections=0,
                ready_sections=0,
                studied_sections=0,
                offset=offset,
                limit=limit,
                has_more=False,
            )

        sections = sorted(document.sections, key=lambda section: section.display_order)
        if group_id:
            sections = [
                section for section in sections if section.parent_group_id == group_id
            ]
        normalized_offset = max(0, offset)
        normalized_limit = min(max(1, limit), 40)
        page = sections[normalized_offset : normalized_offset + normalized_limit]
        return MaterialStudyResponse(
            record=record,
            groups=document.groups,
            sections=page,
            total_sections=len(sections),
            ready_sections=sum(1 for section in sections if section.quiz_ready),
            studied_sections=sum(
                1 for section in sections if section.studied_status == "studied"
            ),
            offset=normalized_offset,
            limit=normalized_limit,
            has_more=normalized_offset + normalized_limit < len(sections),
        )

    def get_study_section(
        self,
        material_id: str,
        section_id: str,
    ) -> MaterialStudySectionResponse:
        document = SectionStudyService(self.store).ensure_study_document(material_id)
        if document is None:
            raise MaterialIngestionError("Study material is not ready yet.")
        for section in document.sections:
            if section.section_id == section_id or section_id in section.source_ids:
                return MaterialStudySectionResponse(section=section)
        raise MaterialIngestionError("Study section not found.")

    def update_study_section(
        self,
        material_id: str,
        section_id: str,
        request: MaterialStudySectionUpdateRequest,
    ) -> MaterialStudySectionResponse:
        section = SectionStudyService(self.store).update_studied_status(
            material_id,
            section_id,
            request.studied_status,
        )
        if section is None:
            raise MaterialIngestionError("Study section not found.")
        return MaterialStudySectionResponse(section=section)

    def regenerate_study_material(self, material_id: str) -> MaterialStudyResponse:
        record = self.store.get_record(material_id)
        if record is None:
            raise MaterialIngestionError("Material not found.")
        self.store.save_record(
            record.model_copy(
                update={
                    "processing_status": MaterialProcessingStage.ENRICHING,
                    "processing_progress": min(record.processing_progress, 90),
                    "enrichment_status": MaterialStageStatus.PROCESSING,
                }
            )
        )
        SectionStudyService(self.store).ensure_study_document(material_id, force=True)
        refreshed = self.store.get_record(material_id) or record
        self.store.save_record(
            refreshed.model_copy(
                update={
                    "processing_status": MaterialProcessingStage.READY,
                    "processing_progress": 100,
                    "enrichment_status": MaterialStageStatus.COMPLETED,
                }
            )
        )
        return self.get_study_material(material_id)

    def reprocess_material(
        self,
        material_id: str,
        job_runner: MaterialJobRunner | None = None,
    ) -> MaterialStatusResponse:
        record = self.store.get_record(material_id)
        if record is None:
            raise MaterialIngestionError("Material not found.")

        self._log_reprocess_event(
            "Material reprocess cleanup started.",
            record,
            parser_phase="cleanup",
        )
        self.store.clear_material_processing_artifacts(material_id)

        queued_record = record.model_copy(
            update={
                "status": MaterialParseStatus.PROCESSING,
                "processing_status": MaterialProcessingStage.EXTRACTING,
                "processing_progress": 10,
                "outline_status": MaterialStageStatus.PROCESSING,
                "enrichment_status": MaterialStageStatus.PENDING,
                "section_count": 0,
                "chunk_count": 0,
                "error_message": None,
                "last_processed_at": None,
            }
        )
        self.store.save_record(queued_record)

        if job_runner is not None:
            job_runner.enqueue(material_id)
            self._log_reprocess_event(
                "Material reprocess queued.",
                queued_record,
                parser_phase=queued_record.processing_status.value,
            )
            return MaterialStatusResponse(record=queued_record)

        try:
            processed_record = self.pipeline.process_registered_material(material_id)
            self._log_reprocess_event(
                "Material reprocess completed.",
                processed_record,
                parser_phase=processed_record.processing_status.value,
            )
            return MaterialStatusResponse(record=processed_record)
        except MaterialIngestionError as exc:
            failed_record = self._mark_reprocess_failed(material_id, queued_record, exc)
            self._log_reprocess_event(
                "Material reprocess failed.",
                failed_record,
                parser_phase=failed_record.processing_status.value,
                exc=exc,
            )
            raise
        except Exception as exc:  # noqa: BLE001
            failed_record = self._mark_reprocess_failed(material_id, queued_record, exc)
            self._log_reprocess_event(
                "Material reprocess crashed.",
                failed_record,
                parser_phase=failed_record.processing_status.value,
                exc=exc,
            )
            raise MaterialIngestionError(f"Material reprocess failed: {exc}") from exc

    def list_course_materials(
        self,
        course_id: str,
        module_id: str | None = None,
    ) -> CourseMaterialsResponse:
        normalized_course_id = course_id.strip()
        if not normalized_course_id:
            raise MaterialIngestionError("Course ID is required.")

        records = self.store.list_records_by_course(normalized_course_id, module_id)
        sections = self._sections_from_documents(normalized_course_id, module_id)
        quiz_sources = self._quiz_sources_from_documents(normalized_course_id, module_id)
        return CourseMaterialsResponse(
            course_id=normalized_course_id,
            records=records,
            sections=sections,
            quiz_sources=quiz_sources,
            default_source_ids=[section.source_id for section in sections if section.is_default],
            default_quiz_source_ids=[
                quiz_source.quiz_source_id for quiz_source in quiz_sources if quiz_source.is_default
            ],
        )

    def delete_material(self, material_id: str) -> MaterialDeleteResponse:
        record = self.store.get_record(material_id)
        if record is None:
            raise MaterialIngestionError("Material not found.")

        if not self.store.delete_material(material_id):
            raise MaterialIngestionError("Material not found.")

        remaining_records = self.store.list_records_by_course(record.course_id)
        remaining_documents = self.store.list_parsed_documents_by_course(record.course_id)
        if self.vector_store is not None:
            if remaining_documents:
                GroundingService(
                    material_store=self.store,
                    vector_store=self.vector_store,
                ).refresh_course_index(record.course_id)
            else:
                self.vector_store.delete_course_index(record.course_id)

        current_course_id = self.workflow_store.get_current_course_id() if self.workflow_store else None
        current_module_id = self.workflow_store.get_current_module_id() if self.workflow_store else None
        if self.workflow_store is not None and current_course_id == record.course_id and not remaining_records:
            self.workflow_store.clear_current_selection()
            current_course_id = None
            current_module_id = None
        elif (
            self.workflow_store is not None
            and current_course_id == record.course_id
            and current_module_id == record.module_id
            and record.module_id is not None
            and not self.store.list_records_by_course(record.course_id, record.module_id)
        ):
            self.workflow_store.set_current_selection(record.course_id, None)
            current_module_id = None

        return MaterialDeleteResponse(
            material_id=material_id,
            course_id=record.course_id,
            removed=True,
            remaining_material_count=len(remaining_records),
            current_course_id=current_course_id,
        )

    def retry_processing(
        self,
        material_id: str,
        job_runner: MaterialJobRunner | None = None,
    ) -> MaterialStatusResponse:
        record = self.store.get_record(material_id)
        if record is None:
            raise MaterialIngestionError("Material not found.")
        if job_runner is not None:
            queued_record = record.model_copy(
                update={
                    "status": MaterialParseStatus.PROCESSING,
                    "processing_status": MaterialProcessingStage.EXTRACTING,
                    "processing_progress": max(record.processing_progress, 10),
                    "error_message": None,
                }
            )
            self.store.save_record(queued_record)
            job_runner.enqueue(material_id)
            return MaterialStatusResponse(record=queued_record)
        return MaterialStatusResponse(record=self.pipeline.process_registered_material(material_id))

    def _mark_reprocess_failed(
        self,
        material_id: str,
        fallback_record: MaterialRecord,
        exc: BaseException,
    ) -> MaterialRecord:
        current_record = self.store.get_record(material_id) or fallback_record
        failed_record = current_record.model_copy(
            update={
                "status": MaterialParseStatus.FAILED,
                "processing_status": MaterialProcessingStage.FAILED,
                "processing_progress": 0,
                "outline_status": MaterialStageStatus.FAILED,
                "enrichment_status": MaterialStageStatus.FAILED,
                "section_count": 0,
                "chunk_count": 0,
                "last_processed_at": datetime.now(UTC).isoformat(),
                "error_message": str(exc),
            }
        )
        self.store.save_record(failed_record)
        return failed_record

    def _log_reprocess_event(
        self,
        message: str,
        record: MaterialRecord,
        *,
        parser_phase: str,
        exc: BaseException | None = None,
    ) -> None:
        extra = {
            "material_id": record.material_id,
            "file_name": record.file_name,
            "page_count": record.page_count,
            "parser_phase": parser_phase,
            "current_page_number": getattr(exc, "current_page_number", None) if exc else None,
            "detected_page_type": getattr(exc, "detected_page_type", None) if exc else None,
            "failing_source_unit_id": getattr(exc, "source_unit_id", None) if exc else None,
            "failing_card_id": getattr(exc, "card_id", None) if exc else None,
            "failure_reason": str(exc) if exc else None,
        }
        if exc is None:
            logger.info(message, extra=extra)
            return
        logger.exception(message, extra=extra)

    def _should_process_async(self, record: MaterialRecord, byte_count: int) -> bool:
        suffix = Path(record.file_name).suffix.lower()
        if suffix == ".pdf" and (record.page_count or 0) >= 30:
            return True
        return byte_count >= 8 * 1024 * 1024

    def _find_existing_upload(
        self,
        *,
        course_id: str,
        module_id: str | None,
        data: bytes,
    ) -> MaterialRecord | None:
        content_hash = sha256(data).hexdigest()
        for record in self.store.list_records_by_course(course_id, module_id):
            if record.content_hash == content_hash:
                return record
        return None

    def _sections_from_documents(
        self,
        course_id: str,
        module_id: str | None = None,
    ) -> list[MaterialSectionSummary]:
        summaries: list[MaterialSectionSummary] = []
        for document in self.store.list_parsed_documents_by_course(course_id, module_id):
            summaries.extend(
                MaterialSectionSummary(
                    source_id=section.source_id,
                    material_id=section.material_id,
                    course_id=section.course_id,
                    module_id=section.module_id,
                    file_name=section.file_name,
                    content_type=section.content_type,
                    section_title=section.section_title,
                    section_kind=section.section_kind,
                    content_label=section.content_label,
                    priority_score=section.priority_score,
                    is_default=section.is_default,
                    citation_label=section.citation_label,
                    locator=section.locator,
                )
                for section in document.sections
            )
        return sorted(
            summaries,
            key=lambda section: (
                0 if section.is_default else 1,
                -section.priority_score,
                section.file_name,
                section.locator.section_index,
            ),
        )

    def _quiz_sources_from_documents(
        self,
        course_id: str,
        module_id: str | None = None,
    ) -> list[QuizSourceSummary]:
        quiz_sources: list[QuizSourceSummary] = []
        for document in self.store.list_parsed_documents_by_course(course_id, module_id):
            quiz_sources.extend(self._group_document_for_quiz_sources(document.sections))
        return sorted(
            quiz_sources,
            key=lambda source: (
                0 if source.is_default else 1,
                -source.priority_score,
                source.file_name,
                source.locator.section_index,
            ),
        )

    def _group_document_for_quiz_sources(
        self,
        sections: list[SourceSection],
    ) -> list[QuizSourceSummary]:
        if not sections:
            return []

        normalized_sections = sorted(
            sections,
            key=lambda section: section.locator.section_index,
        )
        testable_sections = [
            section
            for section in normalized_sections
            if section.content_label == ContentLabel.TESTABLE_CONTENT
        ]
        weak_sections = [
            section
            for section in normalized_sections
            if section.content_label == ContentLabel.WEAK_CONTENT
        ]

        quiz_sources: list[QuizSourceSummary] = []
        if testable_sections:
            quiz_sources.extend(self._build_instructional_quiz_sources(testable_sections))
        elif weak_sections:
            quiz_sources.extend(self._build_instructional_quiz_sources(weak_sections, weak_mode=True))
        return quiz_sources

    def _build_instructional_quiz_sources(
        self,
        sections: list[SourceSection],
        *,
        weak_mode: bool = False,
    ) -> list[QuizSourceSummary]:
        if not sections:
            return []
        if len(sections) <= 6:
            return [
                self._build_quiz_source([section], group_index=index, weak_mode=weak_mode)
                for index, section in enumerate(sections, start=1)
            ]

        total_characters = sum(len(section.section_title) + 1 + len(getattr(section, "text", "")) for section in sections)
        estimated_group_count = max(2, ceil(len(sections) / 5), ceil(total_characters / 3200))
        target_group_count = min(8, estimated_group_count)
        max_sections_per_group = max(2, ceil(len(sections) / target_group_count))
        max_characters_per_group = max(1800, ceil(total_characters / target_group_count))

        grouped_sections: list[list[SourceSection]] = []
        current_group: list[SourceSection] = []
        current_characters = 0

        for section in sections:
            section_characters = len(section.section_title) + 1 + len(getattr(section, "text", ""))
            if current_group and (
                len(current_group) >= max_sections_per_group
                or (current_characters >= max_characters_per_group and self._looks_like_new_topic(section))
            ):
                grouped_sections.append(current_group)
                current_group = []
                current_characters = 0

            current_group.append(section)
            current_characters += section_characters

        if current_group:
            grouped_sections.append(current_group)

        return [
            self._build_quiz_source(group, group_index=index, weak_mode=weak_mode)
            for index, group in enumerate(grouped_sections, start=1)
        ]

    def _build_quiz_source(
        self,
        group: list[SourceSection],
        *,
        group_index: int,
        weak_mode: bool = False,
    ) -> QuizSourceSummary:
        first = group[0]
        last = group[-1]
        source_ids = [section.source_id for section in group]
        section_titles = list(dict.fromkeys(section.section_title for section in group))
        display_title = section_titles[0] if len(section_titles) == 1 else self._group_title(first.file_name, section_titles, first.locator, last.locator, group_index)
        location_label = self._location_label(first.locator, last.locator)
        summary = " | ".join(section_titles[:3])
        if len(section_titles) > 3:
            summary = f"{summary} | +{len(section_titles) - 3} more"

        priority_score = round(sum(section.priority_score for section in group) / len(group), 2)
        section_kind = (
            first.section_kind
            if all(section.section_kind == first.section_kind for section in group)
            else SectionKind.INSTRUCTIONAL
        )
        content_label = (
            ContentLabel.TESTABLE_CONTENT
            if any(section.content_label == ContentLabel.TESTABLE_CONTENT for section in group)
            else ContentLabel.WEAK_CONTENT
        )
        is_default = content_label == ContentLabel.TESTABLE_CONTENT or weak_mode

        return QuizSourceSummary(
            quiz_source_id=f"{first.material_id}-quiz-source-{group_index}",
            material_id=first.material_id,
            course_id=first.course_id,
            module_id=first.module_id,
            file_name=first.file_name,
            title=display_title,
            summary=summary,
            source_ids=source_ids,
            section_count=len(group),
            section_kind=section_kind,
            content_label=content_label,
            priority_score=priority_score,
            is_default=is_default,
            citation_label=f"{first.file_name} | {display_title}",
            location_label=location_label,
            locator=first.locator,
        )

    def _group_title(
        self,
        file_name: str,
        section_titles: list[str],
        first_locator: SourceLocator,
        last_locator: SourceLocator,
        group_index: int,
    ) -> str:
        meaningful_titles = [
            title for title in section_titles
            if title and not title.lower().startswith("page ")
        ]
        if meaningful_titles:
            if len(meaningful_titles) == 1:
                return meaningful_titles[0]
            if meaningful_titles[0] == meaningful_titles[-1]:
                return meaningful_titles[0]
            return f"{meaningful_titles[0]}: {meaningful_titles[-1]}"
        location_label = self._location_label(first_locator, last_locator)
        if location_label:
            return f"{Path(file_name).stem} · {location_label}"
        return f"{Path(file_name).stem} · section group {group_index}"

    def _location_label(
        self,
        first_locator: SourceLocator,
        last_locator: SourceLocator,
    ) -> str:
        if first_locator.page_number is not None and last_locator.page_number is not None:
            if first_locator.page_number == last_locator.page_number:
                return f"page {first_locator.page_number}"
            return f"pages {first_locator.page_number}-{last_locator.page_number}"
        if first_locator.slide_number is not None and last_locator.slide_number is not None:
            if first_locator.slide_number == last_locator.slide_number:
                return f"slide {first_locator.slide_number}"
            return f"slides {first_locator.slide_number}-{last_locator.slide_number}"
        if first_locator.section_index == last_locator.section_index:
            return f"section {first_locator.section_index}"
        return f"sections {first_locator.section_index}-{last_locator.section_index}"

    def _looks_like_new_topic(self, section: SourceSection) -> bool:
        lowered_title = section.section_title.strip().lower()
        if not lowered_title:
            return False
        if lowered_title.startswith("page "):
            return False
        return len(lowered_title.split()) <= 9
