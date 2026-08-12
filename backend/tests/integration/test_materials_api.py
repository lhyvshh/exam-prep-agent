from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_material_upload_status_and_preview_flow(client: TestClient) -> None:
    response = client.post(
        "/api/v1/materials/upload",
        data={"course_id": "course-1"},
        files={"file": ("notes.txt", b"# Topic\nAlpha beta gamma", "text/plain")},
    )

    assert response.status_code == 201
    record = response.json()["record"]
    assert record["status"] == "completed"
    assert record["section_count"] == 1

    material_id = record["material_id"]
    status_response = client.get(f"/api/v1/materials/{material_id}/status")
    preview_response = client.get(f"/api/v1/materials/{material_id}/preview")

    assert status_response.status_code == 200
    assert preview_response.status_code == 200
    assert preview_response.json()["chunks"][0]["citation_label"].startswith("notes.txt | ")
    assert "Topic" not in preview_response.json()["chunks"][0]["citation_label"]

    file_response = client.get(f"/api/v1/materials/{material_id}/file")
    assert file_response.status_code == 200
    assert file_response.content == b"# Topic\nAlpha beta gamma"
    assert "inline" in file_response.headers["content-disposition"]


def test_material_study_sections_can_be_read_and_marked_studied(client: TestClient) -> None:
    response = client.post(
        "/api/v1/materials/upload",
        data={"course_id": "course-study"},
        files={
            "file": (
                "gradient-notes.txt",
                (
                    b"# Gradient Descent Basics\n"
                    b"Gradient descent updates parameters by subtracting the learning rate times the gradient. "
                    b"The gradient points toward steepest increase, so the descent step moves in the opposite direction. "
                    b"Students should memorize theta_next = theta - alpha * gradient and explain why large learning rates can overshoot. "
                    b"Common exam traps include confusing ascent with descent and treating convergence as guaranteed for every objective."
                ),
                "text/plain",
            )
        },
    )

    assert response.status_code == 201
    material_id = response.json()["record"]["material_id"]

    study_response = client.get(f"/api/v1/materials/{material_id}/study?limit=1")
    assert study_response.status_code == 200
    study_payload = study_response.json()
    assert study_payload["total_sections"] >= 1
    assert study_payload["sections"][0]["summary"]
    assert study_payload["sections"][0]["key_points"]
    assert study_payload["sections"][0]["memorize_keywords"]
    assert study_payload["sections"][0]["quiz_ready"] is True

    section_id = study_payload["sections"][0]["section_id"]
    update_response = client.patch(
        f"/api/v1/materials/{material_id}/study/sections/{section_id}",
        json={"studied_status": "studied"},
    )

    assert update_response.status_code == 200
    assert update_response.json()["section"]["studied_status"] == "studied"

    refreshed_response = client.get(f"/api/v1/materials/{material_id}/study")
    assert refreshed_response.status_code == 200
    assert refreshed_response.json()["studied_sections"] == 1

    quiz_response = client.post(
        f"/api/v1/materials/{material_id}/study/sections/{section_id}/quiz"
    )
    assert quiz_response.status_code == 200
    assert quiz_response.json()["job_id"]


def test_material_upload_rejects_unsupported_file_type(client: TestClient) -> None:
    response = client.post(
        "/api/v1/materials/upload",
        data={"course_id": "course-1"},
        files={"file": ("data.csv", b"a,b,c", "text/csv")},
    )

    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]


def test_material_delete_removes_persisted_artifacts(client: TestClient) -> None:
    upload_response = client.post(
        "/api/v1/materials/upload",
        data={"course_id": "course-delete"},
        files={"file": ("notes.txt", b"# Topic\nAlpha beta gamma", "text/plain")},
    )
    assert upload_response.status_code == 201
    material_id = upload_response.json()["record"]["material_id"]

    delete_response = client.delete(f"/api/v1/materials/{material_id}")
    assert delete_response.status_code == 200
    assert delete_response.json()["removed"] is True
    assert delete_response.json()["remaining_material_count"] == 0

    status_response = client.get(f"/api/v1/materials/{material_id}/status")
    assert status_response.status_code == 404

    course_response = client.get("/api/v1/materials/course/course-delete")
    assert course_response.status_code == 200
    assert course_response.json()["records"] == []


