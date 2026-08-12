import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from exam_prep.core.config import Settings
from exam_prep.main import create_app


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return Settings(
        app_name="Exam Prep Agent Test",
        app_env="test",
        debug=False,
        demo_mode=True,
        sqlite_path=tmp_path / "test.sqlite3",
        material_storage_path=tmp_path / "materials",
        default_llm_provider="openai",
        default_llm_model="gpt-4.1-mini",
        llm_api_key=None,
        enable_web_search=False,
        frontend_origin="http://localhost:3000",
    )


@pytest.fixture()
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture()
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def wait_for_quiz_job(client: TestClient) -> Callable[[str], dict[str, object]]:
    def _wait(job_id: str) -> dict[str, object]:
        for _ in range(60):
            response = client.get(f"/api/v1/quiz/jobs/{job_id}")
            assert response.status_code == 200
            payload = response.json()
            if payload["status"] not in {"queued", "running"}:
                return payload
            time.sleep(0.05)
        raise AssertionError(f"Quiz generation job {job_id} did not finish in time.")

    return _wait
