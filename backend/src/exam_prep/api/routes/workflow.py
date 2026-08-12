from fastapi import APIRouter, Depends, HTTPException, status

from exam_prep.api.deps import (
    get_course_store,
    get_material_catalog,
    get_material_store,
    get_quiz_store,
    get_workflow_store,
)
from exam_prep.core.exceptions import WorkflowStateError
from exam_prep.repositories.course_store import CourseStore
from exam_prep.repositories.material_catalog import MaterialCatalog
from exam_prep.repositories.material_store import MaterialStore
from exam_prep.repositories.quiz_store import QuizStore
from exam_prep.repositories.workflow_store import WorkflowStore
from exam_prep.schemas.workflow import CurrentWorkflowResponse, WorkflowCourseSelectionRequest
from exam_prep.services.workflow_service import WorkflowService

router = APIRouter(tags=["workflow"])


@router.get("/workflow/current", response_model=CurrentWorkflowResponse)
def get_current_workflow(
    workflow_store: WorkflowStore = Depends(get_workflow_store),
    course_store: CourseStore = Depends(get_course_store),
    material_store: MaterialStore = Depends(get_material_store),
    material_catalog: MaterialCatalog = Depends(get_material_catalog),
    quiz_store: QuizStore = Depends(get_quiz_store),
) -> CurrentWorkflowResponse:
    service = WorkflowService(
        workflow_store=workflow_store,
        course_store=course_store,
        material_store=material_store,
        material_catalog=material_catalog,
        quiz_store=quiz_store,
    )
    return service.get_current_workflow()


@router.post("/workflow/current", response_model=CurrentWorkflowResponse)
def set_current_workflow(
    payload: WorkflowCourseSelectionRequest,
    workflow_store: WorkflowStore = Depends(get_workflow_store),
    course_store: CourseStore = Depends(get_course_store),
    material_store: MaterialStore = Depends(get_material_store),
    material_catalog: MaterialCatalog = Depends(get_material_catalog),
    quiz_store: QuizStore = Depends(get_quiz_store),
) -> CurrentWorkflowResponse:
    service = WorkflowService(
        workflow_store=workflow_store,
        course_store=course_store,
        material_store=material_store,
        material_catalog=material_catalog,
        quiz_store=quiz_store,
    )
    try:
        return service.get_workflow_for_course(payload.course_id, payload.module_id)
    except WorkflowStateError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