def test_course_materials_returns_grouped_quiz_sources(client: TestClient) -> None:
    upload_response = client.post(
        "/api/v1/materials/upload",
        data={"course_id": "course-quiz-sources"},
        files={"file": ("notes.txt", b"# Topic\nAlpha beta gamma\n# Worked Example\nDelta epsilon zeta", "text/plain")},
    )
    assert upload_response.status_code == 201

    course_response = client.get("/api/v1/materials/course/course-quiz-sources")
    assert course_response.status_code == 200
    payload = course_response.json()

    assert payload["sections"]
    assert payload["quiz_sources"]
    assert payload["default_quiz_source_ids"]
    assert payload["quiz_sources"][0]["source_ids"]


def test_structured_material_section_chunk_and_concept_endpoints(client: TestClient) -> None:
    upload_response = client.post(
        "/api/v1/materials/upload",
        data={"course_id": "course-structured", "module_id": "module-a"},
        files={
            "file": (
                "python-notes.txt",
                (
                    b"# Variables\n"
                    b"Variables store data values. Python names are case sensitive and assignment uses name = value. "
                    b"Common traps include confusing assignment with equality and using reserved words as variable names.\n\n"
                    b"# Type Conversion\n"
                    b"Type conversion changes a value from one data type to another. "
                    b"Functions like int(), float(), and str() convert common inputs before expressions use them."
                ),
                "text/plain",
            )
        },
    )

    assert upload_response.status_code == 201
    material = upload_response.json()["record"]
    material_id = material["material_id"]
    assert material["raw_text_path"]

    materials_response = client.get("/api/v1/materials?course_id=course-structured")
    assert materials_response.status_code == 200
    assert materials_response.json()["records"][0]["material_id"] == material_id

    material_response = client.get(f"/api/v1/materials/{material_id}")
    assert material_response.status_code == 200
    assert material_response.json()["record"]["material_id"] == material_id

    sections_response = client.get(f"/api/v1/materials/{material_id}/sections")
    assert sections_response.status_code == 200
    sections = sections_response.json()["sections"]
    assert len(sections) >= 1
    assert sections[0]["source_text"]
    assert sections[0]["clean_title"]
    assert sections[0]["summary"]
    assert sections[0]["key_terms"]
    assert sections[0]["key_concepts"]
    assert sections[0]["is_junk"] is False
    assert sections[0]["source_text_hash"]
    assert sections[0]["enhancement_cache_key"]
    assert sections[0]["enhancement_prompt_version"]
    assert sections[0]["enhancement_input_excerpt"]
    assert sections[0]["enhancement_input_token_limit"] == 4000
    assert len(sections[0]["enhancement_input_excerpt"].split()) <= 4000

    section_id = sections[0]["id"]
    section_response = client.get(f"/api/v1/sections/{section_id}")
    assert section_response.status_code == 200
    assert section_response.json()["section"]["id"] == section_id

    chunks_response = client.get(f"/api/v1/sections/{section_id}/chunks")
    assert chunks_response.status_code == 200
    chunks = chunks_response.json()["chunks"]
    assert chunks
    assert chunks[0]["section_id"] == section_id
    assert chunks[0]["token_count"] > 0

    concepts = section_response.json()["section"]["concepts"]
    assert concepts
    source_response = client.get(f"/api/v1/concepts/{concepts[0]['id']}/source")
    assert source_response.status_code == 200
    source_payload = source_response.json()
    assert source_payload["concept"]["section_id"] == section_id
    assert source_payload["source"]["material_id"] == material_id

    concept_quiz_response = client.post(f"/api/v1/concepts/{concepts[0]['id']}/quiz")
    assert concept_quiz_response.status_code == 200
    assert concept_quiz_response.json()["job_id"]


