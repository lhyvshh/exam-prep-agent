from pathlib import Path

from fastapi.testclient import TestClient


def _correct_option_id(question: dict) -> str:
    correct_answer = str(question.get("correct_answer") or "").strip().lower()
    positive_phrases = (
        "opposite the gradient",
        "size of each update step",
        "full dataset",
    )
    for option in question.get("options", []):
        option_id = str(option.get("option_id") or "")
        option_text = str(option.get("text") or "").strip().lower()
        if option_id.lower() == correct_answer or option_text == correct_answer:
            return option_id
        if correct_answer and (option_text in correct_answer or correct_answer in option_text):
            return option_id
        if any(phrase in option_text for phrase in positive_phrases):
            return option_id
    return "A"


def test_quiz_generation_job_and_grading_happy_path(
    client: TestClient,
    wait_for_quiz_job,
) -> None:
    fixture_dir = Path("backend/tests/fixtures/sample_course")
    upload_response = client.post(
        "/api/v1/materials/upload",
        data={"course_id": "course-quiz"},
        files={
            "file": (
                "optimization_notes.txt",
                (fixture_dir / "optimization_notes.txt").read_bytes(),
                "text/plain",
            )
        },
    )
    assert upload_response.status_code == 201

    generate_response = client.post(
        "/api/v1/quiz/generate",
        json={
            "course_id": "course-quiz",
            "query": "gradient descent learning rate",
            "question_count": 2,
            "question_types": ["mcq", "short_answer"],
            "retrieval_top_k": 4,
        },
    )

    assert generate_response.status_code == 200
    job_id = generate_response.json()["job_id"]
    job_payload = wait_for_quiz_job(job_id)
    assert job_payload["status"] in {"completed", "partial"}

    quiz = job_payload["quiz"]
    assert quiz is not None
    assert len(quiz["questions"]) == 2
    assert quiz["questions"][0]["question_type"] == "mcq"
    assert quiz["questions"][1]["question_type"] == "mcq"

    grade_response = client.post(
        "/api/v1/quiz/grade",
        json={
            "quiz_id": quiz["quiz_id"],
            "answers": [
                {
                    "question_id": question["question_id"],
                    "selected_option_id": _correct_option_id(question),
                }
                for question in quiz["questions"]
            ],
        },
    )

    assert grade_response.status_code == 200
    payload = grade_response.json()
    assert payload["overall_score"] == 100.0
    assert payload["wrong_concepts"] == []
    assert payload["mastery_by_concept"]
    assert all(result["is_correct"] for result in payload["results"])
    assert payload["results"][0]["grading_label"] == "correct"
    assert "Correct." in payload["results"][0]["explanation"]
    assert "optimization_notes.txt" in payload["results"][0]["citations"][0]["citation_label"]


