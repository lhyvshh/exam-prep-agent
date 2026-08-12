from pathlib import Path

from fastapi.testclient import TestClient


def test_remediation_suppresses_duplicates_across_retry_history(
    client: TestClient,
    wait_for_quiz_job,
) -> None:
    fixture_dir = Path("backend/tests/fixtures/sample_course")
    upload_response = client.post(
        "/api/v1/materials/upload",
        data={"course_id": "course-remediation"},
        files={
            "file": (
                "gradient_descent_section.txt",
                (fixture_dir / "gradient_descent_section.txt").read_bytes(),
                "text/plain",
            )
        },
    )
    assert upload_response.status_code == 201

    generate_response = client.post(
        "/api/v1/quiz/generate",
        json={
            "course_id": "course-remediation",
            "query": "gradient descent learning rate",
            "question_count": 2,
            "question_types": ["mcq", "short_answer"],
            "retrieval_top_k": 5,
        },
    )
    assert generate_response.status_code == 200
    quiz = wait_for_quiz_job(generate_response.json()["job_id"])["quiz"]

    grade_response = client.post(
        "/api/v1/quiz/grade",
        json={
            "quiz_id": quiz["quiz_id"],
            "answers": [
                {
                    "question_id": quiz["questions"][0]["question_id"],
                    "selected_option_id": "Z",
                },
                {
                    "question_id": quiz["questions"][1]["question_id"],
                    "answer_text": "",
                },
            ],
        },
    )
    assert grade_response.status_code == 200
    assert "Gradient Descent" in grade_response.json()["wrong_concepts"]

    first_remediation = client.post(
        "/api/v1/quiz/remediation",
        json={
            "course_id": "course-remediation",
            "concepts": [],
            "default_question_count": 3,
        },
    )
    assert first_remediation.status_code == 200

    second_remediation = client.post(
        "/api/v1/quiz/remediation",
        json={
            "course_id": "course-remediation",
            "concepts": [],
            "default_question_count": 3,
        },
    )
    assert second_remediation.status_code == 200

    first_prompts = {
        question["prompt"]
        for bundle in first_remediation.json()["concept_bundles"]
        for question in bundle["questions"]
    }
    second_prompts = {
        question["prompt"]
        for bundle in second_remediation.json()["concept_bundles"]
        for question in bundle["questions"]
    }

    assert len(first_prompts) == 3
    assert len(second_prompts) == 3
    assert first_prompts.isdisjoint(second_prompts)


def test_remediation_returns_not_found_for_empty_wrong_concepts(client: TestClient) -> None:
    response = client.post(
        "/api/v1/quiz/remediation",
        json={
            "course_id": "course-without-misses",
            "concepts": [],
            "default_question_count": 3,
        },
    )

    assert response.status_code == 404
    assert "No wrong concepts available for remediation" in response.json()["detail"]