def test_duplicate_material_upload_reuses_existing_parse_by_hash(client: TestClient) -> None:
    payload = (
        b"# Gradient Descent\n"
        b"Gradient descent updates parameters using the learning rate and the gradient."
    )
    first_response = client.post(
        "/api/v1/materials/upload",
        data={"course_id": "course-dedupe", "module_id": "module-1"},
        files={"file": ("notes-a.txt", payload, "text/plain")},
    )
    assert first_response.status_code == 201
    material_id = first_response.json()["record"]["material_id"]
    first_sections_response = client.get(f"/api/v1/materials/{material_id}/sections")
    assert first_sections_response.status_code == 200
    first_cache_key = first_sections_response.json()["sections"][0]["enhancement_cache_key"]

    second_response = client.post(
        "/api/v1/materials/upload",
        data={"course_id": "course-dedupe", "module_id": "module-1"},
        files={"file": ("renamed-notes.txt", payload, "text/plain")},
    )

    assert second_response.status_code == 201
    assert second_response.json()["record"]["material_id"] == first_response.json()["record"]["material_id"]

    second_sections_response = client.get(f"/api/v1/materials/{material_id}/sections")
    assert second_sections_response.status_code == 200
    assert second_sections_response.json()["sections"][0]["enhancement_cache_key"] == first_cache_key

    list_response = client.get("/api/v1/materials?course_id=course-dedupe")
    assert list_response.status_code == 200
    assert len(list_response.json()["records"]) == 1


def test_material_reprocess_clears_stale_derived_artifacts(
    app: FastAPI,
    client: TestClient,
) -> None:
    upload_response = client.post(
        "/api/v1/materials/upload",
        data={"course_id": "course-reprocess-cleanup", "module_id": "module-a"},
        files={
            "file": (
                "notes.txt",
                (
                    b"# Probability Rules\n"
                    b"Two events A and B are independent if P(A intersect B) = P(A)P(B), "
                    b"or equivalently P(A given B) = P(A) when P(B) is positive. "
                    b"Two events are mutually exclusive if they cannot occur together, so "
                    b"P(A intersect B) = 0. Exam questions often ask students to distinguish "
                    b"independence from mutual exclusivity because the concepts are frequently confused."
                ),
                "text/plain",
            )
        },
    )
    assert upload_response.status_code == 201
    record = upload_response.json()["record"]
    material_id = record["material_id"]
    now = datetime.now(UTC).isoformat()

    stale_card_id = uuid4().hex
    stale_session_id = uuid4().hex
    with app.state.database.connect() as connection:
        connection.execute(
            """
            INSERT INTO study_sessions(
                id, user_id, course_id, module_id, material_id, section_id,
                started_at, metadata_json, session_type, title, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                stale_session_id,
                "demo-user",
                record["course_id"],
                record["module_id"],
                material_id,
                "stale-section",
                now,
                "{}",
                "formulas",
                "Stale formulas",
                "ready",
                now,
                now,
            ),
        )
        connection.execute(
            """
            INSERT INTO flashcards(
                id, course_id, material_id, module_id, section_id, front, back_concise,
                card_type, confidence_group, interval_days, ease_factor, repetitions,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                stale_card_id,
                record["course_id"],
                material_id,
                record["module_id"],
                "stale-section",
                "What stale card should disappear?",
                "**Stale card.**",
                "definition",
                "new",
                0,
                2.5,
                0,
                now,
                now,
            ),
        )
        connection.execute(
            """
            INSERT INTO flashcard_reviews(
                id, user_id, course_id, module_id, material_id, section_id, concept_id,
                flashcard_id, rating, previous_interval_days, new_interval_days,
                previous_confidence_group, new_confidence_group, metadata_json, reviewed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                uuid4().hex,
                "demo-user",
                record["course_id"],
                record["module_id"],
                material_id,
                "stale-section",
                None,
                stale_card_id,
                "good",
                0,
                3,
                "new",
                "learning",
                "{}",
                now,
            ),
        )
        connection.execute(
            """
            INSERT INTO generated_content_quality_flags(
                id, course_id, material_id, section_id, content_id, content_type, flag_type, reason, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                uuid4().hex,
                record["course_id"],
                material_id,
                "stale-section",
                stale_card_id,
                "flashcard",
                "generic_question",
                "stale",
                now,
            ),
        )

    material_dir = Path(app.state.settings.material_storage_path) / material_id
    stale_formula_dir = material_dir / "formula-crops"
    stale_formula_dir.mkdir(parents=True, exist_ok=True)
    stale_formula_asset = stale_formula_dir / "stale.png"
    stale_formula_asset.write_bytes(b"stale")

    reprocess_response = client.post(f"/api/v1/materials/{material_id}/reprocess")

    assert reprocess_response.status_code == 200
    refreshed_record = reprocess_response.json()["record"]
    assert refreshed_record["material_id"] == material_id
    assert refreshed_record["status"] == "completed"
    assert refreshed_record["section_count"] >= 1

    sections_response = client.get(f"/api/v1/materials/{material_id}/sections")
    assert sections_response.status_code == 200
    sections = sections_response.json()["sections"]
    assert sections
    assert all(len(section["source_text"]) < 250_000 for section in sections)
    assert all("data:image" not in section["source_text"] for section in sections)
    assert all(";base64," not in section["source_text"] for section in sections)

    with app.state.database.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) AS count FROM study_sessions WHERE id = ?",
            (stale_session_id,),
        ).fetchone()["count"] == 0
        assert connection.execute(
            "SELECT COUNT(*) AS count FROM flashcards WHERE id = ?",
            (stale_card_id,),
        ).fetchone()["count"] == 0
        assert connection.execute(
            "SELECT COUNT(*) AS count FROM flashcard_reviews WHERE flashcard_id = ?",
            (stale_card_id,),
        ).fetchone()["count"] == 0
        assert connection.execute(
            "SELECT COUNT(*) AS count FROM generated_content_quality_flags WHERE content_id = ?",
            (stale_card_id,),
        ).fetchone()["count"] == 0

    assert not stale_formula_asset.exists()


