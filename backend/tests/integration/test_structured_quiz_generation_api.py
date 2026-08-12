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


def _first_section_and_concept(client: TestClient, material_id: str) -> tuple[dict[str, object], dict[str, object]]:
    sections_response = client.get(f"/api/v1/materials/{material_id}/sections")
    assert sections_response.status_code == 200
    sections = [
        section
        for section in sections_response.json()["sections"]
        if not section["is_junk"] and section["concepts"]
    ]
    assert sections
    section = sections[0]
    return section, section["concepts"][0]


def _wait_for_structured_quiz(
    client: TestClient,
    wait_for_quiz_job,
    response,
) -> dict[str, object]:
    assert response.status_code == 200
    payload = wait_for_quiz_job(response.json()["job_id"])
    assert payload["status"] in {"completed", "partial"}
    assert payload["quiz"] is not None
    assert payload["quiz"]["questions"]
    return payload


def test_generate_quiz_from_section_stores_source_linked_question_metadata(
    client: TestClient,
    wait_for_quiz_job,
) -> None:
    material_id = _upload_notes(
        client,
        course_id="course-structured-section",
        module_id="module-variables",
        file_name="python-variables.txt",
        body=(
            b"# Variables\n"
            b"Variables store data values. Python assignment uses name = value. "
            b"Variable names are case sensitive. A common trap is confusing assignment with equality."
        ),
    )
    section, _concept = _first_section_and_concept(client, material_id)

    quiz_payload = _wait_for_structured_quiz(
        client,
        wait_for_quiz_job,
        client.post(
            "/api/v1/quiz/generate-from-section",
            json={
                "section_id": section["id"],
                "question_count": 2,
                "question_types": ["mcq", "short_answer"],
                "question_styles": ["definition", "application"],
            },
        ),
    )

    questions = quiz_payload["quiz"]["questions"]
    assert {question["section_id"] for question in questions} == {section["id"]}
    assert {question["material_id"] for question in questions} == {material_id}
    assert {question["course_id"] for question in questions} == {"course-structured-section"}
    assert {question["module_id"] for question in questions} == {"module-variables"}
    assert questions[0]["id"] == questions[0]["question_id"]
    assert questions[0]["quiz_id"] == quiz_payload["job_id"]
    assert questions[0]["source_page"] == section["start_page"]
    assert questions[0]["question_text"] == questions[0]["prompt"]
    assert questions[0]["answer_choices_json"] == questions[0]["options"]
    assert questions[0]["correct_answer"]
    assert questions[0]["explanation"]
    assert "citation" not in questions[0]["explanation"].lower()
    assert questions[0]["source_evidence"]
    assert questions[0]["question_style"] == "definition"
    assert questions[1]["question_style"] == "application"


def test_generate_quiz_from_concept_reuses_concept_and_source_scope(
    client: TestClient,
    wait_for_quiz_job,
) -> None:
    material_id = _upload_notes(
        client,
        course_id="course-structured-concept",
        module_id="module-python",
        file_name="type-conversion.txt",
        body=(
            b"# Type Conversion\n"
            b"Type conversion changes a value from one data type to another. "
            b"Python commonly uses int(), float(), and str() to convert values before expressions use them."
        ),
    )
    section, concept = _first_section_and_concept(client, material_id)

    quiz_payload = _wait_for_structured_quiz(
        client,
        wait_for_quiz_job,
        client.post(
            "/api/v1/quiz/generate-from-concept",
            json={
                "concept_id": concept["id"],
                "question_count": 1,
                "question_types": ["mcq"],
                "question_styles": ["concept_check"],
            },
        ),
    )

    question = quiz_payload["quiz"]["questions"][0]
    assert question["concept_id"] == concept["id"]
    assert question["section_id"] == section["id"]
    assert question["material_id"] == material_id
    assert question["source_page"] == concept["source_page"]
    assert question["source_evidence"]
    assert question["question_style"] == "concept_check"