def test_duplicate_quiz_submit_returns_same_job_id(
    client: TestClient,
) -> None:
    upload_response = client.post(
        "/api/v1/materials/upload",
        data={"course_id": "course-dedupe"},
        files={
            "file": (
                "notes.txt",
                b"# Gradient Descent Basics\nGradient descent updates model parameters using the learning rate.",
                "text/plain",
            )
        },
    )
    assert upload_response.status_code == 201

    payload = {
        "course_id": "course-dedupe",
        "query": "learning rate",
        "question_count": 2,
        "question_types": ["mcq"],
        "retrieval_top_k": 4,
        "selected_source_ids": [],
    }

    first = client.post("/api/v1/quiz/generate", json=payload)
    second = client.post("/api/v1/quiz/generate", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["job_id"] == second.json()["job_id"]


def test_quiz_generation_job_fails_cleanly_when_retrieval_is_empty(
    client: TestClient,
    wait_for_quiz_job,
) -> None:
    fixture_dir = Path("backend/tests/fixtures/sample_course")
    upload_response = client.post(
        "/api/v1/materials/upload",
        data={"course_id": "course-empty"},
        files={
            "file": (
                "portfolio_basics.txt",
                (fixture_dir / "portfolio_basics.txt").read_bytes(),
                "text/plain",
            )
        },
    )
    assert upload_response.status_code == 201

    generate_response = client.post(
        "/api/v1/quiz/generate",
        json={
            "course_id": "course-empty",
            "query": "quantum entanglement qubits superposition",
            "question_count": 2,
            "question_types": ["mcq", "short_answer"],
        },
    )

    assert generate_response.status_code == 200
    job_payload = wait_for_quiz_job(generate_response.json()["job_id"])
    assert job_payload["status"] == "failed"
    assert "No relevant materials found for quiz generation" in (job_payload["error_summary"] or "")


def test_quiz_generation_avoids_logistics_sections_by_default(
    client: TestClient,
    wait_for_quiz_job,
) -> None:
    upload_response = client.post(
        "/api/v1/materials/upload",
        data={"course_id": "course-logistics"},
        files={
            "file": (
                "session_notes.txt",
                (
                    b"# Office Hours Schedule\nOffice hours are Tuesdays at 3 PM.\n"
                    b"# Gradient Descent Basics\nGradient descent updates model parameters using the learning rate."
                ),
                "text/plain",
            )
        },
    )
    assert upload_response.status_code == 201

    generate_response = client.post(
        "/api/v1/quiz/generate",
        json={
            "course_id": "course-logistics",
            "query": "learning rate",
            "question_count": 1,
            "question_types": ["mcq"],
            "retrieval_top_k": 4,
            "selected_source_ids": [],
        },
    )

    assert generate_response.status_code == 200
    job_payload = wait_for_quiz_job(generate_response.json()["job_id"])
    quiz_payload = job_payload["quiz"]
    assert quiz_payload["questions"][0]["citations"][0]["section_title"] == "Gradient Descent Basics"


def test_quiz_generation_uses_selected_sources_even_when_query_text_is_weak(
    client: TestClient,
    wait_for_quiz_job,
) -> None:
    upload_response = client.post(
        "/api/v1/materials/upload",
        data={"course_id": "course-selected-sources"},
        files={
            "file": (
                "notes.txt",
                (
                    b"# Gradient Descent Basics\n"
                    b"Gradient descent updates model parameters using the learning rate.\n"
                    b"# Worked Example\n"
                    b"A smaller learning rate takes more steps but can improve stability."
                ),
                "text/plain",
            )
        },
    )
    assert upload_response.status_code == 201

    materials_response = client.get("/api/v1/materials/course/course-selected-sources")
    assert materials_response.status_code == 200
    quiz_source = materials_response.json()["quiz_sources"][0]

    generate_response = client.post(
        "/api/v1/quiz/generate",
        json={
            "course_id": "course-selected-sources",
            "query": "packet pages bundle",
            "question_count": 1,
            "question_types": ["mcq"],
            "retrieval_top_k": 4,
            "selected_source_ids": quiz_source["source_ids"],
        },
    )

    assert generate_response.status_code == 200
    job_payload = wait_for_quiz_job(generate_response.json()["job_id"])
    quiz_payload = job_payload["quiz"]
    assert quiz_payload["questions"][0]["citations"][0]["section_title"] in {
        "Gradient Descent Basics",
        "Worked Example",
    }


def test_quiz_review_and_delete_attempt_endpoints(
    client: TestClient,
    wait_for_quiz_job,
) -> None:
    upload_response = client.post(
        "/api/v1/materials/upload",
        data={"course_id": "course-review"},
        files={
            "file": (
                "notes.txt",
                b"# Gradient Descent Basics\nGradient descent updates model parameters using the learning rate.",
                "text/plain",
            )
        },
    )
    assert upload_response.status_code == 201

    generate_response = client.post(
        "/api/v1/quiz/generate",
        json={
            "course_id": "course-review",
            "query": "learning rate",
            "question_count": 1,
            "question_types": ["mcq"],
            "retrieval_top_k": 4,
        },
    )
    assert generate_response.status_code == 200

    quiz_payload = wait_for_quiz_job(generate_response.json()["job_id"])["quiz"]
    grade_response = client.post(
        "/api/v1/quiz/grade",
        json={
            "quiz_id": quiz_payload["quiz_id"],
            "answers": [
                {
                    "question_id": quiz_payload["questions"][0]["question_id"],
                    "selected_option_id": "Z",
                }
            ],
        },
    )
    assert grade_response.status_code == 200

    review_response = client.get(f"/api/v1/quiz/{quiz_payload['quiz_id']}/review")
    assert review_response.status_code == 200
    review_payload = review_response.json()
    assert review_payload["quiz"]["quiz_id"] == quiz_payload["quiz_id"]
    assert len(review_payload["results"]) == 1

    delete_response = client.delete(f"/api/v1/quiz/{quiz_payload['quiz_id']}")
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] is True

    missing_review_response = client.get(f"/api/v1/quiz/{quiz_payload['quiz_id']}/review")
    assert missing_review_response.status_code == 404
