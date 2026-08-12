from exam_prep.schemas.graph import ExamPrepGraphState, NodeExecutionRecord


def remediation_node(state: dict) -> dict:
    graph_state = ExamPrepGraphState.model_validate(state)
    status = "needs_practice" if graph_state.wrong_concepts else "clear"
    details = (
        f"{len(graph_state.wrong_concepts)} concept(s) ready for remediation."
        if graph_state.wrong_concepts
        else "No wrong concepts recorded for remediation."
    )
    graph_state.execution_trace.append(
        NodeExecutionRecord(node_name="remediation", status=status, details=details)
    )
    return graph_state.model_dump()