def test_generate_quiz_from_material_and_module_respect_explicit_scope(
    client: TestClient,
    wait_for_quiz_job,
) -> None:
    material_a = _upload_notes(
        client,
        course_id="course-structured-scope",
        module_id="module-a",
        file_name="variables.txt",
        body=b"# Variables\nVariables store values and assignment uses name = value.",
    )
    _upload_notes(
        client,
        course_id="course-structured-scope",
        module_id="module-b",
        file_name="loops.txt",
        body=b"# Loops\nLoops repeat a block while a condition or sequence still has work.",
    )

    material_quiz = _wait_for_structured_quiz(
        client,
        wait_for_quiz_job,
        client.post(
            "/api/v1/quiz/generate-from-material",
            json={
                "material_id": material_a,
                "question_count": 1,
                "question_types": ["mcq"],
            },
        ),
    )
    assert material_quiz["quiz"]["questions"][0]["material_id"] == material_a
    assert material_quiz["quiz"]["questions"][0]["module_id"] == "module-a"

    module_quiz = _wait_for_structured_quiz(
        client,
        wait_for_quiz_job,
        client.post(
            "/api/v1/quiz/generate-from-module",
            json={
                "course_id": "course-structured-scope",
                "module_id": "module-b",
                "question_count": 1,
                "question_types": ["mcq"],
            },
        ),
    )
    assert module_quiz["quiz"]["questions"][0]["module_id"] == "module-b"


def test_generate_from_missed_questions_and_weak_area_reuses_missed_source(
    client: TestClient,
    wait_for_quiz_job,
) -> None:
    material_id = _upload_notes(
        client,
        course_id="course-structured-missed",
        module_id="module-missed",
        file_name="operators.txt",
        body=(
            b"# Comparison Operators\n"
            b"Comparison operators compare values and return Boolean results. "
            b"Use == to test equality and = to assign a value. The trap is mixing assignment and equality."
        ),
    )
    section, _concept = _first_section_and_concept(client, material_id)

    first_quiz = _wait_for_structured_quiz(
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
    first_question = first_quiz["quiz"]["questions"][0]
    answer_key = first_quiz["partial_results"][0]["answer_key"]
    wrong_option = next(
        option["option_id"]
        for option in first_question["options"]
        if option["option_id"] != answer_key["correct_option_id"]
    )
    grade_response = client.post(
        "/api/v1/quiz/grade",
        json={
            "quiz_id": first_quiz["quiz"]["quiz_id"],
            "answers": [
                {
                    "question_id": first_question["question_id"],
                    "selected_option_id": wrong_option,
                }
            ],
        },
    )
    assert grade_response.status_code == 200
    assert grade_response.json()["wrong_concepts"]

    missed_quiz = _wait_for_structured_quiz(
        client,
        wait_for_quiz_job,
        client.post(
            "/api/v1/quiz/generate-from-missed-questions",
            json={
                "course_id": "course-structured-missed",
                "module_id": "module-missed",
                "quiz_id": first_quiz["quiz"]["quiz_id"],
                "question_ids": [first_question["question_id"]],
                "question_count": 1,
                "question_types": ["mcq"],
            },
        ),
    )
    assert missed_quiz["quiz"]["questions"][0]["section_id"] == section["id"]
    assert missed_quiz["quiz"]["questions"][0]["material_id"] == material_id

    weak_area = grade_response.json()["wrong_concepts"][0]
    weak_quiz = _wait_for_structured_quiz(
        client,
        wait_for_quiz_job,
        client.post(
            "/api/v1/quiz/generate-from-weak-area",
            json={
                "course_id": "course-structured-missed",
                "module_id": "module-missed",
                "weak_area_id": weak_area,
                "question_count": 1,
                "question_types": ["mcq"],
            },
        ),
    )
    assert weak_quiz["quiz"]["questions"][0]["section_id"] == section["id"]
