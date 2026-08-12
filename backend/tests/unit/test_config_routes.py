from fastapi.testclient import TestClient


def test_config_validate_and_health_round_trip(client: TestClient) -> None:
    response = client.post(
        "/api/v1/config/validate",
        json={
            "provider": "openai",
            "model": "gpt-4.1-mini",
            "api_key": "",
            "demo_mode": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["can_proceed"] is True
    assert response.json()["status"] == "demo_ready"

    health_response = client.get("/api/v1/config/health")

    assert health_response.status_code == 200
    assert health_response.json() == {
        "ok": True,
        "status": "demo_mode",
        "config_present": True,
    }


def test_config_validate_accepts_parser_profile(client: TestClient) -> None:
    response = client.post(
        "/api/v1/config/validate?profile=parser",
        json={
            "provider": "openai",
            "model": "gpt-5.4-parser",
            "api_key": "",
            "demo_mode": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["can_proceed"] is True

    runtime_response = client.get("/api/v1/config/runtime")

    assert runtime_response.status_code == 200
    assert runtime_response.json()["parser_config"]["model"] == "gpt-5.4-parser"
