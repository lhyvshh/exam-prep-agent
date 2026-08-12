from pathlib import Path

from fastapi.testclient import TestClient


def _correct_option_id(question: dict) -> str:
    correct_answer = str(question.get("correct_answer") or "").strip().lower()
    positive_phrases = (
        "opposite the gradient",
        "size of each update step",
        "diversification reduces",
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


def _create_course(client: TestClient, *, code: str, name: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/courses",
        json={
            "course_code": code,
            "display_name": name,
            "description": f"{name} description",
        },
    )
    assert response.status_code == 201
    return response.json()


def _create_module(
    client: TestClient,
    *,
    course_id: str,
    module_number: str,
    display_name: str,
) -> dict[str, str]:
    response = client.post(
        "/api/v1/courses/modules",
        json={
            "course_id": course_id,
            "module_number": module_number,
            "display_name": display_name,
            "description": f"{display_name} description",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_mock_exam_generation_and_grading_happy_path(client: TestClient) -> None:
    fixture_dir = Path("backend/tests/fixtures/sample_course")
    for file_name in ("optimization_notes.txt", "portfolio_basics.txt"):
        upload_response = client.post(
            "/api/v1/materials/upload",
            data={"course_id": "course-exam"},
            files={
                "file": (
                    file_name,
                    (fixture_dir / file_name).read_bytes(),
                    "text/plain",
                )
            },
        )
        assert upload_response.status_code == 201

    style_example = (fixture_dir / "mock_exam_style.txt").read_text(encoding="utf-8")
    generate_response = client.post(
        "/api/v1/exams/generate",
        json={
            "course_id": "course-exam",
            "blueprint": {
                "title": "Finance and Optimization Mock",
                "instructions": "Answer all questions.",
                "topic_coverage": [
                    {
                        "topic": "Gradient Descent",
                        "question_count": 2,
                        "question_types": ["mcq", "short_answer"],
                    },
                    {
                        "topic": "Sharpe Ratio",
                        "question_count": 1,
                        "question_types": ["mcq"],
                    },
                ],
                "target_difficulty": 0.6,
                "style_example": style_example,
            },
            "retrieval_top_k": 6,
        },
    )

    assert generate_response.status_code == 200
    exam = generate_response.json()["exam"]
    assert len(exam["questions"]) == 3
    assert exam["blueprint"]["target_difficulty"] == 0.6
    assert exam["created_at"]

    question_one = exam["questions"][0]
    question_two = exam["questions"][1]
    question_three = exam["questions"][2]
    assert all(question["question_type"] == "mcq" for question in exam["questions"])

    grade_response = client.post(
        "/api/v1/exams/grade",
        json={
            "exam_id": exam["exam_id"],
            "answers": [
                {
                    "question_id": question_one["question_id"],
                    "selected_option_id": _correct_option_id(question_one),
                },
                {
                    "question_id": question_two["question_id"],
                    "selected_option_id": _correct_option_id(question_two),
                },
                {
                    "question_id": question_three["question_id"],
                    "selected_option_id": _correct_option_id(question_three),
                },
            ],
        },
    )

    assert grade_response.status_code == 200
    payload = grade_response.json()
    assert payload["overall_score"] == 100.0
    assert payload["completed_at"]
    assert len(payload["analytics_by_concept"]) >= 1
    assert "optimization_notes.txt" in payload["results"][0]["citations"][0]["citation_label"]

    review_response = client.get(f"/api/v1/exams/{exam['exam_id']}/review")
    assert review_response.status_code == 200
    review_payload = review_response.json()
    assert review_payload["exam"]["exam_id"] == exam["exam_id"]
    assert review_payload["grade_result"]["overall_score"] == 100.0


def test_mock_exam_generation_respects_selected_multiple_modules(client: TestClient) -> None:
    course = _create_course(client, code="401", name="Programming Foundations")
    module_a = _create_module(
        client,
        course_id=course["course_id"],
        module_number="Module 1",
        display_name="Python Basics",
    )
    module_b = _create_module(
        client,
        course_id=course["course_id"],
        module_number="Module 2",
        display_name="Control Flow",
    )
    module_c = _create_module(
        client,
        course_id=course["course_id"],
        module_number="Module 3",
        display_name="Portfolio Theory",
    )

    upload_a = client.post(
        "/api/v1/materials/upload",
        data={"course_id": course["course_id"], "module_id": module_a["module_id"]},
        files={
            "file": (
                "python_basics.txt",
                b"# Variables\nVariables store values in Python.\n# Type Conversion\nUse int(), float(), and str() to change data types.",
                "text/plain",
            )
        },
    )
    assert upload_a.status_code == 201

    upload_b = client.post(
        "/api/v1/materials/upload",
        data={"course_id": course["course_id"], "module_id": module_b["module_id"]},
        files={
            "file": (
                "control_flow.txt",
                b"# Conditionals\nConditionals use if, elif, and else to branch logic.",
                "text/plain",
            )
        },
    )
    assert upload_b.status_code == 201

    upload_c = client.post(
        "/api/v1/materials/upload",
        data={"course_id": course["course_id"], "module_id": module_c["module_id"]},
        files={
            "file": (
                "portfolio.txt",
                b"# Sharpe Ratio\nSharpe ratio measures excess return per unit of risk.",
                "text/plain",
            )
        },
    )
    assert upload_c.status_code == 201

    generate_response = client.post(
        "/api/v1/exams/generate",
        json={
            "course_id": course["course_id"],
            "module_ids": [module_a["module_id"], module_b["module_id"]],
            "blueprint": {
                "title": "Python Midterm",
                "instructions": "Answer all questions.",
                "topic_coverage": [
                    {
                        "topic": "Type Conversion",
                        "question_count": 1,
                        "question_types": ["mcq"],
                    },
                    {
                        "topic": "Conditionals",
                        "question_count": 1,
                        "question_types": ["short_answer"],
                    },
                ],
                "target_difficulty": 0.55,
                "style_example": "Answer clearly in exam style.",
            },
            "retrieval_top_k": 6,
        },
    )

    assert generate_response.status_code == 200
    exam = generate_response.json()["exam"]
    assert exam["module_id"] is None
    assert set(exam["module_ids"]) == {module_a["module_id"], module_b["module_id"]}
    citation_titles = {
        question["citations"][0]["section_title"]
        for question in exam["questions"]
        if question["citations"]
    }
    assert "Type Conversion" in citation_titles
    assert "Conditionals" in citation_titles
    assert "Sharpe Ratio" not in citation_titles

    review_response = client.get(f"/api/v1/exams/{exam['exam_id']}/review")
    assert review_response.status_code == 200
    review_payload = review_response.json()
    assert set(review_payload["exam"]["module_ids"]) == {
        module_a["module_id"],
        module_b["module_id"],
    }

    dashboard_a = client.get(
        f"/api/v1/dashboard/{course['course_id']}?module_id={module_a['module_id']}"
    )
    assert dashboard_a.status_code == 200
    assert dashboard_a.json()["mock_exams"][0]["exam_id"] == exam["exam_id"]

    dashboard_c = client.get(
        f"/api/v1/dashboard/{course['course_id']}?module_id={module_c['module_id']}"
    )
    assert dashboard_c.status_code == 200
    assert dashboard_c.json()["mock_exams"] == []
