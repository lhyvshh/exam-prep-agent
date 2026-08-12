from hashlib import sha256
import io
import json
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from pypdf import PdfReader

from exam_prep.api.deps import (
    get_app_settings,
    get_material_catalog,
    get_material_job_runner,
    get_material_store,
    get_quiz_job_runner,
    get_quiz_job_store,
    get_runtime_llm_config,
    get_vector_store,
    get_workflow_store,
)
from exam_prep.core.config import Settings
from exam_prep.core.exceptions import MaterialIngestionError
from exam_prep.repositories.material_catalog import MaterialCatalog
from exam_prep.repositories.quiz_job_store import QuizJobStore
from exam_prep.repositories.material_store import MaterialStore
from exam_prep.repositories.vector_store import VectorStore
from exam_prep.repositories.workflow_store import WorkflowStore
from exam_prep.schemas.config import UserLLMConfig
from exam_prep.schemas.materials import (
    ConceptSourceResponse,
    CourseMaterialsResponse,
    MaterialDeleteResponse,
    MaterialDetailResponse,
    MaterialListResponse,
    MaterialSectionsResponse,
    MaterialPreviewResponse,
    MaterialStudyResponse,
    MaterialStudySectionResponse,
    MaterialStudySectionUpdateRequest,
    MaterialStatusResponse,
    MaterialUploadResponse,
    SectionChunksResponse,
    SectionDetailResponse,
)
from exam_prep.schemas.quiz import (
    QuestionType,
    QuizGenerationAcceptedResponse,
    QuizGenerationRequest,
)
from exam_prep.schemas.scope import StudyScope
from exam_prep.services.material_service import MaterialService
from exam_prep.services.material_job_runner import MaterialJobRunner
from exam_prep.services.quiz_job_runner import QuizJobRunner

router = APIRouter(tags=["materials"])


