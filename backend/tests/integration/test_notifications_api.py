from fastapi.testclient import TestClient


def test_notification_preferences_draft_and_demo_send(client: TestClient) -> None:
    memory_response = client.put(
        "/api/v1/agents/courses/course-notify/memory",
        json={
            "preferred_study_style": "quick_review",
            "preferred_quiz_format": "mixed",
            "default_question_count": 3,
            "focus_areas": ["Type conversion", "Comparison operators"],
            "encouragement_style": "warm",
            "progress_notes": ["Responds well to short reminders."],
        },
    )
    assert memory_response.status_code == 200

    default_response = client.get("/api/v1/notifications/courses/course-notify/preferences")
    assert default_response.status_code == 200
    assert default_response.json()["email_enabled"] is False

    save_response = client.put(
        "/api/v1/notifications/courses/course-notify/preferences",
        json={
            "email_enabled": True,
            "email_address": "student@example.com",
            "daily_reminder_enabled": True,
            "final_week_enabled": True,
            "weak_concept_enabled": True,
            "exam_date": "2026-05-02",
            "preferred_reminder_time": "18:30",
            "busy_windows": ["Mon 9-5"],
        },
    )
    assert save_response.status_code == 200
    assert save_response.json()["email_address"] == "student@example.com"

    draft_response = client.post(
        "/api/v1/notifications/courses/course-notify/drafts",
        json={"reminder_type": "weak_concept"},
    )
    assert draft_response.status_code == 200
    draft = draft_response.json()
    assert "Type conversion" in draft["subject"]
    assert draft["quality_reviewed"] is True
    assert draft["quality_notes"]

    send_response = client.post(f"/api/v1/notifications/drafts/{draft['draft_id']}/send")
    assert send_response.status_code == 200
    sent = send_response.json()
    assert sent["draft"]["status"] == "simulated_sent"
    assert "demo mode" in sent["delivery_message"].lower()

    drafts_response = client.get("/api/v1/notifications/courses/course-notify/drafts")
    assert drafts_response.status_code == 200
    assert drafts_response.json()[0]["draft_id"] == draft["draft_id"]
