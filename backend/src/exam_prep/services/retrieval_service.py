from exam_prep.core.exceptions import MaterialIngestionError
from exam_prep.repositories.material_store import MaterialStore
from exam_prep.repositories.vector_store import VectorStore
from exam_prep.retrieval.grounding import GroundingService
from exam_prep.schemas.materials import ContentLabel, ParsedMaterialDocument
from exam_prep.schemas.retrieval import RetrievalHit, RetrievalQueryResponse


class RetrievalService:
    def __init__(self, *, material_store: MaterialStore, vector_store: VectorStore) -> None:
        self.grounding_service = GroundingService(
            material_store=material_store,
            vector_store=vector_store,
        )

    def query(
        self,
        course_id: str,
        module_id: str | None,
        query: str,
        top_k: int,
        selected_source_ids: list[str] | None = None,
        module_ids: list[str] | None = None,
    ) -> RetrievalQueryResponse:
        normalized_query = query.strip()
        if not normalized_query:
            raise MaterialIngestionError("Query text is required.")

        normalized_module_ids = self._normalize_module_ids(module_id, module_ids)
        scoped_source_ids = self._scoped_source_ids(
            course_id,
            module_id if len(normalized_module_ids) <= 1 else None,
            normalized_module_ids=normalized_module_ids,
        )
        requested_source_ids = [source_id for source_id in (selected_source_ids or []) if source_id]
        if scoped_source_ids is not None:
            if requested_source_ids:
                effective_source_ids = [
                    source_id for source_id in requested_source_ids if source_id in scoped_source_ids
                ]
            else:
                effective_source_ids = sorted(scoped_source_ids)
        else:
            effective_source_ids = requested_source_ids

        if scoped_source_ids is not None and not effective_source_ids:
            return RetrievalQueryResponse(
                course_id=course_id,
                module_id=normalized_module_ids[0] if len(normalized_module_ids) == 1 else None,
                module_ids=normalized_module_ids,
                query=normalized_query,
                hits=[],
            )

        hits = self.grounding_service.retrieve(
            course_id,
            normalized_query,
            top_k,
            selected_source_ids=effective_source_ids,
        )
        if not hits and effective_source_ids:
            hits = self._fallback_hits_for_selected_sources(
                course_id=course_id,
                module_id=normalized_module_ids[0] if len(normalized_module_ids) == 1 else None,
                module_ids=normalized_module_ids,
                selected_source_ids=effective_source_ids,
                top_k=top_k,
            )
        hits = self._filter_hits_by_content_quality(hits)
        return RetrievalQueryResponse(
            course_id=course_id,
            module_id=normalized_module_ids[0] if len(normalized_module_ids) == 1 else None,
            module_ids=normalized_module_ids,
            query=normalized_query,
            hits=hits,
        )

    def _scoped_source_ids(
        self,
        course_id: str,
        module_id: str | None,
        *,
        normalized_module_ids: list[str] | None = None,
    ) -> set[str] | None:
        effective_module_ids = normalized_module_ids or self._normalize_module_ids(module_id, None)
        if not effective_module_ids:
            return None
        documents = self._documents_for_scope(course_id, effective_module_ids)
        return {
            section.source_id
            for document in documents
            for section in document.sections
        }

    def _fallback_hits_for_selected_sources(
        self,
        *,
        course_id: str,
        module_id: str | None,
        module_ids: list[str] | None = None,
        selected_source_ids: list[str],
        top_k: int,
    ) -> list[RetrievalHit]:
        selected_source_id_set = {source_id for source_id in selected_source_ids if source_id}
        if not selected_source_id_set:
            return []

        effective_module_ids = self._normalize_module_ids(module_id, module_ids)
        candidate_chunks = [
            chunk
            for document in self._documents_for_scope(course_id, effective_module_ids)
            for chunk in document.chunks
            if chunk.source_id in selected_source_id_set
        ]
        candidate_chunks.sort(
            key=lambda chunk: (
                0 if chunk.is_default else 1,
                -chunk.priority_score,
                chunk.locator.section_index,
                chunk.locator.char_start or 0,
            )
        )
        hits = [
            RetrievalHit(score=round(max(chunk.priority_score, 0.05), 6), chunk=chunk)
            for chunk in candidate_chunks[:top_k]
        ]
        return self._filter_hits_by_content_quality(hits)

    def resolve_scope_source_ids(
        self,
        *,
        course_id: str,
        module_id: str | None = None,
        module_ids: list[str] | None = None,
    ) -> list[str]:
        normalized_module_ids = self._normalize_module_ids(module_id, module_ids)
        scoped = self._scoped_source_ids(
            course_id,
            module_id if len(normalized_module_ids) <= 1 else None,
            normalized_module_ids=normalized_module_ids,
        )
        return sorted(scoped) if scoped is not None else []

    def _documents_for_scope(
        self,
        course_id: str,
        module_ids: list[str],
    ) -> list[ParsedMaterialDocument]:
        if not module_ids:
            return self.grounding_service.material_store.list_parsed_documents_by_course(
                course_id,
                None,
            )
        if len(module_ids) == 1:
            return self.grounding_service.material_store.list_parsed_documents_by_course(
                course_id,
                module_ids[0],
            )
        documents = []
        seen_material_ids: set[str] = set()
        for scoped_module_id in module_ids:
            for document in self.grounding_service.material_store.list_parsed_documents_by_course(
                course_id,
                scoped_module_id,
            ):
                if document.record.material_id in seen_material_ids:
                    continue
                seen_material_ids.add(document.record.material_id)
                documents.append(document)
        return documents

    def _normalize_module_ids(
        self,
        module_id: str | None,
        module_ids: list[str] | None,
    ) -> list[str]:
        normalized = [value.strip() for value in (module_ids or []) if value and value.strip()]
        if not normalized and module_id and module_id.strip():
            normalized = [module_id.strip()]
        return list(dict.fromkeys(normalized))

    def _filter_hits_by_content_quality(self, hits: list[RetrievalHit]) -> list[RetrievalHit]:
        if not hits:
            return []

        testable_hits = [
            hit for hit in hits if hit.chunk.content_label == ContentLabel.TESTABLE_CONTENT
        ]
        if testable_hits:
            return testable_hits

        weak_hits = [
            hit for hit in hits if hit.chunk.content_label == ContentLabel.WEAK_CONTENT
        ]
        if weak_hits:
            return weak_hits

        return []
