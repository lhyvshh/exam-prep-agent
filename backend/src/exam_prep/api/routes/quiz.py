import logging
from hashlib import sha256
import json
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from exam_prep.api.deps import (
    get_activity_store,
    get_app_settings,
    get_llm_client_registry,
    get_material_catalog,
    get_runtime_llm_client,
    get_material_store,
    get_question_quality_service,
    get_quiz_job_runner,
    get_quiz_job_store,
    get_quiz_store,
    get_runtime_llm_config,
    get_vector_store,
)
from exam_prep.core.config import Settings
from exam_prep.core.exceptions import ConfigurationError, LLMProviderError, MaterialIngestionError
from exam_prep.llm.base import LLMClient
from exam_prep.llm.registry import LLMClientRegistry
from exam_prep.ml.inference import QuestionQualityInferenceService
from exam_prep.repositories.material_catalog import MaterialCatalog
from exam_prep.repositories.material_store import MaterialStore
from exam_prep.repositories.activity_store import ActivityStore
from exam_prep.repositories.quiz_job_store import QuizJobStore
from exam_prep.repositories.quiz_store import QuizStore
from exam_prep.repositories.vector_store import VectorStore
from exam_prep.schemas.config import UserLLMConfig
from exam_prep.schemas.quiz import (
    QuizFromConceptRequest,
    QuizFromCourseRequest,
    QuizFromMaterialRequest,
    QuizFromMissedQuestionsRequest,
    QuizFromModuleRequest,
    QuizFromSectionRequest,
    QuizFromWeakAreaRequest,
    QuestionType,
    QuizGenerationAcceptedResponse,
    QuizGenerationCancelResponse,
    QuizGenerationJobResponse,
    QuizGenerationRequest,
    QuizReviewResponse,
    QuizGradeRequest,
    QuizGradeResponse,
    RemediationRequest,
    RemediationResponse,
    StructuredQuizGenerationRequestBase,
)
from exam_prep.schemas.scope import StudyScope
from exam_prep.services.quiz_job_runner import QuizJobRunner
from exam_prep.services.quiz_service import QuizService

router = APIRouter(tags=["quiz"])
logger = logging.getLogger(__name__)


@router.post("/quiz/generate", response_model=QuizGenerationAcceptedResponse)
def generate_quiz(
    payload: QuizGenerationRequest,
    runtime_config: UserLLMConfig = Depends(get_runtime_llm_config),
    settings: Settings = Depends(get_app_settings),
    quiz_job_store: QuizJobStore = Depends(get_quiz_job_store),
    quiz_job_runner: QuizJobRunner = Depends(get_quiz_job_runner),
) -> QuizGenerationAcceptedResponse:
    return _enqueue_quiz_generation(
        payload=payload,
        runtime_config=runtime_config,
        settings=settings,
        quiz_job_store=quiz_job_store,
        quiz_job_runner=quiz_job_runner,
    )


@router.post("/quiz/generate-from-course", response_model=QuizGenerationAcceptedResponse)
def generate_quiz_from_course(
    payload: QuizFromCourseRequest,
    runtime_config: UserLLMConfig = Depends(get_runtime_llm_config),
    settings: Settings = Depends(get_app_settings),
    quiz_job_store: QuizJobStore = Depends(get_quiz_job_store),
    quiz_job_runner: QuizJobRunner = Depends(get_quiz_job_runner),
) -> QuizGenerationAcceptedResponse:
    generation_request = _structured_generation_request(
        payload,
        course_id=payload.course_id,
        module_id=None,
        query=payload.query or "Course review",
        scope=StudyScope(course_id=payload.course_id, module_ids=payload.module_ids),
        client_request_prefix="course",
    )
    return _enqueue_quiz_generation(
        payload=generation_request,
        runtime_config=runtime_config,
        settings=settings,
        quiz_job_store=quiz_job_store,
        quiz_job_runner=quiz_job_runner,
    )


