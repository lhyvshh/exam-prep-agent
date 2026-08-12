from typing import Protocol

from exam_prep.schemas.library import CourseRecord, ModuleRecord


class CourseStore(Protocol):
    def create_course(self, course: CourseRecord) -> CourseRecord:
        ...

    def list_courses(self) -> list[CourseRecord]:
        ...

    def get_course(self, course_id: str) -> CourseRecord | None:
        ...

    def update_course(self, course: CourseRecord) -> CourseRecord:
        ...

    def soft_delete_course(self, course_id: str) -> bool:
        ...

    def create_module(self, module: ModuleRecord) -> ModuleRecord:
        ...

    def list_modules(self, course_id: str) -> list[ModuleRecord]:
        ...

    def get_module(self, module_id: str) -> ModuleRecord | None:
        ...

    def update_module(self, module: ModuleRecord) -> ModuleRecord:
        ...

    def soft_delete_module(self, module_id: str) -> bool:
        ...
