from typing import Protocol

from ..packages.models import (
    PackageFile,
    PackageGenerationJob,
    PackageGenerationJobStep,
    PackageRecord,
    PackageValidationReport,
    PackageVersion,
)
from ..packages.completed_exam import ImportedExamAttemptRecord


class PackageStore(Protocol):
    def create_package(self, record: PackageRecord) -> PackageRecord:
        ...

    def get_package(self, package_id: str) -> PackageRecord | None:
        ...

    def list_packages(self, course_id: str) -> list[PackageRecord]:
        ...

    def save_version(self, version: PackageVersion) -> None:
        ...

    def get_version(self, package_id: str, version: int) -> PackageVersion | None:
        ...

    def list_versions(self, package_id: str) -> list[PackageVersion]:
        ...

    def replace_files(
        self,
        package_id: str,
        version: int,
        files: list[PackageFile],
    ) -> None:
        ...

    def list_files(self, package_id: str, version: int) -> list[PackageFile]:
        ...

    def save_validation(self, report: PackageValidationReport) -> None:
        ...

    def get_validation(
        self,
        package_id: str,
        version: int,
    ) -> PackageValidationReport | None:
        ...

    def save_exam_attempt(self, record: ImportedExamAttemptRecord) -> bool:
        ...

    def get_exam_attempt(self, attempt_id: str) -> ImportedExamAttemptRecord | None:
        ...

    def list_exam_attempts(self, package_id: str) -> list[ImportedExamAttemptRecord]:
        ...


class PackageJobStore(Protocol):
    def save_job(self, job: PackageGenerationJob) -> None:
        ...

    def save_job_step(self, step: PackageGenerationJobStep) -> None:
        ...

    def get_job(self, job_id: str) -> PackageGenerationJob | None:
        ...

    def get_latest_job(self, package_id: str) -> PackageGenerationJob | None:
        ...

    def list_incomplete_jobs(self) -> list[PackageGenerationJob]:
        ...
