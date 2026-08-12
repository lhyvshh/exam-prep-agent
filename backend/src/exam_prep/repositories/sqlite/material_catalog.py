from datetime import UTC, datetime
from hashlib import sha256
import json
import sqlite3

from exam_prep.db.sqlite import SQLiteDatabase
from exam_prep.repositories.material_catalog import MaterialCatalog
from exam_prep.schemas.materials import (
    MaterialParseStatus,
    MaterialProcessingStage,
    MaterialRecord,
    MaterialSectionSummary,
    MaterialStudyDocument,
    MaterialStageStatus,
    ParsedMaterialDocument,
    SourceLocator,
    SourceSection,
    StructuredConcept,
    StructuredMaterialChunk,
    StructuredMaterialSection,
)

DEFAULT_PARSE_SECTION_TOKEN_LIMIT = 4000


class SQLiteMaterialCatalog(MaterialCatalog):
    def __init__(
        self,
        database: SQLiteDatabase,
        *,
        parse_section_token_limit: int = DEFAULT_PARSE_SECTION_TOKEN_LIMIT,
    ) -> None:
        self.database = database
        self.parse_section_token_limit = max(1, parse_section_token_limit)

    def list_course_ids(self) -> list[str]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT course_id
                FROM material_records
                ORDER BY course_id ASC
                """
            ).fetchall()
        return [row["course_id"] for row in rows]

    def upsert_record(self, record: MaterialRecord) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO material_records(
                    material_id, course_id, module_id, file_name, display_name, file_path, uploaded_at, content_type, status,
                    page_count, processing_status, processing_progress, outline_status, enrichment_status,
                    last_processed_at, content_hash, raw_text_path, chunk_count, section_count, error_message,
                    parse_debug_report
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(material_id) DO UPDATE SET
                    course_id = excluded.course_id,
                    module_id = excluded.module_id,
                    file_name = excluded.file_name,
                    display_name = excluded.display_name,
                    file_path = excluded.file_path,
                    uploaded_at = excluded.uploaded_at,
                    content_type = excluded.content_type,
                    status = excluded.status,
                    page_count = excluded.page_count,
                    processing_status = excluded.processing_status,
                    processing_progress = excluded.processing_progress,
                    outline_status = excluded.outline_status,
                    enrichment_status = excluded.enrichment_status,
                    last_processed_at = excluded.last_processed_at,
                    content_hash = excluded.content_hash,
                    raw_text_path = excluded.raw_text_path,
                    chunk_count = excluded.chunk_count,
                    section_count = excluded.section_count,
                    error_message = excluded.error_message,
                    parse_debug_report = excluded.parse_debug_report
                """,
                (
                    record.material_id,
                    record.course_id,
                    record.module_id,
                    record.file_name,
                    record.display_name,
                    record.file_path,
                    record.uploaded_at,
                    record.content_type,
                    record.status.value,
                    record.page_count,
                    record.processing_status.value,
                    record.processing_progress,
                    record.outline_status.value,
                    record.enrichment_status.value,
                    record.last_processed_at,
                    record.content_hash,
                    record.raw_text_path,
                    record.chunk_count,
                    record.section_count,
                    record.error_message,
                    json.dumps(record.parse_debug_report) if record.parse_debug_report is not None else None,
                ),
            )

    def get_record(self, material_id: str) -> MaterialRecord | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT material_id, course_id, file_name, content_type, status,
                       module_id, display_name, file_path, uploaded_at,
                       page_count, processing_status, processing_progress, outline_status, enrichment_status,
                       last_processed_at, content_hash, raw_text_path,
                       chunk_count, section_count, error_message, parse_debug_report
                FROM material_records
                WHERE material_id = ?
                """,
                (material_id,),
            ).fetchone()

        if row is None:
            return None

        return self._record_from_row(row)

    def list_records(
        self,
        course_id: str | None = None,
        module_id: str | None = None,
    ) -> list[MaterialRecord]:
        where_parts: list[str] = []
        params: list[str] = []
        if course_id is not None:
            where_parts.append("course_id = ?")
            params.append(course_id)
        if module_id is not None:
            where_parts.append("module_id = ?")
            params.append(module_id)
        where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT material_id, course_id, module_id, file_name, display_name, file_path, uploaded_at, content_type, status,
                       page_count, processing_status, processing_progress, outline_status, enrichment_status,
                       last_processed_at, content_hash, raw_text_path,
                       chunk_count, section_count, error_message, parse_debug_report
                FROM material_records
                {where_clause}
                ORDER BY course_id ASC, file_name ASC, material_id ASC
                """,
                tuple(params),
            ).fetchall()
        return [self._record_from_row(row) for row in rows]

    def list_records_by_course(
        self,
        course_id: str,
        module_id: str | None = None,
    ) -> list[MaterialRecord]:
        where_clause = "WHERE course_id = ?"
        params: tuple[str, ...] | tuple[str, str] = (course_id,)
        if module_id is not None:
            where_clause += " AND module_id = ?"
            params = (course_id, module_id)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT material_id, course_id, module_id, file_name, display_name, file_path, uploaded_at, content_type, status,
                       page_count, processing_status, processing_progress, outline_status, enrichment_status,
                       last_processed_at, content_hash, raw_text_path,
                       chunk_count, section_count, error_message, parse_debug_report
                FROM material_records
                {where_clause}
                ORDER BY file_name ASC, material_id ASC
                """,
                params,
            ).fetchall()

        return [self._record_from_row(row) for row in rows]

    def replace_sections(
        self,
        material_id: str,
        course_id: str,
        module_id: str | None,
        sections: list[SourceSection],
    ) -> None:
        with self.database.connect() as connection:
            connection.execute(
                "DELETE FROM material_sections WHERE material_id = ?",
                (material_id,),
            )
            connection.executemany(
                """
                INSERT INTO material_sections(
                    source_id, material_id, course_id, module_id, file_name, content_type,
                    section_title, citation_label, section_index,
                    page_number, slide_number, paragraph_index
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        section.source_id,
                        material_id,
                        course_id,
                        module_id,
                        section.file_name,
                        section.content_type,
                        section.section_title,
                        section.citation_label,
                        section.locator.section_index,
                        section.locator.page_number,
                        section.locator.slide_number,
                        section.locator.paragraph_index,
                    )
                    for section in sections
                ],
            )

    def replace_chunks(self, document: ParsedMaterialDocument) -> None:
        created_at = datetime.now(UTC).isoformat()
        with self.database.connect() as connection:
            connection.execute(
                "DELETE FROM material_chunks WHERE material_id = ?",
                (document.record.material_id,),
            )
            connection.executemany(
                """
                INSERT INTO material_chunks(
                    id, material_id, section_id, course_id, module_id, page_number,
                    chunk_order, text, embedding_id, token_count, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        chunk.chunk_id,
                        chunk.material_id,
                        chunk.source_id,
                        chunk.course_id,
                        chunk.module_id,
                        chunk.locator.page_number,
                        index,
                        chunk.text,
                        None,
                        chunk.token_count or self._token_count(chunk.text),
                        created_at,
                    )
                    for index, chunk in enumerate(document.chunks, start=1)
                ],
            )

    def replace_study_assets(
        self,
        study_document: MaterialStudyDocument,
        parsed_document: ParsedMaterialDocument | None = None,
    ) -> None:
        if parsed_document is None:
            record = self.get_record(study_document.material_id)
            if record is None:
                return
            source_lookup: dict[str, SourceSection] = {}
            file_name = record.file_name
            content_type = record.content_type
            course_id = record.course_id
            module_id = record.module_id
        else:
            record = parsed_document.record
            source_lookup = {
                section.source_id: section
                for section in parsed_document.sections
            }
            file_name = record.file_name
            content_type = record.content_type
            course_id = record.course_id
            module_id = record.module_id

        now = datetime.now(UTC).isoformat()
        concept_rows: list[tuple[object, ...]] = []
        section_rows: list[tuple[object, ...]] = []

        for fallback_order, study_section in enumerate(study_document.sections, start=1):
            source_sections = [
                source_lookup[source_id]
                for source_id in study_section.source_ids
                if source_id in source_lookup
            ]
            anchor_source = source_sections[0] if source_sections else None
            source_text = "\n\n".join(source.text for source in source_sections).strip()
            if not source_text and anchor_source is not None:
                source_text = anchor_source.text.strip()
            start_page = study_section.page_start
            end_page = study_section.page_end
            if anchor_source is not None:
                start_page = start_page or anchor_source.locator.page_number
                end_page = end_page or anchor_source.page_end or anchor_source.locator.page_number

            key_terms = self._clean_items(study_section.memorize_keywords)
            key_concepts = self._clean_items(study_section.key_points)
            formulas = self._clean_items(study_section.memorize_functions_or_formulas)
            is_junk = not (
                source_text.strip()
                and study_section.summary.strip()
                and (key_terms or key_concepts or formulas)
            )
            section_order = study_section.display_order or fallback_order
            source_text_hash = self._hash_text(source_text)
            prompt_version = f"section-study-v{study_document.pipeline_version}"
            enhancement_cache_key = self._enhancement_cache_key(
                record.content_hash,
                source_text_hash,
                prompt_version,
            )
            enhancement_input_excerpt = self._bounded_excerpt(
                source_text,
                self.parse_section_token_limit,
            )

            section_rows.append(
                (
                    study_section.section_id,
                    study_section.material_id,
                    course_id,
                    module_id,
                    file_name,
                    content_type,
                    study_section.title,
                    study_section.normalized_title,
                    study_section.summary,
                    source_text,
                    study_section.source_anchor,
                    section_order,
                    start_page,
                    None,
                    None,
                    section_order,
                    start_page,
                    end_page,
                    json.dumps(key_terms),
                    json.dumps(key_concepts),
                    json.dumps(formulas),
                    self._exam_weight(study_section.difficulty.value),
                    1 if is_junk else 0,
                    source_text_hash,
                    enhancement_cache_key,
                    prompt_version,
                    enhancement_input_excerpt,
                    self.parse_section_token_limit,
                    now,
                    now,
                )
            )

            for concept_name in self._concept_names(study_section.normalized_title, key_terms):
                normalized_name = self._normalize_concept(concept_name)
                concept_id = self._stable_id(
                    "concept",
                    course_id,
                    study_section.material_id,
                    study_section.section_id,
                    normalized_name,
                )
                concept_rows.append(
                    (
                        concept_id,
                        course_id,
                        module_id,
                        study_section.material_id,
                        study_section.section_id,
                        concept_name,
                        normalized_name,
                        study_section.summary,
                        json.dumps(key_terms),
                        start_page,
                        now,
                    )
                )

        with self.database.connect() as connection:
            connection.execute(
                "DELETE FROM material_sections WHERE material_id = ?",
                (study_document.material_id,),
            )
            connection.execute(
                "DELETE FROM concepts WHERE material_id = ?",
                (study_document.material_id,),
            )
            connection.executemany(
                """
                INSERT INTO material_sections(
                    source_id, material_id, course_id, module_id, file_name, content_type,
                    section_title, clean_title, summary, source_text, citation_label,
                    section_index, page_number, slide_number, paragraph_index,
                    section_order, start_page, end_page, key_terms_json,
                    key_concepts_json, formulas_json, exam_weight, is_junk,
                    source_text_hash, enhancement_cache_key, enhancement_prompt_version,
                    enhancement_input_excerpt, enhancement_input_token_limit,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                section_rows,
            )
            connection.executemany(
                """
                INSERT INTO concepts(
                    id, course_id, module_id, material_id, section_id, name, normalized_name,
                    description, keywords_json, source_page, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                concept_rows,
            )

    def clear_material_processing_artifacts(self, material_id: str) -> None:
        with self.database.connect() as connection:
            flashcard_rows = connection.execute(
                "SELECT id FROM flashcards WHERE material_id = ?",
                (material_id,),
            ).fetchall()
            flashcard_ids = [row["id"] for row in flashcard_rows]
            if flashcard_ids:
                placeholders = ",".join("?" for _ in flashcard_ids)
                connection.execute(
                    f"DELETE FROM flashcard_reviews WHERE flashcard_id IN ({placeholders})",
                    tuple(flashcard_ids),
                )
                connection.execute(
                    f"DELETE FROM generated_content_quality_flags WHERE content_id IN ({placeholders})",
                    tuple(flashcard_ids),
                )
            connection.execute(
                "DELETE FROM flashcard_reviews WHERE material_id = ?",
                (material_id,),
            )
            connection.execute(
                "DELETE FROM flashcards WHERE material_id = ?",
                (material_id,),
            )
            connection.execute(
                "DELETE FROM generated_content_quality_flags WHERE material_id = ?",
                (material_id,),
            )
            connection.execute(
                "DELETE FROM study_sessions WHERE material_id = ?",
                (material_id,),
            )
            connection.execute(
                "DELETE FROM material_chunks WHERE material_id = ?",
                (material_id,),
            )
            connection.execute(
                "DELETE FROM concepts WHERE material_id = ?",
                (material_id,),
            )
            connection.execute(
                "DELETE FROM material_sections WHERE material_id = ?",
                (material_id,),
            )

    def list_structured_sections(self, material_id: str) -> list[StructuredMaterialSection]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT source_id, material_id, course_id, module_id, section_title, clean_title,
                       summary, source_text, start_page, end_page, section_order,
                       key_terms_json, key_concepts_json, formulas_json, exam_weight,
                       is_junk, source_text_hash, enhancement_cache_key,
                       enhancement_prompt_version, enhancement_input_excerpt,
                       enhancement_input_token_limit, created_at, updated_at
                FROM material_sections
                WHERE material_id = ?
                ORDER BY COALESCE(section_order, section_index) ASC, source_id ASC
                """,
                (material_id,),
            ).fetchall()
        return [self._structured_section_from_row(row) for row in rows]

    def get_structured_section(self, section_id: str) -> StructuredMaterialSection | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT source_id, material_id, course_id, module_id, section_title, clean_title,
                       summary, source_text, start_page, end_page, section_order,
                       key_terms_json, key_concepts_json, formulas_json, exam_weight,
                       is_junk, source_text_hash, enhancement_cache_key,
                       enhancement_prompt_version, enhancement_input_excerpt,
                       enhancement_input_token_limit, created_at, updated_at
                FROM material_sections
                WHERE source_id = ?
                """,
                (section_id,),
            ).fetchone()
        if row is None:
            return None
        return self._structured_section_from_row(row)

    def list_chunks_by_section(self, section_id: str) -> list[StructuredMaterialChunk]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, material_id, section_id, course_id, module_id, page_number,
                       chunk_order, text, embedding_id, token_count, created_at
                FROM material_chunks
                WHERE section_id = ?
                ORDER BY chunk_order ASC, id ASC
                """,
                (section_id,),
            ).fetchall()
        return [
            StructuredMaterialChunk(
                id=row["id"],
                material_id=row["material_id"],
                section_id=row["section_id"],
                course_id=row["course_id"],
                module_id=row["module_id"],
                page_number=row["page_number"],
                chunk_order=row["chunk_order"],
                text=row["text"],
                embedding_id=row["embedding_id"],
                token_count=row["token_count"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def get_concept(self, concept_id: str) -> StructuredConcept | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT id, course_id, module_id, material_id, section_id, name,
                       normalized_name, description, keywords_json, source_page, created_at
                FROM concepts
                WHERE id = ?
                """,
                (concept_id,),
            ).fetchone()
        if row is None:
            return None
        return self._concept_from_row(row)

    def list_sections_by_course(
        self,
        course_id: str,
        module_id: str | None = None,
    ) -> list[MaterialSectionSummary]:
        where_clause = "WHERE course_id = ?"
        params: tuple[str, ...] | tuple[str, str] = (course_id,)
        if module_id is not None:
            where_clause += " AND module_id = ?"
            params = (course_id, module_id)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT source_id, material_id, course_id, module_id, file_name, content_type,
                       section_title, citation_label, section_index,
                       page_number, slide_number, paragraph_index
                FROM material_sections
                {where_clause}
                ORDER BY file_name ASC, section_index ASC
                """,
                params,
            ).fetchall()

        return [
            MaterialSectionSummary(
                source_id=row["source_id"],
                material_id=row["material_id"],
                course_id=row["course_id"],
                module_id=row["module_id"],
                file_name=row["file_name"],
                content_type=row["content_type"],
                section_title=row["section_title"],
                citation_label=row["citation_label"],
                locator=SourceLocator(
                    section_index=row["section_index"],
                    page_number=row["page_number"],
                    slide_number=row["slide_number"],
                    paragraph_index=row["paragraph_index"],
                    char_start=None,
                    char_end=None,
                ),
            )
            for row in rows
        ]

    def delete_material(self, material_id: str) -> None:
        with self.database.connect() as connection:
            flashcard_rows = connection.execute(
                "SELECT id FROM flashcards WHERE material_id = ?",
                (material_id,),
            ).fetchall()
            flashcard_ids = [row["id"] for row in flashcard_rows]
            if flashcard_ids:
                placeholders = ",".join("?" for _ in flashcard_ids)
                connection.execute(
                    f"DELETE FROM flashcard_reviews WHERE flashcard_id IN ({placeholders})",
                    tuple(flashcard_ids),
                )
                connection.execute(
                    f"DELETE FROM generated_content_quality_flags WHERE content_id IN ({placeholders})",
                    tuple(flashcard_ids),
                )
            connection.execute(
                "DELETE FROM flashcard_reviews WHERE material_id = ?",
                (material_id,),
            )
            connection.execute(
                "DELETE FROM flashcards WHERE material_id = ?",
                (material_id,),
            )
            connection.execute(
                "DELETE FROM generated_content_quality_flags WHERE material_id = ?",
                (material_id,),
            )
            connection.execute(
                "DELETE FROM study_sessions WHERE material_id = ?",
                (material_id,),
            )
            connection.execute(
                "DELETE FROM material_chunks WHERE material_id = ?",
                (material_id,),
            )
            connection.execute(
                "DELETE FROM concepts WHERE material_id = ?",
                (material_id,),
            )
            connection.execute(
                "DELETE FROM material_sections WHERE material_id = ?",
                (material_id,),
            )
            connection.execute(
                "DELETE FROM material_records WHERE material_id = ?",
                (material_id,),
            )

    def _record_from_row(self, row: sqlite3.Row) -> MaterialRecord:
        return MaterialRecord(
            material_id=row["material_id"],
            course_id=row["course_id"],
            module_id=row["module_id"],
            file_name=row["file_name"],
            display_name=row["display_name"],
            file_path=row["file_path"],
            uploaded_at=row["uploaded_at"],
            content_type=row["content_type"],
            status=MaterialParseStatus(row["status"]),
            page_count=row["page_count"],
            processing_status=MaterialProcessingStage(row["processing_status"] or "registered"),
            processing_progress=row["processing_progress"],
            outline_status=MaterialStageStatus(row["outline_status"] or "pending"),
            enrichment_status=MaterialStageStatus(row["enrichment_status"] or "pending"),
            last_processed_at=row["last_processed_at"],
            content_hash=row["content_hash"],
            raw_text_path=row["raw_text_path"] if "raw_text_path" in row.keys() else None,
            chunk_count=row["chunk_count"],
            section_count=row["section_count"],
            error_message=row["error_message"],
            parse_debug_report=(
                self._json_dict(row["parse_debug_report"])
                if "parse_debug_report" in row.keys()
                else None
            ),
        )

    def _json_dict(self, value: str | None) -> dict[str, object] | None:
        if not value:
            return None
        try:
            loaded = json.loads(value)
        except json.JSONDecodeError:
            return None
        return loaded if isinstance(loaded, dict) else None

    def _structured_section_from_row(self, row: sqlite3.Row) -> StructuredMaterialSection:
        section_id = row["source_id"]
        return StructuredMaterialSection(
            id=section_id,
            material_id=row["material_id"],
            course_id=row["course_id"],
            module_id=row["module_id"],
            title=row["section_title"],
            clean_title=row["clean_title"] or row["section_title"],
            summary=row["summary"] or "",
            source_text=row["source_text"] or "",
            start_page=row["start_page"],
            end_page=row["end_page"],
            section_order=row["section_order"] or 0,
            key_terms=self._json_list(row["key_terms_json"]),
            key_concepts=self._json_list(row["key_concepts_json"]),
            formulas=self._json_list(row["formulas_json"]),
            exam_weight=float(row["exam_weight"] or 0.5),
            is_junk=bool(row["is_junk"]),
            source_text_hash=row["source_text_hash"] if "source_text_hash" in row.keys() else None,
            enhancement_cache_key=(
                row["enhancement_cache_key"] if "enhancement_cache_key" in row.keys() else None
            ),
            enhancement_prompt_version=(
                row["enhancement_prompt_version"] if "enhancement_prompt_version" in row.keys() else None
            ),
            enhancement_input_excerpt=(
                row["enhancement_input_excerpt"] if "enhancement_input_excerpt" in row.keys() else None
            ),
            enhancement_input_token_limit=(
                row["enhancement_input_token_limit"]
                if "enhancement_input_token_limit" in row.keys()
                else None
            ),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            concepts=self._list_concepts_for_section(section_id),
        )

    def _list_concepts_for_section(self, section_id: str) -> list[StructuredConcept]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, course_id, module_id, material_id, section_id, name,
                       normalized_name, description, keywords_json, source_page, created_at
                FROM concepts
                WHERE section_id = ?
                ORDER BY name ASC, id ASC
                """,
                (section_id,),
            ).fetchall()
        return [self._concept_from_row(row) for row in rows]

    def _concept_from_row(self, row: sqlite3.Row) -> StructuredConcept:
        return StructuredConcept(
            id=row["id"],
            course_id=row["course_id"],
            module_id=row["module_id"],
            material_id=row["material_id"],
            section_id=row["section_id"],
            name=row["name"],
            normalized_name=row["normalized_name"],
            description=row["description"] or "",
            keywords=self._json_list(row["keywords_json"]),
            source_page=row["source_page"],
            created_at=row["created_at"],
        )

    def _json_list(self, payload: str | None) -> list[str]:
        if not payload:
            return []
        try:
            value = json.loads(payload)
        except json.JSONDecodeError:
            return []
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if str(item).strip()]

    def _clean_items(self, items: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for item in items:
            normalized = " ".join(str(item).split()).strip()
            if not normalized:
                continue
            key = normalized.casefold()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(normalized)
        return cleaned

    def _concept_names(self, title: str, key_terms: list[str]) -> list[str]:
        candidates = [title, *key_terms[:4]]
        names: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            normalized = " ".join(candidate.replace("•", " ").split()).strip(" -|:")
            if not normalized:
                continue
            key = self._normalize_concept(normalized)
            if key in seen:
                continue
            seen.add(key)
            names.append(normalized[:120])
        return names[:5]

    def _normalize_concept(self, name: str) -> str:
        return " ".join(name.casefold().replace("•", " ").split()).strip()

    def _stable_id(self, *parts: str) -> str:
        digest = sha256("|".join(parts).encode("utf-8")).hexdigest()[:24]
        return "-".join([parts[0], digest])

    def _hash_text(self, text: str) -> str:
        normalized = " ".join(text.split())
        return sha256(normalized.encode("utf-8")).hexdigest()

    def _enhancement_cache_key(
        self,
        file_hash: str | None,
        section_text_hash: str,
        prompt_version: str,
    ) -> str:
        raw_key = "|".join([file_hash or "", section_text_hash, prompt_version])
        return sha256(raw_key.encode("utf-8")).hexdigest()

    def _bounded_excerpt(self, text: str, token_limit: int) -> str:
        words = text.split()
        if len(words) <= token_limit:
            return " ".join(words)
        return " ".join(words[:token_limit])

    def _token_count(self, text: str) -> int:
        return max(1, len(text.split()))

    def _exam_weight(self, difficulty: str) -> float:
        return {
            "easy": 0.35,
            "medium": 0.6,
            "hard": 0.85,
        }.get(difficulty, 0.5)
