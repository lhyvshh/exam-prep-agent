from exam_prep.schemas.graph import ExamPrepGraphState, NodeExecutionRecord


def intake_node(state: dict) -> dict:
    graph_state = ExamPrepGraphState.model_validate(state)
    if graph_state.course_id is None:
        status = "needs_course"
        details = "No active course selected."
    elif not graph_state.material_ids:
        status = "needs_materials"
        details = "Course selected, but no parsed materials are available."
    else:
        status = "ready"
        details = f"{len(graph_state.material_ids)} material(s) available."
    graph_state.execution_trace.append(
        NodeExecutionRecord(node_name="intake", status=status, details=details)
    )
    return graph_state.model_dump()
