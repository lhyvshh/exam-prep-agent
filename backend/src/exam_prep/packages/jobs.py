from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime
import re
from threading import Lock
from uuid import uuid4

from ..repositories.package_store import PackageJobStore

from .models import PackageGenerationJob, PackageGenerationJobStep, PackageJobStatus
from .service import PackageService


class PackageJobRunner:
    def __init__(
        self,
        *,
        service: PackageService,
        job_store: PackageJobStore,
    ) -> None:
        self.service = service
        self.job_store = job_store
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="package-build")
        self.futures: dict[str, Future[None]] = {}
        self.lock = Lock()

    def submit(self, package_id: str) -> PackageGenerationJob:
        version = self.service.prepare_build(package_id)
        now = self._now()
        job = PackageGenerationJob(
            job_id=uuid4().hex,
            package_id=package_id,
            version=version.version,
            status=PackageJobStatus.QUEUED,
            current_step="queued",
            expected_questions=(
                version.configuration.mock_exam_count
                * version.configuration.questions_per_exam
            ),
            created_at=now,
            updated_at=now,
        )
        self.job_store.save_job(job)
        self._schedule(job)
        return job

    def get(self, job_id: str) -> PackageGenerationJob | None:
        return self.job_store.get_job(job_id)

    def latest(self, package_id: str) -> PackageGenerationJob | None:
        return self.job_store.get_latest_job(package_id)

    def resume_incomplete_jobs(self) -> None:
        for job in self.job_store.list_incomplete_jobs():
            self._schedule(job.model_copy(update={"status": PackageJobStatus.QUEUED}))

    def cancel(self, job_id: str) -> PackageGenerationJob | None:
        job = self.job_store.get_job(job_id)
        if job is None:
            return None
        with self.lock:
            future = self.futures.get(job_id)
            if future is None or not future.cancel():
                return job
        cancelled = job.model_copy(
            update={
                "status": PackageJobStatus.CANCELLED,
                "current_step": "cancelled",
                "updated_at": self._now(),
                "completed_at": self._now(),
            }
        )
        self.job_store.save_job(cancelled)
        return cancelled

    def shutdown(self) -> None:
        self.executor.shutdown(wait=True, cancel_futures=False)

    def _schedule(self, job: PackageGenerationJob) -> None:
        with self.lock:
            existing = self.futures.get(job.job_id)
            if existing is not None and not existing.done():
                return
            self.futures[job.job_id] = self.executor.submit(self._run, job)

    def _run(self, job: PackageGenerationJob) -> None:
        version = self.service.get_version(job.package_id)
        running = job.model_copy(
            update={
                "status": PackageJobStatus.RUNNING,
                "current_step": "assemble",
                "updated_at": self._now(),
            }
        )
        self.job_store.save_job(running)
        self.job_store.save_job_step(
            PackageGenerationJobStep(
                job_id=running.job_id,
                step_name="assemble",
                status=PackageJobStatus.RUNNING,
                input_fingerprint=version.source_fingerprint,
                checkpoint_json=f'{{"version":{running.version}}}',
                attempts=1,
                output_version=running.version,
                updated_at=self._now(),
            )
        )
        try:
            result = self.service.build(job.package_id)
            counts = result.manifest.content_counts
            completed = running.model_copy(
                update={
                    "status": PackageJobStatus.COMPLETE,
                    "current_step": "complete",
                    "accepted_flashcards": counts.flashcards,
                    "expected_flashcards": counts.concepts * 10,
                    "accepted_questions": counts.exam_questions,
                    "artifact_size_bytes": result.zip_path.stat().st_size,
                    "updated_at": self._now(),
                    "completed_at": self._now(),
                }
            )
            self.job_store.save_job_step(
                PackageGenerationJobStep(
                    job_id=completed.job_id,
                    step_name="assemble",
                    status=PackageJobStatus.COMPLETE,
                    input_fingerprint=version.source_fingerprint,
                    accepted_count=counts.exam_questions,
                    checkpoint_json=f'{{"version":{completed.version}}}',
                    attempts=1,
                    output_version=completed.version,
                    updated_at=self._now(),
                )
            )
        except Exception as exc:
            message = self._sanitize_error(str(exc))
            self.service.mark_failed(job.package_id)
            completed = running.model_copy(
                update={
                    "status": PackageJobStatus.FAILED,
                    "current_step": "failed",
                    "updated_at": self._now(),
                    "completed_at": self._now(),
                    "error_message": message,
                }
            )
            self.job_store.save_job_step(
                PackageGenerationJobStep(
                    job_id=completed.job_id,
                    step_name="assemble",
                    status=PackageJobStatus.FAILED,
                    input_fingerprint=version.source_fingerprint,
                    checkpoint_json=f'{{"version":{completed.version}}}',
                    attempts=1,
                    error_message=message,
                    output_version=completed.version,
                    updated_at=self._now(),
                )
            )
        self.job_store.save_job(completed)

    @staticmethod
    def _sanitize_error(message: str) -> str:
        return re.sub(r"(?<!\S)/(?:[^\s/]+/)*[^\s:]+", "[redacted-path]", message)

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()
