import json

from fastapi.testclient import TestClient

from exam_prep.llm.models import LLMResponse


def test_live_provider_and_persistent_material_workflow_smoke(
    client: TestClient,
    monkeypatch,
    wait_for_quiz_job,
) -> None:
    provider_calls: list[str] = []

    def fake_generate(self, request):  # type: ignore[no-untyped-def]
        provider_calls.append(request.user_prompt)
        if "Reply with OK." in request.user_prompt or "Return OK." in request.user_prompt:
            return LLMResponse(model_name=request.model_name, raw_text="OK", provider_name="nvidia")
        if "Create one multiple-choice exam-style question" in request.user_prompt:
            return LLMResponse(
                model_name=request.model_name,
                raw_text=json.dumps(
                    {
                        "prompt": "What best describes gradient descent?",
                        "correct_answer": "Gradient descent updates parameters using the learning rate.",
                        "rationale": "Gradient descent is defined in the uploaded notes.",
                        "options": [
                            {
                                "option_id": "A",
                                "text": "Gradient descent updates parameters using the learning rate."
                            },
                            {"option_id": "B", "text": "Gradient descent removes all model parameters."},
                            {"option_id": "C", "text": "Gradient descent ignores the objective function."},
                            {"option_id": "D", "text": "Gradient descent guarantees zero loss in one step."},
                        ],
                        "correct_option_id": "A",
                    }
                ),
                provider_name="nvidia",
            )
        raise AssertionError(f"Unexpected provider prompt: {request.user_prompt}")

    monkeypatch.setattr(
        "exam_prep.llm.nvidia.NvidiaOpenAICompatibleClient.generate",
        fake_generate,
    )

    validate_response = client.post(
        "/api/v1/config/validate",
        json={
            "provider": "nvidia",
            "model": "meta/llama-3.1-70b-instruct",
            "api_key": "nvapi-test-key",
            "demo_mode": False,
        },
    )
    assert validate_response.status_code == 200
    assert validate_response.json()["status"] == "valid"

    create_course_response = client.post(
        "/api/v1/courses",
        json={
            "course_code": "LIVE",
            "display_name": "Live Course",
            "description": "Smoke test course",
        },
    )
    assert create_course_response.status_code == 201
    course_id = create_course_response.json()["course_id"]

    upload_response = client.post(
        "/api/v1/materials/upload",
        data={"course_id": course_id},
        files={
            "file": (
                "gradient.txt",
                b"# Gradient Descent Basics\nGradient descent updates parameters using the learning rate.",
                "text/plain",
            )
        },
    )
    assert upload_response.status_code == 201
    material_id = upload_response.json()["record"]["material_id"]

    set_workflow_response = client.post(
        "/api/v1/workflow/current",
        json={
            "course_id": course_id,
            "module_id": None,
        },
    )
    assert set_workflow_response.status_code == 200

    workflow_response = client.get("/api/v1/workflow/current")
    assert workflow_response.status_code == 200
    assert workflow_response.json()["course_id"] == course_id
    assert workflow_response.json()["material_count"] == 1

    materials_response = client.get(f"/api/v1/materials/course/{course_id}")
    assert materials_response.status_code == 200
    assert materials_response.json()["records"][0]["material_id"] == material_id
    assert materials_response.json()["sections"][0]["section_title"] == "Gradient Descent Basics"

    dashboard_response = client.get(f"/api/v1/dashboard/{course_id}")
    assert dashboard_response.status_code == 200
    assert dashboard_response.json()["material_count"] == 1

    quiz_response = client.post(
        "/api/v1/quiz/generate",
        json={
            "course_id": course_id,
            "module_id": None,
            "query": "gradient descent learning rate",
            "question_count": 1,
            "question_types": ["mcq"],
            "retrieval_top_k": 3,
        },
    )
    assert quiz_response.status_code == 200
    quiz_payload = wait_for_quiz_job(quiz_response.json()["job_id"])["quiz"]
    assert "gradient descent" in quiz_payload["questions"][0]["prompt"].lower()
    assert quiz_payload["questions"][0]["citations"][0]["citation_label"] == "gradient.txt | Gradient Descent Basics"

    grade_response = client.post(
        "/api/v1/quiz/grade",
        json={
            "quiz_id": quiz_payload["quiz_id"],
            "answers": [{"question_id": quiz_payload["questions"][0]["question_id"], "selected_option_id": "A"}],
        },
    )
    assert grade_response.status_code == 200
    assert grade_response.json()["results"][0]["explanation"].startswith(
        "Correct."
    )

    assert any("Reply with OK." in prompt or "Return OK." in prompt for prompt in provider_calls)
    assert any("Create one multiple-choice exam-style question" in prompt for prompt in provider_calls)
    assert not any("Return JSON with a single key: explanation." in prompt for prompt in provider_calls)
