from fastapi import APIRouter, Depends, HTTPException, status

from exam_prep.api.deps import (
    get_course_store,
    get_exam_store,
    get_material_store,
    get_quiz_store,
    get_workflow_store,
)
from exam_prep.core.exceptions import MaterialIngestionError
from exam_prep.repositories.course_store import CourseStore
from exam_prep.repositories.exam_store import ExamStore
from exam_prep.repositories.material_store import MaterialStore
from exam_prep.repositories.quiz_store import QuizStore
from exam_prep.repositories.workflow_store import WorkflowStore
from exam_prep.schemas.library import (
    CourseListResponse,
    CourseRecord,
    CreateCourseRequest,
    CreateModuleRequest,
    DeleteScopeResponse,
    MaterialLibraryResponse,
    ModuleListResponse,
    ModuleRecord,
    UpdateCourseRequest,
    UpdateModuleRequest,
)
from exam_prep.services.course_service import CourseService

router = APIRouter(tags=["courses"])


@router.get("/courses", response_model=CourseListResponse)
def list_courses(
    course_store: CourseStore = Depends(get_course_store),
    material_store: MaterialStore = Depends(get_material_store),
    quiz_store: QuizStore = Depends(get_quiz_store),
    exam_store: ExamStore = Depends(get_exam_store),
) -> CourseListResponse:
    return CourseService(
        course_store=course_store,
        material_store=material_store,
        quiz_store=quiz_store,
        exam_store=exam_store,
    ).list_courses()


@router.post("/courses", response_model=CourseRecord, status_code=status.HTTP_201_CREATED)
def create_course(
    payload: CreateCourseRequest,
    course_store: CourseStore = Depends(get_course_store),
    material_store: MaterialStore = Depends(get_material_store),
    quiz_store: QuizStore = Depends(get_quiz_store),
    exam_store: ExamStore = Depends(get_exam_store),
) -> CourseRecord:
    try:
        return CourseService(
            course_store=course_store,
            material_store=material_store,
            quiz_store=quiz_store,
            exam_store=exam_store,
        ).create_course(payload)
    except MaterialIngestionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.put("/courses/{course_id}", response_model=CourseRecord)
def update_course(
    course_id: str,
    payload: UpdateCourseRequest,
    course_store: CourseStore = Depends(get_course_store),
    material_store: MaterialStore = Depends(get_material_store),
    quiz_store: QuizStore = Depends(get_quiz_store),
    exam_store: ExamStore = Depends(get_exam_store),
) -> CourseRecord:
    try:
        return CourseService(
            course_store=course_store,
            material_store=material_store,
            quiz_store=quiz_store,
            exam_store=exam_store,
        ).update_course(course_id, payload)
    except MaterialIngestionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete("/courses/{course_id}", response_model=DeleteScopeResponse)
def delete_course(
    course_id: str,
    course_store: CourseStore = Depends(get_course_store),
    material_store: MaterialStore = Depends(get_material_store),
    quiz_store: QuizStore = Depends(get_quiz_store),
    exam_store: ExamStore = Depends(get_exam_store),
    workflow_store: WorkflowStore = Depends(get_workflow_store),
) -> DeleteScopeResponse:
    try:
        return CourseService(
            course_store=course_store,
            material_store=material_store,
            quiz_store=quiz_store,
            exam_store=exam_store,
            workflow_store=workflow_store,
        ).delete_course(course_id)
    except MaterialIngestionError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/courses/{course_id}/modules", response_model=ModuleListResponse)
def list_modules(
    course_id: str,
    course_store: CourseStore = Depends(get_course_store),
    material_store: MaterialStore = Depends(get_material_store),
    quiz_store: QuizStore = Depends(get_quiz_store),
    exam_store: ExamStore = Depends(get_exam_store),
) -> ModuleListResponse:
    return CourseService(
        course_store=course_store,
        material_store=material_store,
        quiz_store=quiz_store,
        exam_store=exam_store,
    ).list_modules(course_id)


@router.post("/courses/modules", response_model=ModuleRecord, status_code=status.HTTP_201_CREATED)
def create_module(
    payload: CreateModuleRequest,
    course_store: CourseStore = Depends(get_course_store),
    material_store: MaterialStore = Depends(get_material_store),
    quiz_store: QuizStore = Depends(get_quiz_store),
    exam_store: ExamStore = Depends(get_exam_store),
) -> ModuleRecord:
    try:
        return CourseService(
            course_store=course_store,
            material_store=material_store,
            quiz_store=quiz_store,
            exam_store=exam_store,
        ).create_module(payload)
    except MaterialIngestionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.put("/courses/modules/{module_id}", response_model=ModuleRecord)
def update_module(
    module_id: str,
    payload: UpdateModuleRequest,
    course_store: CourseStore = Depends(get_course_store),
    material_store: MaterialStore = Depends(get_material_store),
    quiz_store: QuizStore = Depends(get_quiz_store),
    exam_store: ExamStore = Depends(get_exam_store),
) -> ModuleRecord:
    try:
        return CourseService(
            course_store=course_store,
            material_store=material_store,
            quiz_store=quiz_store,
            exam_store=exam_store,
        ).update_module(module_id, payload)
    except MaterialIngestionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete("/courses/modules/{module_id}", response_model=DeleteScopeResponse)
def delete_module(
    module_id: str,
    course_store: CourseStore = Depends(get_course_store),
    material_store: MaterialStore = Depends(get_material_store),
    quiz_store: QuizStore = Depends(get_quiz_store),
    exam_store: ExamStore = Depends(get_exam_store),
    workflow_store: WorkflowStore = Depends(get_workflow_store),
) -> DeleteScopeResponse:
    try:
        return CourseService(
            course_store=course_store,
            material_store=material_store,
            quiz_store=quiz_store,
            exam_store=exam_store,
            workflow_store=workflow_store,
        ).delete_module(module_id)
    except MaterialIngestionError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/courses/library", response_model=MaterialLibraryResponse)
def get_material_library(
    course_store: CourseStore = Depends(get_course_store),
    material_store: MaterialStore = Depends(get_material_store),
    quiz_store: QuizStore = Depends(get_quiz_store),
    exam_store: ExamStore = Depends(get_exam_store),
) -> MaterialLibraryResponse:
    return CourseService(
        course_store=course_store,
        material_store=material_store,
        quiz_store=quiz_store,
        exam_store=exam_store,
    ).get_library()
