from __future__ import annotations

import logging
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any
from urllib.parse import urlencode
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from exam_prep.agent_core.models import AgentRunRequest
from exam_prep.agent_core.orchestrator import AgentOrchestrator, AgentOrchestratorRuntime
from exam_prep.agent_core.profiles import all_agent_profiles, get_agent_profile
from exam_prep.core.config import Settings
from exam_prep.core.exceptions import LLMProviderError, LLMResponseSchemaError
from exam_prep.repositories.agent_store import AgentStore
from exam_prep.repositories.analytics_store import AnalyticsStore
from exam_prep.repositories.exam_store import ExamStore
from exam_prep.repositories.material_store import MaterialStore
from exam_prep.repositories.quiz_store import QuizStore
from exam_prep.repositories.vector_store import VectorStore
from exam_prep.schemas.agent import (
    AgentActionCard,
    AgentChatRequest,
    AgentChatResponse,
    AgentMemoryProfile,
    AgentMemoryUpdateRequest,
    AgentPageContext,
    AgentPageQuestionContext,
    AgentRecommendation,
    AgentRecommendationListResponse,
    AgentRunRecord,
)
from exam_prep.schemas.graph import GroundingContext
from exam_prep.schemas.quiz import QuestionGradeResult
from exam_prep.schemas.scope import StudyScope
from exam_prep.services.llm_service import StructuredLLMService
from exam_prep.services.retrieval_service import RetrievalService

logger = logging.getLogger(__name__)

MCQ_QUIZ_FORMAT = "mcq"


class CoachReplyPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=800)


