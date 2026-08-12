from fastapi.testclient import TestClient


def _upload_notes(
    client: TestClient,
    *,
    course_id: str,
    module_id: str | None,
    file_name: str,
    body: bytes,
) -> str:
    response = client.post(
        "/api/v1/materials/upload",
        data={"course_id": course_id, "module_id": module_id or ""},
        files={"file": (file_name, body, "text/plain")},
    )
    assert response.status_code == 201
    return response.json()["record"]["material_id"]


def _first_quiz_ready_section(client: TestClient, material_id: str) -> dict[str, object]:
    response = client.get(f"/api/v1/materials/{material_id}/sections")
    assert response.status_code == 200
    sections = [
        section
        for section in response.json()["sections"]
        if not section["is_junk"] and section["source_text"]
    ]
    assert sections
    return sections[0]


def _wait_for_quiz(client: TestClient, wait_for_quiz_job, response) -> dict[str, object]:
    assert response.status_code == 200
    payload = wait_for_quiz_job(response.json()["job_id"])
    assert payload["status"] in {"completed", "partial"}
    assert payload["quiz"] is not None
    assert payload["quiz"]["questions"]
    return payload


def test_activity_events_and_study_sessions_persist(client: TestClient) -> None:
    event_response = client.post(
        "/api/v1/activity/events",
        json={
            "user_id": "demo-user",
            "course_id": "course-activity",
            "module_id": "module-one",
            "material_id": "material-one",
            "section_id": "section-one",
            "event_type": "material_section_viewed",
            "metadata_json": {"source": "book-library"},
        },
    )
    assert event_response.status_code == 201
    event = event_response.json()
    assert event["event_type"] == "material_section_viewed"
    assert event["timestamp"]

    start_response = client.post(
        "/api/v1/activity/study-sessions/start",
        json={
            "user_id": "demo-user",
            "course_id": "course-activity",
            "module_id": "module-one",
            "material_id": "material-one",
            "section_id": "section-one",
            "metadata_json": {"origin": "recommendation"},
        },
    )
    assert start_response.status_code == 201
    session_id = start_response.json()["id"]

    end_response = client.post(
        f"/api/v1/activity/study-sessions/{session_id}/end",
        json={"metadata_json": {"ended_by": "test"}},
    )
    assert end_response.status_code == 200
    ended_session = end_response.json()
    assert ended_session["ended_at"]
    assert ended_session["duration_seconds"] is not None

    events_response = client.get(
        "/api/v1/activity/events",
        params={"user_id": "demo-user", "course_id": "course-activity"},
    )
    assert events_response.status_code == 200
    event_types = {item["event_type"] for item in events_response.json()["events"]}
    assert {
        "material_section_viewed",
        "study_session_started",
        "study_session_ended",
    }.issubset(event_types)

    material_events_response = client.get(
        "/api/v1/activity/events",
        params={
            "user_id": "demo-user",
            "course_id": "course-activity",
            "event_type": "material_section_viewed",
        },
    )
    assert material_events_response.status_code == 200
    assert [item["event_type"] for item in material_events_response.json()["events"]] == [
        "material_section_viewed"
    ]

    sessions_response = client.get(
        "/api/v1/activity/study-sessions",
        params={"user_id": "demo-user", "course_id": "course-activity"},
    )
    assert sessions_response.status_code == 200
    sessions = sessions_response.json()["study_sessions"]
    assert len(sessions) == 1
    assert sessions[0]["id"] == session_id
    assert sessions[0]["ended_at"]


def test_flashcard_reviews_persist_and_can_be_listed(client: TestClient) -> None:
    review_response = client.post(
        "/api/v1/activity/flashcard-reviews",
        json={
            "user_id": "demo-user",
            "course_id": "course-activity",
            "module_id": "module-one",
            "material_id": "material-one",
            "section_id": "section-one",
            "concept_id": "concept-one",
            "flashcard_id": "flashcard-one",
            "rating": "good",
            "previous_interval_days": 0,
            "new_interval_days": 3,
            "previous_confidence_group": "new",
            "new_confidence_group": "learning",
            "metadata_json": {"card_type": "definition", "source_page": 13},
        },
    )
    assert review_response.status_code == 201
    review = review_response.json()
    assert review["flashcard_id"] == "flashcard-one"
    assert review["rating"] == "good"
    assert review["new_interval_days"] == 3
    assert review["reviewed_at"]

    list_response = client.get(
        "/api/v1/activity/flashcard-reviews",
        params={"user_id": "demo-user", "course_id": "course-activity"},
    )
    assert list_response.status_code == 200
    reviews = list_response.json()["flashcard_reviews"]
    assert len(reviews) == 1
    assert reviews[0]["id"] == review["id"]
    assert reviews[0]["new_confidence_group"] == "learning"


