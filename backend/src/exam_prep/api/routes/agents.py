from fastapi import APIRouter, Depends, HTTPException, Query, status

from exam_prep.api.deps import (
    get_activity_store,
    get_agent_store,
    get_analytics_store,
    get_app_settings,
    get_config_store,
    get_exam_store,
    get_material_catalog,
    get_llm_client_registry,
    get_material_store,
    get_quiz_store,
    get_vector_store,
)
from exam_prep.repositories.activity_store import ActivityStore
from exam_prep.llm.registry import LLMClientRegistry
from exam_prep.repositories.agent_store import AgentStore
from exam_prep.repositories.analytics_store import AnalyticsStore
from exam_prep.repositories.config_store import ConfigStore
from exam_prep.repositories.exam_store import ExamStore
from exam_prep.repositories.material_catalog import MaterialCatalog
from exam_prep.repositories.material_store import MaterialStore
from exam_prep.repositories.quiz_store import QuizStore
from exam_prep.repositories.vector_store import VectorStore
from exam_prep.schemas.agent_tools import SmartAgentStudyPlanResponse
from exam_prep.schemas.agent import (
    AgentChatRequest,
    AgentChatResponse,
    AgentMemoryProfile,
    AgentMemoryUpdateRequest,
    AgentRecommendationDismissResponse,
    AgentRecommendationListResponse,
    AgentRunRecord,
    AgentRunRequestBody,
)
from exam_prep.services.agent_service import AgentService
from exam_prep.services.agent_tool_service import AgentToolService
from exam_prep.services.config_service import ConfigService
from exam_prep.services.llm_service import StructuredLLMService

router = APIRouter(tags=["agents"])


@router.get("/agent/study-plan", response_model=SmartAgentStudyPlanResponse)
def get_smart_agent_study_plan(
    course_id: str = Query(alias="courseId"),
    user_id: str = Query(default="demo-user", alias="userId"),
    analytics_store: AnalyticsStore = Depends(get_analytics_store),
    material_catalog: MaterialCatalog = Depends(get_material_catalog),
    activity_store: ActivityStore = Depends(get_activity_store),
) -> SmartAgentStudyPlanResponse:
    service = AgentToolService(
        analytics_store=analytics_store,
        material_catalog=material_catalog,
        activity_store=activity_store,
    )
    return service.createRecommendationCards(user_id, course_id)


@router.get("/agents/courses/{course_id}/recommendations", response_model=AgentRecommendationListResponse)
def list_course_recommendations(
    course_id: str,
    settings=Depends(get_app_settings),  # noqa: ANN001
    agent_store: AgentStore = Depends(get_agent_store),
    analytics_store: AnalyticsStore = Depends(get_analytics_store),
    material_store: MaterialStore = Depends(get_material_store),
    vector_store: VectorStore = Depends(get_vector_store),
    quiz_store: QuizStore = Depends(get_quiz_store),
    exam_store: ExamStore = Depends(get_exam_store),
) -> AgentRecommendationListResponse:
    service = AgentService(
        settings=settings,
        agent_store=agent_store,
        material_store=material_store,
        vector_store=vector_store,
        quiz_store=quiz_store,
        exam_store=exam_store,
        analytics_store=analytics_store,
    )
    return service.list_recommendations(course_id)


@router.get("/agents/courses/{course_id}/memory", response_model=AgentMemoryProfile)
def get_course_memory(
    course_id: str,
    settings=Depends(get_app_settings),  # noqa: ANN001
    agent_store: AgentStore = Depends(get_agent_store),
    analytics_store: AnalyticsStore = Depends(get_analytics_store),
    material_store: MaterialStore = Depends(get_material_store),
    vector_store: VectorStore = Depends(get_vector_store),
    quiz_store: QuizStore = Depends(get_quiz_store),
    exam_store: ExamStore = Depends(get_exam_store),
) -> AgentMemoryProfile:
    service = AgentService(
        settings=settings,
        agent_store=agent_store,
        material_store=material_store,
        vector_store=vector_store,
        quiz_store=quiz_store,
        exam_store=exam_store,
        analytics_store=analytics_store,
    )
    return service.get_memory(course_id)


