from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse

from exam_prep.api.deps import (
    get_exam_store,
    get_material_store,
    get_package_job_runner,
    get_package_service,
    get_package_store,
    get_question_quality_service,
    get_vector_store,
)
from exam_prep.ml.inference import QuestionQualityInferenceService
from exam_prep.repositories.exam_store import ExamStore
from exam_prep.repositories.material_store import MaterialStore
from exam_prep.repositories.package_store import PackageStore
from exam_prep.repositories.vector_store import VectorStore
from exam_prep.services.exam_service import ExamService
from exam_prep.packages.completed_exam import (
    CompletedExamImportResponse,
    ImportedExamAttemptListResponse,
)
from exam_prep.packages.import_service import (
    MAX_COMPLETED_EXAM_BYTES,
    CompletedExamImportError,
    CompletedExamImportService,
)
from exam_prep.packages.jobs import PackageJobRunner
from exam_prep.packages.models import (
    PackageCreateRequest,
    PackageFileListResponse,
    PackageGenerationJob,
    PackageListResponse,
    PackageRecord,
    PackageValidationReport,
    PackageVersionListResponse,
    PackageVersionResponse,
)
from exam_prep.packages.service import (
    PackageBuildError,
    PackageNotFoundError,
    PackageService,
)

router = APIRouter(tags=["packages"])


def _completed_exam_import_service(
    package_service: PackageService,
    package_store: PackageStore,
    material_store: MaterialStore,
    vector_store: VectorStore,
    exam_store: ExamStore,
    question_quality_service: QuestionQualityInferenceService,
) -> CompletedExamImportService:
    return CompletedExamImportService(
        package_service=package_service,
        package_store=package_store,
        exam_store=exam_store,
        exam_service=ExamService(
            material_store=material_store,
            vector_store=vector_store,
            exam_store=exam_store,
            question_quality_service=question_quality_service,
        ),
    )


@router.post("/packages", response_model=PackageRecord, status_code=status.HTTP_201_CREATED)
def create_package(
    payload: PackageCreateRequest,
    service: PackageService = Depends(get_package_service),
) -> PackageRecord:
    return service.create(payload)


@router.get("/packages", response_model=PackageListResponse)
def list_packages(
    course_id: str = Query(..., min_length=1),
    service: PackageService = Depends(get_package_service),
) -> PackageListResponse:
    return PackageListResponse(packages=tuple(service.list_packages(course_id)))


@router.get("/packages/jobs/{job_id}", response_model=PackageGenerationJob)
def get_package_job(
    job_id: str,
    runner: PackageJobRunner = Depends(get_package_job_runner),
) -> PackageGenerationJob:
    job = runner.get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Package job not found.")
    return job


@router.post("/packages/jobs/{job_id}/cancel", response_model=PackageGenerationJob)
def cancel_package_job(
    job_id: str,
    runner: PackageJobRunner = Depends(get_package_job_runner),
) -> PackageGenerationJob:
    job = runner.cancel(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Package job not found.")
    if job.status.value in {"running", "complete", "failed"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only queued package jobs can be cancelled.",
        )
    return job


@router.get("/packages/{package_id}", response_model=PackageRecord)
def get_package(
    package_id: str,
    service: PackageService = Depends(get_package_service),
) -> PackageRecord:
    try:
        return service.get(package_id)
    except PackageNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/packages/{package_id}/jobs/latest", response_model=PackageGenerationJob | None)
def get_latest_package_job(
    package_id: str,
    runner: PackageJobRunner = Depends(get_package_job_runner),
) -> PackageGenerationJob | None:
    return runner.latest(package_id)


@router.get("/packages/{package_id}/versions", response_model=PackageVersionListResponse)
def list_package_versions(
    package_id: str,
    service: PackageService = Depends(get_package_service),
) -> PackageVersionListResponse:
    try:
        return PackageVersionListResponse(versions=tuple(service.list_versions(package_id)))
    except PackageNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/packages/{package_id}/versions/{version_number}",
    response_model=PackageVersionResponse,
)
def get_package_version(
    package_id: str,
    version_number: int,
    service: PackageService = Depends(get_package_service),
) -> PackageVersionResponse:
    try:
        return service.get_version_response(package_id, version_number)
    except PackageNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/packages/{package_id}/build",
    response_model=PackageGenerationJob,
    status_code=status.HTTP_202_ACCEPTED,
)
def build_package(
    package_id: str,
    runner: PackageJobRunner = Depends(get_package_job_runner),
) -> PackageGenerationJob:
    try:
        return runner.submit(package_id)
    except PackageNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/packages/{package_id}/validate", response_model=PackageValidationReport)
def validate_package(
    package_id: str,
    service: PackageService = Depends(get_package_service),
) -> PackageValidationReport:
    try:
        return service.validate(package_id)
    except PackageNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PackageBuildError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/packages/{package_id}/files", response_model=PackageFileListResponse)
def list_package_files(
    package_id: str,
    service: PackageService = Depends(get_package_service),
) -> PackageFileListResponse:
    try:
        return PackageFileListResponse(files=tuple(service.list_files(package_id)))
    except PackageNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/packages/{package_id}/attempts",
    response_model=ImportedExamAttemptListResponse,
)
def list_imported_exam_attempts(
    package_id: str,
    service: PackageService = Depends(get_package_service),
    store: PackageStore = Depends(get_package_store),
) -> ImportedExamAttemptListResponse:
    try:
        service.get(package_id)
    except PackageNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ImportedExamAttemptListResponse(attempts=tuple(store.list_exam_attempts(package_id)))


@router.post(
    "/packages/{package_id}/attempts/import",
    response_model=CompletedExamImportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def import_completed_exam_attempt(
    package_id: str,
    response: Response,
    file: UploadFile = File(...),
    package_service: PackageService = Depends(get_package_service),
    package_store: PackageStore = Depends(get_package_store),
    material_store: MaterialStore = Depends(get_material_store),
    vector_store: VectorStore = Depends(get_vector_store),
    exam_store: ExamStore = Depends(get_exam_store),
    question_quality_service: QuestionQualityInferenceService = Depends(
        get_question_quality_service
    ),
) -> CompletedExamImportResponse:
    content = await file.read(MAX_COMPLETED_EXAM_BYTES + 1)
    service = _completed_exam_import_service(
        package_service,
        package_store,
        material_store,
        vector_store,
        exam_store,
        question_quality_service,
    )
    try:
        result = service.import_completed_exam(package_id, file.filename or "", content)
    except CompletedExamImportError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if result.duplicate:
        response.status_code = status.HTTP_200_OK
    return result


@router.get("/packages/{package_id}/files/{file_id}", response_class=FileResponse)
def download_package_file(
    package_id: str,
    file_id: str,
    service: PackageService = Depends(get_package_service),
) -> FileResponse:
    try:
        file, path = service.resolve_file(package_id, file_id)
    except PackageNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PackageBuildError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return FileResponse(
        path=path,
        media_type=file.media_type,
        filename=file.file_name,
    )


@router.get(
    "/packages/{package_id}/versions/{version_number}/files/{file_id}",
    response_class=FileResponse,
)
def download_package_version_file(
    package_id: str,
    version_number: int,
    file_id: str,
    service: PackageService = Depends(get_package_service),
) -> FileResponse:
    try:
        file, path = service.resolve_version_file(package_id, version_number, file_id)
    except PackageNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PackageBuildError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return FileResponse(path=path, media_type=file.media_type, filename=file.file_name)
