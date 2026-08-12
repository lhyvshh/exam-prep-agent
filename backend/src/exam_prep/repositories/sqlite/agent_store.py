import json
from datetime import UTC, datetime

from exam_prep.db.sqlite import SQLiteDatabase
from exam_prep.repositories.agent_store import AgentStore
from exam_prep.schemas.agent import AgentMemoryProfile, AgentRecommendation, AgentRunRecord
from exam_prep.schemas.graph import AgentMessage, NodeExecutionRecord, QualityCheckSummary
from exam_prep.schemas.scope import StudyScope

MCQ_QUIZ_FORMAT = "mcq"


class SQLiteAgentStore(AgentStore):
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def save_run(self, run: AgentRunRecord) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO agent_runs(
                    run_id, course_id, intent, scope_json, node_statuses_json,
                    agent_messages_json, recommendations_json, quality_summary_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.run_id,
                    run.course_id,
                    run.intent,
                    run.scope.model_dump_json(),
                    json.dumps([item.model_dump(mode="json") for item in run.node_statuses]),
                    json.dumps([item.model_dump(mode="json") for item in run.agent_messages]),
                    json.dumps([item.model_dump(mode="json") for item in run.recommendations]),
                    run.quality_summary.model_dump_json() if run.quality_summary else None,
                    run.created_at,
                ),
            )

    def get_latest_run(self, course_id: str) -> AgentRunRecord | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT run_id, course_id, intent, scope_json, node_statuses_json,
                       agent_messages_json, recommendations_json, quality_summary_json, created_at
                FROM agent_runs
                WHERE course_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (course_id,),
            ).fetchone()
        if row is None:
            return None
        return self._run_from_row(row)

    def upsert_recommendations(self, recommendations: list[AgentRecommendation]) -> None:
        with self.database.connect() as connection:
            connection.executemany(
                """
                INSERT INTO agent_recommendations(
                    id, course_id, scope_json, agent_name, recommendation_type, title,
                    reason, target_action, target_payload_json, priority, created_at, dismissed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    course_id = excluded.course_id,
                    scope_json = excluded.scope_json,
                    agent_name = excluded.agent_name,
                    recommendation_type = excluded.recommendation_type,
                    title = excluded.title,
                    reason = excluded.reason,
                    target_action = excluded.target_action,
                    target_payload_json = excluded.target_payload_json,
                    priority = excluded.priority,
                    created_at = excluded.created_at,
                    dismissed_at = COALESCE(agent_recommendations.dismissed_at, excluded.dismissed_at)
                """,
                [
                    (
                        recommendation.id,
                        recommendation.course_id,
                        recommendation.scope.model_dump_json(),
                        recommendation.agent_name,
                        recommendation.recommendation_type,
                        recommendation.title,
                        recommendation.reason,
                        recommendation.target_action,
                        json.dumps(recommendation.target_payload),
                        recommendation.priority,
                        recommendation.created_at,
                        recommendation.dismissed_at,
                    )
                    for recommendation in recommendations
                ],
            )

    def list_recommendations(
        self,
        course_id: str,
        *,
        include_dismissed: bool = False,
    ) -> list[AgentRecommendation]:
        where_clause = "WHERE course_id = ?"
        params: tuple[object, ...] = (course_id,)
        if not include_dismissed:
            where_clause += " AND dismissed_at IS NULL"
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT id, course_id, scope_json, agent_name, recommendation_type, title,
                       reason, target_action, target_payload_json, priority, created_at, dismissed_at
                FROM agent_recommendations
                {where_clause}
                ORDER BY dismissed_at IS NOT NULL ASC, priority DESC, created_at DESC
                LIMIT 12
                """,
                params,
            ).fetchall()
        return [self._recommendation_from_row(row) for row in rows]

    def dismiss_recommendation(self, recommendation_id: str) -> bool:
        now = datetime.now(UTC).isoformat()
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE agent_recommendations
                SET dismissed_at = ?
                WHERE id = ? AND dismissed_at IS NULL
                """,
                (now, recommendation_id),
            )
        return cursor.rowcount > 0

    def get_memory(self, course_id: str) -> AgentMemoryProfile | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT course_id, preferred_study_style, preferred_quiz_format,
                       default_question_count, focus_areas_json, encouragement_style,
                       progress_notes_json, updated_at
                FROM agent_memory
                WHERE course_id = ?
                """,
                (course_id,),
            ).fetchone()
        if row is None:
            return None
        return self._memory_from_row(row)

    def save_memory(self, memory: AgentMemoryProfile) -> AgentMemoryProfile:
        updated = memory.model_copy(
            update={
                "preferred_quiz_format": MCQ_QUIZ_FORMAT,
                "updated_at": memory.updated_at or datetime.now(UTC).isoformat(),
            }
        )
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO agent_memory(
                    course_id, preferred_study_style, preferred_quiz_format,
                    default_question_count, focus_areas_json, encouragement_style,
                    progress_notes_json, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(course_id) DO UPDATE SET
                    preferred_study_style = excluded.preferred_study_style,
                    preferred_quiz_format = excluded.preferred_quiz_format,
                    default_question_count = excluded.default_question_count,
                    focus_areas_json = excluded.focus_areas_json,
                    encouragement_style = excluded.encouragement_style,
                    progress_notes_json = excluded.progress_notes_json,
                    updated_at = excluded.updated_at
                """,
                (
                    updated.course_id,
                    updated.preferred_study_style,
                    updated.preferred_quiz_format,
                    updated.default_question_count,
                    json.dumps(updated.focus_areas),
                    updated.encouragement_style,
                    json.dumps(updated.progress_notes),
                    updated.updated_at,
                ),
            )
        return updated

    def _run_from_row(self, row) -> AgentRunRecord:  # noqa: ANN001
        quality_summary = (
            QualityCheckSummary.model_validate_json(row["quality_summary_json"])
            if row["quality_summary_json"]
            else None
        )
        return AgentRunRecord(
            run_id=row["run_id"],
            course_id=row["course_id"],
            intent=row["intent"],
            scope=StudyScope.model_validate_json(row["scope_json"]),
            node_statuses=[
                NodeExecutionRecord.model_validate(item)
                for item in json.loads(row["node_statuses_json"] or "[]")
            ],
            agent_messages=[
                AgentMessage.model_validate(item)
                for item in json.loads(row["agent_messages_json"] or "[]")
            ],
            recommendations=[
                AgentRecommendation.model_validate(item)
                for item in json.loads(row["recommendations_json"] or "[]")
            ],
            quality_summary=quality_summary,
            created_at=row["created_at"],
        )

    def _recommendation_from_row(self, row) -> AgentRecommendation:  # noqa: ANN001
        return AgentRecommendation(
            id=row["id"],
            course_id=row["course_id"],
            scope=StudyScope.model_validate_json(row["scope_json"]),
            agent_name=row["agent_name"],
            recommendation_type=row["recommendation_type"],
            title=row["title"],
            reason=row["reason"],
            target_action=row["target_action"],
            target_payload=json.loads(row["target_payload_json"] or "{}"),
            priority=row["priority"],
            created_at=row["created_at"],
            dismissed_at=row["dismissed_at"],
        )

    def _memory_from_row(self, row) -> AgentMemoryProfile:  # noqa: ANN001
        return AgentMemoryProfile(
            course_id=row["course_id"],
            preferred_study_style=row["preferred_study_style"],
            preferred_quiz_format=MCQ_QUIZ_FORMAT,
            default_question_count=row["default_question_count"],
            focus_areas=json.loads(row["focus_areas_json"] or "[]"),
            encouragement_style=row["encouragement_style"],
            progress_notes=json.loads(row["progress_notes_json"] or "[]"),
            updated_at=row["updated_at"] or None,
        )
