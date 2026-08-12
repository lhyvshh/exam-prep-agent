from dataclasses import dataclass

from exam_prep.repositories.exam_store import ExamStore
from exam_prep.repositories.material_store import MaterialStore
from exam_prep.repositories.quiz_store import QuizStore


@dataclass(slots=True)
class DashboardRepositories:
    material_store: MaterialStore
    quiz_store: QuizStore
    exam_store: ExamStore
