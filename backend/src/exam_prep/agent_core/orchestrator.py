from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from langchain_core.runnables import RunnableLambda

from exam_prep.agent_core.models import AgentRunRequest
from exam_prep.schemas.graph import (
    AgentMessage,
    ExamPrepGraphState,
    GroundingContext,
    NodeExecutionRecord,
    QualityCheckSummary,
)
from exam_prep.schemas.quiz import QuizBundle


@dataclass(slots=True)
class AgentOrchestratorRuntime:
    resolve_material_ids: Callable[[ExamPrepGraphState], list[str]] | None = None
    retrieve_grounding_context: Callable[[ExamPrepGraphState], list[GroundingContext]] | None = None
    resolve_scope_source_ids: Callable[[ExamPrepGraphState], list[str]] | None = None
    resolve_active_quiz: Callable[[ExamPrepGraphState], QuizBundle | None] | None = None
    resolve_mastery: Callable[[ExamPrepGraphState], tuple[dict[str, float], list[str]]] | None = None
    build_recommendations: Callable[[ExamPrepGraphState], list[dict[str, Any]]] | None = None
    enable_torch_inference: bool = False


class AgentOrchestrator:
    def __init__(self, runtime: AgentOrchestratorRuntime | None = None) -> None:
        self.runtime = runtime or AgentOrchestratorRuntime()
        self.graph = self._build_graph()

    def create_initial_state(self, request: AgentRunRequest) -> ExamPrepGraphState:
        return ExamPrepGraphState(
            intent=request.intent,
            course_id=request.course_id,
            module_id=request.module_id,
            requested_module_ids=request.module_ids,
            requested_material_ids=request.material_ids,
            requested_section_ids=request.section_ids,
        )

    def run(self, request: AgentRunRequest | ExamPrepGraphState) -> ExamPrepGraphState:
        initial_state = (
            request if isinstance(request, ExamPrepGraphState) else self.create_initial_state(request)
        )
        result = self.graph.invoke(initial_state.model_dump())
        return ExamPrepGraphState.model_validate(result)

    def _build_graph(self) -> Any:
        from langgraph.graph import END, START, StateGraph

        workflow = StateGraph(dict)
        workflow.add_node("supervisor", RunnableLambda(self._supervisor_node))
        workflow.add_node("materials_agent", RunnableLambda(self._materials_agent_node))
        workflow.add_node("assessment_agent", RunnableLambda(self._assessment_agent_node))
        workflow.add_node("study_coach_agent", RunnableLambda(self._study_coach_agent_node))
        workflow.add_node("quality_agent", RunnableLambda(self._quality_agent_node))
        workflow.add_edge(START, "supervisor")
        workflow.add_edge("supervisor", "materials_agent")
        workflow.add_edge("materials_agent", "assessment_agent")
        workflow.add_edge("assessment_agent", "study_coach_agent")
        workflow.add_edge("study_coach_agent", "quality_agent")
        workflow.add_edge("quality_agent", END)
        return workflow.compile()

    def _supervisor_node(self, raw_state: dict[str, Any]) -> dict[str, Any]:
        state = ExamPrepGraphState.model_validate(raw_state)
        scope_label = "whole course"
        if len(state.requested_module_ids) == 1:
            scope_label = "1 module selected"
        elif len(state.requested_module_ids) > 1:
            scope_label = f"{len(state.requested_module_ids)} modules selected"
        state.active_exam_scope_label = scope_label
        state.agent_messages.append(
            AgentMessage(
                agent_name="supervisor",
                message=f"Prepared {state.intent or 'workflow'} run for {scope_label}.",
            )
        )
        state.execution_trace.append(
            NodeExecutionRecord(
                agent_name="supervisor",
                node_name="supervisor",
                status="ready",
                details=scope_label,
            )
        )
        return state.model_dump()

    def _materials_agent_node(self, raw_state: dict[str, Any]) -> dict[str, Any]:
        state = ExamPrepGraphState.model_validate(raw_state)
        if state.requested_material_ids:
            state.material_ids = list(dict.fromkeys(state.requested_material_ids))
        elif state.course_id and self.runtime.resolve_material_ids is not None:
            state.material_ids = list(dict.fromkeys(self.runtime.resolve_material_ids(state)))
        if state.course_id and self.runtime.resolve_scope_source_ids is not None:
            state.scope_source_ids = list(dict.fromkeys(self.runtime.resolve_scope_source_ids(state)))
        if state.requested_section_ids:
            scoped = set(state.scope_source_ids)
            requested = list(dict.fromkeys(state.requested_section_ids))
            state.scope_source_ids = [source_id for source_id in requested if not scoped or source_id in scoped]
        if state.course_id and self.runtime.retrieve_grounding_context is not None:
            state.grounding_context = self.runtime.retrieve_grounding_context(state)

        status = "grounded" if state.material_ids else "needs_materials"
        state.agent_messages.append(
            AgentMessage(
                agent_name="materials_agent",
                message=(
                    f"Scoped {len(state.material_ids)} materials and "
                    f"{len(state.scope_source_ids)} eligible sources."
                ),
            )
        )
        state.execution_trace.append(
            NodeExecutionRecord(
                agent_name="materials_agent",
                node_name="materials_agent",
                status=status,
                details=f"{len(state.grounding_context)} excerpts ready",
            )
        )
        return state.model_dump()

    def _assessment_agent_node(self, raw_state: dict[str, Any]) -> dict[str, Any]:
        state = ExamPrepGraphState.model_validate(raw_state)
        if state.course_id and self.runtime.resolve_active_quiz is not None:
            state.active_quiz = self.runtime.resolve_active_quiz(state)
        status = "assessment_ready" if state.material_ids else "waiting_for_materials"
        state.agent_messages.append(
            AgentMessage(
                agent_name="assessment_agent",
                message=(
                    f"Assessment scope ready with {len(state.material_ids)} materials "
                    f"and {len(state.scope_source_ids)} scoped sources."
                ),
            )
        )
        state.execution_trace.append(
            NodeExecutionRecord(
                agent_name="assessment_agent",
                node_name="assessment_agent",
                status=status,
                details=state.active_exam_scope_label,
            )
        )
        return state.model_dump()

    def _study_coach_agent_node(self, raw_state: dict[str, Any]) -> dict[str, Any]:
        state = ExamPrepGraphState.model_validate(raw_state)
        if state.course_id and self.runtime.resolve_mastery is not None:
            mastery_by_concept, wrong_concepts = self.runtime.resolve_mastery(state)
            state.mastery_by_concept = mastery_by_concept
            state.wrong_concepts = wrong_concepts
        if state.course_id and self.runtime.build_recommendations is not None:
            state.agent_recommendations = self.runtime.build_recommendations(state)

        top_recommendation = (
            state.agent_recommendations[0].get("title")
            if state.agent_recommendations
            else "Study signal is still warming up."
        )
        state.agent_messages.append(
            AgentMessage(
                agent_name="study_coach_agent",
                message=f"Coach prepared {len(state.agent_recommendations)} next-step recommendations.",
            )
        )
        state.execution_trace.append(
            NodeExecutionRecord(
                agent_name="study_coach_agent",
                node_name="study_coach_agent",
                status="recommendations_ready" if state.agent_recommendations else "watching",
                details=str(top_recommendation),
            )
        )
        return state.model_dump()

    def _quality_agent_node(self, raw_state: dict[str, Any]) -> dict[str, Any]:
        state = ExamPrepGraphState.model_validate(raw_state)
        if state.course_id and self.runtime.resolve_mastery is not None and not state.mastery_by_concept:
            mastery_by_concept, wrong_concepts = self.runtime.resolve_mastery(state)
            state.mastery_by_concept = mastery_by_concept
            state.wrong_concepts = wrong_concepts

        quality_summary = QualityCheckSummary(
            gate_enabled=True,
            uses_torch=self.runtime.enable_torch_inference,
            accepted_for_delivery=bool(state.material_ids),
            notes=[
                f"PyTorch quality scoring {'enabled' if self.runtime.enable_torch_inference else 'disabled'}",
                f"{len(state.wrong_concepts)} weak concepts currently tracked",
            ],
        )
        state.quality_summary = quality_summary
        state.agent_messages.append(
            AgentMessage(
                agent_name="quality_agent",
                message=(
                    "Quality gate "
                    f"{'enabled with PyTorch' if quality_summary.uses_torch else 'enabled with heuristic fallback'}."
                ),
            )
        )
        state.execution_trace.append(
            NodeExecutionRecord(
                agent_name="quality_agent",
                node_name="quality_agent",
                status="quality_ready" if quality_summary.accepted_for_delivery else "quality_waiting",
                details="torch" if quality_summary.uses_torch else "heuristic",
            )
        )
        return state.model_dump()
