from pathlib import Path

from exam_prep.db.sqlite import SQLiteDatabase


def _table_columns(database: SQLiteDatabase, table_name: str) -> set[str]:
    with database.connect() as connection:
        rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row["name"] for row in rows}


def test_flashcards_table_has_required_study_card_fields(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "schema.sqlite3")
    database.initialize()

    columns = _table_columns(database, "flashcards")

    assert {
        "id",
        "course_id",
        "material_id",
        "module_id",
        "learning_outcome_id",
        "concept_id",
        "formula_id",
        "front",
        "back_concise",
        "source_excerpt",
        "source_page",
        "card_type",
        "difficulty",
        "confidence_group",
        "interval_days",
        "ease_factor",
        "repetitions",
        "due_at",
        "last_reviewed_at",
        "created_at",
        "updated_at",
        "archived",
        "needs_more_source",
        "quality_score",
    }.issubset(columns)


def test_study_sessions_preserve_activity_fields_and_support_formula_sessions(
    tmp_path: Path,
) -> None:
    database = SQLiteDatabase(tmp_path / "schema.sqlite3")
    database.initialize()

    columns = _table_columns(database, "study_sessions")

    assert {
        "id",
        "user_id",
        "course_id",
        "module_id",
        "material_id",
        "section_id",
        "started_at",
        "ended_at",
        "duration_seconds",
        "metadata_json",
    }.issubset(columns)
    assert {
        "session_type",
        "title",
        "reading_number",
        "source_page_start",
        "source_page_end",
        "status",
        "created_at",
        "updated_at",
    }.issubset(columns)


def test_offline_package_tables_are_initialized(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "schema.sqlite3")
    database.initialize()

    with database.connect() as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    tables = {row["name"] for row in rows}

    assert {
        "study_packages",
        "package_exam_attempts",
        "package_versions",
        "generation_jobs",
        "generation_job_steps",
        "export_files",
    }.issubset(tables)
