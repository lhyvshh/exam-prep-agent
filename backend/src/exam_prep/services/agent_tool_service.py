from __future__ import annotations

import re
from urllib.parse import urlencode

from exam_prep.repositories.activity_store import ActivityStore
from exam_prep.repositories.analytics_store import AnalyticsStore
from exam_prep.repositories.material_catalog import MaterialCatalog
from exam_prep.schemas.activity import ActivityEventType, QuestionAttemptRecord
from exam_prep.schemas.agent_tools import (
    AgentRecommendationButton,
    AgentToolRecommendationCard,
    AgentWeakAreaSummary,
    SmartAgentStudyPlanResponse,
)
from exam_prep.schemas.analytics import (
    AnalyticsOverviewResponse,
    ConceptMasteryRecord,
    ModuleMasteryRecord,
    QuestionTypeMasteryRecord,
)
from exam_prep.schemas.materials import MaterialRecord, StructuredConcept, StructuredMaterialSection


INTERNAL_ID_RE = re.compile(
    r"(?i)\b(?:[a-f0-9]{20,}(?:-[a-z]+-\d+)?|[a-z0-9]+-[a-z0-9-]+-section-\d+)\b"
)
GENERIC_ID_RE = re.compile(r"(?i)^(?:module|concept|section|material|quiz|question)[_-][a-z0-9_-]+$")
MCQ_QUESTION_TYPE = "mcq"


