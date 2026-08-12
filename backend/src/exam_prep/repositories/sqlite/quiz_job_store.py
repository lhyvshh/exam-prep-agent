import json
from datetime import UTC, datetime
from uuid import uuid4

from exam_prep.db.sqlite import SQLiteDatabase
from exam_prep.repositories.quiz_job_store import QuizJobStore
from exam_prep.schemas.quiz import (
    QuestionGenerationAttempt,
    QuizBundle,
    QuizGenerationAcceptedResponse,
    QuizGenerationJobProgress,
    QuizGenerationJobResponse,
    QuizGenerationJobStatus,
    QuizGenerationRequest,
    QuizGenerationResultItem,
)


class SQLiteQuizJobStore(QuizJobStore):
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def create_job(
        self,
        *,
        job_id: str,
        dedupe_key: str,
        request: QuizGenerationRequest,
        provider: str,
        model: str,
    ) -> QuizGenerationAcceptedResponse:
        created_at = datetime.now(UTC).isoformat()
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO quiz_generation_jobs(
                    job_id, dedupe_key, status, request_payload_json, provider, model,
                    total_questions, completed_questions, fallback_questions, error_count,
                    created_at, started_at, completed_at, last_heartbeat_at, failure_reason, cancel_requested
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 0, ?, NULL, NULL, ?, NULL, 0)
                """,
                (
                    job_id,
                    dedupe_key,
                    QuizGenerationJobStatus.QUEUED.value,
                    request.model_dump_json(),
                    provider,
                    model,
                    request.question_count,
                    created_at,
                    created_at,
                ),
            )
        return QuizGenerationAcceptedResponse(
            job_id=job_id,
            status=QuizGenerationJobStatus.QUEUED,
            created_at=created_at,
            dedupe_key=dedupe_key,
        )

    def find_active_job_by_dedupe_key(self, dedupe_key: str) -> QuizGenerationAcceptedResponse | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT job_id, status, created_at, dedupe_key
                FROM quiz_generation_jobs
                WHERE dedupe_key = ?
                  AND status IN (?, ?)
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (
                    dedupe_key,
                    QuizGenerationJobStatus.QUEUED.value,
                    QuizGenerationJobStatus.RUNNING.value,
                ),
            ).fetchone()
        if row is None:
            return None
        return QuizGenerationAcceptedResponse(
            job_id=row["job_id"],
            status=QuizGenerationJobStatus(row["status"]),
            created_at=row["created_at"],
            dedupe_key=row["dedupe_key"],
        )

    def get_job(self, job_id: str) -> QuizGenerationJobResponse | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT job_id, dedupe_key, status, request_payload_json, provider, model,
                       total_questions, completed_questions, fallback_questions, error_count,
                       created_at, started_at, completed_at, last_heartbeat_at, failure_reason
                FROM quiz_generation_jobs
                WHERE job_id = ?
                """,
                (job_id,),
            ).fetchone()
            if row is None:
                return None
            result_rows = connection.execute(
                """
                SELECT job_id, question_id, ordinal, source_id, section_title, generation_mode, payload_json, created_at
                FROM quiz_generation_results
                WHERE job_id = ?
                ORDER BY ordinal ASC
                """,
                (job_id,),
            ).fetchall()

        request = QuizGenerationRequest.model_validate_json(row["request_payload_json"])
        partial_results = [
            QuizGenerationResultItem(
                job_id=result_row["job_id"],
                question_id=result_row["question_id"],
                ordinal=result_row["ordinal"],
                source_id=result_row["source_id"],
                section_title=result_row["section_title"],
                generation_mode=result_row["generation_mode"],
                created_at=result_row["created_at"],
                **json.loads(result_row["payload_json"]),
            )
            for result_row in result_rows
        ]
        quiz = None
        if partial_results:
            quiz = QuizBundle(
                quiz_id=job_id,
                course_id=request.course_id,
                module_id=request.module_id,
                query=request.query,
                questions=[item.question for item in partial_results],
            )

        return QuizGenerationJobResponse(
            job_id=row["job_id"],
            dedupe_key=row["dedupe_key"],
            status=QuizGenerationJobStatus(row["status"]),
            provider=row["provider"],
            model=row["model"],
            request_payload=request,
            progress=QuizGenerationJobProgress(
                total_questions=row["total_questions"],
                completed_questions=row["completed_questions"],
                fallback_questions=row["fallback_questions"],
                current_question_index=min(
                    row["completed_questions"] + 1,
                    row["total_questions"],
                )
                if row["status"] in {
                    QuizGenerationJobStatus.RUNNING.value,
                    QuizGenerationJobStatus.QUEUED.value,
                }
                else row["completed_questions"],
            ),
            quiz=quiz,
            partial_results=partial_results,
            error_summary=row["failure_reason"],
            created_at=row["created_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            last_heartbeat_at=row["last_heartbeat_at"],
        )

    def mark_running(self, job_id: str) -> None:
        now = datetime.now(UTC).isoformat()
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE quiz_generation_jobs
                SET status = ?, started_at = COALESCE(started_at, ?), last_heartbeat_at = ?
                WHERE job_id = ?
                """,
                (QuizGenerationJobStatus.RUNNING.value, now, now, job_id),
            )

    def update_progress(
        self,
        job_id: str,
        *,
        completed_questions: int,
        fallback_questions: int,
        current_question_index: int,
    ) -> None:
        del current_question_index
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE quiz_generation_jobs
                SET completed_questions = ?,
                    fallback_questions = ?,
                    last_heartbeat_at = ?
                WHERE job_id = ?
                """,
                (
                    completed_questions,
                    fallback_questions,
                    datetime.now(UTC).isoformat(),
                    job_id,
                ),
            )

    def append_result(self, result: QuizGenerationResultItem) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO quiz_generation_results(
                    job_id, question_id, ordinal, source_id, section_title, generation_mode, payload_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.job_id,
                    result.question_id,
                    result.ordinal,
                    result.source_id,
                    result.section_title,
                    result.generation_mode.value,
                    json.dumps(
                        {
                            "question": result.question.model_dump(mode="json"),
                            "answer_key": result.answer_key.model_dump(mode="json"),
                        }
                    ),
                    result.created_at,
                ),
            )

    def append_attempt(self, attempt: QuestionGenerationAttempt) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO question_generation_attempts(
                    attempt_id, job_id, question_id, attempt_number, provider, model,
                    latency_ms, response_phase, timeout_hit, error_type, request_id, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    uuid4().hex,
                    attempt.job_id,
                    attempt.question_id,
                    attempt.attempt_number,
                    attempt.provider,
                    attempt.model,
                    attempt.latency_ms,
                    attempt.response_phase,
                    int(attempt.timeout_hit),
                    attempt.error_type,
                    attempt.request_id,
                    attempt.created_at,
                ),
            )

    def mark_completed(
        self,
        job_id: str,
        *,
        status: QuizGenerationJobStatus,
        failure_reason: str | None = None,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE quiz_generation_jobs
                SET status = ?, completed_at = ?, last_heartbeat_at = ?, failure_reason = ?
                WHERE job_id = ?
                """,
                (status.value, now, now, failure_reason, job_id),
            )

    def increment_error_count(self, job_id: str, *, failure_reason: str | None = None) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE quiz_generation_jobs
                SET error_count = error_count + 1,
                    failure_reason = COALESCE(?, failure_reason),
                    last_heartbeat_at = ?
                WHERE job_id = ?
                """,
                (failure_reason, datetime.now(UTC).isoformat(), job_id),
            )

    def request_cancel(self, job_id: str) -> QuizGenerationJobStatus | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT status FROM quiz_generation_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            if row is None:
                return None
            current_status = QuizGenerationJobStatus(row["status"])
            if current_status in {
                QuizGenerationJobStatus.COMPLETED,
                QuizGenerationJobStatus.PARTIAL,
                QuizGenerationJobStatus.FAILED,
                QuizGenerationJobStatus.CANCELLED,
            }:
                return current_status
            connection.execute(
                """
                UPDATE quiz_generation_jobs
                SET cancel_requested = 1,
                    last_heartbeat_at = ?
                WHERE job_id = ?
                """,
                (datetime.now(UTC).isoformat(), job_id),
            )
            return current_status

    def is_cancel_requested(self, job_id: str) -> bool:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT cancel_requested FROM quiz_generation_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        return bool(row["cancel_requested"]) if row is not None else False

    def list_incomplete_jobs(self) -> list[str]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT job_id
                FROM quiz_generation_jobs
                WHERE status IN (?, ?)
                ORDER BY created_at ASC
                """,
                (
                    QuizGenerationJobStatus.QUEUED.value,
                    QuizGenerationJobStatus.RUNNING.value,
                ),
            ).fetchall()
        return [row["job_id"] for row in rows]
