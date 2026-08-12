from fastapi import APIRouter, Depends

from exam_prep.api.deps import get_analytics_store, get_exam_store, get_material_store, get_quiz_store
from exam_prep.repositories.analytics_store import AnalyticsStore
from exam_prep.repositories.dashboard_repos import DashboardRepositories
from exam_prep.repositories.exam_store import ExamStore
from exam_prep.repositories.material_store import MaterialStore
from exam_prep.repositories.quiz_store import QuizStore
from exam_prep.schemas.dashboard import CourseDashboardResponse
from exam_prep.schemas.quiz import QuestionGradeResult
from exam_prep.services.dashboard_service import DashboardService

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard/{course_id}", response_model=CourseDashboardResponse)
def get_dashboard(
    course_id: str,
    module_id: str | None = None,
    material_store: MaterialStore = Depends(get_material_store),
    quiz_store: QuizStore = Depends(get_quiz_store),
    exam_store: ExamStore = Depends(get_exam_store),
    analytics_store: AnalyticsStore = Depends(get_analytics_store),
) -> CourseDashboardResponse:
    service = DashboardService(
        DashboardRepositories(
            material_store=material_store,
            quiz_store=quiz_store,
            exam_store=exam_store,
        ),
        analytics_store=analytics_store,
    )
    return service.get_course_dashboard(course_id, module_id)


@router.get("/dashboard/{course_id}/wrong-questions", response_model=list[QuestionGradeResult])
def get_wrong_questions(
    course_id: str,
    module_id: str | None = None,
    material_store: MaterialStore = Depends(get_material_store),
    quiz_store: QuizStore = Depends(get_quiz_store),
    exam_store: ExamStore = Depends(get_exam_store),
    analytics_store: AnalyticsStore = Depends(get_analytics_store),
) -> list[QuestionGradeResult]:
    service = DashboardService(
        DashboardRepositories(
            material_store=material_store,
            quiz_store=quiz_store,
            exam_store=exam_store,
        ),
        analytics_store=analytics_store,
    )
    return service.list_wrong_questions(course_id, module_id)