class AgentToolService:
    """Grounded platform tools for the Study Coach agent.

    The methods intentionally read from existing persistence layers. The agent layer can
    compose these tool outputs into cards without inventing capabilities or routes.
    """

    def __init__(
        self,
        *,
        analytics_store: AnalyticsStore,
        material_catalog: MaterialCatalog,
        activity_store: ActivityStore,
    ) -> None:
        self.analytics_store = analytics_store
        self.material_catalog = material_catalog
        self.activity_store = activity_store

    def get_user_learning_profile(self, user_id: str, course_id: str) -> AnalyticsOverviewResponse:
        return self.analytics_store.get_overview(user_id=user_id, course_id=course_id)

    def get_weak_modules(self, user_id: str, course_id: str) -> list[ModuleMasteryRecord]:
        return self.analytics_store.list_modules(user_id=user_id, course_id=course_id)

    def get_weak_concepts(self, user_id: str, course_id: str) -> list[ConceptMasteryRecord]:
        return self.analytics_store.list_concepts(user_id=user_id, course_id=course_id)

    def get_question_type_performance(
        self,
        user_id: str,
        course_id: str,
    ) -> list[QuestionTypeMasteryRecord]:
        return self.analytics_store.list_question_types(user_id=user_id, course_id=course_id)

    def get_material_links_for_concept(self, concept_id: str) -> dict[str, object] | None:
        concept = self.material_catalog.get_concept(concept_id)
        if concept is None:
            return None
        section = self.material_catalog.get_structured_section(concept.section_id)
        if section is None:
            return None
        page = self._source_page(concept, section)
        return {
            "course_id": concept.course_id,
            "material_id": concept.material_id,
            "section_id": concept.section_id,
            "concept_id": concept.id,
            "page": page,
            "study_url": self._study_url(
                course_id=concept.course_id,
                material_id=concept.material_id,
                section_id=concept.section_id,
                page=page,
            ),
            "source_url": self._source_url(
                course_id=concept.course_id,
                material_id=concept.material_id,
                section_id=concept.section_id,
                page=page,
            ),
        }

    def get_source_section_for_concept(self, concept_id: str) -> StructuredMaterialSection | None:
        concept = self.material_catalog.get_concept(concept_id)
        if concept is None:
            return None
        return self.material_catalog.get_structured_section(concept.section_id)

    def get_missed_questions_for_concept(self, user_id: str, concept_id: str) -> list[str]:
        attempts = self.activity_store.list_question_attempts(user_id=user_id)
        return [
            attempt.question_id
            for attempt in attempts
            if attempt.concept_id == concept_id and not attempt.is_correct
        ]

    def generate_quiz_from_concept(
        self,
        concept_id: str,
        question_type: str | None = None,
        difficulty: float | None = None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {"concept_id": concept_id}
        if question_type:
            payload["question_styles"] = [question_type]
        if difficulty is not None:
            payload["difficulty"] = difficulty
        return {"method": "POST", "path": "/api/v1/quiz/generate-from-concept", "payload": payload}

    def generate_quiz_from_module(
        self,
        module_id: str,
        question_type: str | None = None,
        difficulty: float | None = None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {"module_id": module_id}
        if question_type:
            payload["question_styles"] = [question_type]
        if difficulty is not None:
            payload["difficulty"] = difficulty
        return {"method": "POST", "path": "/api/v1/quiz/generate-from-module", "payload": payload}

    def generate_quiz_from_section(
        self,
        section_id: str,
        question_type: str | None = None,
        difficulty: float | None = None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {"section_id": section_id}
        if question_type:
            payload["question_styles"] = [question_type]
        if difficulty is not None:
            payload["difficulty"] = difficulty
        return {"method": "POST", "path": "/api/v1/quiz/generate-from-section", "payload": payload}

    def generate_quiz_from_missed_questions(self, question_ids: list[str]) -> dict[str, object]:
        return {
            "method": "POST",
            "path": "/api/v1/quiz/generate-from-missed-questions",
            "payload": {"question_ids": question_ids},
        }

    def create_recommendation_cards(self, user_id: str, course_id: str) -> SmartAgentStudyPlanResponse:
        overview = self.get_user_learning_profile(user_id, course_id)
        weak_concepts = self.get_weak_concepts(user_id, course_id)
        if weak_concepts:
            return self._performance_driven_plan(
                user_id=user_id,
                course_id=course_id,
                overview=overview,
                weak_concepts=weak_concepts,
            )

        materials = self.material_catalog.list_records_by_course(course_id)
        if materials:
            return self._material_first_plan(course_id=course_id, materials=materials)

        return SmartAgentStudyPlanResponse(
            summary="Upload course material and complete a quiz so the Study Coach can build grounded recommendations.",
            readinessScore=0,
            recommendations=[
                AgentToolRecommendationCard(
                    title="Open book library",
                    reason="The agent needs uploaded material before it can recommend exact study sections.",
                    actionType="open_materials",
                    buttonText="Open Book Library",
                    targetUrl=f"/courses/{course_id}/materials",
                    priorityScore=50,
                )
            ],
        )

    # Compatibility aliases matching the product-level tool names in the spec.
    def getUserLearningProfile(self, userId: str, courseId: str) -> AnalyticsOverviewResponse:  # noqa: N802
        return self.get_user_learning_profile(userId, courseId)

    def getWeakModules(self, userId: str, courseId: str) -> list[ModuleMasteryRecord]:  # noqa: N802
        return self.get_weak_modules(userId, courseId)

    def getWeakConcepts(self, userId: str, courseId: str) -> list[ConceptMasteryRecord]:  # noqa: N802
        return self.get_weak_concepts(userId, courseId)

    def getQuestionTypePerformance(self, userId: str, courseId: str) -> list[QuestionTypeMasteryRecord]:  # noqa: N802
        return self.get_question_type_performance(userId, courseId)

    def getMaterialLinksForConcept(self, conceptId: str) -> dict[str, object] | None:  # noqa: N802
        return self.get_material_links_for_concept(conceptId)

    def getSourceSectionForConcept(self, conceptId: str) -> StructuredMaterialSection | None:  # noqa: N802
        return self.get_source_section_for_concept(conceptId)

    def getMissedQuestionsForConcept(self, userId: str, conceptId: str) -> list[str]:  # noqa: N802
        return self.get_missed_questions_for_concept(userId, conceptId)

    def generateQuizFromConcept(  # noqa: N802
        self,
        conceptId: str,
        questionType: str | None = None,
        difficulty: float | None = None,
    ) -> dict[str, object]:
        return self.generate_quiz_from_concept(conceptId, questionType, difficulty)

    def generateQuizFromModule(  # noqa: N802
        self,
        moduleId: str,
        questionType: str | None = None,
        difficulty: float | None = None,
    ) -> dict[str, object]:
        return self.generate_quiz_from_module(moduleId, questionType, difficulty)

    def generateQuizFromSection(  # noqa: N802
        self,
        sectionId: str,
        questionType: str | None = None,
        difficulty: float | None = None,
    ) -> dict[str, object]:
        return self.generate_quiz_from_section(sectionId, questionType, difficulty)

    def generateQuizFromMissedQuestions(self, questionIds: list[str]) -> dict[str, object]:  # noqa: N802
        return self.generate_quiz_from_missed_questions(questionIds)

    def createRecommendationCards(self, userId: str, courseId: str) -> SmartAgentStudyPlanResponse:  # noqa: N802
        return self.create_recommendation_cards(userId, courseId)

    def _performance_driven_plan(
        self,
        *,
        user_id: str,
        course_id: str,
        overview: AnalyticsOverviewResponse,
        weak_concepts: list[ConceptMasteryRecord],
    ) -> SmartAgentStudyPlanResponse:
        top = weak_concepts[0]
        concept = self.material_catalog.get_concept(top.concept_id)
        section = self.material_catalog.get_structured_section(top.section_id or concept.section_id) if (top.section_id or concept) else None
        display_name = self._friendly_concept_name(concept, section, top.concept_id)
        module_name = self._friendly_module_name(top.module_id, section)
        question_type = self._weak_question_type(
            user_id=user_id,
            course_id=course_id,
            concept_id=top.concept_id,
            weak_concept=top,
        )
        missed_question_ids = self.get_missed_questions_for_concept(user_id, top.concept_id)
        page = self._source_page(concept, section)
        material_id = top.material_id or (concept.material_id if concept else None)
        section_id = top.section_id or (concept.section_id if concept else None)
        recent_trend = self._recent_trend_label(top)
        review_count = self._source_review_count(
            user_id=user_id,
            course_id=course_id,
            material_id=material_id,
            section_id=section_id,
            concept_id=top.concept_id,
        )
        weak_type_misses = self._missed_question_ids_for_type(
            user_id=user_id,
            concept_id=top.concept_id,
            question_type=question_type,
        )
        targeted_miss_count = len(weak_type_misses) or len(missed_question_ids) or top.repeat_misses
        recommended_action = f"Review material first, then practice {question_type.replace('_', ' ')} questions."
        why_it_matters = self._why_it_matters(top, display_name, review_count, targeted_miss_count)
        buttons = self._exam_butler_buttons(
            course_id=course_id,
            material_id=material_id,
            section_id=section_id,
            concept_id=top.concept_id,
            module_id=top.module_id,
            page=page,
            question_type=question_type,
            weak_area_name=display_name,
        )
        top_weak_modules = [
            self._module_summary(record)
            for record in self.get_weak_modules(user_id, course_id)[:3]
        ]
        top_weak_concepts = [
            self._concept_summary(record)
            for record in weak_concepts[:5]
        ]
        weakest_question_types = [
            self._question_type_summary(record)
            for record in self.get_question_type_performance(user_id, course_id)[:5]
        ]

        recommendations: list[AgentToolRecommendationCard] = []
        if material_id and section_id:
            recommendations.append(
                AgentToolRecommendationCard(
                    title=f"Review {display_name}",
                    reason=f"You missed {top.repeat_misses} of {top.attempts} related attempts.",
                    actionType="review_material",
                    buttonText="Review Material",
                    targetUrl=self._source_url(
                        course_id=course_id,
                        material_id=material_id,
                        section_id=section_id,
                        page=page,
                    ),
                    targetMaterialId=material_id,
                    targetSectionId=section_id,
                    targetConceptId=top.concept_id,
                    targetModuleId=top.module_id,
                    sourcePage=page,
                    priorityScore=top.priority_score,
                    weakAreaName=display_name,
                    accuracy=self._round_metric(top.accuracy),
                    attempts=top.attempts,
                    recentTrend=recent_trend,
                    whyItMatters=why_it_matters,
                    recommendedAction=recommended_action,
                    buttons=buttons,
                )
            )
            recommendations.append(
                AgentToolRecommendationCard(
                    title=f"Practice {question_type.replace('_', ' ')} questions",
                    reason=(
                        f"Your {question_type.replace('_', ' ')} accuracy for this concept is weak. "
                        "Start from the exact section so practice stays grounded."
                    ),
                    actionType="generate_quiz",
                    buttonText="Practice This Concept",
                    targetUrl=self._study_url(
                        course_id=course_id,
                        material_id=material_id,
                        section_id=section_id,
                        page=page,
                    ),
                    targetMaterialId=material_id,
                    targetSectionId=section_id,
                    targetConceptId=top.concept_id,
                    targetModuleId=top.module_id,
                    sourcePage=page,
                    questionType=question_type,
                    priorityScore=max(top.priority_score - 5, 0),
                    weakAreaName=display_name,
                    accuracy=self._round_metric(top.accuracy),
                    attempts=top.attempts,
                    recentTrend=recent_trend,
                    whyItMatters=why_it_matters,
                    recommendedAction=recommended_action,
                    buttons=buttons,
                )
            )

        if missed_question_ids:
            recommendations.append(
                AgentToolRecommendationCard(
                    title="Retake missed questions",
                    reason=f"You have {len(missed_question_ids)} missed questions tied to this concept.",
                    actionType="missed_questions",
                    buttonText="Review Missed Questions",
                    targetUrl=f"/courses/{course_id}/wrong-questions?{urlencode({'concept': top.concept_id})}",
                    targetMaterialId=material_id,
                    targetSectionId=section_id,
                    targetConceptId=top.concept_id,
                    targetModuleId=top.module_id,
                    sourcePage=page,
                    questionType=question_type,
                    priorityScore=max(top.priority_score - 10, 0),
                    weakAreaName=display_name,
                    accuracy=self._round_metric(top.accuracy),
                    attempts=top.attempts,
                    recentTrend=recent_trend,
                    whyItMatters=why_it_matters,
                    recommendedAction=recommended_action,
                    buttons=buttons,
                )
            )

        return SmartAgentStudyPlanResponse(
            summary=self._agent_response_summary(
                display_name=display_name,
                module_name=module_name,
                record=top,
                section=section,
                question_type=question_type,
                review_count=review_count,
                missed_count=targeted_miss_count,
            ),
            readinessScore=round(overview.exam_readiness_score),
            recommendations=recommendations,
            topWeakModules=top_weak_modules,
            topWeakConcepts=top_weak_concepts,
            weakestQuestionTypes=weakest_question_types,
            recommendedNextAction=f"Review {display_name}, then practice {question_type.replace('_', ' ')} questions.",
        )

    def _material_first_plan(
        self,
        *,
        course_id: str,
        materials: list[MaterialRecord],
    ) -> SmartAgentStudyPlanResponse:
        sections: list[StructuredMaterialSection] = []
        for material in materials:
            sections.extend(
                section
                for section in self.material_catalog.list_structured_sections(material.material_id)
                if not section.is_junk
            )
        sections = sorted(sections, key=lambda item: (-item.exam_weight, item.section_order, item.clean_title))
        recommendations: list[AgentToolRecommendationCard] = []
        for section in sections[:3]:
            concept = section.concepts[0] if section.concepts else None
            page = self._source_page(concept, section)
            title = self._friendly_section_name(section)
            buttons = self._exam_butler_buttons(
                course_id=course_id,
                material_id=section.material_id,
                section_id=section.id,
                concept_id=concept.id if concept else None,
                module_id=section.module_id,
                page=page,
                question_type=MCQ_QUESTION_TYPE,
                weak_area_name=title,
            )
            recommendations.append(
                AgentToolRecommendationCard(
                    title=f"Study {title}",
                    reason="This is a high-weight section. Complete a quiz afterward to unlock performance-driven coaching.",
                    actionType="review_material",
                    buttonText="Study Section",
                    targetUrl=self._study_url(
                        course_id=course_id,
                        material_id=section.material_id,
                        section_id=section.id,
                        page=page,
                    ),
                    targetMaterialId=section.material_id,
                    targetSectionId=section.id,
                    targetConceptId=concept.id if concept else None,
                    targetModuleId=section.module_id,
                    sourcePage=page,
                    priorityScore=round(section.exam_weight * 100, 2),
                    weakAreaName=title,
                    accuracy=None,
                    attempts=0,
                    recentTrend="Not enough data",
                    whyItMatters="This section has a high exam-weight estimate and no quiz history yet.",
                    recommendedAction="Study the section, then generate a short quiz.",
                    buttons=buttons,
                )
            )
        if not recommendations:
            recommendations.append(
                AgentToolRecommendationCard(
                    title="Open book library",
                    reason="Material exists, but no quiz-ready study sections are available yet.",
                    actionType="open_materials",
                    buttonText="Open Book Library",
                    targetUrl=f"/courses/{course_id}/materials",
                    priorityScore=40,
                )
            )
        return SmartAgentStudyPlanResponse(
            summary="Complete a quiz to unlock performance-driven coaching. Start with high-weight sections first.",
            readinessScore=0,
            recommendations=recommendations,
            recommendedNextAction=f"{recommendations[0].title}." if recommendations else "Open the book library.",
        )

    def _weak_question_type(
        self,
        *,
        user_id: str,
        course_id: str,
        concept_id: str,
        weak_concept: ConceptMasteryRecord,
    ) -> str:
        del user_id, course_id, concept_id, weak_concept
        return MCQ_QUESTION_TYPE

    def _source_page(
        self,
        concept: StructuredConcept | None,
        section: StructuredMaterialSection | None,
    ) -> int | None:
        if concept is not None and concept.source_page is not None:
            return concept.source_page
        if section is not None:
            return section.start_page
        return None

    def _study_url(
        self,
        *,
        course_id: str,
        material_id: str,
        section_id: str,
        page: int | None,
        extra_params: dict[str, str] | None = None,
    ) -> str:
        params: dict[str, str] = {
            "materialId": material_id,
            "sectionId": section_id,
            "sourceId": section_id,
            "groupId": "all-sections",
            "study": "1",
        }
        if page is not None:
            params["page"] = str(page)
        if extra_params:
            params.update(extra_params)
        return f"/courses/{course_id}/materials?{urlencode(params)}"

    def _source_url(
        self,
        *,
        course_id: str,
        material_id: str,
        section_id: str,
        page: int | None,
    ) -> str:
        params: dict[str, str] = {
            "materialId": material_id,
            "sectionId": section_id,
            "sourceId": section_id,
            "groupId": "all-sections",
            "source": "1",
        }
        if page is not None:
            params["page"] = str(page)
        return f"/courses/{course_id}/materials?{urlencode(params)}"

    def _exam_butler_buttons(
        self,
        *,
        course_id: str,
        material_id: str | None,
        section_id: str | None,
        concept_id: str | None,
        module_id: str | None,
        page: int | None,
        question_type: str | None,
        weak_area_name: str | None = None,
    ) -> list[AgentRecommendationButton]:
        if not material_id or not section_id:
            return [
                AgentRecommendationButton(
                    label="Open Book Library",
                    actionType="open_materials",
                    targetUrl=f"/courses/{course_id}/materials",
                    targetModuleId=module_id,
                    targetConceptId=concept_id,
                    questionType=question_type,
                )
            ]

        source_url = self._source_url(
            course_id=course_id,
            material_id=material_id,
            section_id=section_id,
            page=page,
        )
        quiz_params = {
            "quiz": "1",
            "conceptId": concept_id or "",
        }
        if question_type:
            quiz_params["questionType"] = question_type
        practice_url = self._study_url(
            course_id=course_id,
            material_id=material_id,
            section_id=section_id,
            page=page,
            extra_params={**quiz_params, "quizMode": "practice_concept"},
        )
        generate_url = self._study_url(
            course_id=course_id,
            material_id=material_id,
            section_id=section_id,
            page=page,
            extra_params={**quiz_params, "quizMode": "generate_quiz"},
        )
        similar_url = self._study_url(
            course_id=course_id,
            material_id=material_id,
            section_id=section_id,
            page=page,
            extra_params={**quiz_params, "quizMode": "similar_questions"},
        )
        missed_url = f"/courses/{course_id}/wrong-questions"
        if concept_id:
            missed_url = f"{missed_url}?{urlencode({'concept': concept_id})}"

        common = {
            "targetMaterialId": material_id,
            "targetSectionId": section_id,
            "targetConceptId": concept_id,
            "targetModuleId": module_id,
            "sourcePage": page,
            "questionType": question_type,
        }
        practice_label = self._practice_button_label(weak_area_name, question_type)
        return [
            AgentRecommendationButton(
                label="Review Material",
                actionType="review_material",
                targetUrl=source_url,
                **common,
            ),
            AgentRecommendationButton(
                label=practice_label,
                actionType="practice_concept",
                targetUrl=practice_url,
                **common,
            ),
            AgentRecommendationButton(
                label="Generate Quiz",
                actionType="generate_quiz",
                targetUrl=generate_url,
                **common,
            ),
            AgentRecommendationButton(
                label="Retake Missed Questions",
                actionType="retake_missed_questions",
                targetUrl=missed_url,
                **common,
            ),
            AgentRecommendationButton(
                label="View Source PDF Page",
                actionType="view_source_pdf_page",
                targetUrl=source_url,
                **common,
            ),
            AgentRecommendationButton(
                label="Study Similar Questions",
                actionType="study_similar_questions",
                targetUrl=similar_url,
                **common,
            ),
        ]

    def _module_summary(self, record: ModuleMasteryRecord) -> AgentWeakAreaSummary:
        return AgentWeakAreaSummary(
            id=record.module_id,
            name=self._friendly_module_name(record.module_id, None) or "Current module",
            accuracy=self._round_metric(record.accuracy),
            attempts=record.attempts,
            recentTrend=self._mastery_trend_label(record.accuracy, record.attempts),
            priorityScore=record.priority_score,
        )

    def _concept_summary(self, record: ConceptMasteryRecord) -> AgentWeakAreaSummary:
        concept = self.material_catalog.get_concept(record.concept_id)
        section = self.material_catalog.get_structured_section(record.section_id) if record.section_id else None
        return AgentWeakAreaSummary(
            id=record.concept_id,
            name=self._friendly_concept_name(concept, section, record.concept_id),
            accuracy=self._round_metric(record.accuracy),
            attempts=record.attempts,
            recentTrend=self._recent_trend_label(record),
            priorityScore=record.priority_score,
        )

    def _question_type_summary(self, record: QuestionTypeMasteryRecord) -> AgentWeakAreaSummary:
        return AgentWeakAreaSummary(
            id=record.question_type,
            name=record.question_type,
            accuracy=self._round_metric(record.accuracy),
            attempts=record.attempts,
            recentTrend=self._mastery_trend_label(record.accuracy, record.attempts),
            priorityScore=record.priority_score,
        )

    def _recent_trend_label(self, record: ConceptMasteryRecord) -> str:
        if record.attempts < 2:
            return "Not enough data"
        if record.repeat_misses >= 2 or record.accuracy < 0.5:
            return "Needs attention"
        if record.accuracy >= 0.8:
            return "Improving"
        return "Mixed"

    def _mastery_trend_label(self, accuracy: float, attempts: int) -> str:
        if attempts < 2:
            return "Not enough data"
        if accuracy < 0.5:
            return "Needs attention"
        if accuracy >= 0.8:
            return "Improving"
        return "Mixed"

    def _why_it_matters(
        self,
        record: ConceptMasteryRecord,
        display_name: str,
        review_count: int,
        missed_count: int,
    ) -> str:
        misses = missed_count or max(record.attempts - record.correct_attempts, record.repeat_misses)
        reasons = [
            f"Low accuracy on {display_name}",
            f"{misses} recent misses",
        ]
        if review_count <= 1:
            reasons.append(f"reviewed source material {self._review_count_phrase(review_count)}")
        if record.priority_score >= 60:
            reasons.append("high-priority exam coverage")
        return ", ".join(reasons) + "."

    def _round_metric(self, value: float | None) -> float | None:
        if value is None:
            return None
        return round(value, 4)

    def _agent_response_summary(
        self,
        *,
        display_name: str,
        module_name: str | None,
        record: ConceptMasteryRecord,
        section: StructuredMaterialSection | None,
        question_type: str,
        review_count: int,
        missed_count: int,
    ) -> str:
        question_type_label = question_type.replace("_", " ")
        question_type_phrase = f"{question_type_label}-based" if question_type_label == "scenario" else question_type_label
        contrast = self._section_contrast_phrase(section)
        contrast_sentence = f", especially {contrast}" if contrast else ""
        review_phrase = self._review_count_phrase(review_count)
        missed_phrase = self._miss_count_phrase(missed_count)
        return (
            f"You are weakest in {module_name or display_name}.\n\n"
            f"Your accuracy is {round(record.accuracy * 100)}% across {record.attempts} attempts. "
            f"Most of your mistakes are on {question_type_phrase} questions{contrast_sentence}. "
            f"You reviewed the source material {review_phrase}, but missed this concept {missed_phrase}.\n\n"
            "Recommended next step:\n"
            f"1. Review the source section on {display_name}.\n"
            f"2. Practice 10 {question_type_label} questions.\n"
            f"3. Retake your {missed_count} missed questions after that."
        )

    def _source_review_count(
        self,
        *,
        user_id: str,
        course_id: str,
        material_id: str | None,
        section_id: str | None,
        concept_id: str | None,
    ) -> int:
        review_events = [
            ActivityEventType.REVIEW_MATERIAL_CLICKED,
            ActivityEventType.MATERIAL_SECTION_VIEWED,
            ActivityEventType.PDF_SOURCE_CLICKED,
        ]
        count = 0
        for event_type in review_events:
            for event in self.activity_store.list_events(
                user_id=user_id,
                course_id=course_id,
                event_type=event_type,
            ):
                if material_id and event.material_id and event.material_id != material_id:
                    continue
                if section_id and event.section_id and event.section_id != section_id:
                    continue
                if concept_id and event.concept_id and event.concept_id != concept_id:
                    continue
                count += 1
        return count

    def _missed_question_ids_for_type(self, *, user_id: str, concept_id: str, question_type: str) -> list[str]:
        return [
            attempt.question_id
            for attempt in self._attempts_for_concept(user_id=user_id, concept_id=concept_id)
            if not attempt.is_correct and attempt.question_type == question_type
        ]

    def _attempts_for_concept(self, *, user_id: str, concept_id: str) -> list[QuestionAttemptRecord]:
        return [
            attempt
            for attempt in self.activity_store.list_question_attempts(user_id=user_id)
            if attempt.concept_id == concept_id
        ]

    def _section_contrast_phrase(self, section: StructuredMaterialSection | None) -> str | None:
        if section is None:
            return None
        source_upper = section.source_text.upper()
        if "INNER JOIN" in source_upper and "LEFT JOIN" in source_upper:
            return "deciding between INNER JOIN and LEFT JOIN"
        join_terms = [term for term in section.key_terms if "JOIN" in term.upper()]
        if len(join_terms) >= 2:
            return f"deciding between {join_terms[0]} and {join_terms[1]}"
        if len(section.key_terms) >= 2:
            return f"distinguishing {section.key_terms[0]} from {section.key_terms[1]}"
        return None

    def _practice_button_label(self, weak_area_name: str | None, question_type: str | None) -> str:
        weak_area_name = self._safe_display_label(weak_area_name, "this concept")
        if weak_area_name == "this concept" or len(weak_area_name) > 48:
            return "Practice This Concept"
        type_label = self._button_question_type_label(question_type)
        return f"Practice {weak_area_name} {type_label}"

    def _button_question_type_label(self, question_type: str | None) -> str:
        return "MCQ Questions"

    def _review_count_phrase(self, count: int) -> str:
        if count == 0:
            return "zero times"
        if count == 1:
            return "only once"
        return f"{count} times"

    def _miss_count_phrase(self, count: int) -> str:
        if count == 1:
            return "1 time"
        return f"{count} times"

    def _friendly_concept_name(
        self,
        concept: StructuredConcept | None,
        section: StructuredMaterialSection | None,
        fallback: str | None,
    ) -> str:
        if concept is not None:
            label = self._safe_display_label(concept.name, "")
            if label:
                return label
        section_label = self._friendly_section_name(section)
        if section_label != "this section":
            return section_label
        return self._safe_display_label(fallback, "this section")

    def _friendly_section_name(self, section: StructuredMaterialSection | None) -> str:
        if section is None:
            return "this section"
        for candidate in (section.clean_title, section.title):
            label = self._safe_display_label(candidate, "")
            if label:
                return label
        return "this section"

    def _friendly_module_name(
        self,
        module_id: str | None,
        section: StructuredMaterialSection | None,
    ) -> str | None:
        label = self._safe_display_label(module_id, "")
        if label:
            return label
        if section is not None:
            title = self._friendly_section_name(section)
            if title != "this section":
                return title
        return None

    def _safe_display_label(self, value: str | None, fallback: str) -> str:
        label = " ".join((value or "").split()).strip()
        if not label or INTERNAL_ID_RE.search(label) or GENERIC_ID_RE.fullmatch(label):
            return fallback
        return label
