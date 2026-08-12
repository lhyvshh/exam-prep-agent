from exam_prep.schemas.activity import ActivityEventCreate, ActivityEventType, QuestionAttemptCreate
from exam_prep.schemas.materials import (
    ContentLabel,
    MaterialParseStatus,
    MaterialProcessingStage,
    MaterialRecord,
    MaterialStageStatus,
    MaterialStudyDocument,
    MaterialStudySection,
    ParsedMaterialDocument,
    SourceLocator,
    SourceSection,
    StudyDifficulty,
)


COURSE_ID = "course-agent-tools"
MODULE_ID = "module-normalization"
MATERIAL_ID = "material-normalization"
SECTION_ID = "section-3nf"
SQL_COURSE_ID = "course-sql-agent"
SQL_MODULE_ID = "Module 4: SQL Joins"
SQL_MATERIAL_ID = "material-sql-joins"
SQL_SECTION_ID = "section-sql-joins"


def test_smart_agent_study_plan_uses_real_weaknesses_and_source_links(client):
    concept_id = _seed_material_section(client)
    _seed_attempts(client, concept_id)

    response = client.get("/api/v1/agent/study-plan", params={"courseId": COURSE_ID})

    assert response.status_code == 200
    payload = response.json()
    assert payload["readinessScore"] < 80
    assert "Third Normal Form" in payload["summary"]
    assert payload["recommendedNextAction"].startswith("Review Third Normal Form")

    assert len(payload["topWeakModules"]) <= 3
    assert payload["topWeakModules"][0]["id"] == MODULE_ID
    assert payload["topWeakModules"][0]["attempts"] == 5
    assert payload["topWeakModules"][0]["accuracy"] == 0.4

    assert len(payload["topWeakConcepts"]) <= 5
    concept_summary = payload["topWeakConcepts"][0]
    assert concept_summary["id"] == concept_id
    assert concept_summary["name"] == "Third Normal Form"
    assert concept_summary["attempts"] == 5
    assert concept_summary["accuracy"] == 0.4
    assert concept_summary["recentTrend"] == "Needs attention"

    assert payload["weakestQuestionTypes"][0]["name"] == "scenario"
    assert payload["weakestQuestionTypes"][0]["attempts"] == 3
    assert payload["weakestQuestionTypes"][0]["accuracy"] == 0.0

    recommendations = payload["recommendations"]
    action_types = {card["actionType"] for card in recommendations}
    assert {"review_material", "generate_quiz", "missed_questions"}.issubset(action_types)

    review_card = next(card for card in recommendations if card["actionType"] == "review_material")
    assert review_card["buttonText"] == "Review Material"
    assert review_card["targetMaterialId"] == MATERIAL_ID
    assert review_card["targetSectionId"] == SECTION_ID
    assert review_card["targetConceptId"] == concept_id
    assert review_card["targetUrl"].startswith(f"/courses/{COURSE_ID}/materials?")
    assert f"materialId={MATERIAL_ID}" in review_card["targetUrl"]
    assert f"sourceId={SECTION_ID}" in review_card["targetUrl"]
    assert "source=1" in review_card["targetUrl"]
    assert "page=47" in review_card["targetUrl"]
    assert review_card["weakAreaName"] == "Third Normal Form"
    assert review_card["accuracy"] == 0.4
    assert review_card["attempts"] == 5
    assert review_card["recentTrend"] == "Needs attention"
    assert "Low accuracy" in review_card["whyItMatters"]
    assert review_card["recommendedAction"] == "Review material first, then practice mcq questions."
    button_labels = {button["label"] for button in review_card["buttons"]}
    assert {
        "Review Material",
        "Practice Third Normal Form MCQ Questions",
        "Generate Quiz",
        "Retake Missed Questions",
        "View Source PDF Page",
        "Study Similar Questions",
    }.issubset(button_labels)
    button_by_label = {button["label"]: button for button in review_card["buttons"]}
    assert button_by_label["Practice Third Normal Form MCQ Questions"]["targetUrl"].startswith(f"/courses/{COURSE_ID}/materials?")
    assert "quiz=1" in button_by_label["Practice Third Normal Form MCQ Questions"]["targetUrl"]
    assert "questionType=mcq" in button_by_label["Study Similar Questions"]["targetUrl"]
    assert button_by_label["Retake Missed Questions"]["targetUrl"] == f"/courses/{COURSE_ID}/wrong-questions?concept={concept_id}"
    assert "source=1" in button_by_label["View Source PDF Page"]["targetUrl"]

    practice_card = next(card for card in recommendations if card["actionType"] == "generate_quiz")
    assert practice_card["buttonText"] == "Practice This Concept"
    assert practice_card["targetConceptId"] == concept_id
    assert practice_card["questionType"] == "mcq"
    assert practice_card["targetUrl"].startswith(f"/courses/{COURSE_ID}/materials?")
    assert "/quiz/new" not in practice_card["targetUrl"]

    missed_card = next(card for card in recommendations if card["actionType"] == "missed_questions")
    assert missed_card["buttonText"] == "Review Missed Questions"
    assert missed_card["targetUrl"] == f"/courses/{COURSE_ID}/wrong-questions?concept={concept_id}"


