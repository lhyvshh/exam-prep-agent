from exam_prep.schemas.graph import ExamPrepGraphState, NodeExecutionRecord


def generate_quiz_node(state: dict) -> dict:
    graph_state = ExamPrepGraphState.model_validate(state)
    status = "active_quiz_loaded" if graph_state.active_quiz is not None else "ready_for_generation"
    details = (
        f"Loaded active quiz {graph_state.active_quiz.quiz_id}."
        if graph_state.active_quiz is not None
        else "Quiz generation will run through the async job runner."
    )
    graph_state.execution_trace.append(
        NodeExecutionRecord(node_name="generate_quiz", status=status, details=details)
    )
    return graph_state.model_dump()
