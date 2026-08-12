from pathlib import Path

from fastapi.testclient import TestClient


def test_question_quality_endpoint_scores_batch_with_fallback_model(client: TestClient) -> None:
    response = client.post(
        "/api/v1/ml/question-quality/score",
        json={
            "questions": [
                {
                    "question_id": "good-q",
                    "prompt": 'Which statement is supported by the section "Gradient Descent Basics"?',
                    "question_type": "mcq",
                    "concept": "Gradient Descent",
                    "section_title": "Gradient Descent Basics",
                    "difficulty": 0.55,
                    "options": [
                        "Correct grounded option.",
                        "Distractor one.",
                        "Distractor two.",
                        "Distractor three.",
                    ],
                    "rationale": "Grounded in the retrieved passage for this section.",
                    "citation_count": 1,
                },
                {
                    "question_id": "bad-q",
                    "prompt": "What?",
                    "question_type": "mcq",
                    "difficulty": 0.5,
                    "options": ["A", "B"],
                    "citation_count": 0,
                },
            ]
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["results"]) == 2
    assert payload["results"][0]["score"] > payload["results"][1]["score"]
    assert payload["results"][0]["model_source"] == "heuristic_fallback"
    assert payload["results"][1]["accepted_for_delivery"] is False


def test_quiz_generation_attaches_quality_validation(
    client: TestClient,
    wait_for_quiz_job,
) -> None:
    fixture_dir = Path("backend/tests/fixtures/sample_course")
    upload_response = client.post(
        "/api/v1/materials/upload",
        data={"course_id": "course-quality"},
        files={
            "file": (
                "optimization_notes.txt",
                (fixture_dir / "optimization_notes.txt").read_bytes(),
                "text/plain",
            )
        },
    )
    assert upload_response.status_code == 201

    response = client.post(
        "/api/v1/quiz/generate",
        json={
            "course_id": "course-quality",
            "query": "gradient descent learning rate",
            "question_count": 2,
            "question_types": ["mcq", "short_answer"],
            "retrieval_top_k": 4,
        },
    )

    assert response.status_code == 200
    job_payload = wait_for_quiz_job(response.json()["job_id"])
    questions = job_payload["quiz"]["questions"]
    assert len(questions) == 2
    assert all(question["quality_validation"] is not None for question in questions)
    assert all(question["quality_validation"]["score"] >= 0.5 for question in questions)
