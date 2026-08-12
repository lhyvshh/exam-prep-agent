from fastapi.testclient import TestClient


def test_source_resolver_and_agent_recommendations_are_persisted(client: TestClient) -> None:
    upload_response = client.post(
        "/api/v1/materials/upload",
        data={"course_id": "course-agentic"},
        files={
            "file": (
                "variables.txt",
                (
                    b"# Python Variables\n"
                    b"A variable stores a value under a name. Python variable names are case sensitive. "
                    b"Students should remember that name = value assigns a value, while invalid keywords "
                    b"cannot be used as variable names."
                ),
                "text/plain",
            )
        },
    )
    assert upload_response.status_code == 201
    material_id = upload_response.json()["record"]["material_id"]

    study_response = client.get(f"/api/v1/materials/{material_id}/study")
    assert study_response.status_code == 200
    section = study_response.json()["sections"][0]
    source_id = section["source_ids"][0]

    source_response = client.post(
        "/api/v1/source/resolve",
        json={
            "target": {
                "material_id": material_id,
                "section_id": section["section_id"],
                "source_id": source_id,
                "page_start": section["page_start"],
                "anchor_text": section["summary"],
                "return_origin": {"course_id": "course-agentic"},
            }
        },
    )
    assert source_response.status_code == 200
    source_payload = source_response.json()
    assert source_payload["material"]["material_id"] == material_id
    assert source_payload["section"]["section_id"] == section["section_id"]
    assert source_payload["file_url"].startswith(f"/api/v1/materials/{material_id}/file")

    agent_response = client.post(
        "/api/v1/agents/run",
        json={
            "intent": "progress_check",
            "scope": {
                "course_id": "course-agentic",
                "material_ids": [material_id],
                "section_ids": [source_id],
                "source_type": "study_material",
            },
        },
    )
    assert agent_response.status_code == 200
    agent_payload = agent_response.json()
    node_names = [node["node_name"] for node in agent_payload["node_statuses"]]
    assert node_names == [
        "supervisor",
        "materials_agent",
        "assessment_agent",
        "study_coach_agent",
        "quality_agent",
    ]
    assert isinstance(agent_payload["quality_summary"]["uses_torch"], bool)
    assert agent_payload["quality_summary"]["notes"]
    assert agent_payload["recommendations"]
    assert agent_payload["recommendations"][0]["target_payload"]["href"]
    profiles_by_name = {profile["agent_name"]: profile for profile in agent_payload["agent_profiles"]}
    assert profiles_by_name["study_coach_agent"]["display_name"] == "Exam Butler"
    assert "weak concept triage" in profiles_by_name["study_coach_agent"]["skills"]
    assert profiles_by_name["materials_agent"]["personality"]

    list_response = client.get("/api/v1/agents/courses/course-agentic/recommendations")
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert list_payload["latest_run"]["run_id"] == agent_payload["run_id"]
    assert list_payload["recommendations"]
    assert any(profile["agent_name"] == "assessment_agent" for profile in list_payload["agent_profiles"])

    recommendation_id = list_payload["recommendations"][0]["id"]
    dismiss_response = client.post(f"/api/v1/agents/recommendations/{recommendation_id}/dismiss")
    assert dismiss_response.status_code == 200
    assert dismiss_response.json() == {"id": recommendation_id, "dismissed": True}

    refreshed_response = client.get("/api/v1/agents/courses/course-agentic/recommendations")
    assert refreshed_response.status_code == 200
    assert all(item["id"] != recommendation_id for item in refreshed_response.json()["recommendations"])

    memory_response = client.get("/api/v1/agents/courses/course-agentic/memory")
    assert memory_response.status_code == 200
    assert memory_response.json()["course_id"] == "course-agentic"

    save_memory_response = client.put(
        "/api/v1/agents/courses/course-agentic/memory",
        json={
            "preferred_study_style": "exam_cram",
            "preferred_quiz_format": "mixed",
            "default_question_count": 4,
            "focus_areas": ["Variables", "Assignment"],
            "encouragement_style": "warm",
            "progress_notes": ["Likes short review before quizzes."],
        },
    )
    assert save_memory_response.status_code == 200
    assert save_memory_response.json()["preferred_study_style"] == "exam_cram"

    chat_response = client.post(
        "/api/v1/agents/chat",
        json={
            "course_id": "course-agentic",
            "message": "what should I study next?",
            "scope": {
                "course_id": "course-agentic",
                "material_ids": [material_id],
                "section_ids": [source_id],
                "source_type": "study_material",
            },
        },
    )
    assert chat_response.status_code == 200
    chat_payload = chat_response.json()
    assert chat_payload["message"]
    assert chat_payload["actions"]
    assert chat_payload["memory"]["preferred_study_style"] == "exam_cram"
    assert chat_payload["active_agent_profile"]["display_name"] == "Exam Butler"
    assert any(profile["agent_name"] == "quality_agent" for profile in chat_payload["agent_profiles"])
