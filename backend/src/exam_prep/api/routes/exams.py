from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status

from exam_prep.api.deps import (
    get_exam_store,
    get_llm_client_registry,
    get_material_store,
    get_parser_runtime_llm_config,
    get_question_quality_service,
    get_vector_store,
)
from exam_prep.core.exceptions import LLMProviderError, MaterialIngestionError
from exam_prep.llm.registry import LLMClientRegistry
from exam_prep.ml.inference import QuestionQualityInferenceService
from exam_prep.repositories.exam_store import ExamStore
from exam_prep.repositories.material_store import MaterialStore
from exam_prep.repositories.vector_store import VectorStore
from exam_prep.schemas.exam import (
    MockExamGenerationRequest,
    MockExamGenerationResponse,
    MockExamGradeRequest,
    MockExamGradeResponse,
    MockExamReviewResponse,
    MockExamSourceBankSummary,
    MockExamSourceIngestResponse,
    MockExamSourceListResponse,
    MockExamSourceSummary,
)
from exam_prep.schemas.config import UserLLMConfig
from exam_prep.services.exam_service import ExamService
from exam_prep.services.mock_exam_source_service import MockExamSourceService

router = APIRouter(tags=["exams"])


@router.post("/exams/generate", response_model=MockExamGenerationResponse)
def generate_mock_exam(
    payload: MockExamGenerationRequest,
    material_store: MaterialStore = Depends(get_material_store),
    vector_store: VectorStore = Depends(get_vector_store),
    exam_store: ExamStore = Depends(get_exam_store),
    question_quality_service: QuestionQualityInferenceService = Depends(get_question_quality_service),
    parser_runtime_config: UserLLMConfig = Depends(get_parser_runtime_llm_config),
    llm_client_registry: LLMClientRegistry = Depends(get_llm_client_registry),
) -> MockExamGenerationResponse:
    try:
        parser_llm_client = (
            llm_client_registry.get_or_create_for_profile(
                parser_runtime_config,
                profile="parser",
            )
            if payload.source_exam_id
            else None
        )
        service = ExamService(
            material_store=material_store,
            vector_store=vector_store,
            exam_store=exam_store,
            question_quality_service=question_quality_service,
            llm_client=parser_llm_client,
            llm_model=parser_runtime_config.model if payload.source_exam_id else None,
        )
        return service.generate_exam(payload)
    except MaterialIngestionError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LLMProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Parser model generation failed. Verify parser model settings and retry.",
        ) from exc


@router.post(
    "/exams/sources/upload",
    response_model=MockExamSourceIngestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_mock_exam_source(
    course_id: str = Form(...),
    enable_ocr: bool = Form(False),
    file: UploadFile = File(...),
    material_store: MaterialStore = Depends(get_material_store),
    exam_store: ExamStore = Depends(get_exam_store),
) -> MockExamSourceIngestResponse:
    data = await file.read()
    service = MockExamSourceService(material_store=material_store, exam_store=exam_store)
    try:
        bank = service.ingest_source_bank(
            course_id=course_id,
            file_name=file.filename or "mock-exam-source.pdf",
            content_type=file.content_type,
            data=data,
            enable_ocr=enable_ocr,
        )
        return MockExamSourceIngestResponse(bank=bank)
    except MaterialIngestionError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get("/exams/sources", response_model=MockExamSourceListResponse)
def list_mock_exam_sources(
    course_id: str = Query(...),
    exam_store: ExamStore = Depends(get_exam_store),
) -> MockExamSourceListResponse:
    return MockExamSourceListResponse(
        sources=[
            MockExamSourceBankSummary(
                bank_id=bank.bank_id,
                course_id=bank.course_id,
                file_name=bank.file_name,
                uploaded_at=bank.uploaded_at,
                exam_count=len(bank.exams),
                question_count=sum(exam.question_count for exam in bank.exams),
                exams=[
                    MockExamSourceSummary(
                        source_exam_id=exam.source_exam_id,
                        title=exam.title,
                        question_count=exam.question_count,
                        answer_count=exam.answer_count,
                        average_difficulty=(
                            sum(question.difficulty for question in exam.questions)
                            / len(exam.questions)
                            if exam.questions
                            else 0.6
                        ),
                    )
                    for exam in bank.exams
                ],
                warnings=bank.warnings,
            )
            for bank in exam_store.list_source_banks_by_course(course_id)
        ]
    )


@router.get("/exams/{exam_id}/review", response_model=MockExamReviewResponse)
def get_mock_exam_review(
    exam_id: str,
    material_store: MaterialStore = Depends(get_material_store),
    vector_store: VectorStore = Depends(get_vector_store),
    exam_store: ExamStore = Depends(get_exam_store),
    question_quality_service: QuestionQualityInferenceService = Depends(get_question_quality_service),
) -> MockExamReviewResponse:
    service = ExamService(
        material_store=material_store,
        vector_store=vector_store,
        exam_store=exam_store,
        question_quality_service=question_quality_service,
    )
    try:
        return service.get_exam_review(exam_id)
    except MaterialIngestionError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/exams/grade", response_model=MockExamGradeResponse)
def grade_mock_exam(
    payload: MockExamGradeRequest,
    material_store: MaterialStore = Depends(get_material_store),
    vector_store: VectorStore = Depends(get_vector_store),
    exam_store: ExamStore = Depends(get_exam_store),
    question_quality_service: QuestionQualityInferenceService = Depends(get_question_quality_service),
) -> MockExamGradeResponse:
    service = ExamService(
        material_store=material_store,
        vector_store=vector_store,
        exam_store=exam_store,
        question_quality_service=question_quality_service,
    )
    try:
        return service.grade_exam(payload)
    except MaterialIngestionError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
