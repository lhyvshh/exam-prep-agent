from pathlib import Path

import pytest

from exam_prep.db.sqlite import SQLiteDatabase
from exam_prep.packages.models import (
    PackageCreateRequest,
    PackageFile,
    PackageFileKind,
    PackageGenerationJob,
    PackageGenerationJobStep,
    PackageJobStatus,
    PackageRecord,
    PackageStatus,
    PackageValidationReport,
    PackageVersion,
)
from exam_prep.packages.completed_exam import (
    CompletedExamAttempt,
    ImportedExamAttemptRecord,
)
from exam_prep.schemas.exam import MockExamGradeResponse
from exam_prep.repositories.sqlite.package_store import SQLitePackageStore


def _package_fixture() -> PackageRecord:
    return PackageRecord(
        package_id="package-1",
        course_id="course-1",
        title="FRM Part I Offline Package",
        exam_name="Financial Risk Manager",
        exam_part="Part I",
        status=PackageStatus.BUILDING,
        active_version=1,
        created_at="2026-07-13T12:00:00Z",
        updated_at="2026-07-13T12:00:00Z",
    )


def _version_fixture(package_id: str) -> PackageVersion:
    return PackageVersion(
        package_id=package_id,
        version=1,
        status=PackageStatus.BUILDING,
        configuration=PackageCreateRequest(
            course_id="course-1",
            title="FRM Part I Offline Package",
        ),
        created_at="2026-07-13T12:00:00Z",
        source_fingerprint="source-fingerprint-1",
    )


def _file_fixture(package_id: str) -> PackageFile:
    return PackageFile(
        file_id="file-1",
        package_id=package_id,
        version=1,
        kind=PackageFileKind.FLASHCARDS,
        file_name="Book-1-Flashcards.html",
        media_type="text/html",
        size_bytes=1024,
        sha256="a" * 64,
        content_count=10,
        artifact_path="packages/package-1/v1/Book-1-Flashcards.html",
    )


def test_package_store_round_trips_version_and_files(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "packages.sqlite3")
    database.initialize()
    store = SQLitePackageStore(database)
    package = _package_fixture()
    version = _version_fixture(package.package_id)
    file = _file_fixture(package.package_id)

    assert store.create_package(package) == package
    store.save_version(version)
    version_two = version.model_copy(
        update={
            "version": 2,
            "created_at": "2026-07-13T12:05:00Z",
            "source_fingerprint": "source-fingerprint-2",
        }
    )
    store.save_version(version_two)
    store.replace_files(package.package_id, version.version, [file])

    assert store.get_package(package.package_id) == package
    assert store.list_packages(package.course_id) == [package]
    assert store.get_version(package.package_id, version.version) == version
    assert store.list_versions(package.package_id) == [version_two, version]
    assert store.list_files(package.package_id, version.version) == [file]


def test_package_store_round_trips_validation_report(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "packages.sqlite3")
    database.initialize()
    store = SQLitePackageStore(database)
    report = PackageValidationReport(
        package_id="package-1",
        version=1,
        passed=True,
        created_at="2026-07-13T12:04:00Z",
    )

    store.save_validation(report)

    assert store.get_validation(report.package_id, report.version) == report


def test_package_store_refuses_to_overwrite_completed_version(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "packages.sqlite3")
    database.initialize()
    store = SQLitePackageStore(database)
    version = _version_fixture("package-1").model_copy(
        update={"status": PackageStatus.COMPLETE, "completed_at": "2026-07-13T12:10:00Z"}
    )

    store.save_version(version)

    with pytest.raises(ValueError, match="completed package versions are immutable"):
        store.save_version(version.model_copy(update={"status": PackageStatus.FAILED}))


def test_package_store_returns_latest_job_for_package(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "packages.sqlite3")
    database.initialize()
    store = SQLitePackageStore(database)
    older = PackageGenerationJob(
        job_id="job-older",
        package_id="package-1",
        version=1,
        status=PackageJobStatus.FAILED,
        created_at="2026-07-13T12:00:00Z",
        updated_at="2026-07-13T12:01:00Z",
    )
    latest = older.model_copy(
        update={
            "job_id": "job-latest",
            "status": PackageJobStatus.COMPLETE,
            "created_at": "2026-07-13T12:02:00Z",
            "updated_at": "2026-07-13T12:03:00Z",
        }
    )

    store.save_job(older)
    store.save_job(latest)

    assert store.get_latest_job("package-1") == latest


def test_package_store_persists_generation_step_checkpoint(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "packages.sqlite3")
    database.initialize()
    store = SQLitePackageStore(database)
    step = PackageGenerationJobStep(
        job_id="job-1",
        step_name="assemble",
        status=PackageJobStatus.RUNNING,
        input_fingerprint="source-fingerprint-1",
        accepted_count=40,
        rejected_count=0,
        checkpoint_json='{"version":2}',
        attempts=1,
        output_version=2,
        updated_at="2026-07-13T12:03:00Z",
    )

    store.save_job_step(step)

    with database.connect() as connection:
        row = connection.execute(
            """
            SELECT job_id, step_name, status, input_fingerprint, accepted_count,
                   rejected_count, checkpoint_json, attempts, output_version, updated_at
            FROM generation_job_steps
            WHERE job_id = ? AND step_name = ?
            """,
            (step.job_id, step.step_name),
        ).fetchone()
    assert row["job_id"] == step.job_id
    assert row["step_name"] == step.step_name
    assert row["status"] == step.status.value
    assert row["input_fingerprint"] == step.input_fingerprint
    assert row["accepted_count"] == step.accepted_count
    assert row["rejected_count"] == step.rejected_count
    assert row["checkpoint_json"] == step.checkpoint_json
    assert row["attempts"] == step.attempts
    assert row["output_version"] == step.output_version
    assert row["updated_at"] == step.updated_at


def test_package_store_round_trips_imported_exam_attempts(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "packages.sqlite3")
    database.initialize()
    store = SQLitePackageStore(database)
    attempt = CompletedExamAttempt(
        attempt_id="attempt-1",
        package_id="package-1",
        package_version=1,
        file_id="mock-exam-1",
        exam_id="exam-1",
        content_sha256="a" * 64,
        started_at="2026-08-06T12:00:00Z",
        completed_at="2026-08-06T13:00:00Z",
        remaining_seconds=10800,
        answers={"question-1": 2},
    )
    record = ImportedExamAttemptRecord(
        attempt=attempt,
        imported_at="2026-08-06T13:05:00Z",
        grade=MockExamGradeResponse(
            exam_id="exam-1",
            course_id="course-1",
            overall_score=100.0,
        ),
    )

    assert store.save_exam_attempt(record) is True
    assert store.save_exam_attempt(record) is False
    assert store.get_exam_attempt("attempt-1") == record
    assert store.list_exam_attempts("package-1") == [record]