@router.post("/quiz/generate-from-section", response_model=QuizGenerationAcceptedResponse)
def generate_quiz_from_section(
    payload: QuizFromSectionRequest,
    runtime_config: UserLLMConfig = Depends(get_runtime_llm_config),
    settings: Settings = Depends(get_app_settings),
    material_catalog: MaterialCatalog = Depends(get_material_catalog),
    quiz_job_store: QuizJobStore = Depends(get_quiz_job_store),
    quiz_job_runner: QuizJobRunner = Depends(get_quiz_job_runner),
) -> QuizGenerationAcceptedResponse:
    section = material_catalog.get_structured_section(payload.section_id)
    if section is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material section not found.")
    if section.is_junk:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Section is not quiz-ready.")
    if payload.course_id is not None and payload.course_id != section.course_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Section does not belong to course.")

    generation_request = _structured_generation_request(
        payload,
        course_id=section.course_id,
        module_id=section.module_id,
        material_id=section.material_id,
        section_id=section.id,
        query=payload.query or f"Section: {section.clean_title or section.title}",
        selected_source_ids=[section.id],
        scope=StudyScope(
            course_id=section.course_id,
            module_ids=[section.module_id] if section.module_id else [],
            material_ids=[section.material_id],
            section_ids=[section.id],
        ),
        client_request_prefix="section",
    )
    return _enqueue_quiz_generation(
        payload=generation_request,
        runtime_config=runtime_config,
        settings=settings,
        quiz_job_store=quiz_job_store,
        quiz_job_runner=quiz_job_runner,
    )


@router.post("/quiz/generate-from-concept", response_model=QuizGenerationAcceptedResponse)
def generate_quiz_from_concept(
    payload: QuizFromConceptRequest,
    runtime_config: UserLLMConfig = Depends(get_runtime_llm_config),
    settings: Settings = Depends(get_app_settings),
    material_catalog: MaterialCatalog = Depends(get_material_catalog),
    quiz_job_store: QuizJobStore = Depends(get_quiz_job_store),
    quiz_job_runner: QuizJobRunner = Depends(get_quiz_job_runner),
) -> QuizGenerationAcceptedResponse:
    concept = material_catalog.get_concept(payload.concept_id)
    if concept is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Concept not found.")
    section = material_catalog.get_structured_section(concept.section_id)
    if section is None or section.is_junk:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Concept source section not found.")

    generation_request = _structured_generation_request(
        payload,
        course_id=concept.course_id,
        module_id=concept.module_id,
        material_id=concept.material_id,
        section_id=concept.section_id,
        concept_id=concept.id,
        query=payload.query or f"Concept: {concept.name}",
        selected_source_ids=[concept.section_id],
        scope=StudyScope(
            course_id=concept.course_id,
            module_ids=[concept.module_id] if concept.module_id else [],
            material_ids=[concept.material_id],
            section_ids=[concept.section_id],
        ),
        client_request_prefix="concept",
    )
    return _enqueue_quiz_generation(
        payload=generation_request,
        runtime_config=runtime_config,
        settings=settings,
        quiz_job_store=quiz_job_store,
        quiz_job_runner=quiz_job_runner,
    )


