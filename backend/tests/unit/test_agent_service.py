import json
from types import SimpleNamespace

from exam_prep.core.config import Settings
from exam_prep.llm.models import LLMResponse
from exam_prep.schemas.materials import MaterialRecord, ParsedMaterialDocument, SourceChunk, SourceLocator
from exam_prep.schemas.agent import (
    AgentChatRequest,
    AgentMemoryProfile,
    AgentMemoryUpdateRequest,
    AgentPageContext,
    AgentPageQuestionContext,
    AgentPageQuestionOption,
    AgentRecommendation,
)
from exam_prep.schemas.scope import StudyScope
from exam_prep.services.agent_service import AgentService
from exam_prep.services.llm_service import StructuredLLMService


class FakeLLMClient:
    supports_json_schema_response_format = True
    enable_response_format = True
    last_request = None

    def generate(self, request):  # type: ignore[no-untyped-def]
        self.last_request = request
        return LLMResponse(
            model_name=request.model_name,
            provider_name="openai",
            raw_text=json.dumps({"message": "Review Variables first, then use the Study now action."}),
        )


class FakeAgentStore:
    def __init__(self) -> None:
        self.memory = AgentMemoryProfile(course_id="course-1", preferred_study_style="exam_cram")
        self.recommendations = [
            AgentRecommendation(
                id="rec-1",
                course_id="course-1",
                scope=StudyScope(course_id="course-1"),
                agent_name="study_coach_agent",
                recommendation_type="weak_concept",
                title="Study Variables",
                reason="You missed this recently.",
                target_action="study_section",
                target_payload={"href": "/courses/course-1/materials?materialId=mat-1&sourceId=source-1&study=1"},
                priority=95,
                created_at="2026-04-27T00:00:00Z",
            )
        ]

    def get_memory(self, course_id: str) -> AgentMemoryProfile | None:
        return self.memory if course_id == self.memory.course_id else None

    def list_recommendations(self, course_id: str):  # type: ignore[no-untyped-def]
        return self.recommendations if course_id == "course-1" else []

    def save_memory(self, memory: AgentMemoryProfile) -> AgentMemoryProfile:
        self.memory = memory
        return memory


def _agent_source_chunk(index: int, text: str) -> SourceChunk:
    return SourceChunk(
        chunk_id=f"chunk-{index}",
        source_id=f"source-{index}",
        material_id="material-1",
        course_id="course-1",
        module_id=None,
        file_name="notes.txt",
        content_type="text/plain",
        section_title=f"Section {index}",
        text=text,
        token_count=len(text.split()),
        locator=SourceLocator(section_index=index, page_number=index),
        citation_label=f"notes.txt | Section {index}",
    )


class FakeMaterialStore:
    def __init__(self) -> None:
        record = MaterialRecord(
            material_id="material-1",
            course_id="course-1",
            file_name="notes.txt",
            content_type="text/plain",
        )
        self.document = ParsedMaterialDocument(
            record=record,
            sections=[],
            chunks=[
                _agent_source_chunk(1, "alpha beta gamma delta epsilon"),
                _agent_source_chunk(2, "zeta eta theta iota kappa"),
                _agent_source_chunk(3, "lambda mu nu xi omicron"),
            ],
        )

    def list_parsed_documents_by_course(self, course_id: str, module_id):  # type: ignore[no-untyped-def]
        del module_id
        return [self.document] if course_id == "course-1" else []


def test_agent_chat_uses_live_llm_when_available() -> None:
    llm_client = FakeLLMClient()
    service = AgentService(
        settings=Settings(),
        agent_store=FakeAgentStore(),  # type: ignore[arg-type]
        material_store=object(),  # type: ignore[arg-type]
        vector_store=object(),  # type: ignore[arg-type]
        quiz_store=object(),  # type: ignore[arg-type]
        exam_store=object(),  # type: ignore[arg-type]
        structured_llm=StructuredLLMService(llm_client, "gpt-5.4-mini"),  # type: ignore[arg-type]
    )

    response = service.chat(AgentChatRequest(course_id="course-1", message="help me study variables"))

    assert response.response_mode == "live_llm"
    assert response.message == "Review Variables first, then use the Study now action."
    assert response.actions == []
    assert response.recommendations == []
    assert response.active_agent_profile.display_name == "Exam Butler"
    assert "weak concept triage" in response.active_agent_profile.skills
    assert any(profile.agent_name == "quality_agent" for profile in response.agent_profiles)
    assert llm_client.last_request is not None
    assert "teaching assistant" in llm_client.last_request.system_prompt.lower()
    assert "after-school teacher" in llm_client.last_request.system_prompt.lower()
    assert "do not show progress dashboards" in llm_client.last_request.system_prompt.lower()


