from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from exam_prep.graph.nodes.generate_quiz import generate_quiz_node
from exam_prep.graph.nodes.grade_quiz import grade_quiz_node
from exam_prep.graph.nodes.intake import intake_node
from exam_prep.graph.nodes.remediation import remediation_node
from exam_prep.graph.nodes.retrieve_context import retrieve_context_node
from exam_prep.schemas.graph import ExamPrepGraphState, GroundingContext, NodeExecutionRecord
from exam_prep.schemas.quiz import QuizBundle


@dataclass(slots=True)
class ExamPrepGraphRuntime:
    resolve_material_ids: Callable[[ExamPrepGraphState], list[str]] | None = None
    retrieve_grounding_context: Callable[[ExamPrepGraphState], list[GroundingContext]] | None = None
    resolve_active_quiz: Callable[[ExamPrepGraphState], QuizBundle | None] | None = None
    resolve_mastery: Callable[[ExamPrepGraphState], tuple[dict[str, float], list[str]]] | None = None


def build_exam_prep_graph(runtime: ExamPrepGraphRuntime | None = None) -> Any:
    from langgraph.graph import END, START, StateGraph

    active_runtime = runtime or ExamPrepGraphRuntime()
    workflow = StateGraph(dict)
    workflow.add_node("intake", _runtime_intake_node(active_runtime))
    workflow.add_node("retrieve_context", _runtime_retrieve_context_node(active_runtime))
    workflow.add_node("generate_quiz", _runtime_generate_quiz_node(active_runtime))
    workflow.add_node("grade_quiz", _runtime_grade_quiz_node(active_runtime))
    workflow.add_node("remediation", remediation_node)

    workflow.add_edge(START, "intake")
    workflow.add_edge("intake", "retrieve_context")
    workflow.add_edge("retrieve_context", "generate_quiz")
    workflow.add_edge("generate_quiz", "grade_quiz")
    workflow.add_edge("grade_quiz", "remediation")
    workflow.add_edge("remediation", END)
    return workflow.compile()


def build_default_graph() -> Any:
    return build_exam_prep_graph()


def _runtime_intake_node(runtime: ExamPrepGraphRuntime) -> Callable[[dict], dict]:
    def _node(state: dict) -> dict:
        graph_state = ExamPrepGraphState.model_validate(state)
        if graph_state.course_id is not None and runtime.resolve_material_ids is not None:
            graph_state.material_ids = list(dict.fromkeys(runtime.resolve_material_ids(graph_state)))
        return intake_node(graph_state.model_dump())

    return _node


def _runtime_retrieve_context_node(runtime: ExamPrepGraphRuntime) -> Callable[[dict], dict]:
    def _node(state: dict) -> dict:
        graph_state = ExamPrepGraphState.model_validate(state)
        if graph_state.material_ids and runtime.retrieve_grounding_context is not None:
            graph_state.grounding_context = runtime.retrieve_grounding_context(graph_state)
        return retrieve_context_node(graph_state.model_dump())

    return _node


def _runtime_generate_quiz_node(runtime: ExamPrepGraphRuntime) -> Callable[[dict], dict]:
    def _node(state: dict) -> dict:
        graph_state = ExamPrepGraphState.model_validate(state)
        if graph_state.course_id is not None and runtime.resolve_active_quiz is not None:
            graph_state.active_quiz = runtime.resolve_active_quiz(graph_state)
        return generate_quiz_node(graph_state.model_dump())

    return _node


def _runtime_grade_quiz_node(runtime: ExamPrepGraphRuntime) -> Callable[[dict], dict]:
    def _node(state: dict) -> dict:
        graph_state = ExamPrepGraphState.model_validate(state)
        if graph_state.course_id is not None and runtime.resolve_mastery is not None:
            mastery_by_concept, wrong_concepts = runtime.resolve_mastery(graph_state)
            graph_state.mastery_by_concept = mastery_by_concept
            graph_state.wrong_concepts = wrong_concepts
        elif graph_state.course_id is None:
            graph_state.execution_trace.append(
                NodeExecutionRecord(
                    node_name="grade_quiz",
                    status="skipped",
                    details="No course selected.",
                )
            )
            return graph_state.model_dump()
        return grade_quiz_node(graph_state.model_dump())

    return _node
