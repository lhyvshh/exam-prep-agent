from exam_prep.repositories.dashboard_repos import DashboardRepositories
from exam_prep.repositories.analytics_store import AnalyticsStore
from exam_prep.schemas.dashboard import (
    CourseDashboardResponse,
    MockExamHistoryItem,
    QuizHistoryItem,
)
from exam_prep.schemas.quiz import QuestionGradeResult, QuizAttemptSummary


class DashboardService:
    def __init__(self, repos: DashboardRepositories, analytics_store: AnalyticsStore | None = None) -> None:
        self.repos = repos
        self.analytics_store = analytics_store

    def get_course_dashboard(
        self,
        course_id: str,
        module_id: str | None = None,
    ) -> CourseDashboardResponse:
        materials = self.repos.material_store.list_records_by_course(course_id, module_id)
        mastery = self.repos.quiz_store.get_mastery_snapshot(course_id, module_id)
        remediation_history = self.repos.quiz_store.list_retry_history(course_id, module_id)
        quiz_sessions = self.repos.quiz_store.list_quiz_sessions_by_course(course_id, module_id)
        exam_sessions = self.repos.exam_store.list_exam_sessions_by_course(course_id, module_id)

        grouped_quizzes: dict[str, list[QuizAttemptSummary]] = {}
        wrong_questions = []
        for session in quiz_sessions:
            if session.quiz.query.startswith("remediation:"):
                continue
            grade_results = self.repos.quiz_store.get_grade_results(session.quiz.quiz_id)
            wrong_results = [result for result in grade_results if not result.is_correct]
            wrong_questions.extend(wrong_results)
            score = (
                round(sum(result.score for result in grade_results) / len(grade_results) * 100.0, 2)
                if grade_results
                else None
            )
            attempt = QuizAttemptSummary(
                quiz_id=session.quiz.quiz_id,
                created_at=session.quiz.created_at,
                question_count=len(session.quiz.questions),
                overall_score=score,
                wrong_question_count=len(wrong_results),
                module_id=session.quiz.module_id,
            )
            grouped_quizzes.setdefault(session.quiz.query, []).append(attempt)

        quizzes: list[QuizHistoryItem] = []
        for query, attempts in grouped_quizzes.items():
            sorted_attempts = sorted(
                attempts,
                key=lambda attempt: attempt.created_at or attempt.quiz_id,
                reverse=True,
            )
            latest = sorted_attempts[0]
            quizzes.append(
                QuizHistoryItem(
                    quiz_id=latest.quiz_id,
                    module_id=latest.module_id,
                    record_type="concept_practice" if query.lower().startswith("practice:") else "quiz",
                    query=query,
                    question_count=latest.question_count,
                    overall_score=latest.overall_score,
                    wrong_question_count=latest.wrong_question_count,
                    created_at=latest.created_at,
                    attempts=sorted_attempts,
                )
            )
        quizzes.sort(key=lambda item: item.created_at or item.quiz_id, reverse=True)

        mock_exams = [
            MockExamHistoryItem(
                exam_id=session.exam.exam_id,
                module_id=session.exam.module_id,
                module_ids=session.exam.module_ids,
                title=session.exam.blueprint.title,
                question_count=len(session.exam.questions),
                target_difficulty=session.exam.blueprint.target_difficulty,
                created_at=session.exam.created_at,
                completed_at=session.grade_result.completed_at if session.grade_result else None,
                score_percent=session.grade_result.overall_score if session.grade_result else None,
            )
            for session in exam_sessions
        ]
        mock_exams.sort(key=lambda item: item.completed_at or item.created_at or item.exam_id, reverse=True)

        analytics_payload = self._analytics_payload(course_id=course_id)

        return CourseDashboardResponse(
            course_id=course_id,
            module_id=module_id,
            material_count=len(materials),
            section_count=sum(record.section_count for record in materials),
            chunk_count=sum(record.chunk_count for record in materials),
            mastery_percent=mastery.percent_mastery,
            mastery_by_concept=mastery.mastery_by_concept,
            wrong_concepts=mastery.wrong_concepts,
            materials=materials,
            quizzes=quizzes,
            mock_exams=mock_exams,
            remediation_history=remediation_history,
            wrong_questions=wrong_questions,
            **analytics_payload,
        )

    def list_wrong_questions(
        self,
        course_id: str,
        module_id: str | None = None,
    ) -> list[QuestionGradeResult]:
        summary = self.get_course_dashboard(course_id, module_id)
        return summary.wrong_questions

    def _analytics_payload(self, *, course_id: str) -> dict[str, object]:
        if self.analytics_store is None:
            return {}
        overview = self.analytics_store.get_overview(user_id="demo-user", course_id=course_id)
        weak_modules = self.analytics_store.list_modules(user_id="demo-user", course_id=course_id)[:5]
        weak_concepts = self.analytics_store.list_concepts(user_id="demo-user", course_id=course_id)[:8]
        weak_question_types = self.analytics_store.list_question_types(user_id="demo-user", course_id=course_id)[:8]
        recommendations = self.analytics_store.list_recommendations(user_id="demo-user", course_id=course_id)[:5]
        concept_by_id = {concept.concept_id: concept for concept in weak_concepts}
        return {
            "exam_readiness_score": overview.exam_readiness_score,
            "weak_modules": [
                {
                    "module_id": module.module_id,
                    "accuracy": module.accuracy,
                    "mastery_score": module.mastery_score,
                    "priority_score": module.priority_score,
                    "weak_concepts": module.weak_concepts,
                    "weak_question_types": module.weak_question_types,
                }
                for module in weak_modules
            ],
            "weak_concepts_ranked": [
                {
                    "concept_id": concept.concept_id,
                    "module_id": concept.module_id,
                    "material_id": concept.material_id,
                    "section_id": concept.section_id,
                    "accuracy": concept.accuracy,
                    "mastery_score": concept.mastery_score,
                    "repeat_misses": concept.repeat_misses,
                    "priority_score": concept.priority_score,
                    "weak_question_types": concept.weak_question_types,
                }
                for concept in weak_concepts
            ],
            "weak_question_types": [
                {
                    "question_type": item.question_type,
                    "concept_id": item.concept_id,
                    "module_id": item.module_id,
                    "accuracy": item.accuracy,
                    "attempts": item.attempts,
                    "priority_score": item.priority_score,
                }
                for item in weak_question_types
            ],
            "study_recommendations": [
                self._dashboard_recommendation_payload(recommendation, concept_by_id)
                for recommendation in recommendations
            ],
        }

    def _dashboard_recommendation_payload(self, recommendation, concept_by_id) -> dict[str, object]:  # noqa: ANN001
        concept = concept_by_id.get(recommendation.target_concept_id or "")
        material_id = concept.material_id if concept else None
        section_id = recommendation.target_section_id or (concept.section_id if concept else None)
        href = None
        if material_id and section_id:
            href = (
                f"/courses/{recommendation.course_id}/materials?"
                f"materialId={material_id}&sourceId={section_id}&groupId=all-sections&study=1"
            )
        return {
            "title": recommendation.title,
            "reason": recommendation.reason,
            "recommended_action": recommendation.recommended_action,
            "target_module_id": recommendation.target_module_id,
            "target_section_id": section_id,
            "target_concept_id": recommendation.target_concept_id,
            "material_id": material_id,
            "href": href,
            "priority_score": recommendation.priority_score,
        }
