from exam_prep.schemas.graph import ExamPrepGraphState, NodeExecutionRecord


def retrieve_context_node(state: dict) -> dict:
    graph_state = ExamPrepGraphState.model_validate(state)
    status = "ready" if graph_state.grounding_context else "awaiting_query"
    details = (
        f"{len(graph_state.grounding_context)} grounding snippet(s) prepared."
        if graph_state.grounding_context
        else "Grounding context will be retrieved when the learner requests a quiz."
    )
    graph_state.execution_trace.append(
        NodeExecutionRecord(node_name="retrieve_context", status=status, details=details)
    )
    return graph_state.model_dump()