def test_agent_chat_grounds_question_review_in_page_context_and_book_source() -> None:
    llm_client = FakeLLMClient()
    service = AgentService(
        settings=Settings(max_chunks_per_retrieval=2, max_agent_context_tokens=80),
        agent_store=FakeAgentStore(),  # type: ignore[arg-type]
        material_store=FakeMaterialStore(),  # type: ignore[arg-type]
        vector_store=object(),  # type: ignore[arg-type]
        quiz_store=object(),  # type: ignore[arg-type]
        exam_store=object(),  # type: ignore[arg-type]
        structured_llm=StructuredLLMService(llm_client, "gpt-5.4-mini"),  # type: ignore[arg-type]
    )

    response = service.chat(
        AgentChatRequest(
            course_id="course-1",
            message="Why did I get question 2 wrong?",
            scope=StudyScope(course_id="course-1", material_ids=["material-1"], section_ids=["source-2"]),
            page_context=AgentPageContext(
                page_type="quiz_review",
                route="/courses/course-1/quiz",
                title="Quiz review",
                visible_text="Question 2 asks why diversification reduces unsystematic risk.",
                source_ids=["source-2"],
                material_ids=["material-1"],
                section_ids=["source-2"],
                question=AgentPageQuestionContext(
                    question_number=2,
                    question_id="q2",
                    prompt="Why does diversification reduce unsystematic risk?",
                    selected_option_id="A",
                    correct_option_id="C",
                    correct_answer="It offsets firm-specific risks across holdings.",
                    explanation="Diversification reduces firm-specific risk because imperfectly correlated holdings offset one another.",
                    concept="Diversification",
                    source_page=2,
                    options=[
                        AgentPageQuestionOption(option_id="A", text="It removes systematic market risk."),
                        AgentPageQuestionOption(option_id="C", text="It offsets firm-specific risks across holdings."),
                    ],
                ),
            ),
        )
    )

    assert response.response_mode == "live_llm"
    assert llm_client.last_request is not None
    assert "Question 2 asks why diversification reduces unsystematic risk." in llm_client.last_request.user_prompt
    assert "Selected answer: A. It removes systematic market risk." in llm_client.last_request.user_prompt
    assert "Correct answer: C. It offsets firm-specific risks across holdings." in llm_client.last_request.user_prompt
    assert "zeta eta theta iota kappa" in llm_client.last_request.user_prompt
    assert "why the selected answer is wrong" in llm_client.last_request.system_prompt.lower()


def test_agent_chat_normalizes_mismatched_scope_to_request_course() -> None:
    llm_client = FakeLLMClient()
    service = AgentService(
        settings=Settings(),
        agent_store=FakeAgentStore(),  # type: ignore[arg-type]
        material_store=object(),  # type: ignore[arg-type]
        vector_store=object(),  # type: ignore[arg-type]
        quiz_store=object(),  # type: ignore[arg-type]
        exam_store=object(),  # type: ignore[arg-type]
        structured_llm=StructuredLLMService(llm_client, "gpt-5.4-mini"),  # type: ignore[arg-type]
    )

    response = service.chat(
        AgentChatRequest(
            course_id="course-1",
            message="help me study variables",
            scope=StudyScope(course_id="course-2", module_ids=["other-module"]),
        )
    )

    assert response.course_id == "course-1"
    assert response.memory.course_id == "course-1"
    assert llm_client.last_request is not None
    assert "'course_id': 'course-1'" in llm_client.last_request.user_prompt
    assert "'course_id': 'course-2'" not in llm_client.last_request.user_prompt
    assert "other-module" not in llm_client.last_request.user_prompt


