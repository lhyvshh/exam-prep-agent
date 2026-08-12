from exam_prep.schemas.graph import ExamPrepGraphState, NodeExecutionRecord


def grade_quiz_node(state: dict) -> dict:
    graph_state = ExamPrepGraphState.model_validate(state)
    status = "mastery_loaded" if graph_state.mastery_by_concept else "awaiting_grades"
    details = (
        f"{len(graph_state.mastery_by_concept)} concept mastery score(s) loaded."
        if graph_state.mastery_by_concept
        else "No graded quiz results are available in this context yet."
    )
    graph_state.execution_trace.append(
        NodeExecutionRecord(node_name="grade_quiz", status=status, details=details)
    )
    return graph_state.model_dump()
