from typing import Protocol


class WorkflowStore(Protocol):
    def get_current_course_id(self) -> str | None:
        ...

    def get_current_module_id(self) -> str | None:
        ...

    def set_current_selection(self, course_id: str, module_id: str | None = None) -> None:
        ...

    def clear_current_selection(self) -> None:
        ...