@router.post("/materials/upload", response_model=MaterialUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_material(
    course_id: str = Form(...),
    module_id: str | None = Form(default=None),
    file: UploadFile = File(...),
    store: MaterialStore = Depends(get_material_store),
    vector_store: VectorStore = Depends(get_vector_store),
    workflow_store: WorkflowStore = Depends(get_workflow_store),
    material_catalog: MaterialCatalog = Depends(get_material_catalog),
    material_job_runner: MaterialJobRunner = Depends(get_material_job_runner),
    settings: Settings = Depends(get_app_settings),
) -> MaterialUploadResponse:
    service = MaterialService(
        store=store,
        vector_store=vector_store,
        workflow_store=workflow_store,
        material_catalog=material_catalog,
        settings=settings,
    )
    try:
        payload = await file.read()
        return service.ingest_material(
            course_id=course_id,
            module_id=module_id,
            file_name=file.filename or "",
            content_type=file.content_type,
            data=payload,
            job_runner=material_job_runner,
        )
    except MaterialIngestionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/materials", response_model=MaterialListResponse)
def list_materials(
    course_id: str | None = None,
    module_id: str | None = None,
    store: MaterialStore = Depends(get_material_store),
    material_catalog: MaterialCatalog = Depends(get_material_catalog),
) -> MaterialListResponse:
    service = MaterialService(store=store, material_catalog=material_catalog)
    try:
        return service.list_materials(course_id, module_id)
    except MaterialIngestionError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/materials/{material_id}", response_model=MaterialDetailResponse)
def get_material(
    material_id: str,
    store: MaterialStore = Depends(get_material_store),
    material_catalog: MaterialCatalog = Depends(get_material_catalog),
) -> MaterialDetailResponse:
    service = MaterialService(store=store, material_catalog=material_catalog)
    try:
        return service.get_material(material_id)
    except MaterialIngestionError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/materials/{material_id}/sections", response_model=MaterialSectionsResponse)
def list_material_sections(
    material_id: str,
    store: MaterialStore = Depends(get_material_store),
    material_catalog: MaterialCatalog = Depends(get_material_catalog),
) -> MaterialSectionsResponse:
    service = MaterialService(store=store, material_catalog=material_catalog)
    try:
        return service.list_material_sections(material_id)
    except MaterialIngestionError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/sections/{section_id}", response_model=SectionDetailResponse)
def get_section(
    section_id: str,
    store: MaterialStore = Depends(get_material_store),
    material_catalog: MaterialCatalog = Depends(get_material_catalog),
) -> SectionDetailResponse:
    service = MaterialService(store=store, material_catalog=material_catalog)
    try:
        return service.get_section_detail(section_id)
    except MaterialIngestionError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/sections/{section_id}/chunks", response_model=SectionChunksResponse)
def list_section_chunks(
    section_id: str,
    store: MaterialStore = Depends(get_material_store),
    material_catalog: MaterialCatalog = Depends(get_material_catalog),
) -> SectionChunksResponse:
    service = MaterialService(store=store, material_catalog=material_catalog)
    try:
        return service.list_section_chunks(section_id)
    except MaterialIngestionError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/concepts/{concept_id}/source", response_model=ConceptSourceResponse)
def get_concept_source(
    concept_id: str,
    store: MaterialStore = Depends(get_material_store),
    material_catalog: MaterialCatalog = Depends(get_material_catalog),
) -> ConceptSourceResponse:
    service = MaterialService(store=store, material_catalog=material_catalog)
    try:
        return service.get_concept_source(concept_id)
    except MaterialIngestionError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/concepts/{concept_id}/quiz", response_model=QuizGenerationAcceptedResponse)
def generate_quiz_for_concept(
    concept_id: str,
    runtime_config: UserLLMConfig = Depends(get_runtime_llm_config),
    settings: Settings = Depends(get_app_settings),
    store: MaterialStore = Depends(get_material_store),
    material_catalog: MaterialCatalog = Depends(get_material_catalog),
    quiz_job_store: QuizJobStore = Depends(get_quiz_job_store),
    quiz_job_runner: QuizJobRunner = Depends(get_quiz_job_runner),
) -> QuizGenerationAcceptedResponse:
    service = MaterialService(store=store, material_catalog=material_catalog)
    try:
        source_response = service.get_concept_source(concept_id)
    except MaterialIngestionError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    concept = source_response.concept
    record = store.get_record(concept.material_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material not found.")

    payload = QuizGenerationRequest(
        course_id=concept.course_id,
        module_id=concept.module_id,
        query=f"Concept: {concept.name}",
        question_count=3,
        question_types=[QuestionType.MCQ],
        retrieval_top_k=4,
        selected_source_ids=[concept.section_id],
        scope=StudyScope(
            course_id=concept.course_id,
            module_ids=[concept.module_id] if concept.module_id else [],
            material_ids=[concept.material_id],
            section_ids=[concept.section_id],
        ),
        client_request_id=f"concept-{concept.id}-{uuid4().hex}",
    )
    generation_model = settings.llm_quiz_generation_model or settings.llm_quiz_model or runtime_config.model
    dedupe_key = _build_section_quiz_dedupe_key(
        payload=payload,
        provider=runtime_config.provider.value,
        model=generation_model,
    )
    existing_job = (
        quiz_job_store.find_active_job_by_dedupe_key(dedupe_key)
        if settings.enable_quiz_cache
        else None
    )
    if existing_job is not None:
        quiz_job_runner.enqueue(existing_job.job_id)
        return existing_job

    job_id = uuid4().hex
    response = quiz_job_store.create_job(
        job_id=job_id,
        dedupe_key=dedupe_key,
        request=payload,
        provider=runtime_config.provider.value,
        model=generation_model,
    )
    quiz_job_runner.enqueue(job_id)
    return response


@router.get("/materials/{material_id}/status", response_model=MaterialStatusResponse)
def get_material_status(
    material_id: str,
    store: MaterialStore = Depends(get_material_store),
) -> MaterialStatusResponse:
    service = MaterialService(store=store)
    try:
        return service.get_status(material_id)
    except MaterialIngestionError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/materials/{material_id}/retry", response_model=MaterialStatusResponse)
def retry_material_processing(
    material_id: str,
    store: MaterialStore = Depends(get_material_store),
    vector_store: VectorStore = Depends(get_vector_store),
    material_job_runner: MaterialJobRunner = Depends(get_material_job_runner),
) -> MaterialStatusResponse:
    service = MaterialService(store=store, vector_store=vector_store)
    try:
        return service.retry_processing(material_id, material_job_runner)
    except MaterialIngestionError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/materials/{material_id}/reprocess", response_model=MaterialStatusResponse)
def reprocess_material(
    material_id: str,
    store: MaterialStore = Depends(get_material_store),
    vector_store: VectorStore = Depends(get_vector_store),
) -> MaterialStatusResponse:
    service = MaterialService(store=store, vector_store=vector_store)
    initial_record = store.get_record(material_id)
    try:
        return service.reprocess_material(material_id)
    except MaterialIngestionError as exc:
        record = store.get_record(material_id) or initial_record
        if record is None or "not found" in str(exc).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_material_reprocess_error_detail(material_id, record, exc),
        ) from exc


def _material_reprocess_error_detail(
    material_id: str,
    record,
    exc: BaseException,
) -> dict[str, object]:
    return {
        "error": "material_reprocess_failed",
        "material_id": material_id,
        "file_name": getattr(record, "file_name", None),
        "page_count": getattr(record, "page_count", None),
        "parser_phase": getattr(getattr(record, "processing_status", None), "value", "reprocess"),
        "current_page_number": getattr(exc, "current_page_number", None),
        "detected_page_type": getattr(exc, "detected_page_type", None),
        "failing_source_unit_id": getattr(exc, "source_unit_id", None),
        "failing_card_id": getattr(exc, "card_id", None),
        "failure_reason": str(exc),
    }


@router.get("/materials/{material_id}/preview", response_model=MaterialPreviewResponse)
def get_material_preview(
    material_id: str,
    chunk_limit: int = 5,
    store: MaterialStore = Depends(get_material_store),
) -> MaterialPreviewResponse:
    service = MaterialService(store=store)
    try:
        return service.get_preview(material_id, chunk_limit=chunk_limit)
    except MaterialIngestionError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/materials/{material_id}/file")
def get_material_file(
    material_id: str,
    store: MaterialStore = Depends(get_material_store),
) -> Response:
    record = store.get_record(material_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material not found.")

    if record.file_path:
        source_path = Path(record.file_path)
        if source_path.exists():
            return FileResponse(
                source_path,
                media_type=record.content_type,
                filename=record.file_name,
                content_disposition_type="inline",
            )

    raw_bytes = store.get_raw_material(material_id)
    if raw_bytes is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material source file not found.")
    return Response(
        content=raw_bytes,
        media_type=record.content_type,
        headers={"Content-Disposition": f'inline; filename="{record.file_name}"'},
    )


@router.get("/materials/{material_id}/formula-crops/{asset_name}")
def get_material_formula_crop(
    material_id: str,
    asset_name: str,
    store: MaterialStore = Depends(get_material_store),
) -> Response:
    record = store.get_record(material_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material not found.")
    asset_path = store.get_formula_crop_asset_path(material_id, asset_name)
    if asset_path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Formula crop not found.")
    return FileResponse(
        asset_path,
        media_type="image/png",
        filename=asset_path.name,
        content_disposition_type="inline",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/materials/{material_id}/pages/{page_number}/image")
def get_material_page_image(
    material_id: str,
    page_number: int,
    width: int = Query(default=1100, ge=320, le=2200),
    crop: str | None = Query(default=None),
    store: MaterialStore = Depends(get_material_store),
) -> Response:
    record = store.get_record(material_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material not found.")
    if not _is_pdf(record.content_type, record.file_name):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Material is not a PDF.")

    raw_bytes = _material_bytes(material_id, store)
    try:
        import fitz  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="PDF page image rendering requires PyMuPDF. Install the project dependencies and retry.",
        ) from exc

    try:
        document = fitz.open(stream=raw_bytes, filetype="pdf")
        page_index = page_number - 1
        if page_index < 0 or page_index >= len(document):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PDF page not found.")
        page = document[page_index]
        clip = _parse_crop(crop, page.rect, fitz) if crop else None
        source_rect = clip or page.rect
        zoom = width / max(source_rect.width, 1)
        pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip, alpha=False)
        return Response(
            content=pixmap.tobytes("png"),
            media_type="image/png",
            headers={
                "Cache-Control": "public, max-age=86400",
                "Content-Disposition": f'inline; filename="{record.file_name}-page-{page_number}.png"',
            },
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unable to render PDF page.") from exc


@router.get("/materials/{material_id}/pages/{page_number}/images")
def list_material_page_images(
    material_id: str,
    page_number: int,
    store: MaterialStore = Depends(get_material_store),
) -> dict[str, object]:
    record = store.get_record(material_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material not found.")
    if not _is_pdf(record.content_type, record.file_name):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Material is not a PDF.")

    raw_bytes = _material_bytes(material_id, store)
    try:
        reader = PdfReader(io.BytesIO(raw_bytes))
        page_index = page_number - 1
        if page_index < 0 or page_index >= len(reader.pages):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PDF page not found.")
        images = []
        for index, image_file in enumerate(getattr(reader.pages[page_index], "images", []), start=1):
            image_bytes = getattr(image_file, "data", b"")
            if not image_bytes:
                continue
            image_name = getattr(image_file, "name", f"image-{index}")
            extension = Path(image_name).suffix.lower()
            media_type = {
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".gif": "image/gif",
                ".tif": "image/tiff",
                ".tiff": "image/tiff",
            }.get(extension, "application/octet-stream")
            images.append(
                {
                    "image_id": f"{material_id}-page-{page_number}-image-{index}",
                    "name": image_name,
                    "media_type": media_type,
                    "byte_count": len(image_bytes),
                    "src": f"/api/v1/materials/{material_id}/pages/{page_number}/images/{index}",
                }
            )
        return {"material_id": material_id, "page_number": page_number, "images": images}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unable to extract PDF images.") from exc


@router.get("/materials/{material_id}/pages/{page_number}/images/{image_index}")
def get_material_page_embedded_image(
    material_id: str,
    page_number: int,
    image_index: int,
    store: MaterialStore = Depends(get_material_store),
) -> Response:
    payload = _extract_pdf_image(material_id, page_number, image_index, store)
    return Response(
        content=payload["content"],
        media_type=payload["media_type"],
        headers={
            "Cache-Control": "public, max-age=86400",
            "Content-Disposition": f'inline; filename="{payload["name"]}"',
        },
    )


@router.get("/materials/{material_id}/study", response_model=MaterialStudyResponse)
def get_material_study(
    material_id: str,
    group_id: str | None = None,
    offset: int = 0,
    limit: int = 20,
    store: MaterialStore = Depends(get_material_store),
) -> MaterialStudyResponse:
    service = MaterialService(store=store)
    try:
        return service.get_study_material(
            material_id,
            group_id=group_id,
            offset=offset,
            limit=limit,
        )
    except MaterialIngestionError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/materials/{material_id}/study/sections/{section_id}",
    response_model=MaterialStudySectionResponse,
)
def get_material_study_section(
    material_id: str,
    section_id: str,
    store: MaterialStore = Depends(get_material_store),
) -> MaterialStudySectionResponse:
    service = MaterialService(store=store)
    try:
        return service.get_study_section(material_id, section_id)
    except MaterialIngestionError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch(
    "/materials/{material_id}/study/sections/{section_id}",
    response_model=MaterialStudySectionResponse,
)
def update_material_study_section(
    material_id: str,
    section_id: str,
    payload: MaterialStudySectionUpdateRequest,
    store: MaterialStore = Depends(get_material_store),
) -> MaterialStudySectionResponse:
    service = MaterialService(store=store)
    try:
        return service.update_study_section(material_id, section_id, payload)
    except MaterialIngestionError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/materials/{material_id}/study/sections/{section_id}/quiz",
    response_model=QuizGenerationAcceptedResponse,
)
def generate_quiz_for_material_section(
    material_id: str,
    section_id: str,
    runtime_config: UserLLMConfig = Depends(get_runtime_llm_config),
    settings: Settings = Depends(get_app_settings),
    store: MaterialStore = Depends(get_material_store),
    quiz_job_store: QuizJobStore = Depends(get_quiz_job_store),
    quiz_job_runner: QuizJobRunner = Depends(get_quiz_job_runner),
) -> QuizGenerationAcceptedResponse:
    service = MaterialService(store=store)
    try:
        section_response = service.get_study_section(material_id, section_id)
    except MaterialIngestionError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    section = section_response.section
    record = store.get_record(material_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material not found.")
    if not section.quiz_ready or not section.source_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This section is not ready for quiz generation.",
        )

    payload = QuizGenerationRequest(
        course_id=record.course_id,
        module_id=record.module_id,
        query=f"Section: {section.normalized_title}",
        question_count=3,
        question_types=[QuestionType.MCQ],
        retrieval_top_k=6,
        selected_source_ids=section.source_ids,
        scope=StudyScope(
            course_id=record.course_id,
            module_ids=[record.module_id] if record.module_id else [],
            material_ids=[record.material_id],
            section_ids=section.source_ids,
        ),
        client_request_id=f"material-section-{section.section_id}-{uuid4().hex}",
    )
    generation_model = settings.llm_quiz_generation_model or settings.llm_quiz_model or runtime_config.model
    dedupe_key = _build_section_quiz_dedupe_key(
        payload=payload,
        provider=runtime_config.provider.value,
        model=generation_model,
    )
    existing_job = (
        quiz_job_store.find_active_job_by_dedupe_key(dedupe_key)
        if settings.enable_quiz_cache
        else None
    )
    if existing_job is not None:
        quiz_job_runner.enqueue(existing_job.job_id)
        return existing_job

    job_id = uuid4().hex
    response = quiz_job_store.create_job(
        job_id=job_id,
        dedupe_key=dedupe_key,
        request=payload,
        provider=runtime_config.provider.value,
        model=generation_model,
    )
    quiz_job_runner.enqueue(job_id)
    return response


@router.post("/materials/{material_id}/study/regenerate", response_model=MaterialStudyResponse)
def regenerate_material_study(
    material_id: str,
    store: MaterialStore = Depends(get_material_store),
) -> MaterialStudyResponse:
    service = MaterialService(store=store)
    try:
        return service.regenerate_study_material(material_id)
    except MaterialIngestionError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/materials/course/{course_id}", response_model=CourseMaterialsResponse)
def list_course_materials(
    course_id: str,
    module_id: str | None = None,
    store: MaterialStore = Depends(get_material_store),
    material_catalog: MaterialCatalog = Depends(get_material_catalog),
) -> CourseMaterialsResponse:
    service = MaterialService(store=store, material_catalog=material_catalog)
    try:
        return service.list_course_materials(course_id, module_id)
    except MaterialIngestionError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete("/materials/{material_id}", response_model=MaterialDeleteResponse)
def delete_material(
    material_id: str,
    store: MaterialStore = Depends(get_material_store),
    vector_store: VectorStore = Depends(get_vector_store),
    workflow_store: WorkflowStore = Depends(get_workflow_store),
    material_catalog: MaterialCatalog = Depends(get_material_catalog),
) -> MaterialDeleteResponse:
    service = MaterialService(
        store=store,
        vector_store=vector_store,
        workflow_store=workflow_store,
        material_catalog=material_catalog,
    )
    try:
        return service.delete_material(material_id)
    except MaterialIngestionError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


def _build_section_quiz_dedupe_key(
    *,
    payload: QuizGenerationRequest,
    provider: str,
    model: str,
) -> str:
    canonical_payload = {
        "course_id": payload.course_id,
        "module_id": payload.module_id,
        "query": payload.query.strip(),
        "question_count": payload.question_count,
        "question_types": sorted(question_type.value for question_type in payload.question_types),
        "retrieval_top_k": payload.retrieval_top_k,
        "selected_source_ids": sorted(source_id for source_id in payload.selected_source_ids if source_id),
        "scope": payload.scope.model_dump(mode="json") if payload.scope else None,
        "provider": provider,
        "model": model,
    }
    return sha256(json.dumps(canonical_payload, sort_keys=True).encode("utf-8")).hexdigest()


def _is_pdf(content_type: str, file_name: str) -> bool:
    return content_type == "application/pdf" or file_name.lower().endswith(".pdf")


def _material_bytes(material_id: str, store: MaterialStore) -> bytes:
    record = store.get_record(material_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material not found.")
    if record.file_path:
        source_path = Path(record.file_path)
        if source_path.exists():
            return source_path.read_bytes()
    raw_bytes = store.get_raw_material(material_id)
    if raw_bytes is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material source file not found.")
    return raw_bytes


def _parse_crop(crop: str, page_rect, fitz_module):  # noqa: ANN001
    try:
        left, top, right, bottom = [float(part.strip()) for part in crop.split(",")]
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Crop must be left,top,right,bottom fractions between 0 and 1.",
        ) from exc
    values = [left, top, right, bottom]
    if any(value < 0 or value > 1 for value in values) or left >= right or top >= bottom:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Crop must be left,top,right,bottom fractions between 0 and 1.",
        )
    return fitz_module.Rect(
        page_rect.x0 + page_rect.width * left,
        page_rect.y0 + page_rect.height * top,
        page_rect.x0 + page_rect.width * right,
        page_rect.y0 + page_rect.height * bottom,
    )


def _extract_pdf_image(
    material_id: str,
    page_number: int,
    image_index: int,
    store: MaterialStore,
) -> dict[str, object]:
    if image_index < 1:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PDF image not found.")
    raw_bytes = _material_bytes(material_id, store)
    try:
        reader = PdfReader(io.BytesIO(raw_bytes))
        page_index = page_number - 1
        if page_index < 0 or page_index >= len(reader.pages):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PDF page not found.")
        images = list(getattr(reader.pages[page_index], "images", []))
        if image_index > len(images):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PDF image not found.")
        image_file = images[image_index - 1]
        image_name = getattr(image_file, "name", f"page-{page_number}-image-{image_index}.bin")
        image_bytes = getattr(image_file, "data", b"")
        if not image_bytes:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PDF image not found.")
        extension = Path(image_name).suffix.lower()
        media_type = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".tif": "image/tiff",
            ".tiff": "image/tiff",
        }.get(extension, "application/octet-stream")
        return {
            "name": image_name,
            "media_type": media_type,
            "content": image_bytes,
        }
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unable to extract PDF image.") from exc