class AgentService:
    def __init__(
        self,
        *,
        settings: Settings,
        agent_store: AgentStore,
        material_store: MaterialStore,
        vector_store: VectorStore,
        quiz_store: QuizStore,
        exam_store: ExamStore,
        analytics_store: AnalyticsStore | None = None,
        structured_llm: StructuredLLMService | None = None,
    ) -> None:
        self.settings = settings
        self.agent_store = agent_store
        self.material_store = material_store
        self.vector_store = vector_store
        self.quiz_store = quiz_store
        self.exam_store = exam_store
        self.analytics_store = analytics_store
        self.structured_llm = structured_llm
        self.retrieval_service = RetrievalService(
            material_store=material_store,
            vector_store=vector_store,
        )
        self._active_scope: StudyScope | None = None

    def list_recommendations(self, course_id: str) -> AgentRecommendationListResponse:
        analytics_recommendations = self._analytics_recommendations(StudyScope(course_id=course_id))
        if analytics_recommendations:
            stored = self.agent_store.list_recommendations(course_id)
            seen = {recommendation.id for recommendation in analytics_recommendations}
            recommendations = analytics_recommendations + [
                recommendation for recommendation in stored if recommendation.id not in seen
            ]
            return AgentRecommendationListResponse(
                course_id=course_id,
                recommendations=recommendations,
                latest_run=self._with_agent_profiles(self.agent_store.get_latest_run(course_id)),
                agent_profiles=all_agent_profiles(),
            )
        return AgentRecommendationListResponse(
            course_id=course_id,
            recommendations=self.agent_store.list_recommendations(course_id),
            latest_run=self._with_agent_profiles(self.agent_store.get_latest_run(course_id)),
            agent_profiles=all_agent_profiles(),
        )

    def get_memory(self, course_id: str) -> AgentMemoryProfile:
        existing = self.agent_store.get_memory(course_id)
        if existing is not None:
            return self._mcq_memory(existing)
        return self._default_memory(course_id)

    def save_memory(self, course_id: str, request: AgentMemoryUpdateRequest) -> AgentMemoryProfile:
        memory = AgentMemoryProfile(
            course_id=course_id,
            preferred_study_style=request.preferred_study_style,
            preferred_quiz_format=MCQ_QUIZ_FORMAT,
            default_question_count=request.default_question_count,
            focus_areas=self._normalize_memory_list(request.focus_areas, limit=8),
            encouragement_style=request.encouragement_style,
            progress_notes=self._normalize_memory_list(request.progress_notes, limit=8),
            updated_at=datetime.now(UTC).isoformat(),
        )
        return self.agent_store.save_memory(memory)

    def chat(self, request: AgentChatRequest) -> AgentChatResponse:
        scope = self._chat_scope_for_request(request)
        memory = self.get_memory(request.course_id)
        normalized_message = " ".join(request.message.lower().split())
        wants_progress = self._wants_progress_check(normalized_message)
        recommendations: list[AgentRecommendation] = []
        if wants_progress:
            run = self.run_course_check(intent="coach_chat", scope=scope)
            recommendations = run.recommendations
            memory = self._merge_progress_note(
                memory,
                f"Last coach check: {len(recommendations)} recommendations prepared.",
            )

        if normalized_message.startswith("remember "):
            memory = self._merge_progress_note(memory, request.message.removeprefix("remember ").strip())

        actions = self._action_cards_for_recommendations(recommendations) if wants_progress else []
        grounding_context = self._chat_grounding_context(scope, request.page_context)
        reply = self._coach_reply_from_llm(
            raw_message=request.message,
            normalized_message=normalized_message,
            scope=scope,
            memory=memory,
            recommendations=recommendations,
            actions=actions,
            page_context=request.page_context,
            grounding_context=grounding_context,
        )
        response_mode = "live_llm" if reply else "grounded_fallback"
        if not reply:
            reply = self._coach_reply(
                message=normalized_message,
                memory=memory,
                recommendations=recommendations,
            )
        saved_memory = self.agent_store.save_memory(memory)
        return AgentChatResponse(
            course_id=request.course_id,
            message=reply,
            response_mode=response_mode,
            actions=actions,
            memory=saved_memory,
            recommendations=recommendations[:4] if wants_progress else [],
            active_agent_profile=get_agent_profile("study_coach_agent"),
            agent_profiles=all_agent_profiles(),
        )

    def _wants_progress_check(self, normalized_message: str) -> bool:
        return any(
            token in normalized_message
            for token in ["progress", "recommend", "what next", "next step", "what should i study next"]
        )

    def _chat_scope_for_request(self, request: AgentChatRequest) -> StudyScope:
        if request.scope is None or request.scope.course_id != request.course_id:
            return StudyScope(course_id=request.course_id)
        return request.scope

    def run_course_check(self, *, intent: str, scope: StudyScope) -> AgentRunRecord:
        self._active_scope = scope
        orchestrator = AgentOrchestrator(
            AgentOrchestratorRuntime(
                resolve_material_ids=self._resolve_material_ids,
                retrieve_grounding_context=self._retrieve_grounding_context,
                resolve_scope_source_ids=self._resolve_scope_source_ids,
                resolve_mastery=self._resolve_mastery,
                build_recommendations=self._build_recommendation_dicts,
                enable_torch_inference=self.settings.enable_torch_inference,
            )
        )
        state = orchestrator.run(
            AgentRunRequest(
                intent=intent,
                course_id=scope.course_id,
                module_ids=scope.module_ids,
                material_ids=scope.material_ids,
                section_ids=scope.section_ids,
            )
        )
        recommendations = [
            AgentRecommendation.model_validate(item)
            for item in state.agent_recommendations
        ]
        run = AgentRunRecord(
            run_id=state.run_id or uuid4().hex,
            intent=intent,
            course_id=scope.course_id,
            scope=scope,
            node_statuses=state.execution_trace,
            agent_messages=state.agent_messages,
            recommendations=recommendations,
            quality_summary=state.quality_summary,
            agent_profiles=all_agent_profiles(),
            created_at=datetime.now(UTC).isoformat(),
        )
        self.agent_store.save_run(run)
        self.agent_store.upsert_recommendations(recommendations)
        self._active_scope = None
        return run

    def _with_agent_profiles(self, run: AgentRunRecord | None) -> AgentRunRecord | None:
        if run is None:
            return None
        if run.agent_profiles:
            return run
        return run.model_copy(update={"agent_profiles": all_agent_profiles()})

    def _default_memory(self, course_id: str) -> AgentMemoryProfile:
        mastery = self.quiz_store.get_mastery_snapshot(course_id, None)
        focus_areas = mastery.wrong_concepts[:5]
        notes: list[str] = []
        if focus_areas:
            notes.append(f"Recent weak concepts: {', '.join(focus_areas[:3])}.")
        else:
            notes.append("No weak concepts recorded yet. Start with one focused quiz or mock exam.")
        return AgentMemoryProfile(
            course_id=course_id,
            preferred_quiz_format=MCQ_QUIZ_FORMAT,
            focus_areas=focus_areas,
            progress_notes=notes,
            updated_at=datetime.now(UTC).isoformat(),
        )

    def _mcq_memory(self, memory: AgentMemoryProfile) -> AgentMemoryProfile:
        if memory.preferred_quiz_format == MCQ_QUIZ_FORMAT:
            return memory
        normalized = memory.model_copy(
            update={
                "preferred_quiz_format": MCQ_QUIZ_FORMAT,
                "updated_at": datetime.now(UTC).isoformat(),
            }
        )
        return self.agent_store.save_memory(normalized)

    def _merge_progress_note(self, memory: AgentMemoryProfile, note: str) -> AgentMemoryProfile:
        cleaned = " ".join(note.split())
        if not cleaned:
            return memory
        notes = [cleaned, *[item for item in memory.progress_notes if item != cleaned]]
        return memory.model_copy(
            update={
                "progress_notes": notes[:8],
                "updated_at": datetime.now(UTC).isoformat(),
            }
        )

    def _normalize_memory_list(self, values: list[str], *, limit: int) -> list[str]:
        cleaned: list[str] = []
        for value in values:
            normalized = " ".join(value.split())
            if normalized and normalized not in cleaned:
                cleaned.append(normalized)
            if len(cleaned) >= limit:
                break
        return cleaned

    def _action_cards_for_recommendations(
        self,
        recommendations: list[AgentRecommendation],
    ) -> list[AgentActionCard]:
        cards: list[AgentActionCard] = []
        for recommendation in recommendations[:4]:
            href = recommendation.target_payload.get("href")
            label = self._action_label(recommendation.target_action)
            cards.append(
                AgentActionCard(
                    label=label,
                    action=recommendation.target_action,
                    href=href if isinstance(href, str) else None,
                    payload=recommendation.target_payload,
                    tone="primary" if recommendation.target_action in {"study_section", "practice_concept"} else "secondary",
                )
            )
        return cards

    def _coach_reply(
        self,
        *,
        message: str,
        memory: AgentMemoryProfile,
        recommendations: list[AgentRecommendation],
    ) -> str:
        top = recommendations[0] if recommendations else None
        if "remember" in message:
            return "Saved. I will use that preference when you ask for study help."
        if "progress" in message or "recommend" in message or "next" in message:
            if top is not None:
                return f"Progress check complete. Start with {top.title}: {top.reason}"
            return (
                "I do not have enough progress data yet. Take one short quiz or review one missed question, "
                "then ask me for the next step."
            )
        if "why" in message or "wrong" in message or "answer" in message:
            return (
                "Use the current page context: compare the selected answer with the correct answer, "
                "then tie the difference back to the book concept or formula shown in the source."
            )
        if "quiz" in message or "practice" in message:
            return (
                f"Tell me the topic or paste the question, and I will explain the idea before you run a "
                f"{memory.default_question_count}-question MCQ practice set."
            )
        return (
            "I can help with the current page or a specific topic. Ask me about the concept, formula, "
            "question stem, or answer choice you want clarified."
        )

    def _chat_grounding_context(
        self,
        scope: StudyScope,
        page_context: AgentPageContext | None,
    ) -> list[GroundingContext]:
        material_ids = set(scope.material_ids)
        source_ids = set(scope.section_ids)
        if page_context is not None:
            material_ids.update(page_context.material_ids)
            source_ids.update(page_context.source_ids)
            source_ids.update(page_context.section_ids)
        if not material_ids and not source_ids:
            return []

        documents = self.material_store.list_parsed_documents_by_course(scope.course_id, None)
        max_contexts = self.settings.max_chunks_per_retrieval
        remaining_tokens = self.settings.max_agent_context_tokens
        contexts: list[GroundingContext] = []
        for document in documents:
            if material_ids and document.record.material_id not in material_ids:
                continue
            for chunk in document.chunks:
                if source_ids and chunk.source_id not in source_ids:
                    continue
                words = chunk.text.split()
                if not words:
                    continue
                allowed_tokens = min(len(words), remaining_tokens)
                excerpt = " ".join(words[:allowed_tokens])
                if excerpt:
                    contexts.append(
                        GroundingContext(
                            material_id=chunk.material_id,
                            excerpt=excerpt,
                            score=chunk.priority_score,
                        )
                    )
                    remaining_tokens -= allowed_tokens
                if len(contexts) >= max_contexts or remaining_tokens <= 0:
                    return contexts
        return contexts

    def _page_context_prompt(self, page_context: AgentPageContext | None) -> str:
        if page_context is None:
            return "Current page context: not provided."
        lines = [
            "Current page context:",
            f"Page type: {page_context.page_type}",
            f"Route: {page_context.route or 'unknown'}",
            f"Title: {page_context.title or 'unknown'}",
        ]
        if page_context.visible_text:
            lines.append(f"Visible page text: {page_context.visible_text}")
        if page_context.source_ids:
            lines.append(f"Visible source IDs: {page_context.source_ids}")
        if page_context.material_ids:
            lines.append(f"Visible material IDs: {page_context.material_ids}")
        if page_context.question is not None:
            lines.extend(self._question_context_prompt_lines(page_context.question))
        return "\n".join(lines)

    def _question_context_prompt_lines(self, question: AgentPageQuestionContext) -> list[str]:
        lines = ["Current question context:"]
        if question.question_number is not None:
            lines.append(f"Question number: {question.question_number}")
        if question.question_id:
            lines.append(f"Question ID: {question.question_id}")
        if question.prompt:
            lines.append(f"Prompt: {question.prompt}")
        selected = self._question_option_text(question, question.selected_option_id)
        if question.selected_option_id and selected:
            lines.append(f"Selected answer: {question.selected_option_id}. {selected}")
        correct = question.correct_answer or self._question_option_text(question, question.correct_option_id)
        if question.correct_option_id and correct:
            lines.append(f"Correct answer: {question.correct_option_id}. {correct}")
        if question.explanation:
            lines.append(f"Stored explanation: {question.explanation}")
        if question.concept:
            lines.append(f"Concept or LO: {question.concept}")
        if question.source_page is not None:
            lines.append(f"Book page: {question.source_page}")
        if question.options:
            option_lines = [
                f"{option.option_id}. {option.text}"
                for option in question.options
                if option.option_id and option.text
            ]
            if option_lines:
                lines.append("Answer choices: " + " | ".join(option_lines))
        return lines

    def _question_option_text(
        self,
        question: AgentPageQuestionContext,
        option_id: str | None,
    ) -> str | None:
        if not option_id:
            return None
        for option in question.options:
            if option.option_id == option_id:
                return option.text
        return None

    def _grounding_context_prompt(self, grounding_context: list[GroundingContext]) -> str:
        if not grounding_context:
            return "Book/source excerpts: none retrieved for this page."
        lines = ["Book/source excerpts:"]
        for index, context in enumerate(grounding_context, start=1):
            lines.append(
                f"{index}. material={context.material_id} score={context.score:.3f}: {context.excerpt}"
            )
        return "\n".join(lines)

    def _coach_reply_from_llm(
        self,
        *,
        raw_message: str,
        normalized_message: str,
        scope: StudyScope,
        memory: AgentMemoryProfile,
        recommendations: list[AgentRecommendation],
        actions: list[AgentActionCard],
        page_context: AgentPageContext | None,
        grounding_context: list[GroundingContext],
    ) -> str | None:
        if self.structured_llm is None or not self.structured_llm.available():
            return None

        top_recommendations = [
            {
                "title": recommendation.title,
                "reason": recommendation.reason,
                "agent": recommendation.agent_name,
                "action": recommendation.target_action,
            }
            for recommendation in recommendations[:4]
        ]
        action_labels = [action.label for action in actions[:4]]
        profile = get_agent_profile("study_coach_agent")
        system_prompt = (
            f"You are {profile.display_name}, a concise teaching assistant and after-school teacher inside "
            "an exam-prep app. Return JSON only with a single `message` string. Answer the student's "
            "question directly from the current page context and the related book/source excerpts. Do not "
            "show progress dashboards, agent skills, hidden traces, memory folders, recommendation lists, "
            "or internal model details unless the student explicitly asks for progress. When the page "
            "includes a missed question, explain why the selected answer is wrong and why the correct "
            "answer makes sense, using the book excerpt. Do not invent scores, links, facts, formulas, "
            "or course material. If the source is thin, say what context is missing and ask for the "
            "specific question or topic."
        )
        user_prompt = (
            f"Student message: {raw_message}\n"
            f"Normalized intent: {normalized_message}\n"
            f"Scope: {scope.model_dump(mode='json')}\n"
            f"{self._page_context_prompt(page_context)}\n"
            f"{self._grounding_context_prompt(grounding_context)}\n"
            f"Memory: {memory.model_dump(mode='json')}\n"
            f"Stored recommendations: {top_recommendations}\n"
            f"Available action labels: {action_labels}\n"
            "Write 1-4 concise sentences. For a wrong-answer explanation, name the mistaken reasoning, "
            "then name the rule or concept that makes the correct answer right. For a topic question, give "
            "a compact teaching explanation. For progress requests only, use any provided recommendation "
            "as one next step."
        )
        try:
            payload = self.structured_llm.generate_model(
                CoachReplyPayload,
                model_name=self.settings.llm_agent_model or self.structured_llm.model_name,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.25,
                max_tokens=220,
                request_name="study_coach_chat",
                request_context={
                    "course_id": scope.course_id,
                    "recommendation_count": str(len(recommendations)),
                },
            )
            return " ".join(payload.message.split())
        except (LLMProviderError, LLMResponseSchemaError, ValueError) as exc:
            logger.warning(
                "Study coach live LLM reply failed; falling back to grounded deterministic reply. course_id=%s error=%s",
                scope.course_id,
                exc,
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "Unexpected Study Coach LLM failure; falling back. course_id=%s",
                scope.course_id,
            )
        return None

    def _action_label(self, action: str) -> str:
        if action == "study_section":
            return "Open study section"
        if action == "practice_concept":
            return "Start practice quiz"
        if action == "mock_exam":
            return "Build mock exam"
        if action == "open_materials":
            return "Open book library"
        if action == "quality_status":
            return "View quality signal"
        return "Open"

    def _resolve_material_ids(self, state: Any) -> list[str]:
        scope = self._active_scope
        if scope and scope.material_ids:
            return scope.material_ids
        if state.course_id is None:
            return []
        module_ids = scope.module_ids if scope else state.requested_module_ids
        if not module_ids:
            return [
                record.material_id
                for record in self.material_store.list_records_by_course(state.course_id, None)
            ]
        material_ids: list[str] = []
        for module_id in module_ids:
            material_ids.extend(
                record.material_id
                for record in self.material_store.list_records_by_course(state.course_id, module_id)
            )
        return list(dict.fromkeys(material_ids))

    def _resolve_scope_source_ids(self, state: Any) -> list[str]:
        scope = self._active_scope
        if state.course_id is None:
            return []
        scoped_source_ids = self.retrieval_service.resolve_scope_source_ids(
            course_id=state.course_id,
            module_ids=scope.module_ids if scope else state.requested_module_ids,
        )
        if scope and scope.material_ids:
            scoped_source_ids = [
                section.source_id
                for document in self.material_store.list_parsed_documents_by_course(state.course_id, None)
                if document.record.material_id in scope.material_ids
                for section in document.sections
                if section.source_id in scoped_source_ids or not scoped_source_ids
            ]
        if scope and scope.section_ids:
            allowed = set(scoped_source_ids)
            return [source_id for source_id in scope.section_ids if not allowed or source_id in allowed]
        return scoped_source_ids

    def _retrieve_grounding_context(self, state: Any) -> list[GroundingContext]:
        if state.course_id is None:
            return []
        documents = self.material_store.list_parsed_documents_by_course(state.course_id, None)
        scoped_material_ids = set(state.material_ids)
        scoped_source_ids = set(state.scope_source_ids)
        max_contexts = self.settings.max_chunks_per_retrieval
        remaining_tokens = self.settings.max_agent_context_tokens
        contexts: list[GroundingContext] = []
        for document in documents:
            if scoped_material_ids and document.record.material_id not in scoped_material_ids:
                continue
            for chunk in document.chunks:
                if scoped_source_ids and chunk.source_id not in scoped_source_ids:
                    continue
                words = chunk.text.split()
                if not words:
                    continue
                allowed_tokens = min(len(words), remaining_tokens)
                excerpt = " ".join(words[:allowed_tokens])
                if excerpt:
                    contexts.append(
                        GroundingContext(
                            material_id=chunk.material_id,
                            excerpt=excerpt,
                            score=chunk.priority_score,
                        )
                    )
                    remaining_tokens -= allowed_tokens
                if len(contexts) >= max_contexts or remaining_tokens <= 0:
                    return contexts
        return contexts

    def _resolve_mastery(self, state: Any) -> tuple[dict[str, float], list[str]]:
        if state.course_id is None:
            return {}, []
        if self.analytics_store is not None:
            concepts = self.analytics_store.list_concepts(user_id="demo-user", course_id=state.course_id)
            if concepts:
                mastery_by_concept = {
                    record.concept_id: record.mastery_score
                    for record in concepts
                }
                wrong_concepts = [
                    record.concept_id
                    for record in concepts
                    if record.accuracy < 0.75 or record.repeat_misses >= 2
                ]
                return mastery_by_concept, wrong_concepts
        scope = self._active_scope
        module_id = scope.module_ids[0] if scope and len(scope.module_ids) == 1 else None
        mastery = self.quiz_store.get_mastery_snapshot(state.course_id, module_id)
        return mastery.mastery_by_concept, mastery.wrong_concepts

    def _build_recommendation_dicts(self, state: Any) -> list[dict[str, object]]:
        if state.course_id is None:
            return []
        scope = self._active_scope or StudyScope(course_id=state.course_id)
        analytics_recommendations = self._analytics_recommendations(scope)
        if analytics_recommendations:
            return [recommendation.model_dump(mode="json") for recommendation in analytics_recommendations[:4]]
        now = datetime.now(UTC).isoformat()
        recommendations: list[AgentRecommendation] = []
        wrong_questions = self._wrong_questions_for_scope(scope)
        first_wrong = wrong_questions[0] if wrong_questions else None
        first_citation = first_wrong.citations[0] if first_wrong and first_wrong.citations else None

        if first_wrong and first_citation:
            recommendations.append(
                self._recommendation(
                    scope=scope,
                    agent_name="study_coach_agent",
                    recommendation_type="weak_concept",
                    title=f"Study {first_wrong.concept}",
                    reason=(
                        "You recently missed this concept. Review the exact source section before practicing again."
                    ),
                    target_action="study_section",
                    target_payload={
                        "course_id": state.course_id,
                        "material_id": first_citation.material_id,
                        "section_id": first_citation.source_id,
                        "source_id": first_citation.source_id,
                        "page": first_citation.locator.page_number,
                        "href": self._study_href(state.course_id, first_citation.material_id, first_citation.source_id, first_citation.locator.page_number),
                    },
                    priority=95,
                    created_at=now,
                )
            )
            recommendations.append(
                self._recommendation(
                    scope=scope,
                    agent_name="assessment_agent",
                    recommendation_type="reinforcement_quiz",
                    title="Generate a 3-question reinforcement quiz",
                    reason="The Assessment Agent can reuse the missed concept scope and keep the practice focused.",
                    target_action="practice_concept",
                    target_payload={
                        "course_id": state.course_id,
                        "concept": first_wrong.concept,
                        "source_ids": [citation.source_id for citation in first_wrong.citations],
                        "href": f"/courses/{state.course_id}/wrong-questions?{urlencode({'concept': first_wrong.concept})}",
                    },
                    priority=82,
                    created_at=now,
                )
            )
        elif not state.material_ids:
            recommendations.append(
                self._recommendation(
                    scope=scope,
                    agent_name="materials_agent",
                    recommendation_type="add_material",
                    title="Upload the first course material",
                    reason="The Materials Agent needs at least one book, slide deck, or notes file before it can build grounded study actions.",
                    target_action="open_materials",
                    target_payload={"href": f"/courses/{state.course_id}/materials"},
                    priority=90,
                    created_at=now,
                )
            )
        else:
            recommendations.append(
                self._recommendation(
                    scope=scope,
                    agent_name="study_coach_agent",
                    recommendation_type="next_mock_exam",
                    title="Take a short mock exam",
                    reason="Your current scope has materials ready. A short exam will create stronger mastery and weak-concept signals.",
                    target_action="mock_exam",
                    target_payload={"href": f"/courses?mockExamCourseId={state.course_id}"},
                    priority=72,
                    created_at=now,
                )
            )

        if state.scope_source_ids:
            recommendations.append(
                self._recommendation(
                    scope=scope,
                    agent_name="quality_agent",
                    recommendation_type="quality_gate",
                    title="PyTorch quality gate is active",
                    reason=(
                        "Generated quiz and mock-exam questions are scored before delivery; weak live outputs fall back to safer grounded templates."
                    ),
                    target_action="quality_status",
                    target_payload={"source_count": len(state.scope_source_ids)},
                    priority=60,
                    created_at=now,
                )
            )

        return [recommendation.model_dump(mode="json") for recommendation in recommendations[:4]]

    def _analytics_recommendations(self, scope: StudyScope) -> list[AgentRecommendation]:
        if self.analytics_store is None:
            return []
        analytics_records = self.analytics_store.list_recommendations(
            user_id="demo-user",
            course_id=scope.course_id,
        )
        if not analytics_records:
            return []
        concepts = {
            record.concept_id: record
            for record in self.analytics_store.list_concepts(user_id="demo-user", course_id=scope.course_id)
        }
        recommendations: list[AgentRecommendation] = []
        for record in analytics_records:
            concept = concepts.get(record.target_concept_id or "")
            material_id = concept.material_id if concept else None
            section_id = record.target_section_id or (concept.section_id if concept else None)
            target_payload: dict[str, object] = {
                "course_id": scope.course_id,
                "module_id": record.target_module_id,
                "material_id": material_id,
                "section_id": section_id,
                "source_id": section_id,
                "concept_id": record.target_concept_id,
                "priority_score": record.priority_score,
            }
            if material_id and section_id:
                target_payload["href"] = self._study_href(scope.course_id, material_id, section_id, None)
            else:
                target_payload["href"] = f"/courses/{scope.course_id}/materials"
            recommendations.append(
                self._recommendation(
                    scope=scope,
                    agent_name="study_coach_agent",
                    recommendation_type=record.recommendation_type,
                    title=record.title,
                    reason=record.reason,
                    target_action="study_section" if record.recommendation_type == "weak_concept" else "practice_concept",
                    target_payload=target_payload,
                    priority=int(max(0, min(round(record.priority_score), 100))),
                    created_at=record.created_at,
                )
            )
        return recommendations

    def _wrong_questions_for_scope(self, scope: StudyScope) -> list[QuestionGradeResult]:
        quiz_sessions = self.quiz_store.list_quiz_sessions_by_course(
            scope.course_id,
            scope.module_ids[0] if len(scope.module_ids) == 1 else None,
        )
        wrong_questions: list[QuestionGradeResult] = []
        for session in quiz_sessions:
            for result in self.quiz_store.get_grade_results(session.quiz.quiz_id):
                if result.is_correct:
                    continue
                if scope.section_ids and not any(
                    citation.source_id in scope.section_ids for citation in result.citations
                ):
                    continue
                wrong_questions.append(result)
        return wrong_questions

    def _recommendation(
        self,
        *,
        scope: StudyScope,
        agent_name: str,
        recommendation_type: str,
        title: str,
        reason: str,
        target_action: str,
        target_payload: dict[str, object],
        priority: int,
        created_at: str,
    ) -> AgentRecommendation:
        signature = "|".join(
            [
                scope.course_id,
                agent_name,
                recommendation_type,
                title,
                str(target_payload.get("href") or target_payload.get("material_id") or ""),
            ]
        )
        return AgentRecommendation(
            id=sha256(signature.encode("utf-8")).hexdigest()[:24],
            course_id=scope.course_id,
            scope=scope,
            agent_name=agent_name,
            recommendation_type=recommendation_type,
            title=title,
            reason=reason,
            target_action=target_action,
            target_payload=target_payload,
            priority=priority,
            created_at=created_at,
        )

    def _study_href(
        self,
        course_id: str,
        material_id: str,
        source_id: str,
        page: int | None,
    ) -> str:
        params: dict[str, str] = {
            "materialId": material_id,
            "sourceId": source_id,
            "groupId": "all-sections",
            "study": "1",
        }
        if page:
            params["page"] = str(page)
        return f"/courses/{course_id}/materials?{urlencode(params)}"
