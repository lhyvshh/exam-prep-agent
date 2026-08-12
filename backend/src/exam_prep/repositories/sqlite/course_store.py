from datetime import UTC, datetime

from exam_prep.db.sqlite import SQLiteDatabase
from exam_prep.repositories.course_store import CourseStore
from exam_prep.schemas.library import CourseRecord, ModuleRecord


class SQLiteCourseStore(CourseStore):
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def create_course(self, course: CourseRecord) -> CourseRecord:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO courses(course_id, course_code, display_name, description)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(course_id) DO UPDATE SET
                    course_code = excluded.course_code,
                    display_name = excluded.display_name,
                    description = excluded.description,
                    is_deleted = 0,
                    deleted_at = NULL
                """,
                (
                    course.course_id,
                    course.course_code,
                    course.display_name,
                    course.description,
                ),
            )
        return course

    def list_courses(self) -> list[CourseRecord]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT course_id, course_code, display_name, description
                FROM courses
                WHERE is_deleted = 0
                ORDER BY course_code ASC, display_name ASC
                """
            ).fetchall()
        return [
            CourseRecord(
                course_id=row["course_id"],
                course_code=row["course_code"],
                display_name=row["display_name"],
                description=row["description"],
            )
            for row in rows
        ]

    def get_course(self, course_id: str) -> CourseRecord | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT course_id, course_code, display_name, description
                FROM courses
                WHERE course_id = ?
                  AND is_deleted = 0
                """,
                (course_id,),
            ).fetchone()
        if row is None:
            return None
        return CourseRecord(
            course_id=row["course_id"],
            course_code=row["course_code"],
            display_name=row["display_name"],
            description=row["description"],
        )

    def update_course(self, course: CourseRecord) -> CourseRecord:
        return self.create_course(course)

    def soft_delete_course(self, course_id: str) -> bool:
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE courses
                SET is_deleted = 1,
                    deleted_at = ?
                WHERE course_id = ?
                  AND is_deleted = 0
                """,
                (datetime.now(UTC).isoformat(), course_id),
            )
        return cursor.rowcount > 0

    def create_module(self, module: ModuleRecord) -> ModuleRecord:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO modules(module_id, course_id, module_number, display_name, description)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(module_id) DO UPDATE SET
                    course_id = excluded.course_id,
                    module_number = excluded.module_number,
                    display_name = excluded.display_name,
                    description = excluded.description,
                    is_deleted = 0,
                    deleted_at = NULL
                """,
                (
                    module.module_id,
                    module.course_id,
                    module.module_number,
                    module.display_name,
                    module.description,
                ),
            )
        return module

    def list_modules(self, course_id: str) -> list[ModuleRecord]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT module_id, course_id, module_number, display_name, description
                FROM modules
                WHERE course_id = ?
                  AND is_deleted = 0
                ORDER BY module_number ASC, display_name ASC
                """,
                (course_id,),
            ).fetchall()
        return [
            ModuleRecord(
                module_id=row["module_id"],
                course_id=row["course_id"],
                module_number=row["module_number"],
                display_name=row["display_name"],
                description=row["description"],
            )
            for row in rows
        ]

    def get_module(self, module_id: str) -> ModuleRecord | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT module_id, course_id, module_number, display_name, description
                FROM modules
                WHERE module_id = ?
                  AND is_deleted = 0
                """,
                (module_id,),
            ).fetchone()
        if row is None:
            return None
        return ModuleRecord(
            module_id=row["module_id"],
            course_id=row["course_id"],
            module_number=row["module_number"],
            display_name=row["display_name"],
            description=row["description"],
        )

    def update_module(self, module: ModuleRecord) -> ModuleRecord:
        return self.create_module(module)

    def soft_delete_module(self, module_id: str) -> bool:
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE modules
                SET is_deleted = 1,
                    deleted_at = ?
                WHERE module_id = ?
                  AND is_deleted = 0
                """,
                (datetime.now(UTC).isoformat(), module_id),
            )
        return cursor.rowcount > 0
