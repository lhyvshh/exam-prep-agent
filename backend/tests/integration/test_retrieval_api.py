from pathlib import Path

from fastapi.testclient import TestClient


def test_retrieval_query_returns_relevant_chunk_with_citation(client: TestClient) -> None:
    fixture_dir = Path("backend/tests/fixtures/sample_course")

    for file_name in ("optimization_notes.txt", "portfolio_basics.txt"):
        response = client.post(
            "/api/v1/materials/upload",
            data={"course_id": "course-demo"},
            files={
                "file": (
                    file_name,
                    (fixture_dir / file_name).read_bytes(),
                    "text/plain",
                )
            },
        )
        assert response.status_code == 201

    query_response = client.post(
        "/api/v1/retrieval/query",
        json={
            "course_id": "course-demo",
            "query": "How does gradient descent update parameters?",
            "top_k": 2,
        },
    )

    assert query_response.status_code == 200
    payload = query_response.json()
    assert payload["hits"]
    top_hit = payload["hits"][0]
    assert top_hit["chunk"]["file_name"] == "optimization_notes.txt"
    assert "Gradient descent" in top_hit["chunk"]["text"]
    assert "optimization_notes.txt" in top_hit["chunk"]["citation_label"]


def test_retrieval_query_returns_not_found_for_empty_course(client: TestClient) -> None:
    query_response = client.post(
        "/api/v1/retrieval/query",
        json={
            "course_id": "missing-course",
            "query": "efficient frontier",
            "top_k": 3,
        },
    )

    assert query_response.status_code == 404
    assert "No parsed materials found" in query_response.json()["detail"]