def test_smart_agent_study_plan_recommends_high_weight_sections_before_quiz_history(client):
    concept_id = _seed_material_section(client)

    response = client.get("/api/v1/agent/study-plan", params={"courseId": COURSE_ID})

    assert response.status_code == 200
    payload = response.json()
    assert payload["readinessScore"] == 0
    assert "Complete a quiz" in payload["summary"]
    assert payload["recommendedNextAction"].startswith("Study Third Normal Form")
    assert payload["recommendations"]
    card = payload["recommendations"][0]
    assert card["actionType"] == "review_material"
    assert card["buttonText"] == "Study Section"
    assert card["targetConceptId"] == concept_id
    assert card["targetUrl"].startswith(f"/courses/{COURSE_ID}/materials?")
    assert "study=1" in card["targetUrl"]
    assert card["weakAreaName"] == "Third Normal Form"
    assert card["attempts"] == 0
    assert card["buttons"][0]["label"] == "Review Material"


def test_smart_agent_response_uses_attempts_review_history_and_source_links(client):
    concept_id = _seed_sql_join_section(client)
    _seed_sql_join_attempts(client, concept_id)
    _seed_single_sql_review_event(client, concept_id)

    response = client.get("/api/v1/agent/study-plan", params={"courseId": SQL_COURSE_ID})

    assert response.status_code == 200
    payload = response.json()
    assert "You are weakest in Module 4: SQL Joins." in payload["summary"]
    assert "Your accuracy is 48% across 23 attempts." in payload["summary"]
    assert "mcq questions" in payload["summary"]
    assert "especially deciding between INNER JOIN and LEFT JOIN" in payload["summary"]
    assert "reviewed the source material only once" in payload["summary"]
    assert "missed this concept 12 times" in payload["summary"]
    assert "1. Review the source section on SQL Joins." in payload["summary"]
    assert "2. Practice 10 mcq questions." in payload["summary"]
    assert "3. Retake your 12 missed questions after that." in payload["summary"]

    card = payload["recommendations"][0]
    assert card["weakAreaName"] == "SQL Joins"
    assert card["accuracy"] == 0.4783
    assert card["attempts"] == 23
    assert card["whyItMatters"] == (
        "Low accuracy on SQL Joins, 12 recent misses, reviewed source material only once, high-priority exam coverage."
    )
    labels = {button["label"] for button in card["buttons"]}
    assert {"Review Material", "Practice SQL Joins MCQ Questions", "Retake Missed Questions", "View Source PDF Page"}.issubset(labels)
    button_by_label = {button["label"]: button for button in card["buttons"]}
    assert button_by_label["Review Material"]["targetUrl"].startswith(f"/courses/{SQL_COURSE_ID}/materials?")
    assert "source=1" in button_by_label["Review Material"]["targetUrl"]
    assert "page=12" in button_by_label["View Source PDF Page"]["targetUrl"]
    assert "quiz=1" in button_by_label["Practice SQL Joins MCQ Questions"]["targetUrl"]
    assert "questionType=mcq" in button_by_label["Practice SQL Joins MCQ Questions"]["targetUrl"]
    assert button_by_label["Retake Missed Questions"]["targetUrl"] == (
        f"/courses/{SQL_COURSE_ID}/wrong-questions?concept={concept_id}"
    )


