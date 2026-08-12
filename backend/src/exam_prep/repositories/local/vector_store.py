from pathlib import Path

from exam_prep.repositories.vector_store import VectorStore
from exam_prep.schemas.retrieval import LocalVectorIndex


class LocalVectorStore(VectorStore):
    def __init__(self, base_path: Path) -> None:
        self.base_path = base_path / "_indices"
        self.base_path.mkdir(parents=True, exist_ok=True)

    def save_course_index(self, index: LocalVectorIndex) -> None:
        index_path = self.base_path / f"{index.course_id}.json"
        index_path.write_text(index.model_dump_json(indent=2), encoding="utf-8")

    def get_course_index(self, course_id: str) -> LocalVectorIndex | None:
        index_path = self.base_path / f"{course_id}.json"
        if not index_path.exists():
            return None
        return LocalVectorIndex.model_validate_json(index_path.read_text(encoding="utf-8"))

    def delete_course_index(self, course_id: str) -> None:
        index_path = self.base_path / f"{course_id}.json"
        if index_path.exists():
            index_path.unlink()
