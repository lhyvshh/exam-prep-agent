from fastapi.testclient import TestClient


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


def test_course_library_groups_root_and_module_materials(client: TestClient) -> None:
    course = _create_course(client, code="101", name="Foundations")
    module = _create_module(
        client,
        course_id=course["course_id"],
        module_number="Module 3",
        display_name="Optimization",
    )

    root_upload = client.post(
        "/api/v1/materials/upload",
        data={"course_id": course["course_id"]},
        files={
            "file": (
                "course_overview.txt",
                b"# Course Overview\nThis course covers core machine learning concepts.",
                "text/plain",
            )
        },
    )
    assert root_upload.status_code == 201

    module_upload = client.post(
        "/api/v1/materials/upload",
        data={"course_id": course["course_id"], "module_id": module["module_id"]},
        files={
            "file": (
                "gradient_notes.txt",
                b"# Gradient Descent Basics\nGradient descent updates model parameters using the learning rate.",
                "text/plain",
            )
        },
    )
    assert module_upload.status_code == 201

    library_response = client.get("/api/v1/courses/library")
    assert library_response.status_code == 200
    library_payload = library_response.json()

    course_item = next(
        item
        for item in library_payload["courses"]
        if item["course"]["course_id"] == course["course_id"]
    )
    assert len(course_item["root_materials"]) == 1
    assert course_item["root_materials"][0]["file_name"] == "course_overview.txt"
    assert len(course_item["modules"]) == 1
    assert course_item["modules"][0]["module"]["module_id"] == module["module_id"]
    assert len(course_item["modules"][0]["materials"]) == 1
    assert course_item["modules"][0]["materials"][0]["file_name"] == "gradient_notes.txt"

    scoped_materials = client.get(
        f"/api/v1/materials/course/{course['course_id']}?module_id={module['module_id']}"
    )
    assert scoped_materials.status_code == 200
    scoped_payload = scoped_materials.json()
    assert len(scoped_payload["records"]) == 1
    assert scoped_payload["records"][0]["module_id"] == module["module_id"]
    assert scoped_payload["records"][0]["file_name"] == "gradient_notes.txt"


def test_module_scoped_quiz_generation_excludes_other_modules(
    client: TestClient,
    wait_for_quiz_job,
) -> None:
    course = _create_course(client, code="201", name="Advanced Topics")
    module_a = _create_module(
        client,
        course_id=course["course_id"],
        module_number="Module 1",
        display_name="Optimization",
    )
    module_b = _create_module(
        client,
        course_id=course["course_id"],
        module_number="Module 2",
        display_name="Portfolio Theory",
    )

    upload_a = client.post(
        "/api/v1/materials/upload",
        data={"course_id": course["course_id"], "module_id": module_a["module_id"]},
        files={
            "file": (
                "optimization.txt",
                b"# Gradient Descent Basics\nGradient descent updates parameters with the learning rate.",
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
                "portfolio.txt",
                b"# Portfolio Diversification\nDiversification reduces unsystematic risk across assets.",
                "text/plain",
            )
        },
    )
    assert upload_b.status_code == 201

    wrong_scope_response = client.post(
        "/api/v1/quiz/generate",
        json={
            "course_id": course["course_id"],
            "module_id": module_a["module_id"],
            "query": "diversification unsystematic risk",
            "question_count": 1,
            "question_types": ["mcq"],
            "retrieval_top_k": 4,
        },
    )
    assert wrong_scope_response.status_code == 200
    wrong_scope_question = wait_for_quiz_job(wrong_scope_response.json()["job_id"])["quiz"]["questions"][0]
    assert wrong_scope_question["citations"][0]["section_title"] == "Gradient Descent Basics"

    right_scope_response = client.post(
        "/api/v1/quiz/generate",
        json={
            "course_id": course["course_id"],
            "module_id": module_b["module_id"],
            "query": "diversification unsystematic risk",
            "question_count": 1,
            "question_types": ["mcq"],
            "retrieval_top_k": 4,
        },
    )
    assert right_scope_response.status_code == 200
    question = wait_for_quiz_job(right_scope_response.json()["job_id"])["quiz"]["questions"][0]
    assert question["citations"][0]["section_title"] == "Portfolio Diversification"