def _seed_material_section(client) -> str:
    catalog = client.app.state.material_catalog
    record = MaterialRecord(
        material_id=MATERIAL_ID,
        course_id=COURSE_ID,
        module_id=MODULE_ID,
        file_name="Database Normalization.pdf",
        display_name="Database Normalization",
        content_type="application/pdf",
        status=MaterialParseStatus.COMPLETED,
        page_count=80,
        processing_status=MaterialProcessingStage.READY,
        processing_progress=100,
        outline_status=MaterialStageStatus.COMPLETED,
        enrichment_status=MaterialStageStatus.COMPLETED,
        content_hash="hash-normalization",
        section_count=1,
    )
    catalog.upsert_record(record)

    source_section = SourceSection(
        source_id=SECTION_ID,
        material_id=MATERIAL_ID,
        course_id=COURSE_ID,
        module_id=MODULE_ID,
        file_name=record.file_name,
        content_type=record.content_type,
        section_title="Third Normal Form",
        text=(
            "Third Normal Form removes transitive dependencies. A table is in 3NF "
            "when every non-key attribute depends only on the key, the whole key, "
            "and nothing but the key."
        ),
        page_end=48,
        content_label=ContentLabel.TESTABLE_CONTENT,
        priority_score=0.95,
        locator=SourceLocator(section_index=1, page_number=47),
        citation_label="Database Normalization.pdf · pages 47-48",
    )
    study_section = MaterialStudySection(
        section_id=SECTION_ID,
        material_id=MATERIAL_ID,
        title="Third Normal Form",
        normalized_title="Third Normal Form",
        page_start=47,
        page_end=48,
        source_anchor="third-normal-form",
        summary="Third Normal Form removes transitive dependencies from relational tables.",
        key_points=["Non-key attributes should depend only on the candidate key."],
        memorize_keywords=["Third Normal Form", "transitive dependency", "candidate key"],
        memorize_functions_or_formulas=["3NF: every non-key attribute depends only on the key"],
        traps=["Do not confuse partial dependency with transitive dependency."],
        difficulty=StudyDifficulty.HARD,
        display_order=1,
        source_ids=[SECTION_ID],
    )
    catalog.replace_study_assets(
        MaterialStudyDocument(material_id=MATERIAL_ID, sections=[study_section]),
        ParsedMaterialDocument(record=record, sections=[source_section], chunks=[]),
    )
    structured_section = catalog.get_structured_section(SECTION_ID)
    assert structured_section is not None
    concept = next(item for item in structured_section.concepts if item.name == "Third Normal Form")
    return concept.id


def _seed_attempts(client, concept_id: str) -> None:
    activity_store = client.app.state.activity_store
    attempts = [
        ("q1", "definition", True, 44),
        ("q2", "scenario", False, 86),
        ("q3", "scenario", False, 91),
        ("q4", "scenario", False, 75),
        ("q5", "comparison", True, 63),
    ]
    for question_id, question_type, is_correct, seconds in attempts:
        activity_store.record_question_attempt(
            QuestionAttemptCreate(
                user_id="demo-user",
                quiz_id="quiz-agent-tools",
                question_id=question_id,
                course_id=COURSE_ID,
                module_id=MODULE_ID,
                material_id=MATERIAL_ID,
                section_id=SECTION_ID,
                concept_id=concept_id,
                selected_answer="student answer",
                correct_answer="correct answer",
                is_correct=is_correct,
                time_spent_seconds=seconds,
                question_type=question_type,
                difficulty=0.8,
            )
        )