def test_material_reprocess_returns_structured_error_when_parser_crashes(
    app: FastAPI,
    monkeypatch,
) -> None:
    with TestClient(app, raise_server_exceptions=False) as client:
        upload_response = client.post(
            "/api/v1/materials/upload",
            data={"course_id": "course-reprocess-failure"},
            files={"file": ("notes.txt", b"# Topic\nAlpha beta gamma", "text/plain")},
        )
        assert upload_response.status_code == 201
        record = upload_response.json()["record"]
        material_id = record["material_id"]
        stale_card_id = uuid4().hex
        now = datetime.now(UTC).isoformat()

        with app.state.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO flashcards(
                    id, course_id, material_id, module_id, section_id, front, back_concise,
                    card_type, confidence_group, interval_days, ease_factor, repetitions,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    stale_card_id,
                    record["course_id"],
                    material_id,
                    record["module_id"],
                    "stale-section",
                    "What stale failed card should disappear?",
                    "**Stale failed card.**",
                    "definition",
                    "new",
                    0,
                    2.5,
                    0,
                    now,
                    now,
                ),
            )

        def _crash_parser(*args, **kwargs):  # noqa: ANN002, ANN003
            raise RuntimeError("parser exploded")

        monkeypatch.setattr(
            "exam_prep.ingestion.parsers.DocumentParser.parse",
            _crash_parser,
        )

        reprocess_response = client.post(f"/api/v1/materials/{material_id}/reprocess")

    assert reprocess_response.status_code == 500
    detail = reprocess_response.json()["detail"]
    assert detail["error"] == "material_reprocess_failed"
    assert detail["material_id"] == material_id
    assert detail["file_name"] == "notes.txt"
    assert detail["parser_phase"] in {"extracting", "failed"}
    assert "parser exploded" in detail["failure_reason"]

    status_response = TestClient(app).get(f"/api/v1/materials/{material_id}/status")
    assert status_response.status_code == 200
    failed_record = status_response.json()["record"]
    assert failed_record["status"] == "failed"
    assert failed_record["processing_status"] == "failed"
    assert "parser exploded" in failed_record["error_message"]

    sections_response = TestClient(app).get(f"/api/v1/materials/{material_id}/sections")
    assert sections_response.status_code == 200
    assert sections_response.json()["sections"] == []

    with app.state.database.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) AS count FROM flashcards WHERE id = ?",
            (stale_card_id,),
        ).fetchone()["count"] == 0