def test_dashboard_and_wrong_question_filters_respect_selected_module(
    client: TestClient,
    wait_for_quiz_job,
) -> None:
    course = _create_course(client, code="301", name="Applied ML")
    module_a = _create_module(
        client,
        course_id=course["course_id"],
        module_number="Module 1",
        display_name="Optimization",
    )
    module_b = _create_module(
        client,
        course_id=course["course_id"],
        module_number="Module 2",
        display_name="Risk",
    )

    upload_a = client.post(
        "/api/v1/materials/upload",
        data={"course_id": course["course_id"], "module_id": module_a["module_id"]},
        files={
            "file": (
                "optimization.txt",
                b"# Gradient Descent Basics\nGradient descent updates parameters with the learning rate.",
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
                "risk.txt",
                b"# Portfolio Diversification\nDiversification reduces unsystematic risk across assets.",
                "text/plain",
            )
        },
    )
    assert upload_b.status_code == 201

    quiz_a = client.post(
        "/api/v1/quiz/generate",
        json={
            "course_id": course["course_id"],
            "module_id": module_a["module_id"],
            "query": "learning rate",
            "question_count": 1,
            "question_types": ["mcq"],
            "retrieval_top_k": 4,
        },
    )
    assert quiz_a.status_code == 200
    quiz_a_payload = wait_for_quiz_job(quiz_a.json()["job_id"])["quiz"]

    grade_a = client.post(
        "/api/v1/quiz/grade",
        json={
            "quiz_id": quiz_a_payload["quiz_id"],
            "answers": [
                {
                    "question_id": quiz_a_payload["questions"][0]["question_id"],
                    "selected_option_id": "Z",
                }
            ],
        },
    )
    assert grade_a.status_code == 200

    quiz_b = client.post(
        "/api/v1/quiz/generate",
        json={
            "course_id": course["course_id"],
            "module_id": module_b["module_id"],
            "query": "diversification",
            "question_count": 1,
            "question_types": ["mcq"],
            "retrieval_top_k": 4,
        },
    )
    assert quiz_b.status_code == 200
    quiz_b_payload = wait_for_quiz_job(quiz_b.json()["job_id"])["quiz"]

    grade_b = client.post(
        "/api/v1/quiz/grade",
        json={
            "quiz_id": quiz_b_payload["quiz_id"],
            "answers": [
                {
                    "question_id": quiz_b_payload["questions"][0]["question_id"],
                    "selected_option_id": "Z",
                }
            ],
        },
    )
    assert grade_b.status_code == 200

    dashboard_a = client.get(
        f"/api/v1/dashboard/{course['course_id']}?module_id={module_a['module_id']}"
    )
    assert dashboard_a.status_code == 200
    dashboard_payload = dashboard_a.json()
    assert dashboard_payload["module_id"] == module_a["module_id"]
    assert dashboard_payload["material_count"] == 1
    assert len(dashboard_payload["wrong_questions"]) == 1
    assert dashboard_payload["wrong_questions"][0]["citations"][0]["section_title"] == "Gradient Descent Basics"

    wrong_questions_b = client.get(
        f"/api/v1/dashboard/{course['course_id']}/wrong-questions?module_id={module_b['module_id']}"
    )
    assert wrong_questions_b.status_code == 200
    wrong_questions_payload = wrong_questions_b.json()
    assert len(wrong_questions_payload) == 1
    assert wrong_questions_payload[0]["citations"][0]["section_title"] == "Portfolio Diversification"


def test_deleting_active_module_falls_back_to_course_scope(client: TestClient) -> None:
    course = _create_course(client, code="401", name="Systems")
    module = _create_module(
        client,
        course_id=course["course_id"],
        module_number="Module 1",
        display_name="Foundations",
    )

    set_workflow = client.post(
        "/api/v1/workflow/current",
        json={
            "course_id": course["course_id"],
            "module_id": module["module_id"],
        },
    )
    assert set_workflow.status_code == 200
    assert set_workflow.json()["module_id"] == module["module_id"]

    delete_response = client.delete(f"/api/v1/courses/modules/{module['module_id']}")
    assert delete_response.status_code == 200
    payload = delete_response.json()
    assert payload["deleted"] is True
    assert payload["fallback_course_id"] == course["course_id"]
    assert payload["fallback_module_id"] is None

    workflow_response = client.get("/api/v1/workflow/current")
    assert workflow_response.status_code == 200
    workflow_payload = workflow_response.json()
    assert workflow_payload["course_id"] == course["course_id"]
    assert workflow_payload["module_id"] is None


def test_deleting_active_course_clears_scope_when_no_other_course_exists(client: TestClient) -> None:
    course = _create_course(client, code="402", name="Single Course")

    set_workflow = client.post(
        "/api/v1/workflow/current",
        json={
            "course_id": course["course_id"],
            "module_id": None,
        },
    )
    assert set_workflow.status_code == 200

    delete_response = client.delete(f"/api/v1/courses/{course['course_id']}")
    assert delete_response.status_code == 200
    payload = delete_response.json()
    assert payload["deleted"] is True
    assert payload["fallback_course_id"] is None
    assert payload["fallback_module_id"] is None

    workflow_response = client.get("/api/v1/workflow/current")
    assert workflow_response.status_code == 200
    workflow_payload = workflow_response.json()
    assert workflow_payload["course_id"] is None
    assert workflow_payload["module_id"] is None
