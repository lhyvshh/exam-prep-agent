from fastapi import APIRouter, Depends, HTTPException, status

from exam_prep.api.deps import get_material_store
from exam_prep.repositories.material_store import MaterialStore
from exam_prep.schemas.agent import SourceResolveRequest, SourceResolveResponse, SourceTarget
from exam_prep.schemas.materials import MaterialStudySection

router = APIRouter(tags=["source"])


@router.post("/source/resolve", response_model=SourceResolveResponse)
def resolve_source_target(
    payload: SourceResolveRequest,
    store: MaterialStore = Depends(get_material_store),
) -> SourceResolveResponse:
    target = payload.target
    record = store.get_record(target.material_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material not found.")

    section = _resolve_section(target, store)
    page_start = target.page_start
    page_end = target.page_end
    if section is not None:
        page_start = page_start or section.page_start
        page_end = page_end or section.page_end
    if page_start is None and record.page_count:
        page_start = 1
    if page_end is None:
        page_end = page_start

    file_url = f"/api/v1/materials/{record.material_id}/file"
    page_image_url = None
    embedded_images_url = None
    if page_start:
        file_url = f"{file_url}#page={page_start}"
        if record.content_type == "application/pdf" or record.file_name.lower().endswith(".pdf"):
            page_image_url = f"/api/v1/materials/{record.material_id}/pages/{page_start}/image"
            embedded_images_url = f"/api/v1/materials/{record.material_id}/pages/{page_start}/images"

    fallback_notice = None
    if section is None:
        fallback_notice = "Exact section metadata was unavailable, so the viewer opened the nearest material page."

    return SourceResolveResponse(
        target=target,
        material=record,
        section=section,
        page_start=page_start,
        page_end=page_end,
        file_url=file_url,
        page_image_url=page_image_url,
        embedded_images_url=embedded_images_url,
        fallback_notice=fallback_notice,
    )


def _resolve_section(target: SourceTarget, store: MaterialStore) -> MaterialStudySection | None:
    study_document = store.get_study_document(target.material_id)
    if study_document is None:
        return None

    for section in study_document.sections:
        if target.section_id and section.section_id == target.section_id:
            return section
        if target.source_id and target.source_id in section.source_ids:
            return section

    if target.page_start:
        for section in study_document.sections:
            start = section.page_start or target.page_start
            end = section.page_end or start
            if start <= target.page_start <= end:
                return section

    return None