@router.put("/agents/courses/{course_id}/memory", response_model=AgentMemoryProfile)
def save_course_memory(
    course_id: str,
    payload: AgentMemoryUpdateRequest,
    settings=Depends(get_app_settings),  # noqa: ANN001
    agent_store: AgentStore = Depends(get_agent_store),
    analytics_store: AnalyticsStore = Depends(get_analytics_store),
    material_store: MaterialStore = Depends(get_material_store),
    vector_store: VectorStore = Depends(get_vector_store),
    quiz_store: QuizStore = Depends(get_quiz_store),
    exam_store: ExamStore = Depends(get_exam_store),
) -> AgentMemoryProfile:
    service = AgentService(
        settings=settings,
        agent_store=agent_store,
        material_store=material_store,
        vector_store=vector_store,
        quiz_store=quiz_store,
        exam_store=exam_store,
        analytics_store=analytics_store,
    )
    return service.save_memory(course_id, payload)


@router.post("/agents/chat", response_model=AgentChatResponse)
def chat_with_agent(
    payload: AgentChatRequest,
    settings=Depends(get_app_settings),  # noqa: ANN001
    config_store: ConfigStore = Depends(get_config_store),
    llm_client_registry: LLMClientRegistry = Depends(get_llm_client_registry),
    agent_store: AgentStore = Depends(get_agent_store),
    analytics_store: AnalyticsStore = Depends(get_analytics_store),
    material_store: MaterialStore = Depends(get_material_store),
    vector_store: VectorStore = Depends(get_vector_store),
    quiz_store: QuizStore = Depends(get_quiz_store),
    exam_store: ExamStore = Depends(get_exam_store),
) -> AgentChatResponse:
    runtime_config = ConfigService().get_runtime_config(settings, config_store).butler_config
    runtime_llm_client = llm_client_registry.get_or_create_for_profile(
        runtime_config,
        profile="butler",
    )
    service = AgentService(
        settings=settings,
        agent_store=agent_store,
        material_store=material_store,
        vector_store=vector_store,
        quiz_store=quiz_store,
        exam_store=exam_store,
        analytics_store=analytics_store,
        structured_llm=StructuredLLMService(runtime_llm_client, runtime_config.model),
    )
    return service.chat(payload)


@router.post("/agents/run", response_model=AgentRunRecord)
def run_agent_check(
    payload: AgentRunRequestBody,
    settings=Depends(get_app_settings),  # noqa: ANN001
    agent_store: AgentStore = Depends(get_agent_store),
    analytics_store: AnalyticsStore = Depends(get_analytics_store),
    material_store: MaterialStore = Depends(get_material_store),
    vector_store: VectorStore = Depends(get_vector_store),
    quiz_store: QuizStore = Depends(get_quiz_store),
    exam_store: ExamStore = Depends(get_exam_store),
) -> AgentRunRecord:
    service = AgentService(
        settings=settings,
        agent_store=agent_store,
        material_store=material_store,
        vector_store=vector_store,
        quiz_store=quiz_store,
        exam_store=exam_store,
        analytics_store=analytics_store,
    )
    return service.run_course_check(intent=payload.intent, scope=payload.scope)


@router.post(
    "/agents/recommendations/{recommendation_id}/dismiss",
    response_model=AgentRecommendationDismissResponse,
)
def dismiss_recommendation(
    recommendation_id: str,
    agent_store: AgentStore = Depends(get_agent_store),
) -> AgentRecommendationDismissResponse:
    dismissed = agent_store.dismiss_recommendation(recommendation_id)
    if not dismissed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found.")
    return AgentRecommendationDismissResponse(id=recommendation_id, dismissed=True)
