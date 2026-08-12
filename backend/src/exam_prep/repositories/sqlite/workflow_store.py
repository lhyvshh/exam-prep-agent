from datetime import UTC, datetime

from exam_prep.db.sqlite import SQLiteDatabase
from exam_prep.repositories.workflow_store import WorkflowStore


class SQLiteWorkflowStore(WorkflowStore):
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def get_current_course_id(self) -> str | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT course_id
                FROM workflow_state
                WHERE workflow_id = ?
                """,
                ("current",),
            ).fetchone()

        if row is None:
            return None
        return row["course_id"]

    def get_current_module_id(self) -> str | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT module_id
                FROM workflow_state
                WHERE workflow_id = ?
                """,
                ("current",),
            ).fetchone()
        if row is None:
            return None
        return row["module_id"]

    def set_current_selection(self, course_id: str, module_id: str | None = None) -> None:
        normalized_course_id = course_id.strip()
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO workflow_state(workflow_id, course_id, module_id, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(workflow_id) DO UPDATE SET
                    course_id = excluded.course_id,
                    module_id = excluded.module_id,
                    updated_at = excluded.updated_at
                """,
                (
                    "current",
                    normalized_course_id,
                    module_id.strip() if module_id else None,
                    datetime.now(UTC).isoformat(),
                ),
            )

    def clear_current_selection(self) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO workflow_state(workflow_id, course_id, module_id, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(workflow_id) DO UPDATE SET
                    course_id = excluded.course_id,
                    module_id = excluded.module_id,
                    updated_at = excluded.updated_at
                """,
                (
                    "current",
                    None,
                    None,
                    datetime.now(UTC).isoformat(),
                ),
            )
