import sqlite3

from exam_prep.db.sqlite import SQLiteDatabase
from ...packages.completed_exam import ImportedExamAttemptRecord
from ...packages.models import (
    PackageFile,
    PackageGenerationJob,
    PackageGenerationJobStep,
    PackageJobStatus,
    PackageRecord,
    PackageStatus,
    PackageValidationReport,
    PackageVersion,
)
from ..package_store import PackageJobStore, PackageStore


class SQLitePackageStore(PackageStore, PackageJobStore):
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def create_package(self, record: PackageRecord) -> PackageRecord:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO study_packages(
                    package_id, course_id, title, exam_name, exam_part, status,
                    active_version, created_at, updated_at, record_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(package_id) DO UPDATE SET
                    course_id = excluded.course_id,
                    title = excluded.title,
                    exam_name = excluded.exam_name,
                    exam_part = excluded.exam_part,
                    status = excluded.status,
                    active_version = excluded.active_version,
                    updated_at = excluded.updated_at,
                    record_json = excluded.record_json
                """,
                (
                    record.package_id,
                    record.course_id,
                    record.title,
                    record.exam_name,
                    record.exam_part,
                    record.status.value,
                    record.active_version,
                    record.created_at,
                    record.updated_at,
                    record.model_dump_json(),
                ),
            )
        return record

    def get_package(self, package_id: str) -> PackageRecord | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT record_json FROM study_packages WHERE package_id = ?",
                (package_id,),
            ).fetchone()
        return self._row_to_package(row)

    def list_packages(self, course_id: str) -> list[PackageRecord]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT record_json
                FROM study_packages
                WHERE course_id = ?
                ORDER BY updated_at DESC, package_id ASC
                """,
                (course_id,),
            ).fetchall()
        return [PackageRecord.model_validate_json(row["record_json"]) for row in rows]

    def save_version(self, version: PackageVersion) -> None:
        with self.database.connect() as connection:
            existing = connection.execute(
                """
                SELECT snapshot_json
                FROM package_versions
                WHERE package_id = ? AND version = ?
                """,
                (version.package_id, version.version),
            ).fetchone()
            if existing is not None:
                existing_version = PackageVersion.model_validate_json(
                    existing["snapshot_json"]
                )
                if (
                    existing_version.status == PackageStatus.COMPLETE
                    and existing_version != version
                ):
                    raise ValueError("completed package versions are immutable")
            connection.execute(
                """
                INSERT INTO package_versions(
                    package_id, version, status, created_at, completed_at,
                    source_fingerprint, snapshot_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(package_id, version) DO UPDATE SET
                    status = excluded.status,
                    completed_at = excluded.completed_at,
                    source_fingerprint = excluded.source_fingerprint,
                    snapshot_json = excluded.snapshot_json
                """,
                (
                    version.package_id,
                    version.version,
                    version.status.value,
                    version.created_at,
                    version.completed_at,
                    version.source_fingerprint,
                    version.model_dump_json(),
                ),
            )

    def save_job_step(self, step: PackageGenerationJobStep) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO generation_job_steps(
                    job_id, step_name, status, input_fingerprint, accepted_count,
                    rejected_count, checkpoint_json, attempts, error_message,
                    provider_usage_json, output_version, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id, step_name) DO UPDATE SET
                    status = excluded.status,
                    input_fingerprint = excluded.input_fingerprint,
                    accepted_count = excluded.accepted_count,
                    rejected_count = excluded.rejected_count,
                    checkpoint_json = excluded.checkpoint_json,
                    attempts = excluded.attempts,
                    error_message = excluded.error_message,
                    provider_usage_json = excluded.provider_usage_json,
                    output_version = excluded.output_version,
                    updated_at = excluded.updated_at
                """,
                (
                    step.job_id,
                    step.step_name,
                    step.status.value,
                    step.input_fingerprint,
                    step.accepted_count,
                    step.rejected_count,
                    step.checkpoint_json,
                    step.attempts,
                    step.error_message,
                    step.provider_usage_json,
                    step.output_version,
                    step.updated_at,
                ),
            )

    def get_version(self, package_id: str, version: int) -> PackageVersion | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT snapshot_json
                FROM package_versions
                WHERE package_id = ? AND version = ?
                """,
                (package_id, version),
            ).fetchone()
        if row is None:
            return None
        return PackageVersion.model_validate_json(row["snapshot_json"])

    def list_versions(self, package_id: str) -> list[PackageVersion]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT snapshot_json
                FROM package_versions
                WHERE package_id = ?
                ORDER BY version DESC
                """,
                (package_id,),
            ).fetchall()
        return [PackageVersion.model_validate_json(row["snapshot_json"]) for row in rows]

    def replace_files(
        self,
        package_id: str,
        version: int,
        files: list[PackageFile],
    ) -> None:
        with self.database.connect() as connection:
            connection.execute(
                "DELETE FROM export_files WHERE package_id = ? AND version = ?",
                (package_id, version),
            )
            connection.executemany(
                """
                INSERT INTO export_files(
                    package_id, version, file_id, kind, file_name, media_type,
                    size_bytes, sha256, content_count, artifact_path, snapshot_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [self._file_parameters(file) for file in files],
            )

    def list_files(self, package_id: str, version: int) -> list[PackageFile]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT snapshot_json
                FROM export_files
                WHERE package_id = ? AND version = ?
                ORDER BY file_name ASC
                """,
                (package_id, version),
            ).fetchall()
        return [PackageFile.model_validate_json(row["snapshot_json"]) for row in rows]

    def save_validation(self, report: PackageValidationReport) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO validation_results(
                    package_id, version, passed, created_at, report_json
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(package_id, version) DO UPDATE SET
                    passed = excluded.passed,
                    created_at = excluded.created_at,
                    report_json = excluded.report_json
                """,
                (
                    report.package_id,
                    report.version,
                    int(report.passed),
                    report.created_at,
                    report.model_dump_json(),
                ),
            )

    def get_validation(
        self,
        package_id: str,
        version: int,
    ) -> PackageValidationReport | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT report_json
                FROM validation_results
                WHERE package_id = ? AND version = ?
                """,
                (package_id, version),
            ).fetchone()
        if row is None:
            return None
        return PackageValidationReport.model_validate_json(row["report_json"])

    def save_exam_attempt(self, record: ImportedExamAttemptRecord) -> bool:
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO package_exam_attempts(
                    attempt_id, package_id, package_version, file_id, exam_id,
                    completed_at, imported_at, record_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.attempt.attempt_id,
                    record.attempt.package_id,
                    record.attempt.package_version,
                    record.attempt.file_id,
                    record.attempt.exam_id,
                    record.attempt.completed_at,
                    record.imported_at,
                    record.model_dump_json(),
                ),
            )
        return cursor.rowcount == 1

    def get_exam_attempt(self, attempt_id: str) -> ImportedExamAttemptRecord | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT record_json
                FROM package_exam_attempts
                WHERE attempt_id = ?
                """,
                (attempt_id,),
            ).fetchone()
        if row is None:
            return None
        return ImportedExamAttemptRecord.model_validate_json(row["record_json"])

    def list_exam_attempts(self, package_id: str) -> list[ImportedExamAttemptRecord]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT record_json
                FROM package_exam_attempts
                WHERE package_id = ?
                ORDER BY completed_at DESC, attempt_id DESC
                """,
                (package_id,),
            ).fetchall()
        return [
            ImportedExamAttemptRecord.model_validate_json(row["record_json"])
            for row in rows
        ]

    def save_job(self, job: PackageGenerationJob) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO generation_jobs(
                    job_id, package_id, version, status, current_step, created_at,
                    updated_at, completed_at, error_message, snapshot_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    status = excluded.status,
                    current_step = excluded.current_step,
                    updated_at = excluded.updated_at,
                    completed_at = excluded.completed_at,
                    error_message = excluded.error_message,
                    snapshot_json = excluded.snapshot_json
                """,
                (
                    job.job_id,
                    job.package_id,
                    job.version,
                    job.status.value,
                    job.current_step,
                    job.created_at,
                    job.updated_at,
                    job.completed_at,
                    job.error_message,
                    job.model_dump_json(),
                ),
            )

    def get_job(self, job_id: str) -> PackageGenerationJob | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT snapshot_json FROM generation_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        if row is None:
            return None
        return PackageGenerationJob.model_validate_json(row["snapshot_json"])

    def get_latest_job(self, package_id: str) -> PackageGenerationJob | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT snapshot_json
                FROM generation_jobs
                WHERE package_id = ?
                ORDER BY created_at DESC, job_id DESC
                LIMIT 1
                """,
                (package_id,),
            ).fetchone()
        if row is None:
            return None
        return PackageGenerationJob.model_validate_json(row["snapshot_json"])

    def list_incomplete_jobs(self) -> list[PackageGenerationJob]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT snapshot_json
                FROM generation_jobs
                WHERE status IN (?, ?)
                ORDER BY created_at ASC
                """,
                (PackageJobStatus.QUEUED.value, PackageJobStatus.RUNNING.value),
            ).fetchall()
        return [PackageGenerationJob.model_validate_json(row["snapshot_json"]) for row in rows]

    @staticmethod
    def _row_to_package(row: sqlite3.Row | None) -> PackageRecord | None:
        if row is None:
            return None
        return PackageRecord.model_validate_json(row["record_json"])

    @staticmethod
    def _file_parameters(file: PackageFile) -> tuple[object, ...]:
        return (
            file.package_id,
            file.version,
            file.file_id,
            file.kind.value,
            file.file_name,
            file.media_type,
            file.size_bytes,
            file.sha256,
            file.content_count,
            file.artifact_path,
            file.model_dump_json(),
        )