def test_generated_content_quality_flags_persist_and_can_be_listed(client: TestClient) -> None:
    flag_response = client.post(
        "/api/v1/activity/generated-content-quality-flags",
        json={
            "course_id": "course-quality",
            "material_id": "material-one",
            "section_id": "section-one",
            "concept_id": "concept-one",
            "content_id": "flashcard-one",
            "content_type": "flashcard",
            "flag_type": "generic_question",
            "reason": "Rejected placeholder front text before saving the card.",
        },
    )
    assert flag_response.status_code == 201
    flag = flag_response.json()
    assert flag["content_id"] == "flashcard-one"
    assert flag["flag_type"] == "generic_question"
    assert flag["created_at"]

    list_response = client.get(
        "/api/v1/activity/generated-content-quality-flags",
        params={"course_id": "course-quality", "content_id": "flashcard-one"},
    )
    assert list_response.status_code == 200
    flags = list_response.json()["quality_flags"]
    assert len(flags) == 1
    assert flags[0]["id"] == flag["id"]
    assert flags[0]["reason"] == "Rejected placeholder front text before saving the card."


def test_quiz_grading_records_question_attempts_and_missed_question_events(
    client: TestClient,
    wait_for_quiz_job,
) -> None:
    material_id = _upload_notes(
        client,
        course_id="course-attempts",
        module_id="module-python",
        file_name="comparison-operators.txt",
        body=(
            b"# Comparison Operators\n"
            b"Comparison operators compare two values and return Boolean results. "
            b"Python uses == for equality and = for assignment. Students often confuse them."
        ),
    )
    section = _first_quiz_ready_section(client, material_id)
    quiz_payload = _wait_for_quiz(
        client,
        wait_for_quiz_job,
        client.post(
            "/api/v1/quiz/generate-from-section",
            json={
                "section_id": section["id"],
                "question_count": 1,
                "question_types": ["mcq"],
            },
        ),
    )
    quiz = quiz_payload["quiz"]
    question = quiz["questions"][0]
    answer_key = quiz_payload["partial_results"][0]["answer_key"]
    wrong_option = next(
        option["option_id"]
        for option in question["options"]
        if option["option_id"] != answer_key["correct_option_id"]
    )

    grade_response = client.post(
        "/api/v1/quiz/grade",
        json={
            "user_id": "demo-user",
            "quiz_id": quiz["quiz_id"],
            "answers": [
                {
                    "question_id": question["question_id"],
                    "selected_option_id": wrong_option,
                }
            ],
        },
    )
    assert grade_response.status_code == 200

    attempts_response = client.get(
        "/api/v1/activity/question-attempts",
        params={"user_id": "demo-user", "quiz_id": quiz["quiz_id"]},
    )
    assert attempts_response.status_code == 200
    attempts = attempts_response.json()["question_attempts"]
    assert len(attempts) == 1
    attempt = attempts[0]
    assert attempt["course_id"] == "course-attempts"
    assert attempt["module_id"] == "module-python"
    assert attempt["material_id"] == material_id
    assert attempt["section_id"] == section["id"]
    assert attempt["question_id"] == question["question_id"]
    assert attempt["selected_answer"] == wrong_option
    assert attempt["correct_answer"]
    assert attempt["is_correct"] is False
    assert attempt["question_type"] == "mcq"
    assert attempt["attempt_number"] == 1

    events_response = client.get(
        "/api/v1/activity/events",
        params={"user_id": "demo-user", "quiz_id": quiz["quiz_id"]},
    )
    assert events_response.status_code == 200
    event_types = {item["event_type"] for item in events_response.json()["events"]}
    assert {
        "question_submitted",
        "missed_question_saved",
        "quiz_completed",
    }.issubset(event_types)
