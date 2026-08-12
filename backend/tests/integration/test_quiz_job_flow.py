import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from exam_prep.core.exceptions import LLMTransportError
from exam_prep.schemas.config import LLMProvider, UserLLMConfig
from exam_prep.services.quiz_service import QuizService


def test_quiz_job_exposes_partial_results_while_running(
    app: FastAPI,
    monkeypatch,
) -> None:
    original_generate_question_for_hit = QuizService.generate_question_for_hit

    def slow_second_question(self, *, sequence_index, **kwargs):  # type: ignore[no-untyped-def]
        if sequence_index == 2:
            time.sleep(0.2)
        return original_generate_question_for_hit(self, sequence_index=sequence_index, **kwargs)

    monkeypatch.setattr(QuizService, "generate_question_for_hit", slow_second_question)

    with TestClient(app) as client:
        upload_response = client.post(
            "/api/v1/materials/upload",
            data={"course_id": "course-partial"},
            files={
                "file": (
                    "notes.txt",
                    (
                        b"# Gradient Descent Basics\nGradient descent updates parameters using the learning rate.\n"
                        b"# Worked Example\nA smaller learning rate takes more steps but can improve stability."
                    ),
                    "text/plain",
                )
            },
        )
        assert upload_response.status_code == 201

        generate_response = client.post(
            "/api/v1/quiz/generate",
            json={
                "course_id": "course-partial",
                "query": "learning rate",
                "question_count": 2,
                "question_types": ["mcq", "mcq"],
                "retrieval_top_k": 4,
            },
        )
        assert generate_response.status_code == 200
        job_id = generate_response.json()["job_id"]

        time.sleep(0.05)
        status_response = client.get(f"/api/v1/quiz/jobs/{job_id}")
        assert status_response.status_code == 200
        payload = status_response.json()
        assert payload["status"] in {"running", "completed", "partial"}
        assert payload["progress"]["completed_questions"] >= 1
        assert len(payload["partial_results"]) >= 1


def test_quiz_job_timeout_budget_yields_partial_status(
    app: FastAPI,
    monkeypatch,
) -> None:
    monkeypatch.setattr(app.state.quiz_job_runner, "_job_budget_seconds", lambda question_count: 0)

    with TestClient(app) as client:
        upload_response = client.post(
            "/api/v1/materials/upload",
            data={"course_id": "course-budget"},
            files={
                "file": (
                    "notes.txt",
                    (
                        b"# Gradient Descent Basics\nGradient descent updates parameters using the learning rate.\n"
                        b"# Worked Example\nA smaller learning rate takes more steps but can improve stability."
                    ),
                    "text/plain",
                )
            },
        )
        assert upload_response.status_code == 201

        generate_response = client.post(
            "/api/v1/quiz/generate",
            json={
                "course_id": "course-budget",
                "query": "learning rate",
                "question_count": 2,
                "question_types": ["mcq", "mcq"],
                "retrieval_top_k": 4,
            },
        )
        assert generate_response.status_code == 200
        job_payload = _wait_for_job(client, generate_response.json()["job_id"])

        assert job_payload["status"] == "partial"
        assert job_payload["progress"]["fallback_questions"] == 2
        assert "budget" in (job_payload["error_summary"] or "").lower()


def test_quiz_job_transport_timeout_falls_back_without_route_failure(
    app: FastAPI,
) -> None:
    class AlwaysTimeoutClient:
        def generate(self, request):  # type: ignore[no-untyped-def]
            raise LLMTransportError("Synthetic transport timeout.")

    class StaticRegistry:
        def __init__(self) -> None:
            self.client = AlwaysTimeoutClient()
            self.calls = 0

        def get_or_create_for_profile(self, config, *, profile):  # type: ignore[no-untyped-def]
            del config, profile
            self.calls += 1
            return self.client

        def close_all(self) -> None:
            return None

    static_registry = StaticRegistry()
    app.state.llm_client_registry = static_registry
    app.state.quiz_job_runner.llm_client_registry = static_registry
    app.state.config_store.save(
        UserLLMConfig(
            provider=LLMProvider.NVIDIA,
            model="meta/llama-3.1-70b-instruct",
            api_key="nvapi-test-key",
            demo_mode=False,
        )
    )

    with TestClient(app) as client:
        upload_response = client.post(
            "/api/v1/materials/upload",
            data={"course_id": "course-live-timeout"},
            files={
                "file": (
                    "notes.txt",
                    b"# Gradient Descent Basics\nGradient descent updates parameters using the learning rate.",
                    "text/plain",
                )
            },
        )
        assert upload_response.status_code == 201

        generate_response = client.post(
            "/api/v1/quiz/generate",
            json={
                "course_id": "course-live-timeout",
                "query": "learning rate",
                "question_count": 2,
                "question_types": ["mcq", "mcq"],
                "retrieval_top_k": 4,
            },
        )
        assert generate_response.status_code == 200
        job_payload = _wait_for_job(client, generate_response.json()["job_id"])

        assert job_payload["status"] == "completed"
        assert job_payload["progress"]["fallback_questions"] == 2
        assert static_registry.calls == 1


def test_quiz_job_dedupe_key_changes_when_settings_change(
    client: TestClient,
) -> None:
    upload_response = client.post(
        "/api/v1/materials/upload",
        data={"course_id": "course-dedupe-variant"},
        files={
            "file": (
                "notes.txt",
                b"# Gradient Descent Basics\nGradient descent updates parameters using the learning rate.",
                "text/plain",
            )
        },
    )
    assert upload_response.status_code == 201

    base_payload = {
        "course_id": "course-dedupe-variant",
        "query": "learning rate",
        "question_types": ["mcq"],
        "retrieval_top_k": 4,
        "selected_source_ids": [],
    }

    first = client.post("/api/v1/quiz/generate", json={**base_payload, "question_count": 1})
    second = client.post("/api/v1/quiz/generate", json={**base_payload, "question_count": 2})

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["job_id"] != second.json()["job_id"]


def _wait_for_job(client: TestClient, job_id: str) -> dict[str, object]:
    for _ in range(60):
        response = client.get(f"/api/v1/quiz/jobs/{job_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] not in {"queued", "running"}:
            return payload
        time.sleep(0.05)
    raise AssertionError(f"Quiz generation job {job_id} did not finish in time.")
