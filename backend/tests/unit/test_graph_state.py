from exam_prep.agent_core.models import AgentRunRequest
from exam_prep.agent_core.orchestrator import AgentOrchestrator, AgentOrchestratorRuntime
from exam_prep.graph.builder import ExamPrepGraphRuntime, build_exam_prep_graph
from exam_prep.graph.nodes.intake import intake_node
from exam_prep.schemas.graph import ExamPrepGraphState, GroundingContext


def test_graph_state_defaults_are_typed() -> None:
    state = ExamPrepGraphState()

    assert state.material_ids == []
    assert state.execution_trace == []


def test_intake_node_appends_real_trace_status() -> None:
    updated = intake_node(ExamPrepGraphState(course_id="course-1").model_dump())
    validated = ExamPrepGraphState.model_validate(updated)

    assert validated.course_id == "course-1"
    assert validated.execution_trace[0].node_name == "intake"
    assert validated.execution_trace[0].status == "needs_materials"


def test_graph_hydrates_materials_context_and_mastery() -> None:
    graph = build_exam_prep_graph(
        ExamPrepGraphRuntime(
            resolve_material_ids=lambda state: ["mat-1"],
            retrieve_grounding_context=lambda state: [
                GroundingContext(material_id="mat-1", excerpt="Grounded excerpt", score=0.9)
            ],
            resolve_active_quiz=lambda state: None,
            resolve_mastery=lambda state: ({"Gradient Descent": 0.75}, ["Learning Rate"]),
        )
    )

    updated = graph.invoke(ExamPrepGraphState(course_id="course-1").model_dump())
    validated = ExamPrepGraphState.model_validate(updated)

    assert validated.material_ids == ["mat-1"]
    assert validated.grounding_context[0].excerpt == "Grounded excerpt"
    assert validated.mastery_by_concept == {"Gradient Descent": 0.75}
    assert validated.wrong_concepts == ["Learning Rate"]
    assert [record.node_name for record in validated.execution_trace] == [
        "intake",
        "retrieve_context",
        "generate_quiz",
        "grade_quiz",
        "remediation",
    ]
    assert all(record.status != "placeholder" for record in validated.execution_trace)


def test_agent_orchestrator_runs_visible_specialists() -> None:
    orchestrator = AgentOrchestrator(
        AgentOrchestratorRuntime(
            resolve_material_ids=lambda state: ["mat-1", "mat-2"],
            resolve_scope_source_ids=lambda state: ["source-1", "source-2"],
            retrieve_grounding_context=lambda state: [
                GroundingContext(material_id="mat-1", excerpt="Grounded excerpt", score=0.9)
            ],
            resolve_mastery=lambda state: ({"Type Conversion": 0.8}, ["Loops"]),
            build_recommendations=lambda state: [
                {
                    "id": "rec-1",
                    "course_id": state.course_id,
                    "scope": {"course_id": state.course_id},
                    "agent_name": "study_coach_agent",
                    "recommendation_type": "weak_concept",
                    "title": "Study Loops",
                    "reason": "Recent miss",
                    "target_action": "study_section",
                    "target_payload": {},
                    "priority": 90,
                    "created_at": "2026-04-27T00:00:00+00:00",
                }
            ],
            enable_torch_inference=True,
        )
    )

    state = orchestrator.run(
        AgentRunRequest(
            intent="generate_mock_exam",
            course_id="course-1",
            module_ids=["module-a", "module-b"],
        )
    )

    assert state.scope_source_ids == ["source-1", "source-2"]
    assert state.agent_recommendations[0]["title"] == "Study Loops"
    assert state.quality_summary is not None
    assert state.quality_summary.uses_torch is True
    assert [record.agent_name for record in state.execution_trace] == [
        "supervisor",
        "materials_agent",
        "assessment_agent",
        "study_coach_agent",
        "quality_agent",
    ]
