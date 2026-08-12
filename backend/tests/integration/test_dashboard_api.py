from pathlib import Path

from fastapi.testclient import TestClient


def test_dashboard_summary_aggregates_course_activity(
    client: TestClient,
    wait_for_quiz_job,
) -> None:
    fixture_dir = Path("backend/tests/fixtures/sample_course")

    upload_response = client.post(
        "/api/v1/materials/upload",
        data={"course_id": "course-dashboard"},
        files={
            "file": (
                "gradient_descent_section.txt",
                (fixture_dir / "gradient_descent_section.txt").read_bytes(),
                "text/plain",
            )
        },
    )
    assert upload_response.status_code == 201

    quiz_response = client.post(
        "/api/v1/quiz/generate",
        json={
            "course_id": "course-dashboard",
            "query": "gradient descent learning rate",
            "question_count": 2,
            "question_types": ["mcq", "short_answer"],
        },
    )
    assert quiz_response.status_code == 200
    quiz = wait_for_quiz_job(quiz_response.json()["job_id"])["quiz"]

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

    remediation_response = client.post(
        "/api/v1/quiz/remediation",
        json={
            "course_id": "course-dashboard",
            "concepts": [],
            "default_question_count": 3,
        },
    )
    assert remediation_response.status_code == 200

    style_example = (fixture_dir / "mock_exam_style.txt").read_text(encoding="utf-8")
    exam_response = client.post(
        "/api/v1/exams/generate",
        json={
            "course_id": "course-dashboard",
            "blueprint": {
                "title": "Dashboard Mock Exam",
                "instructions": "Answer everything.",
                "topic_coverage": [
                    {
                        "topic": "Gradient Descent",
                        "question_count": 1,
                        "question_types": ["mcq"],
                    }
                ],
                "target_difficulty": 0.55,
                "style_example": style_example,
            },
        },
    )
    assert exam_response.status_code == 200

    dashboard_response = client.get("/api/v1/dashboard/course-dashboard")

    assert dashboard_response.status_code == 200
    payload = dashboard_response.json()
    assert payload["material_count"] == 1
    assert payload["section_count"] >= 1
    assert payload["quizzes"][0]["wrong_question_count"] == 2
    assert payload["mock_exams"][0]["title"] == "Dashboard Mock Exam"
    assert payload["mock_exams"][0]["created_at"]
    assert payload["remediation_history"][0]["concept"] == "Gradient Descent"
    assert payload["wrong_questions"]
    assert payload["mastery_by_concept"]["Gradient Descent"] == 0.0