def _seed_sql_join_section(client) -> str:
    catalog = client.app.state.material_catalog
    record = MaterialRecord(
        material_id=SQL_MATERIAL_ID,
        course_id=SQL_COURSE_ID,
        module_id=SQL_MODULE_ID,
        file_name="SQL Joins.pdf",
        display_name="SQL Joins",
        content_type="application/pdf",
        status=MaterialParseStatus.COMPLETED,
        page_count=40,
        processing_status=MaterialProcessingStage.READY,
        processing_progress=100,
        outline_status=MaterialStageStatus.COMPLETED,
        enrichment_status=MaterialStageStatus.COMPLETED,
        content_hash="hash-sql-joins",
        section_count=1,
    )
    catalog.upsert_record(record)

    source_section = SourceSection(
        source_id=SQL_SECTION_ID,
        material_id=SQL_MATERIAL_ID,
        course_id=SQL_COURSE_ID,
        module_id=SQL_MODULE_ID,
        file_name=record.file_name,
        content_type=record.content_type,
        section_title="SQL Joins",
        text=(
            "SQL joins combine rows from related tables. INNER JOIN returns matching rows only. "
            "LEFT JOIN returns all rows from the left table and matching rows from the right table."
        ),
        page_end=14,
        content_label=ContentLabel.TESTABLE_CONTENT,
        priority_score=0.95,
        locator=SourceLocator(section_index=1, page_number=12),
        citation_label="SQL Joins.pdf · pages 12-14",
    )
    study_section = MaterialStudySection(
        section_id=SQL_SECTION_ID,
        material_id=SQL_MATERIAL_ID,
        title="SQL Joins",
        normalized_title="SQL Joins",
        page_start=12,
        page_end=14,
        source_anchor="sql-joins",
        summary="SQL joins combine rows from related tables using matching keys.",
        key_points=[
            "INNER JOIN returns rows that match in both tables.",
            "LEFT JOIN keeps all rows from the left table and fills missing right-side matches with NULL.",
        ],
        memorize_keywords=["SQL Joins", "INNER JOIN", "LEFT JOIN", "join key"],
        memorize_functions_or_formulas=["SELECT ... FROM left_table LEFT JOIN right_table ON left.id = right.id"],
        traps=["Do not use INNER JOIN when unmatched left-table rows must remain visible."],
        difficulty=StudyDifficulty.HARD,
        display_order=1,
        source_ids=[SQL_SECTION_ID],
    )
    catalog.replace_study_assets(
        MaterialStudyDocument(material_id=SQL_MATERIAL_ID, sections=[study_section]),
        ParsedMaterialDocument(record=record, sections=[source_section], chunks=[]),
    )
    structured_section = catalog.get_structured_section(SQL_SECTION_ID)
    assert structured_section is not None
    concept = next(item for item in structured_section.concepts if item.name == "SQL Joins")
    return concept.id


def _seed_sql_join_attempts(client, concept_id: str) -> None:
    activity_store = client.app.state.activity_store
    attempts: list[tuple[str, str, bool]] = []
    attempts.extend((f"scenario-miss-{index}", "scenario", False) for index in range(1, 7))
    attempts.extend((f"scenario-hit-{index}", "scenario", True) for index in range(1, 5))
    attempts.extend((f"definition-hit-{index}", "definition", True) for index in range(1, 5))
    attempts.extend((f"comparison-hit-{index}", "comparison", True) for index in range(1, 3))
    attempts.extend((f"application-miss-{index}", "application", False) for index in range(1, 2))
    attempts.extend((f"application-hit-{index}", "application", True) for index in range(1, 2))
    attempts.extend((f"mixed-miss-{index}", "mixed", False) for index in range(1, 6))

    assert len(attempts) == 23
    assert sum(1 for _, _, is_correct in attempts if is_correct) == 11
    for question_id, question_type, is_correct in attempts:
        activity_store.record_question_attempt(
            QuestionAttemptCreate(
                user_id="demo-user",
                quiz_id="quiz-sql-joins",
                question_id=question_id,
                course_id=SQL_COURSE_ID,
                module_id=SQL_MODULE_ID,
                material_id=SQL_MATERIAL_ID,
                section_id=SQL_SECTION_ID,
                concept_id=concept_id,
                selected_answer="student answer",
                correct_answer="correct answer",
                is_correct=is_correct,
                time_spent_seconds=72,
                question_type=question_type,
                difficulty=0.75,
            )
        )


def _seed_single_sql_review_event(client, concept_id: str) -> None:
    activity_store = client.app.state.activity_store
    activity_store.record_event(
        ActivityEventCreate(
            user_id="demo-user",
            course_id=SQL_COURSE_ID,
            module_id=SQL_MODULE_ID,
            material_id=SQL_MATERIAL_ID,
            section_id=SQL_SECTION_ID,
            concept_id=concept_id,
            event_type=ActivityEventType.REVIEW_MATERIAL_CLICKED,
            metadata_json={"origin": "test"},
        )
    )
