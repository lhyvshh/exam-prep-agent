import json
from datetime import UTC, datetime
from uuid import uuid4

from exam_prep.db.sqlite import SQLiteDatabase
from exam_prep.repositories.activity_store import ActivityStore
from exam_prep.schemas.activity import (
    ActivityEventCreate,
    ActivityEventRecord,
    ActivityEventType,
    FlashcardReviewCreate,
    FlashcardReviewRecord,
    FlashcardReviewRating,
    GeneratedContentQualityFlagCreate,
    GeneratedContentQualityFlagRecord,
    GeneratedContentQualityFlagType,
    QuestionAttemptCreate,
    QuestionAttemptRecord,
    StudySessionEndRequest,
    StudySessionRecord,
    StudySessionStartRequest,
)


class SQLiteActivityStore(ActivityStore):
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def record_event(self, event: ActivityEventCreate) -> ActivityEventRecord:
        record = ActivityEventRecord(
            id=uuid4().hex,
            timestamp=_now_iso(),
            **event.model_dump(),
        )
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO user_events(
                    id, user_id, course_id, module_id, material_id, section_id,
                    concept_id, quiz_id, question_id, question_type, difficulty,
                    event_type, metadata_json, timestamp
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.user_id,
                    record.course_id,
                    record.module_id,
                    record.material_id,
                    record.section_id,
                    record.concept_id,
                    record.quiz_id,
                    record.question_id,
                    record.question_type,
                    record.difficulty,
                    record.event_type.value,
                    json.dumps(record.metadata_json),
                    record.timestamp,
                ),
            )
        return record

    def list_events(
        self,
        *,
        user_id: str | None = None,
        course_id: str | None = None,
        quiz_id: str | None = None,
        event_type: ActivityEventType | None = None,
    ) -> list[ActivityEventRecord]:
        where, params = _filters(
            {
                "user_id": user_id,
                "course_id": course_id,
                "quiz_id": quiz_id,
                "event_type": event_type.value if event_type else None,
            }
        )
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT id, user_id, course_id, module_id, material_id, section_id,
                       concept_id, quiz_id, question_id, question_type, difficulty,
                       event_type, metadata_json, timestamp
                FROM user_events
                {where}
                ORDER BY timestamp DESC
                LIMIT 200
                """,
                params,
            ).fetchall()
        return [self._event_from_row(row) for row in rows]

    def start_study_session(self, request: StudySessionStartRequest) -> StudySessionRecord:
        record = StudySessionRecord(
            id=uuid4().hex,
            started_at=_now_iso(),
            ended_at=None,
            duration_seconds=None,
            **request.model_dump(),
        )
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO study_sessions(
                    id, user_id, course_id, module_id, material_id, section_id,
                    started_at, ended_at, duration_seconds, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.user_id,
                    record.course_id,
                    record.module_id,
                    record.material_id,
                    record.section_id,
                    record.started_at,
                    record.ended_at,
                    record.duration_seconds,
                    json.dumps(record.metadata_json),
                ),
            )
        self.record_event(
            ActivityEventCreate(
                user_id=record.user_id,
                course_id=record.course_id,
                module_id=record.module_id,
                material_id=record.material_id,
                section_id=record.section_id,
                event_type=ActivityEventType.STUDY_SESSION_STARTED,
                metadata_json={"study_session_id": record.id, **record.metadata_json},
            )
        )
        return record

    def end_study_session(
        self,
        session_id: str,
        request: StudySessionEndRequest,
    ) -> StudySessionRecord | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT id, user_id, course_id, module_id, material_id, section_id,
                       started_at, ended_at, duration_seconds, metadata_json
                FROM study_sessions
                WHERE id = ?
                """,
                (session_id,),
            ).fetchone()
            if row is None:
                return None

            existing = self._session_from_row(row)
            ended_at = existing.ended_at or _now_iso()
            duration_seconds = existing.duration_seconds
            if duration_seconds is None:
                duration_seconds = max(
                    0,
                    int((_parse_iso(ended_at) - _parse_iso(existing.started_at)).total_seconds()),
                )
            metadata = {**existing.metadata_json, **request.metadata_json}
            connection.execute(
                """
                UPDATE study_sessions
                SET ended_at = ?, duration_seconds = ?, metadata_json = ?
                WHERE id = ?
                """,
                (ended_at, duration_seconds, json.dumps(metadata), session_id),
            )

        record = StudySessionRecord(
            id=existing.id,
            user_id=existing.user_id,
            course_id=existing.course_id,
            module_id=existing.module_id,
            material_id=existing.material_id,
            section_id=existing.section_id,
            started_at=existing.started_at,
            ended_at=ended_at,
            duration_seconds=duration_seconds,
            metadata_json=metadata,
        )
        self.record_event(
            ActivityEventCreate(
                user_id=record.user_id,
                course_id=record.course_id,
                module_id=record.module_id,
                material_id=record.material_id,
                section_id=record.section_id,
                event_type=ActivityEventType.STUDY_SESSION_ENDED,
                metadata_json={
                    "study_session_id": record.id,
                    "duration_seconds": record.duration_seconds,
                    **request.metadata_json,
                },
            )
        )
        return record

    def list_study_sessions(
        self,
        *,
        user_id: str | None = None,
        course_id: str | None = None,
    ) -> list[StudySessionRecord]:
        where, params = _filters({"user_id": user_id, "course_id": course_id})
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT id, user_id, course_id, module_id, material_id, section_id,
                       started_at, ended_at, duration_seconds, metadata_json
                FROM study_sessions
                {where}
                ORDER BY started_at DESC
                LIMIT 200
                """,
                params,
            ).fetchall()
        return [self._session_from_row(row) for row in rows]

    def record_question_attempt(self, attempt: QuestionAttemptCreate) -> QuestionAttemptRecord:
        attempt_number = self._next_attempt_number(
            user_id=attempt.user_id,
            quiz_id=attempt.quiz_id,
            question_id=attempt.question_id,
        )
        record = QuestionAttemptRecord(
            id=uuid4().hex,
            attempt_number=attempt_number,
            created_at=_now_iso(),
            **attempt.model_dump(),
        )
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO question_attempts(
                    id, user_id, quiz_id, question_id, course_id, module_id,
                    material_id, section_id, concept_id, selected_answer,
                    correct_answer, is_correct, time_spent_seconds, question_type,
                    difficulty, attempt_number, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.user_id,
                    record.quiz_id,
                    record.question_id,
                    record.course_id,
                    record.module_id,
                    record.material_id,
                    record.section_id,
                    record.concept_id,
                    record.selected_answer,
                    record.correct_answer,
                    int(record.is_correct),
                    record.time_spent_seconds,
                    record.question_type,
                    record.difficulty,
                    record.attempt_number,
                    record.created_at,
                ),
            )
        return record

    def list_question_attempts(
        self,
        *,
        user_id: str | None = None,
        course_id: str | None = None,
        quiz_id: str | None = None,
    ) -> list[QuestionAttemptRecord]:
        where, params = _filters(
            {
                "user_id": user_id,
                "course_id": course_id,
                "quiz_id": quiz_id,
            }
        )
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT id, user_id, quiz_id, question_id, course_id, module_id,
                       material_id, section_id, concept_id, selected_answer,
                       correct_answer, is_correct, time_spent_seconds, question_type,
                       difficulty, attempt_number, created_at
                FROM question_attempts
                {where}
                ORDER BY created_at DESC
                LIMIT 300
                """,
                params,
            ).fetchall()
        return [self._attempt_from_row(row) for row in rows]

    def record_flashcard_review(self, review: FlashcardReviewCreate) -> FlashcardReviewRecord:
        record = FlashcardReviewRecord(
            id=uuid4().hex,
            reviewed_at=_now_iso(),
            **review.model_dump(),
        )
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO flashcard_reviews(
                    id, user_id, course_id, module_id, material_id, section_id,
                    concept_id, flashcard_id, rating, previous_interval_days,
                    new_interval_days, previous_confidence_group,
                    new_confidence_group, metadata_json, reviewed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.user_id,
                    record.course_id,
                    record.module_id,
                    record.material_id,
                    record.section_id,
                    record.concept_id,
                    record.flashcard_id,
                    record.rating.value,
                    record.previous_interval_days,
                    record.new_interval_days,
                    record.previous_confidence_group,
                    record.new_confidence_group,
                    json.dumps(record.metadata_json),
                    record.reviewed_at,
                ),
            )
        return record

    def list_flashcard_reviews(
        self,
        *,
        user_id: str | None = None,
        course_id: str | None = None,
        material_id: str | None = None,
        concept_id: str | None = None,
        flashcard_id: str | None = None,
    ) -> list[FlashcardReviewRecord]:
        where, params = _filters(
            {
                "user_id": user_id,
                "course_id": course_id,
                "material_id": material_id,
                "concept_id": concept_id,
                "flashcard_id": flashcard_id,
            }
        )
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT id, user_id, course_id, module_id, material_id, section_id,
                       concept_id, flashcard_id, rating, previous_interval_days,
                       new_interval_days, previous_confidence_group,
                       new_confidence_group, metadata_json, reviewed_at
                FROM flashcard_reviews
                {where}
                ORDER BY reviewed_at DESC
                LIMIT 500
                """,
                params,
            ).fetchall()
        return [self._flashcard_review_from_row(row) for row in rows]

    def record_generated_content_quality_flag(
        self,
        flag: GeneratedContentQualityFlagCreate,
    ) -> GeneratedContentQualityFlagRecord:
        record = GeneratedContentQualityFlagRecord(
            id=uuid4().hex,
            created_at=_now_iso(),
            **flag.model_dump(),
        )
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO generated_content_quality_flags(
                    id, course_id, material_id, section_id, concept_id,
                    content_id, content_type, flag_type, reason, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.course_id,
                    record.material_id,
                    record.section_id,
                    record.concept_id,
                    record.content_id,
                    record.content_type,
                    record.flag_type.value,
                    record.reason,
                    record.created_at,
                ),
            )
        return record

    def list_generated_content_quality_flags(
        self,
        *,
        course_id: str | None = None,
        material_id: str | None = None,
        section_id: str | None = None,
        concept_id: str | None = None,
        content_id: str | None = None,
        flag_type: GeneratedContentQualityFlagType | None = None,
    ) -> list[GeneratedContentQualityFlagRecord]:
        where, params = _filters(
            {
                "course_id": course_id,
                "material_id": material_id,
                "section_id": section_id,
                "concept_id": concept_id,
                "content_id": content_id,
                "flag_type": flag_type.value if flag_type else None,
            }
        )
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT id, course_id, material_id, section_id, concept_id,
                       content_id, content_type, flag_type, reason, created_at
                FROM generated_content_quality_flags
                {where}
                ORDER BY created_at DESC
                LIMIT 500
                """,
                params,
            ).fetchall()
        return [self._quality_flag_from_row(row) for row in rows]

    def _next_attempt_number(self, *, user_id: str, quiz_id: str, question_id: str) -> int:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS attempt_count
                FROM question_attempts
                WHERE user_id = ? AND quiz_id = ? AND question_id = ?
                """,
                (user_id, quiz_id, question_id),
            ).fetchone()
        return int(row["attempt_count"]) + 1

    def _event_from_row(self, row) -> ActivityEventRecord:  # noqa: ANN001
        return ActivityEventRecord(
            id=row["id"],
            user_id=row["user_id"],
            course_id=row["course_id"],
            module_id=row["module_id"],
            material_id=row["material_id"],
            section_id=row["section_id"],
            concept_id=row["concept_id"],
            quiz_id=row["quiz_id"],
            question_id=row["question_id"],
            question_type=row["question_type"],
            difficulty=row["difficulty"],
            event_type=ActivityEventType(row["event_type"]),
            metadata_json=json.loads(row["metadata_json"] or "{}"),
            timestamp=row["timestamp"],
        )

    def _session_from_row(self, row) -> StudySessionRecord:  # noqa: ANN001
        return StudySessionRecord(
            id=row["id"],
            user_id=row["user_id"],
            course_id=row["course_id"],
            module_id=row["module_id"],
            material_id=row["material_id"],
            section_id=row["section_id"],
            started_at=row["started_at"],
            ended_at=row["ended_at"],
            duration_seconds=row["duration_seconds"],
            metadata_json=json.loads(row["metadata_json"] or "{}"),
        )

    def _attempt_from_row(self, row) -> QuestionAttemptRecord:  # noqa: ANN001
        return QuestionAttemptRecord(
            id=row["id"],
            user_id=row["user_id"],
            quiz_id=row["quiz_id"],
            question_id=row["question_id"],
            course_id=row["course_id"],
            module_id=row["module_id"],
            material_id=row["material_id"],
            section_id=row["section_id"],
            concept_id=row["concept_id"],
            selected_answer=row["selected_answer"],
            correct_answer=row["correct_answer"],
            is_correct=bool(row["is_correct"]),
            time_spent_seconds=row["time_spent_seconds"],
            question_type=row["question_type"],
            difficulty=row["difficulty"],
            attempt_number=row["attempt_number"],
            created_at=row["created_at"],
        )

    def _flashcard_review_from_row(self, row) -> FlashcardReviewRecord:  # noqa: ANN001
        return FlashcardReviewRecord(
            id=row["id"],
            user_id=row["user_id"],
            course_id=row["course_id"],
            module_id=row["module_id"],
            material_id=row["material_id"],
            section_id=row["section_id"],
            concept_id=row["concept_id"],
            flashcard_id=row["flashcard_id"],
            rating=FlashcardReviewRating(row["rating"]),
            previous_interval_days=row["previous_interval_days"],
            new_interval_days=row["new_interval_days"],
            previous_confidence_group=row["previous_confidence_group"],
            new_confidence_group=row["new_confidence_group"],
            metadata_json=json.loads(row["metadata_json"] or "{}"),
            reviewed_at=row["reviewed_at"],
        )

    def _quality_flag_from_row(self, row) -> GeneratedContentQualityFlagRecord:  # noqa: ANN001
        return GeneratedContentQualityFlagRecord(
            id=row["id"],
            course_id=row["course_id"],
            material_id=row["material_id"],
            section_id=row["section_id"],
            concept_id=row["concept_id"],
            content_id=row["content_id"],
            content_type=row["content_type"],
            flag_type=GeneratedContentQualityFlagType(row["flag_type"]),
            reason=row["reason"],
            created_at=row["created_at"],
        )


def _filters(filters: dict[str, object | None]) -> tuple[str, tuple[object, ...]]:
    clauses: list[str] = []
    params: list[object] = []
    for column, value in filters.items():
        if value is None:
            continue
        clauses.append(f"{column} = ?")
        params.append(value)
    if not clauses:
        return "", tuple()
    return "WHERE " + " AND ".join(clauses), tuple(params)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)
