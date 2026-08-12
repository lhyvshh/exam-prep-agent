from fastapi.testclient import TestClient

from exam_prep.core.config import Settings
from exam_prep.main import create_app


def test_health_preflight_allows_localhost_dev_ports(client: TestClient) -> None:
    response = client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:3001",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3001"


def test_health_preflight_allows_loopback_dev_ports(client: TestClient) -> None:
    response = client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://127.0.0.1:3002",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:3002"


def test_production_cors_only_allows_configured_frontend(settings: Settings) -> None:
    production = settings.model_copy(
        update={
            "app_env": "production",
            "frontend_origin": "https://study.example.com",
        }
    )
    with TestClient(create_app(production)) as client:
        local_response = client.options(
            "/api/v1/health",
            headers={
                "Origin": "http://localhost:3001",
                "Access-Control-Request-Method": "GET",
            },
        )
        configured_response = client.options(
            "/api/v1/health",
            headers={
                "Origin": "https://study.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert local_response.status_code == 400
    assert "access-control-allow-origin" not in local_response.headers
    assert configured_response.status_code == 200
    assert configured_response.headers["access-control-allow-origin"] == "https://study.example.com"
