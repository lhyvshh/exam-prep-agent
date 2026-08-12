from typing import Protocol

from exam_prep.schemas.retrieval import LocalVectorIndex


class VectorStore(Protocol):
    def save_course_index(self, index: LocalVectorIndex) -> None:
        ...

    def get_course_index(self, course_id: str) -> LocalVectorIndex | None:
        ...

    def delete_course_index(self, course_id: str) -> None:
        ...
