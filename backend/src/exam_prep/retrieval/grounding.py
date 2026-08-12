from exam_prep.core.exceptions import MaterialIngestionError
from exam_prep.repositories.material_store import MaterialStore
from exam_prep.repositories.vector_store import VectorStore
from exam_prep.schemas.graph import GroundingContext
from exam_prep.schemas.retrieval import RetrievalHit
from exam_prep.retrieval.indexing import IndexingService


class GroundingService:
    def __init__(
        self,
        *,
        material_store: MaterialStore,
        vector_store: VectorStore,
        indexing_service: IndexingService | None = None,
    ) -> None:
        self.material_store = material_store
        self.vector_store = vector_store
        self.indexing_service = indexing_service or IndexingService()

    def build_context(self, course_id: str) -> list[GroundingContext]:
        _ = course_id
        return []

    def refresh_course_index(self, course_id: str) -> None:
        documents = self.material_store.list_parsed_documents_by_course(course_id)
        if not documents:
            raise MaterialIngestionError("No parsed materials found for this course.")

        index = self.indexing_service.build_course_index(course_id, documents)
        self.vector_store.save_course_index(index)

    def retrieve(
        self,
        course_id: str,
        query: str,
        top_k: int,
        selected_source_ids: list[str] | None = None,
    ) -> list[RetrievalHit]:
        index = self.vector_store.get_course_index(course_id)
        if index is None:
            self.refresh_course_index(course_id)
            index = self.vector_store.get_course_index(course_id)

        if index is None or index.chunk_count == 0:
            raise MaterialIngestionError("No indexed materials found for this course.")

        return self.indexing_service.query_index(
            index,
            query,
            top_k,
            selected_source_ids=selected_source_ids,
        )
