from fastapi import APIRouter, Depends, HTTPException, status

from exam_prep.api.deps import get_material_store, get_vector_store
from exam_prep.core.exceptions import MaterialIngestionError
from exam_prep.repositories.material_store import MaterialStore
from exam_prep.repositories.vector_store import VectorStore
from exam_prep.schemas.retrieval import RetrievalQueryRequest, RetrievalQueryResponse
from exam_prep.services.retrieval_service import RetrievalService

router = APIRouter(tags=["retrieval"])


@router.post("/retrieval/query", response_model=RetrievalQueryResponse)
def query_retrieval(
    payload: RetrievalQueryRequest,
    material_store: MaterialStore = Depends(get_material_store),
    vector_store: VectorStore = Depends(get_vector_store),
) -> RetrievalQueryResponse:
    service = RetrievalService(material_store=material_store, vector_store=vector_store)
    try:
        return service.query(
            course_id=payload.course_id,
            module_id=payload.module_id,
            module_ids=payload.module_ids,
            query=payload.query,
            top_k=payload.top_k,
            selected_source_ids=payload.selected_source_ids,
        )
    except MaterialIngestionError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
