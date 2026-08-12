from exam_prep.schemas.activity import (
    QuestionAttemptCreate,
    StudySessionEndRequest,
    StudySessionStartRequest,
)


COURSE_ID = "course-analytics"
MODULE_ID = "module-db"
MATERIAL_ID = "material-db"
SECTION_ID = "section-3nf"
CONCEPT_ID = "concept-3nf"


def test_analytics_endpoints_rank_real_weaknesses(client):
    _seed_low_mastery_signal(client)

    overview_response = client.get("/api/v1/analytics/overview", params={"courseId": COURSE_ID})
    assert overview_response.status_code == 200
    overview = overview_response.json()
    assert overview["course_id"] == COURSE_ID
    assert overview["accuracy_by_concept"][CONCEPT_ID] == 0.4
    assert overview["accuracy_by_question_type"]["scenario"] == 0.0
    assert overview["repeat_misses"] == 3
    assert overview["exam_readiness_score"] < 70
    assert overview["weak_concept_clusters"][0]["concept_id"] == CONCEPT_ID

    concepts_response = client.get("/api/v1/analytics/concepts", params={"courseId": COURSE_ID})
    assert concepts_response.status_code == 200
    top_concept = concepts_response.json()["concepts"][0]
    assert top_concept["concept_id"] == CONCEPT_ID
    assert top_concept["attempts"] == 5
    assert top_concept["correct_attempts"] == 2
    assert top_concept["repeat_misses"] == 3
    assert top_concept["mastery_score"] < 80

    modules_response = client.get("/api/v1/analytics/modules", params={"courseId": COURSE_ID})
    assert modules_response.status_code == 200
    top_module = modules_response.json()["modules"][0]
    assert top_module["module_id"] == MODULE_ID
    assert top_module["weak_concepts"][0]["concept_id"] == CONCEPT_ID
    assert top_module["weak_question_types"][0]["question_type"] == "scenario"

    question_types_response = client.get("/api/v1/analytics/question-types", params={"courseId": COURSE_ID})
    assert question_types_response.status_code == 200
    top_question_type = question_types_response.json()["question_types"][0]
    assert top_question_type["question_type"] == "scenario"
    assert top_question_type["accuracy"] == 0.0

    recommendations_response = client.get("/api/v1/analytics/recommendations", params={"courseId": COURSE_ID})
    assert recommendations_response.status_code == 200
    top_recommendation = recommendations_response.json()["recommendations"][0]
    assert top_recommendation["target_concept_id"] == CONCEPT_ID
    assert top_recommendation["target_section_id"] == SECTION_ID
    assert top_recommendation["priority_score"] > 50
    assert top_recommendation["recommended_action"].startswith("Review material first")


def test_agent_context_uses_analytics_recommendations(client):
    _seed_low_mastery_signal(client)

    response = client.get("/api/v1/agent/context", params={"courseId": COURSE_ID})
    assert response.status_code == 200
    payload = response.json()
    assert payload["course_id"] == COURSE_ID
    assert payload["overview"]["exam_readiness_score"] < 70
    assert payload["recommendations"][0]["target_concept_id"] == CONCEPT_ID
    assert "Low accuracy" in payload["recommendations"][0]["reason"]


def test_agent_run_uses_analytics_recommendations(client):
    _seed_low_mastery_signal(client)

    response = client.post(
        "/api/v1/agents/run",
        json={"intent": "progress_check", "scope": {"course_id": COURSE_ID}},
    )
    assert response.status_code == 200
    payload = response.json()
    recommendation = payload["recommendations"][0]
    assert recommendation["agent_name"] == "study_coach_agent"
    assert recommendation["recommendation_type"] == "weak_concept"
    assert recommendation["target_payload"]["concept_id"] == CONCEPT_ID
    assert recommendation["target_payload"]["section_id"] == SECTION_ID
    assert recommendation["target_action"] == "study_section"


def test_agent_recommendation_list_uses_analytics_signal(client):
    _seed_low_mastery_signal(client)

    response = client.get(f"/api/v1/agents/courses/{COURSE_ID}/recommendations")
    assert response.status_code == 200
    payload = response.json()
    recommendation = payload["recommendations"][0]
    assert recommendation["recommendation_type"] == "weak_concept"
    assert recommendation["target_payload"]["concept_id"] == CONCEPT_ID


def test_dashboard_includes_analytics_mastery_panels(client):
    _seed_low_mastery_signal(client)

    response = client.get(f"/api/v1/dashboard/{COURSE_ID}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["exam_readiness_score"] < 70
    assert payload["weak_modules"][0]["module_id"] == MODULE_ID
    assert payload["weak_concepts_ranked"][0]["concept_id"] == CONCEPT_ID
    assert payload["weak_question_types"][0]["question_type"] == "scenario"
    assert payload["study_recommendations"][0]["target_concept_id"] == CONCEPT_ID
    assert payload["study_recommendations"][0]["href"].endswith(
        f"materialId={MATERIAL_ID}&sourceId={SECTION_ID}&groupId=all-sections&study=1"
    )


def _seed_low_mastery_signal(client) -> None:
    activity_store = client.app.state.activity_store

    attempts = [
        ("q1", "definition", True, 45),
        ("q2", "scenario", False, 72),
        ("q3", "scenario", False, 64),
        ("q4", "scenario", False, 80),
        ("q5", "comparison", True, 52),
    ]
    for question_id, question_type, is_correct, time_spent in attempts:
        activity_store.record_question_attempt(
            QuestionAttemptCreate(
                user_id="demo-user",
                quiz_id="quiz-analytics",
                question_id=question_id,
                course_id=COURSE_ID,
                module_id=MODULE_ID,
                material_id=MATERIAL_ID,
                section_id=SECTION_ID,
                concept_id=CONCEPT_ID,
                selected_answer="student answer",
                correct_answer="correct answer",
                is_correct=is_correct,
                time_spent_seconds=time_spent,
                question_type=question_type,
                difficulty=0.75,
            )
        )

    session = activity_store.start_study_session(
        StudySessionStartRequest(
            user_id="demo-user",
            course_id=COURSE_ID,
            module_id=MODULE_ID,
            material_id=MATERIAL_ID,
            section_id=SECTION_ID,
            metadata_json={"test_started_at": "now"},
        )
    )
    activity_store.end_study_session(
        session.id,
        StudySessionEndRequest(metadata_json={"duration_override_seconds": 15}),
    )