def test_agent_grounding_context_respects_chunk_and_token_caps() -> None:
    service = AgentService(
        settings=Settings(max_chunks_per_retrieval=2, max_agent_context_tokens=7),
        agent_store=FakeAgentStore(),  # type: ignore[arg-type]
        material_store=FakeMaterialStore(),  # type: ignore[arg-type]
        vector_store=object(),  # type: ignore[arg-type]
        quiz_store=object(),  # type: ignore[arg-type]
        exam_store=object(),  # type: ignore[arg-type]
    )

    contexts = service._retrieve_grounding_context(  # noqa: SLF001
        SimpleNamespace(course_id="course-1", material_ids=[], scope_source_ids=[])
    )

    assert len(contexts) == 2
    assert sum(len(context.excerpt.split()) for context in contexts) <= 7
    assert contexts[0].excerpt == "alpha beta gamma delta epsilon"
    assert contexts[1].excerpt == "zeta eta"


def test_agent_chat_grounded_fallback_uses_exam_butler_personality() -> None:
    service = AgentService(
        settings=Settings(),
        agent_store=FakeAgentStore(),  # type: ignore[arg-type]
        material_store=object(),  # type: ignore[arg-type]
        vector_store=object(),  # type: ignore[arg-type]
        quiz_store=object(),  # type: ignore[arg-type]
        exam_store=object(),  # type: ignore[arg-type]
    )

    response = service.chat(AgentChatRequest(course_id="course-1", message="hello"))

    assert response.response_mode == "grounded_fallback"
    assert "current page" in response.message.lower()
    assert response.actions == []
    assert response.recommendations == []
    assert response.active_agent_profile.display_name == "Exam Butler"
    assert "progress interpretation" in response.active_agent_profile.skills


def test_agent_chat_does_not_run_progress_check_for_normal_teaching_question() -> None:
    class NoProgressCheckAgentService(AgentService):
        def run_course_check(self, *, intent: str, scope: StudyScope):  # type: ignore[no-untyped-def]
            del intent, scope
            raise AssertionError("Normal Butler teaching chat should not run a progress check.")

    store = FakeAgentStore()
    store.recommendations = []
    llm_client = FakeLLMClient()
    service = NoProgressCheckAgentService(
        settings=Settings(),
        agent_store=store,  # type: ignore[arg-type]
        material_store=object(),  # type: ignore[arg-type]
        vector_store=object(),  # type: ignore[arg-type]
        quiz_store=object(),  # type: ignore[arg-type]
        exam_store=object(),  # type: ignore[arg-type]
        structured_llm=StructuredLLMService(llm_client, "gpt-5.4-mini"),  # type: ignore[arg-type]
    )

    response = service.chat(AgentChatRequest(course_id="course-1", message="Can you explain CAPM beta?"))

    assert response.response_mode == "live_llm"
    assert response.actions == []
    assert response.recommendations == []


def test_agent_memory_forces_mcq_format_for_existing_and_saved_preferences() -> None:
    store = FakeAgentStore()
    store.memory = AgentMemoryProfile(
        course_id="course-1",
        preferred_study_style="exam_cram",
        preferred_quiz_format="mixed",
    )
    service = AgentService(
        settings=Settings(),
        agent_store=store,  # type: ignore[arg-type]
        material_store=object(),  # type: ignore[arg-type]
        vector_store=object(),  # type: ignore[arg-type]
        quiz_store=object(),  # type: ignore[arg-type]
        exam_store=object(),  # type: ignore[arg-type]
    )

    existing = service.get_memory("course-1")

    assert existing.preferred_quiz_format == "mcq"
    assert store.memory.preferred_quiz_format == "mcq"

    saved = service.save_memory(
        "course-1",
        AgentMemoryUpdateRequest(
            preferred_study_style="balanced",
            preferred_quiz_format="short_answer",
            default_question_count=5,
        ),
    )

    assert saved.preferred_quiz_format == "mcq"
    assert store.memory.preferred_quiz_format == "mcq"
