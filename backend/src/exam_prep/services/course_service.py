from uuid import uuid4

from exam_prep.core.exceptions import MaterialIngestionError
from exam_prep.repositories.course_store import CourseStore
from exam_prep.repositories.exam_store import ExamStore
from exam_prep.repositories.material_store import MaterialStore
from exam_prep.repositories.quiz_store import QuizStore
from exam_prep.repositories.workflow_store import WorkflowStore
from exam_prep.schemas.library import (
    CourseLibraryItem,
    CourseListResponse,
    CourseRecord,
    CreateCourseRequest,
    CreateModuleRequest,
    DeleteScopeResponse,
    MaterialLibraryResponse,
    ModuleLibraryItem,
    ModuleListResponse,
    ModuleRecord,
    ScopeUsageSummary,
    UpdateCourseRequest,
    UpdateModuleRequest,
)


class CourseService:
    def __init__(
        self,
        *,
        course_store: CourseStore,
        material_store: MaterialStore,
        quiz_store: QuizStore | None = None,
        exam_store: ExamStore | None = None,
        workflow_store: WorkflowStore | None = None,
    ) -> None:
        self.course_store = course_store
        self.material_store = material_store
        self.quiz_store = quiz_store
        self.exam_store = exam_store
        self.workflow_store = workflow_store

    def create_course(self, request: CreateCourseRequest) -> CourseRecord:
        course_code = request.course_code.strip()
        display_name = request.display_name.strip()
        if not course_code or not display_name:
            raise MaterialIngestionError("Course code and display name are required.")

        return self.course_store.create_course(
            CourseRecord(
                course_id=uuid4().hex,
                course_code=course_code,
                display_name=display_name,
                description=request.description.strip() if request.description else None,
            )
        )

    def list_courses(self) -> CourseListResponse:
        return CourseListResponse(courses=self.course_store.list_courses())

    def update_course(self, course_id: str, request: UpdateCourseRequest) -> CourseRecord:
        existing = self.course_store.get_course(course_id)
        if existing is None:
            raise MaterialIngestionError("Course not found.")
        course_code = request.course_code.strip()
        display_name = request.display_name.strip()
        if not course_code or not display_name:
            raise MaterialIngestionError("Course code and display name are required.")
        return self.course_store.update_course(
            existing.model_copy(
                update={
                    "course_code": course_code,
                    "display_name": display_name,
                    "description": request.description.strip() if request.description else None,
                }
            )
        )

    def create_module(self, request: CreateModuleRequest) -> ModuleRecord:
        if self.course_store.get_course(request.course_id) is None:
            raise MaterialIngestionError("Course not found.")
        module_number = request.module_number.strip()
        display_name = request.display_name.strip()
        if not module_number or not display_name:
            raise MaterialIngestionError("Module number and display name are required.")

        return self.course_store.create_module(
            ModuleRecord(
                module_id=uuid4().hex,
                course_id=request.course_id,
                module_number=module_number,
                display_name=display_name,
                description=request.description.strip() if request.description else None,
            )
        )

    def list_modules(self, course_id: str) -> ModuleListResponse:
        return ModuleListResponse(
            course_id=course_id,
            modules=self.course_store.list_modules(course_id),
        )

    def update_module(self, module_id: str, request: UpdateModuleRequest) -> ModuleRecord:
        existing = self.course_store.get_module(module_id)
        if existing is None:
            raise MaterialIngestionError("Module not found.")
        module_number = request.module_number.strip()
        display_name = request.display_name.strip()
        if not module_number or not display_name:
            raise MaterialIngestionError("Module number and display name are required.")
        return self.course_store.update_module(
            existing.model_copy(
                update={
                    "module_number": module_number,
                    "display_name": display_name,
                    "description": request.description.strip() if request.description else None,
                }
            )
        )

    def get_library(self) -> MaterialLibraryResponse:
        course_items: list[CourseLibraryItem] = []
        for course in self.course_store.list_courses():
            modules = self.course_store.list_modules(course.course_id)
            module_items = [
                ModuleLibraryItem(
                    module=module,
                    materials=self.material_store.list_records_by_course(
                        course.course_id,
                        module.module_id,
                    ),
                    usage=self._build_usage_summary(course.course_id, module.module_id),
                )
                for module in modules
            ]
            root_materials = [
                material
                for material in self.material_store.list_records_by_course(course.course_id)
                if material.module_id is None
            ]
            course_items.append(
                CourseLibraryItem(
                    course=course,
                    root_materials=root_materials,
                    modules=module_items,
                    usage=self._build_usage_summary(course.course_id, None),
                )
            )
        return MaterialLibraryResponse(courses=course_items)

    def delete_course(self, course_id: str) -> DeleteScopeResponse:
        course = self.course_store.get_course(course_id)
        if course is None:
            raise MaterialIngestionError("Course not found.")
        if not self.course_store.soft_delete_course(course_id):
            raise MaterialIngestionError("Course not found.")
        fallback_course_id = None
        fallback_module_id = None
        if self.workflow_store is not None and self.workflow_store.get_current_course_id() == course_id:
            remaining_courses = self.course_store.list_courses()
            if remaining_courses:
                fallback_course_id = remaining_courses[0].course_id
                self.workflow_store.set_current_selection(fallback_course_id, None)
            else:
                self.workflow_store.clear_current_selection()
        return DeleteScopeResponse(
            deleted=True,
            deleted_id=course_id,
            deleted_kind="course",
            fallback_course_id=fallback_course_id,
            fallback_module_id=fallback_module_id,
        )

    def delete_module(self, module_id: str) -> DeleteScopeResponse:
        module = self.course_store.get_module(module_id)
        if module is None:
            raise MaterialIngestionError("Module not found.")
        if not self.course_store.soft_delete_module(module_id):
            raise MaterialIngestionError("Module not found.")
        fallback_course_id = None
        fallback_module_id = None
        if self.workflow_store is not None and self.workflow_store.get_current_module_id() == module_id:
            fallback_course_id = module.course_id
            self.workflow_store.set_current_selection(module.course_id, None)
        return DeleteScopeResponse(
            deleted=True,
            deleted_id=module_id,
            deleted_kind="module",
            fallback_course_id=fallback_course_id,
            fallback_module_id=fallback_module_id,
        )

    def _build_usage_summary(self, course_id: str, module_id: str | None) -> ScopeUsageSummary:
        materials = self.material_store.list_records_by_course(course_id, module_id)
        quizzes = self.quiz_store.list_quiz_sessions_by_course(course_id, module_id) if self.quiz_store else []
        exams = self.exam_store.list_exam_sessions_by_course(course_id, module_id) if self.exam_store else []
        wrong_question_count = 0
        if self.quiz_store is not None:
            for session in quizzes:
                wrong_question_count += sum(
                    1 for result in self.quiz_store.get_grade_results(session.quiz.quiz_id) if not result.is_correct
                )
        return ScopeUsageSummary(
            material_count=len(materials),
            section_count=sum(record.section_count for record in materials),
            quiz_count=len(quizzes) + len(exams),
            attempt_count=len(quizzes),
            wrong_question_count=wrong_question_count,
        )
