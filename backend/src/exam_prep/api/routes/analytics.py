from fastapi import APIRouter, Depends, Query

from exam_prep.api.deps import get_analytics_store
from exam_prep.repositories.analytics_store import AnalyticsStore
from exam_prep.schemas.analytics import (
    AgentAnalyticsContextResponse,
    AnalyticsConceptsResponse,
    AnalyticsModulesResponse,
    AnalyticsOverviewResponse,
    AnalyticsQuestionTypesResponse,
    AnalyticsRecommendationsResponse,
)

router = APIRouter(tags=["analytics"])


@router.get("/analytics/overview", response_model=AnalyticsOverviewResponse)
def get_analytics_overview(
    course_id: str = Query(alias="courseId"),
    user_id: str = Query(default="demo-user", alias="userId"),
    analytics_store: AnalyticsStore = Depends(get_analytics_store),
) -> AnalyticsOverviewResponse:
    return analytics_store.get_overview(user_id=user_id, course_id=course_id)


@router.get("/analytics/modules", response_model=AnalyticsModulesResponse)
def get_module_analytics(
    course_id: str = Query(alias="courseId"),
    user_id: str = Query(default="demo-user", alias="userId"),
    analytics_store: AnalyticsStore = Depends(get_analytics_store),
) -> AnalyticsModulesResponse:
    return AnalyticsModulesResponse(
        user_id=user_id,
        course_id=course_id,
        modules=analytics_store.list_modules(user_id=user_id, course_id=course_id),
    )


@router.get("/analytics/concepts", response_model=AnalyticsConceptsResponse)
def get_concept_analytics(
    course_id: str = Query(alias="courseId"),
    user_id: str = Query(default="demo-user", alias="userId"),
    analytics_store: AnalyticsStore = Depends(get_analytics_store),
) -> AnalyticsConceptsResponse:
    return AnalyticsConceptsResponse(
        user_id=user_id,
        course_id=course_id,
        concepts=analytics_store.list_concepts(user_id=user_id, course_id=course_id),
    )


@router.get("/analytics/question-types", response_model=AnalyticsQuestionTypesResponse)
def get_question_type_analytics(
    course_id: str = Query(alias="courseId"),
    user_id: str = Query(default="demo-user", alias="userId"),
    analytics_store: AnalyticsStore = Depends(get_analytics_store),
) -> AnalyticsQuestionTypesResponse:
    return AnalyticsQuestionTypesResponse(
        user_id=user_id,
        course_id=course_id,
        question_types=analytics_store.list_question_types(user_id=user_id, course_id=course_id),
    )


@router.get("/analytics/recommendations", response_model=AnalyticsRecommendationsResponse)
def get_analytics_recommendations(
    course_id: str = Query(alias="courseId"),
    user_id: str = Query(default="demo-user", alias="userId"),
    analytics_store: AnalyticsStore = Depends(get_analytics_store),
) -> AnalyticsRecommendationsResponse:
    return AnalyticsRecommendationsResponse(
        user_id=user_id,
        course_id=course_id,
        recommendations=analytics_store.list_recommendations(user_id=user_id, course_id=course_id),
    )


@router.get("/agent/context", response_model=AgentAnalyticsContextResponse)
def get_agent_context(
    course_id: str = Query(alias="courseId"),
    user_id: str = Query(default="demo-user", alias="userId"),
    analytics_store: AnalyticsStore = Depends(get_analytics_store),
) -> AgentAnalyticsContextResponse:
    return analytics_store.get_agent_context(user_id=user_id, course_id=course_id)