@router.post("/quiz/generate-from-material", response_model=QuizGenerationAcceptedResponse)
def generate_quiz_from_material(
    payload: QuizFromMaterialRequest,
    runtime_config: UserLLMConfig = Depends(get_runtime_llm_config),
    settings: Settings = Depends(get_app_settings),
    material_store: MaterialStore = Depends(get_material_store),
    material_catalog: MaterialCatalog = Depends(get_material_catalog),
    quiz_job_store: QuizJobStore = Depends(get_quiz_job_store),
    quiz_job_runner: QuizJobRunner = Depends(get_quiz_job_runner),
) -> QuizGenerationAcceptedResponse:
    record = material_catalog.get_record(payload.material_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material not found.")
    if payload.course_id is not None and payload.course_id != record.course_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Material does not belong to course.")
    material_sections = material_catalog.list_structured_sections(payload.material_id)
    section_ids = [section.id for section in material_sections if not section.is_junk]
    if not section_ids:
        section_ids = [section.id for section in material_sections if section.source_text.strip()]
    if not section_ids:
        parsed_document = material_store.get_parsed_document(payload.material_id)
        if parsed_document is not None:
            section_ids = [section.source_id for section in parsed_document.sections if section.text.strip()]
    if not section_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Material has no quiz-ready sections.")

    generation_request = _structured_generation_request(
        payload,
        course_id=record.course_id,
        module_id=record.module_id,
        material_id=record.material_id,
        query=payload.query or f"Material: {record.display_name or record.file_name}",
        selected_source_ids=section_ids,
        scope=StudyScope(
            course_id=record.course_id,
            module_ids=[record.module_id] if record.module_id else [],
            material_ids=[record.material_id],
            section_ids=section_ids,
        ),
        client_request_prefix="material",
    )
    return _enqueue_quiz_generation(
        payload=generation_request,
        runtime_config=runtime_config,
        settings=settings,
        quiz_job_store=quiz_job_store,
        quiz_job_runner=quiz_job_runner,
    )


@router.post("/quiz/generate-from-module", response_model=QuizGenerationAcceptedResponse)
def generate_quiz_from_module(
    payload: QuizFromModuleRequest,
    runtime_config: UserLLMConfig = Depends(get_runtime_llm_config),
    settings: Settings = Depends(get_app_settings),
    quiz_job_store: QuizJobStore = Depends(get_quiz_job_store),
    quiz_job_runner: QuizJobRunner = Depends(get_quiz_job_runner),
) -> QuizGenerationAcceptedResponse:
    generation_request = _structured_generation_request(
        payload,
        course_id=payload.course_id,
        module_id=payload.module_id,
        query=payload.query or f"Module: {payload.module_id}",
        scope=StudyScope(course_id=payload.course_id, module_ids=[payload.module_id]),
        client_request_prefix="module",
    )
    return _enqueue_quiz_generation(
        payload=generation_request,
        runtime_config=runtime_config,
        settings=settings,
        quiz_job_store=quiz_job_store,
        quiz_job_runner=quiz_job_runner,
    )


@router.post("/quiz/generate-from-weak-area", response_model=QuizGenerationAcceptedResponse)
def generate_quiz_from_weak_area(
    payload: QuizFromWeakAreaRequest,
    runtime_config: UserLLMConfig = Depends(get_runtime_llm_config),
    settings: Settings = Depends(get_app_settings),
    quiz_store: QuizStore = Depends(get_quiz_store),
    quiz_job_store: QuizJobStore = Depends(get_quiz_job_store),
    quiz_job_runner: QuizJobRunner = Depends(get_quiz_job_runner),
) -> QuizGenerationAcceptedResponse:
    source_ids, material_ids, section_id = _source_ids_for_concept(
        quiz_store=quiz_store,
        course_id=payload.course_id,
        module_id=payload.module_id,
        concept=payload.weak_area_id,
    )
    question_types = [QuestionType.MCQ]
    generation_request = _structured_generation_request(
        payload,
        course_id=payload.course_id,
        module_id=payload.module_id,
        section_id=section_id,
        weak_area_id=payload.weak_area_id,
        query=payload.query or f"Practice weak area: {payload.weak_area_id}",
        question_types=question_types,
        selected_source_ids=source_ids,
        scope=StudyScope(
            course_id=payload.course_id,
            module_ids=[payload.module_id] if payload.module_id else [],
            material_ids=material_ids,
            section_ids=source_ids,
        ),
        client_request_prefix="weak-area",
    )
    return _enqueue_quiz_generation(
        payload=generation_request,
        runtime_config=runtime_config,
        settings=settings,
        quiz_job_store=quiz_job_store,
        quiz_job_runner=quiz_job_runner,
    )


@router.post("/quiz/generate-from-missed-questions", response_model=QuizGenerationAcceptedResponse)
def generate_quiz_from_missed_questions(
    payload: QuizFromMissedQuestionsRequest,
    runtime_config: UserLLMConfig = Depends(get_runtime_llm_config),
    settings: Settings = Depends(get_app_settings),
    quiz_store: QuizStore = Depends(get_quiz_store),
    quiz_job_store: QuizJobStore = Depends(get_quiz_job_store),
    quiz_job_runner: QuizJobRunner = Depends(get_quiz_job_runner),
) -> QuizGenerationAcceptedResponse:
    missed_context = _missed_question_context(quiz_store, payload)
    if not missed_context["concepts"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No missed questions found.")
    source_ids = missed_context["source_ids"]
    generation_request = _structured_generation_request(
        payload,
        course_id=payload.course_id,
        module_id=payload.module_id,
        section_id=source_ids[0] if len(source_ids) == 1 else None,
        query=payload.query or "Practice missed questions: " + ", ".join(missed_context["concepts"][:3]),
        selected_source_ids=source_ids,
        scope=StudyScope(
            course_id=payload.course_id,
            module_ids=[payload.module_id] if payload.module_id else [],
            material_ids=missed_context["material_ids"],
            section_ids=source_ids,
        ),
        missed_question_ids=missed_context["question_ids"],
        client_request_prefix="missed",
    )
    return _enqueue_quiz_generation(
        payload=generation_request,
        runtime_config=runtime_config,
        settings=settings,
        quiz_job_store=quiz_job_store,
        quiz_job_runner=quiz_job_runner,
    )


def _enqueue_quiz_generation(
    *,
    payload: QuizGenerationRequest,
    runtime_config: UserLLMConfig,
    settings: Settings,
    quiz_job_store: QuizJobStore,
    quiz_job_runner: QuizJobRunner,
) -> QuizGenerationAcceptedResponse:
    try:
        generation_model = settings.llm_quiz_generation_model or settings.llm_quiz_model or runtime_config.model
        dedupe_key = _build_dedupe_key(
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
            logger.info(
                "Quiz generation dedupe hit job_id=%s dedupe_key=%s client_request_id=%s",
                existing_job.job_id,
                dedupe_key,
                payload.client_request_id,
            )
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
        logger.info(
            "Quiz generation job created job_id=%s dedupe_key=%s client_request_id=%s",
            job_id,
            dedupe_key,
            payload.client_request_id,
        )
        quiz_job_runner.enqueue(job_id)
        return response
    except ConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except LLMProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected quiz generation failure payload=%s", payload.model_dump())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected quiz generation failure. Check the backend logs for details.",
        ) from exc


@router.get("/quiz/jobs/{job_id}", response_model=QuizGenerationJobResponse)
def get_quiz_generation_job(
    job_id: str,
    quiz_job_store: QuizJobStore = Depends(get_quiz_job_store),
) -> QuizGenerationJobResponse:
    job = quiz_job_store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz generation job not found.")
    return job


@router.post("/quiz/jobs/{job_id}/cancel", response_model=QuizGenerationCancelResponse)
def cancel_quiz_generation_job(
    job_id: str,
    quiz_job_runner: QuizJobRunner = Depends(get_quiz_job_runner),
) -> QuizGenerationCancelResponse:
    status_value = quiz_job_runner.cancel(job_id)
    if status_value is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz generation job not found.")
    return QuizGenerationCancelResponse(job_id=job_id, status=status_value)


@router.post("/quiz/grade", response_model=QuizGradeResponse)
def grade_quiz(
    payload: QuizGradeRequest,
    activity_store: ActivityStore = Depends(get_activity_store),
    material_store: MaterialStore = Depends(get_material_store),
    vector_store: VectorStore = Depends(get_vector_store),
    quiz_store: QuizStore = Depends(get_quiz_store),
    question_quality_service: QuestionQualityInferenceService = Depends(get_question_quality_service),
    runtime_config: UserLLMConfig = Depends(get_runtime_llm_config),
    settings: Settings = Depends(get_app_settings),
    llm_client_registry: LLMClientRegistry = Depends(get_llm_client_registry),
) -> QuizGradeResponse:
    try:
        llm_client = (
            llm_client_registry.get_or_create(runtime_config)
            if settings.enable_live_quiz_grading
            else None
        )
        service = QuizService(
            material_store=material_store,
            vector_store=vector_store,
            quiz_store=quiz_store,
            question_quality_service=question_quality_service,
            runtime_config=runtime_config,
            settings=settings,
            llm_client=llm_client,
            activity_store=activity_store,
        )
        return service.grade_quiz(payload)
    except MaterialIngestionError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except LLMProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected quiz grading failure payload=%s", payload.model_dump())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected quiz grading failure. Check the backend logs for details.",
        ) from exc


@router.get("/quiz/{quiz_id}/review", response_model=QuizReviewResponse)
def get_quiz_review(
    quiz_id: str,
    quiz_store: QuizStore = Depends(get_quiz_store),
) -> QuizReviewResponse:
    session = quiz_store.get_quiz_session(quiz_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz session not found.")
    return QuizReviewResponse(
        quiz=session.quiz,
        results=quiz_store.get_grade_results(quiz_id),
    )


@router.delete("/quiz/{quiz_id}")
def delete_quiz_attempt(
    quiz_id: str,
    quiz_store: QuizStore = Depends(get_quiz_store),
) -> dict[str, object]:
    deleted_session = quiz_store.delete_quiz_session(quiz_id)
    deleted_results = quiz_store.delete_grade_results(quiz_id)
    if not deleted_session and not deleted_results:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz session not found.")
    return {
        "deleted": True,
        "quiz_id": quiz_id,
    }


@router.post("/quiz/remediation", response_model=RemediationResponse)
def generate_remediation(
    payload: RemediationRequest,
    material_store: MaterialStore = Depends(get_material_store),
    vector_store: VectorStore = Depends(get_vector_store),
    quiz_store: QuizStore = Depends(get_quiz_store),
    question_quality_service: QuestionQualityInferenceService = Depends(get_question_quality_service),
    runtime_config: UserLLMConfig = Depends(get_runtime_llm_config),
    settings: Settings = Depends(get_app_settings),
    llm_client: LLMClient | None = Depends(get_runtime_llm_client),
) -> RemediationResponse:
    try:
        service = QuizService(
            material_store=material_store,
            vector_store=vector_store,
            quiz_store=quiz_store,
            question_quality_service=question_quality_service,
            runtime_config=runtime_config,
            settings=settings,
            llm_client=llm_client,
        )
        return service.generate_remediation(payload)
    except MaterialIngestionError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except LLMProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected remediation generation failure payload=%s", payload.model_dump())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected remediation generation failure. Check the backend logs for details.",
        ) from exc


def _structured_generation_request(
    payload: StructuredQuizGenerationRequestBase,
    *,
    course_id: str,
    module_id: str | None = None,
    material_id: str | None = None,
    section_id: str | None = None,
    concept_id: str | None = None,
    weak_area_id: str | None = None,
    query: str,
    question_types: list[QuestionType] | None = None,
    selected_source_ids: list[str] | None = None,
    scope: StudyScope | None = None,
    missed_question_ids: list[str] | None = None,
    client_request_prefix: str,
) -> QuizGenerationRequest:
    request_source_ids = list(dict.fromkeys(source_id for source_id in (selected_source_ids or []) if source_id))
    return QuizGenerationRequest(
        course_id=course_id,
        user_id=payload.user_id,
        module_id=module_id,
        material_id=material_id,
        section_id=section_id,
        concept_id=concept_id,
        weak_area_id=weak_area_id,
        query=query.strip() or "Structured study quiz",
        question_count=payload.question_count,
        question_types=[QuestionType.MCQ],
        question_styles=payload.question_styles,
        retrieval_top_k=max(4, payload.question_count * 2),
        selected_source_ids=request_source_ids,
        missed_question_ids=missed_question_ids or [],
        scope=scope,
        client_request_id=payload.client_request_id or f"{client_request_prefix}-{uuid4().hex}",
    )


def _source_ids_for_concept(
    *,
    quiz_store: QuizStore,
    course_id: str,
    module_id: str | None,
    concept: str,
) -> tuple[list[str], list[str], str | None]:
    normalized_concept = _normalize_label(concept)
    source_ids: list[str] = []
    material_ids: list[str] = []
    section_id: str | None = None
    for session in quiz_store.list_quiz_sessions_by_course(course_id, module_id):
        for key in session.answer_keys:
            if _normalize_label(key.concept) != normalized_concept:
                continue
            for citation in key.citations:
                if citation.source_id:
                    source_ids.append(citation.source_id)
                    section_id = section_id or citation.source_id
                if citation.material_id:
                    material_ids.append(citation.material_id)
            if key.section_id:
                source_ids.append(key.section_id)
                section_id = section_id or key.section_id
            if key.material_id:
                material_ids.append(key.material_id)
    return _unique(source_ids), _unique(material_ids), section_id


def _missed_question_context(
    quiz_store: QuizStore,
    payload: QuizFromMissedQuestionsRequest,
) -> dict[str, list[str]]:
    sessions = []
    if payload.quiz_id:
        session = quiz_store.get_quiz_session(payload.quiz_id)
        if session is not None and session.quiz.course_id == payload.course_id:
            sessions = [session]
    else:
        sessions = quiz_store.list_quiz_sessions_by_course(payload.course_id, payload.module_id)

    requested_question_ids = set(payload.question_ids)
    concepts: list[str] = []
    source_ids: list[str] = []
    material_ids: list[str] = []
    question_ids: list[str] = []
    for session in sessions:
        if payload.module_id is not None and session.quiz.module_id != payload.module_id:
            continue
        for result in quiz_store.get_grade_results(session.quiz.quiz_id):
            if result.is_correct:
                continue
            if requested_question_ids and result.question_id not in requested_question_ids:
                continue
            concepts.append(result.concept)
            question_ids.append(result.question_id)
            for citation in result.citations:
                if citation.source_id:
                    source_ids.append(citation.source_id)
                if citation.material_id:
                    material_ids.append(citation.material_id)

    return {
        "concepts": _unique(concepts),
        "source_ids": _unique(source_ids),
        "material_ids": _unique(material_ids),
        "question_ids": _unique(question_ids),
    }


def _normalize_label(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _build_dedupe_key(
    *,
    payload: QuizGenerationRequest,
    provider: str,
    model: str,
) -> str:
    canonical_payload = {
        "course_id": payload.course_id,
        "user_id": payload.user_id,
        "module_id": payload.module_id,
        "material_id": payload.material_id,
        "section_id": payload.section_id,
        "concept_id": payload.concept_id,
        "weak_area_id": payload.weak_area_id,
        "query": payload.query.strip(),
        "question_count": payload.question_count,
        "question_types": sorted(question_type.value for question_type in payload.question_types),
        "question_styles": sorted(question_style.value for question_style in payload.question_styles),
        "retrieval_top_k": payload.retrieval_top_k,
        "selected_source_ids": sorted(source_id for source_id in payload.selected_source_ids if source_id),
        "missed_question_ids": sorted(question_id for question_id in payload.missed_question_ids if question_id),
        "scope": payload.scope.model_dump(mode="json") if payload.scope else None,
        "provider": provider,
        "model": model,
    }
    return sha256(json.dumps(canonical_payload, sort_keys=True).encode("utf-8")).hexdigest()
