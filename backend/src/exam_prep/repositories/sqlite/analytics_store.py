from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from hashlib import sha256
from statistics import mean
from typing import Any

from exam_prep.db.sqlite import SQLiteDatabase
from exam_prep.repositories.analytics_store import AnalyticsStore
from exam_prep.schemas.analytics import (
    AgentAnalyticsContextResponse,
    AnalyticsOverviewResponse,
    ConceptMasteryRecord,
    ModuleMasteryRecord,
    QuestionTypeMasteryRecord,
    RecommendationHistoryRecord,
)


class SQLiteAnalyticsStore(AnalyticsStore):
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def refresh_course(self, *, user_id: str, course_id: str) -> AnalyticsOverviewResponse:
        attempts = self._load_attempt_rows(user_id=user_id, course_id=course_id)
        study_time_by_material, study_time_by_section = self._load_study_time(
            user_id=user_id,
            course_id=course_id,
        )
        material_clicks = self._load_material_clicks(user_id=user_id, course_id=course_id)
        section_exam_weights = self._load_section_exam_weights(course_id=course_id)
        now = _now_iso()

        question_type_records = self._build_question_type_records(
            attempts=attempts,
            updated_at=now,
        )
        concept_records = self._build_concept_records(
            attempts=attempts,
            question_type_records=question_type_records,
            study_time_by_section=study_time_by_section,
            section_exam_weights=section_exam_weights,
            updated_at=now,
        )
        module_records = self._build_module_records(
            attempts=attempts,
            concept_records=concept_records,
            question_type_records=question_type_records,
            updated_at=now,
        )
        recommendations = self._build_recommendations(
            user_id=user_id,
            course_id=course_id,
            concept_records=concept_records,
            question_type_records=question_type_records,
            study_time_by_section=study_time_by_section,
            created_at=now,
        )

        with self.database.connect() as connection:
            connection.execute(
                "DELETE FROM concept_mastery WHERE user_id = ? AND course_id = ?",
                (user_id, course_id),
            )
            connection.execute(
                "DELETE FROM module_mastery WHERE user_id = ? AND course_id = ?",
                (user_id, course_id),
            )
            connection.execute(
                "DELETE FROM question_type_mastery WHERE user_id = ? AND course_id = ?",
                (user_id, course_id),
            )
            for record in concept_records:
                connection.execute(
                    """
                    INSERT INTO concept_mastery(
                        id, user_id, course_id, module_id, material_id, section_id,
                        concept_id, attempts, correct_attempts, accuracy, repeat_misses,
                        average_time_seconds, mastery_score, last_attempt_at, updated_at
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
                        record.attempts,
                        record.correct_attempts,
                        record.accuracy,
                        record.repeat_misses,
                        record.average_time_seconds,
                        record.mastery_score,
                        record.last_attempt_at,
                        record.updated_at,
                    ),
                )
            for record in module_records:
                connection.execute(
                    """
                    INSERT INTO module_mastery(
                        id, user_id, course_id, module_id, attempts, correct_attempts,
                        accuracy, average_time_seconds, mastery_score,
                        weak_concepts_json, weak_question_types_json, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.id,
                        record.user_id,
                        record.course_id,
                        record.module_id,
                        record.attempts,
                        record.correct_attempts,
                        record.accuracy,
                        record.average_time_seconds,
                        record.mastery_score,
                        json.dumps(record.weak_concepts),
                        json.dumps(record.weak_question_types),
                        record.updated_at,
                    ),
                )
            for record in question_type_records:
                connection.execute(
                    """
                    INSERT INTO question_type_mastery(
                        id, user_id, course_id, module_id, concept_id, question_type,
                        attempts, correct_attempts, accuracy, average_time_seconds, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.id,
                        record.user_id,
                        record.course_id,
                        record.module_id,
                        record.concept_id,
                        record.question_type,
                        record.attempts,
                        record.correct_attempts,
                        record.accuracy,
                        record.average_time_seconds,
                        record.updated_at,
                    ),
                )
            recommendation_ids = [record.id for record in recommendations]
            if recommendation_ids:
                placeholders = ", ".join("?" for _ in recommendation_ids)
                connection.execute(
                    f"""
                    DELETE FROM recommendation_history
                    WHERE user_id = ? AND course_id = ? AND completed = 0
                      AND id NOT IN ({placeholders})
                    """,
                    (user_id, course_id, *recommendation_ids),
                )
            else:
                connection.execute(
                    """
                    DELETE FROM recommendation_history
                    WHERE user_id = ? AND course_id = ? AND completed = 0
                    """,
                    (user_id, course_id),
                )
            for record in recommendations:
                existing = connection.execute(
                    """
                    SELECT clicked, completed, created_at
                    FROM recommendation_history
                    WHERE id = ?
                    """,
                    (record.id,),
                ).fetchone()
                clicked = bool(existing["clicked"]) if existing is not None else record.clicked
                completed = bool(existing["completed"]) if existing is not None else record.completed
                created_at = existing["created_at"] if existing is not None else record.created_at
                connection.execute(
                    """
                    INSERT OR REPLACE INTO recommendation_history(
                        id, user_id, course_id, recommendation_type, target_module_id,
                        target_section_id, target_concept_id, reason, priority_score,
                        clicked, completed, created_at, title, recommended_action
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.id,
                        record.user_id,
                        record.course_id,
                        record.recommendation_type,
                        record.target_module_id,
                        record.target_section_id,
                        record.target_concept_id,
                        record.reason,
                        record.priority_score,
                        int(clicked),
                        int(completed),
                        created_at,
                        record.title,
                        record.recommended_action,
                    ),
                )

        return self._build_overview(
            user_id=user_id,
            course_id=course_id,
            attempts=attempts,
            concept_records=concept_records,
            module_records=module_records,
            question_type_records=question_type_records,
            study_time_by_material=study_time_by_material,
            study_time_by_section=study_time_by_section,
            material_clicks=material_clicks,
        )

    def get_overview(self, *, user_id: str, course_id: str) -> AnalyticsOverviewResponse:
        return self.refresh_course(user_id=user_id, course_id=course_id)

    def list_modules(self, *, user_id: str, course_id: str) -> list[ModuleMasteryRecord]:
        self.refresh_course(user_id=user_id, course_id=course_id)
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, user_id, course_id, module_id, attempts, correct_attempts,
                       accuracy, average_time_seconds, mastery_score,
                       weak_concepts_json, weak_question_types_json, updated_at
                FROM module_mastery
                WHERE user_id = ? AND course_id = ?
                ORDER BY mastery_score ASC, attempts DESC
                """,
                (user_id, course_id),
            ).fetchall()
        records = [self._module_from_row(row) for row in rows]
        return sorted(records, key=lambda record: (-record.priority_score, record.mastery_score))

    def list_concepts(self, *, user_id: str, course_id: str) -> list[ConceptMasteryRecord]:
        self.refresh_course(user_id=user_id, course_id=course_id)
        records = self._select_concepts(user_id=user_id, course_id=course_id)
        return sorted(records, key=lambda record: (-record.priority_score, record.mastery_score))

    def list_question_types(self, *, user_id: str, course_id: str) -> list[QuestionTypeMasteryRecord]:
        self.refresh_course(user_id=user_id, course_id=course_id)
        records = self._select_question_types(user_id=user_id, course_id=course_id)
        return sorted(records, key=lambda record: (-record.priority_score, record.accuracy))

    def list_recommendations(self, *, user_id: str, course_id: str) -> list[RecommendationHistoryRecord]:
        self.refresh_course(user_id=user_id, course_id=course_id)
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, user_id, course_id, recommendation_type, target_module_id,
                       target_section_id, target_concept_id, reason, priority_score,
                       clicked, completed, created_at, title, recommended_action
                FROM recommendation_history
                WHERE user_id = ? AND course_id = ?
                ORDER BY completed ASC, clicked ASC, priority_score DESC, created_at DESC
                LIMIT 20
                """,
                (user_id, course_id),
            ).fetchall()
        return [self._recommendation_from_row(row) for row in rows]

    def get_agent_context(self, *, user_id: str, course_id: str) -> AgentAnalyticsContextResponse:
        overview = self.get_overview(user_id=user_id, course_id=course_id)
        return AgentAnalyticsContextResponse(
            user_id=user_id,
            course_id=course_id,
            overview=overview,
            weak_modules=self.list_modules(user_id=user_id, course_id=course_id)[:5],
            weak_concepts=self.list_concepts(user_id=user_id, course_id=course_id)[:8],
            weak_question_types=self.list_question_types(user_id=user_id, course_id=course_id)[:8],
            recommendations=self.list_recommendations(user_id=user_id, course_id=course_id)[:5],
        )

    def _load_attempt_rows(self, *, user_id: str, course_id: str) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, user_id, quiz_id, question_id, course_id, module_id,
                       material_id, section_id, concept_id, selected_answer,
                       correct_answer, is_correct, time_spent_seconds, question_type,
                       difficulty, attempt_number, created_at
                FROM question_attempts
                WHERE user_id = ? AND course_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (user_id, course_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def _load_study_time(self, *, user_id: str, course_id: str) -> tuple[dict[str, int], dict[str, int]]:
        material_totals: dict[str, int] = defaultdict(int)
        section_totals: dict[str, int] = defaultdict(int)
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT material_id, section_id, duration_seconds
                FROM study_sessions
                WHERE user_id = ? AND course_id = ?
                """,
                (user_id, course_id),
            ).fetchall()
        for row in rows:
            duration = max(0, int(row["duration_seconds"] or 0))
            if row["material_id"]:
                material_totals[row["material_id"]] += duration
            if row["section_id"]:
                section_totals[row["section_id"]] += duration
        return dict(material_totals), dict(section_totals)

    def _load_material_clicks(self, *, user_id: str, course_id: str) -> Counter[str]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT material_id
                FROM user_events
                WHERE user_id = ? AND course_id = ?
                  AND material_id IS NOT NULL
                  AND event_type IN ('material_opened', 'material_section_viewed', 'pdf_source_clicked')
                """,
                (user_id, course_id),
            ).fetchall()
        return Counter(row["material_id"] for row in rows if row["material_id"])

    def _load_section_exam_weights(self, *, course_id: str) -> dict[str, float]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT source_id, exam_weight
                FROM material_sections
                WHERE course_id = ?
                """,
                (course_id,),
            ).fetchall()
        return {
            row["source_id"]: float(row["exam_weight"])
            for row in rows
            if row["source_id"] and row["exam_weight"] is not None
        }

    def _build_question_type_records(
        self,
        *,
        attempts: list[dict[str, Any]],
        updated_at: str,
    ) -> list[QuestionTypeMasteryRecord]:
        grouped: dict[tuple[str, str, str, str | None, str | None, str], list[dict[str, Any]]] = defaultdict(list)
        for attempt in attempts:
            question_type = attempt["question_type"] or "mixed"
            key = (
                attempt["user_id"],
                attempt["course_id"],
                attempt["module_id"],
                attempt["concept_id"],
                question_type,
                question_type,
            )
            grouped[key].append(attempt)

        records: list[QuestionTypeMasteryRecord] = []
        for (user_id, course_id, module_id, concept_id, question_type, _), rows in grouped.items():
            attempts_count = len(rows)
            correct = sum(1 for row in rows if row["is_correct"])
            accuracy = _ratio(correct, attempts_count)
            avg_time = _average_time(rows)
            priority = round((1 - accuracy) * 60 + min(attempts_count, 5) * 4, 2)
            records.append(
                QuestionTypeMasteryRecord(
                    id=_stable_id("question_type_mastery", user_id, course_id, module_id, concept_id, question_type),
                    user_id=user_id,
                    course_id=course_id,
                    module_id=module_id,
                    concept_id=concept_id,
                    question_type=question_type,
                    attempts=attempts_count,
                    correct_attempts=correct,
                    accuracy=accuracy,
                    average_time_seconds=avg_time,
                    updated_at=updated_at,
                    priority_score=priority,
                )
            )
        return records

    def _build_concept_records(
        self,
        *,
        attempts: list[dict[str, Any]],
        question_type_records: list[QuestionTypeMasteryRecord],
        study_time_by_section: dict[str, int],
        section_exam_weights: dict[str, float],
        updated_at: str,
    ) -> list[ConceptMasteryRecord]:
        grouped: dict[tuple[str, str, str | None, str | None, str | None, str], list[dict[str, Any]]] = defaultdict(list)
        for attempt in attempts:
            concept_id = attempt["concept_id"] or attempt["section_id"] or attempt["question_id"] or "unknown-concept"
            key = (
                attempt["user_id"],
                attempt["course_id"],
                attempt["module_id"],
                attempt["material_id"],
                attempt["section_id"],
                concept_id,
            )
            grouped[key].append(attempt)

        weak_types_by_concept: dict[str, list[str]] = defaultdict(list)
        for record in question_type_records:
            if record.concept_id and record.accuracy < 0.65:
                weak_types_by_concept[record.concept_id].append(record.question_type)

        records: list[ConceptMasteryRecord] = []
        for (user_id, course_id, module_id, material_id, section_id, concept_id), rows in grouped.items():
            attempts_count = len(rows)
            correct = sum(1 for row in rows if row["is_correct"])
            repeat_misses = attempts_count - correct
            accuracy = _ratio(correct, attempts_count)
            avg_time = _average_time(rows)
            mastery_score = _mastery_score(
                attempts=attempts_count,
                correct_attempts=correct,
                repeat_misses=repeat_misses,
            )
            weak_types = sorted(set(weak_types_by_concept.get(concept_id, [])))
            priority = _priority_score(
                accuracy=accuracy,
                repeat_misses=repeat_misses,
                attempts=attempts_count,
                exam_weight=section_exam_weights.get(section_id or "", 0.5),
                review_seconds=study_time_by_section.get(section_id or "", 0),
                recent_weakness=_recent_weakness(rows),
                question_type_weakness=bool(weak_types),
            )
            records.append(
                ConceptMasteryRecord(
                    id=_stable_id("concept_mastery", user_id, course_id, module_id, material_id, section_id, concept_id),
                    user_id=user_id,
                    course_id=course_id,
                    module_id=module_id,
                    material_id=material_id,
                    section_id=section_id,
                    concept_id=concept_id,
                    attempts=attempts_count,
                    correct_attempts=correct,
                    accuracy=accuracy,
                    repeat_misses=repeat_misses,
                    average_time_seconds=avg_time,
                    mastery_score=mastery_score,
                    last_attempt_at=max((row["created_at"] for row in rows), default=None),
                    updated_at=updated_at,
                    priority_score=priority,
                    weak_question_types=weak_types,
                )
            )
        return records

    def _build_module_records(
        self,
        *,
        attempts: list[dict[str, Any]],
        concept_records: list[ConceptMasteryRecord],
        question_type_records: list[QuestionTypeMasteryRecord],
        updated_at: str,
    ) -> list[ModuleMasteryRecord]:
        grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
        for attempt in attempts:
            module_id = attempt["module_id"] or "unassigned"
            grouped[(attempt["user_id"], attempt["course_id"], module_id)].append(attempt)

        records: list[ModuleMasteryRecord] = []
        for (user_id, course_id, module_id), rows in grouped.items():
            attempts_count = len(rows)
            correct = sum(1 for row in rows if row["is_correct"])
            accuracy = _ratio(correct, attempts_count)
            avg_time = _average_time(rows)
            repeat_misses = attempts_count - correct
            weak_concepts = [
                _weak_concept_payload(record)
                for record in sorted(
                    concept_records,
                    key=lambda record: (-record.priority_score, record.mastery_score),
                )
                if (record.module_id or "unassigned") == module_id and (record.accuracy < 0.75 or record.repeat_misses)
            ][:8]
            weak_question_types = [
                _weak_question_type_payload(record)
                for record in sorted(question_type_records, key=lambda record: (-record.priority_score, record.accuracy))
                if (record.module_id or "unassigned") == module_id and record.accuracy < 0.75
            ][:8]
            mastery = _mastery_score(
                attempts=attempts_count,
                correct_attempts=correct,
                repeat_misses=repeat_misses,
            )
            priority = round((1 - accuracy) * 60 + min(repeat_misses, 5) * 5 + len(weak_concepts) * 2, 2)
            records.append(
                ModuleMasteryRecord(
                    id=_stable_id("module_mastery", user_id, course_id, module_id),
                    user_id=user_id,
                    course_id=course_id,
                    module_id=module_id,
                    attempts=attempts_count,
                    correct_attempts=correct,
                    accuracy=accuracy,
                    average_time_seconds=avg_time,
                    mastery_score=mastery,
                    weak_concepts=weak_concepts,
                    weak_question_types=weak_question_types,
                    updated_at=updated_at,
                    priority_score=priority,
                )
            )
        return records

    def _build_recommendations(
        self,
        *,
        user_id: str,
        course_id: str,
        concept_records: list[ConceptMasteryRecord],
        question_type_records: list[QuestionTypeMasteryRecord],
        study_time_by_section: dict[str, int],
        created_at: str,
    ) -> list[RecommendationHistoryRecord]:
        recommendations: list[RecommendationHistoryRecord] = []
        weak_question_type_by_concept: dict[str, QuestionTypeMasteryRecord] = {}
        for record in sorted(question_type_records, key=lambda item: (-item.priority_score, item.accuracy)):
            if record.concept_id and record.accuracy < 0.65:
                weak_question_type_by_concept.setdefault(record.concept_id, record)

        weak_concepts = [
            record
            for record in sorted(concept_records, key=lambda item: (-item.priority_score, item.mastery_score))
            if record.attempts >= 2 and (record.accuracy < 0.75 or record.repeat_misses >= 2)
        ]
        for record in weak_concepts[:8]:
            weak_type = weak_question_type_by_concept.get(record.concept_id)
            review_seconds = study_time_by_section.get(record.section_id or "", 0)
            action = _recommended_action(
                accuracy=record.accuracy,
                repeat_misses=record.repeat_misses,
                review_seconds=review_seconds,
                weak_question_type=weak_type.question_type if weak_type else None,
            )
            title = _recommendation_title(record)
            reason_parts = [
                f"Low accuracy ({round(record.accuracy * 100)}%)",
                f"{record.repeat_misses} repeated miss{'es' if record.repeat_misses != 1 else ''}",
            ]
            if weak_type:
                reason_parts.append(f"weak {weak_type.question_type} questions")
            reason = ", ".join(reason_parts) + "."
            recommendations.append(
                RecommendationHistoryRecord(
                    id=_stable_id("recommendation", user_id, course_id, record.concept_id, "weak_concept"),
                    user_id=user_id,
                    course_id=course_id,
                    recommendation_type="weak_concept",
                    title=title,
                    target_module_id=record.module_id,
                    target_section_id=record.section_id,
                    target_concept_id=record.concept_id,
                    reason=reason,
                    recommended_action=action,
                    priority_score=record.priority_score,
                    clicked=False,
                    completed=False,
                    created_at=created_at,
                )
            )
        return recommendations

    def _build_overview(
        self,
        *,
        user_id: str,
        course_id: str,
        attempts: list[dict[str, Any]],
        concept_records: list[ConceptMasteryRecord],
        module_records: list[ModuleMasteryRecord],
        question_type_records: list[QuestionTypeMasteryRecord],
        study_time_by_material: dict[str, int],
        study_time_by_section: dict[str, int],
        material_clicks: Counter[str],
    ) -> AnalyticsOverviewResponse:
        total_attempts = len(attempts)
        total_correct = sum(1 for attempt in attempts if attempt["is_correct"])
        accuracy = _ratio(total_correct, total_attempts)
        avg_question_time = _average_time(attempts)
        readiness = _exam_readiness_score(
            accuracy=accuracy,
            concept_records=concept_records,
            module_records=module_records,
            question_type_records=question_type_records,
        )
        difficulty_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for attempt in attempts:
            difficulty_groups[_difficulty_bucket(attempt["difficulty"])].append(attempt)
        completed_quizzes = {attempt["quiz_id"] for attempt in attempts if attempt["quiz_id"]}

        return AnalyticsOverviewResponse(
            user_id=user_id,
            course_id=course_id,
            accuracy_by_module={
                record.module_id: record.accuracy for record in module_records
            },
            accuracy_by_concept={
                record.concept_id: record.accuracy for record in concept_records
            },
            accuracy_by_question_type=_aggregate_question_type_accuracy(question_type_records),
            accuracy_by_difficulty={
                bucket: _ratio(sum(1 for row in rows if row["is_correct"]), len(rows))
                for bucket, rows in difficulty_groups.items()
            },
            average_time_per_question=avg_question_time,
            time_spent_per_material=study_time_by_material,
            time_spent_per_section=study_time_by_section,
            repeat_misses=sum(record.repeat_misses for record in concept_records),
            recent_improvement_trend=_recent_improvement_trend(attempts),
            quiz_completion_rate=1.0 if completed_quizzes else 0.0,
            most_clicked_materials=[
                {"material_id": material_id, "clicks": clicks}
                for material_id, clicks in material_clicks.most_common(5)
            ],
            least_reviewed_weak_materials=_least_reviewed_weak_materials(
                concept_records=concept_records,
                study_time_by_material=study_time_by_material,
            ),
            weak_concept_clusters=[
                _weak_concept_payload(record)
                for record in sorted(concept_records, key=lambda item: (-item.priority_score, item.mastery_score))
                if record.accuracy < 0.75 or record.repeat_misses >= 2
            ][:10],
            exam_readiness_score=readiness,
        )

    def _select_concepts(self, *, user_id: str, course_id: str) -> list[ConceptMasteryRecord]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, user_id, course_id, module_id, material_id, section_id,
                       concept_id, attempts, correct_attempts, accuracy, repeat_misses,
                       average_time_seconds, mastery_score, last_attempt_at, updated_at
                FROM concept_mastery
                WHERE user_id = ? AND course_id = ?
                """,
                (user_id, course_id),
            ).fetchall()
        records = [self._concept_from_row(row) for row in rows]
        priorities = {
            generated.concept_id: generated.priority_score
            for generated in self._build_concept_records(
                attempts=self._load_attempt_rows(user_id=user_id, course_id=course_id),
                question_type_records=self._select_question_types(user_id=user_id, course_id=course_id),
                study_time_by_section=self._load_study_time(user_id=user_id, course_id=course_id)[1],
                section_exam_weights=self._load_section_exam_weights(course_id=course_id),
                updated_at=_now_iso(),
            )
        }
        return [
            record.model_copy(update={"priority_score": priorities.get(record.concept_id, 0.0)})
            for record in records
        ]

    def _select_question_types(self, *, user_id: str, course_id: str) -> list[QuestionTypeMasteryRecord]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, user_id, course_id, module_id, concept_id, question_type,
                       attempts, correct_attempts, accuracy, average_time_seconds, updated_at
                FROM question_type_mastery
                WHERE user_id = ? AND course_id = ?
                """,
                (user_id, course_id),
            ).fetchall()
        return [self._question_type_from_row(row) for row in rows]

    def _concept_from_row(self, row) -> ConceptMasteryRecord:  # noqa: ANN001
        return ConceptMasteryRecord(
            id=row["id"],
            user_id=row["user_id"],
            course_id=row["course_id"],
            module_id=row["module_id"],
            material_id=row["material_id"],
            section_id=row["section_id"],
            concept_id=row["concept_id"],
            attempts=row["attempts"],
            correct_attempts=row["correct_attempts"],
            accuracy=row["accuracy"],
            repeat_misses=row["repeat_misses"],
            average_time_seconds=row["average_time_seconds"],
            mastery_score=row["mastery_score"],
            last_attempt_at=row["last_attempt_at"],
            updated_at=row["updated_at"],
        )

    def _module_from_row(self, row) -> ModuleMasteryRecord:  # noqa: ANN001
        weak_concepts = json.loads(row["weak_concepts_json"] or "[]")
        weak_question_types = json.loads(row["weak_question_types_json"] or "[]")
        priority = round((1 - float(row["accuracy"])) * 60 + len(weak_concepts) * 2, 2)
        return ModuleMasteryRecord(
            id=row["id"],
            user_id=row["user_id"],
            course_id=row["course_id"],
            module_id=row["module_id"],
            attempts=row["attempts"],
            correct_attempts=row["correct_attempts"],
            accuracy=row["accuracy"],
            average_time_seconds=row["average_time_seconds"],
            mastery_score=row["mastery_score"],
            weak_concepts=weak_concepts,
            weak_question_types=weak_question_types,
            updated_at=row["updated_at"],
            priority_score=priority,
        )

    def _question_type_from_row(self, row) -> QuestionTypeMasteryRecord:  # noqa: ANN001
        priority = round((1 - float(row["accuracy"])) * 60 + min(int(row["attempts"]), 5) * 4, 2)
        return QuestionTypeMasteryRecord(
            id=row["id"],
            user_id=row["user_id"],
            course_id=row["course_id"],
            module_id=row["module_id"],
            concept_id=row["concept_id"],
            question_type=row["question_type"],
            attempts=row["attempts"],
            correct_attempts=row["correct_attempts"],
            accuracy=row["accuracy"],
            average_time_seconds=row["average_time_seconds"],
            updated_at=row["updated_at"],
            priority_score=priority,
        )

    def _recommendation_from_row(self, row) -> RecommendationHistoryRecord:  # noqa: ANN001
        return RecommendationHistoryRecord(
            id=row["id"],
            user_id=row["user_id"],
            course_id=row["course_id"],
            recommendation_type=row["recommendation_type"],
            title=row["title"],
            target_module_id=row["target_module_id"],
            target_section_id=row["target_section_id"],
            target_concept_id=row["target_concept_id"],
            reason=row["reason"],
            recommended_action=row["recommended_action"],
            priority_score=row["priority_score"],
            clicked=bool(row["clicked"]),
            completed=bool(row["completed"]),
            created_at=row["created_at"],
        )


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _stable_id(*parts: object) -> str:
    return sha256("|".join(str(part or "") for part in parts).encode("utf-8")).hexdigest()[:24]


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _average_time(rows: list[dict[str, Any]]) -> float | None:
    values = [int(row["time_spent_seconds"]) for row in rows if row.get("time_spent_seconds") is not None]
    if not values:
        return None
    return round(float(mean(values)), 2)


def _mastery_score(*, attempts: int, correct_attempts: int, repeat_misses: int) -> float:
    if attempts <= 0:
        return 0.0
    accuracy = correct_attempts / attempts
    attempt_depth = min(correct_attempts, 3) / 3
    evidence_depth = min(max(attempts - 1, 0), 4) / 4
    score = accuracy * 62 + attempt_depth * 23 + evidence_depth * 15 - min(repeat_misses * 8, 45)
    return round(max(0.0, min(100.0, score)), 2)


def _recent_weakness(rows: list[dict[str, Any]]) -> bool:
    recent = rows[-3:]
    return any(not row["is_correct"] for row in recent)


def _priority_score(
    *,
    accuracy: float,
    repeat_misses: int,
    attempts: int,
    exam_weight: float,
    review_seconds: int,
    recent_weakness: bool,
    question_type_weakness: bool,
) -> float:
    repeat_miss_rate = repeat_misses / max(attempts, 1)
    low_review_time_penalty = 1.0 if accuracy < 0.7 and review_seconds < 60 else 0.0
    recent_weakness_penalty = 1.0 if recent_weakness else 0.0
    question_type_penalty = 1.0 if question_type_weakness else 0.0
    score = (
        (1 - accuracy) * 35
        + repeat_miss_rate * 20
        + max(0.0, min(exam_weight, 1.0)) * 20
        + low_review_time_penalty * 10
        + recent_weakness_penalty * 10
        + question_type_penalty * 5
    )
    return round(max(0.0, min(score, 100.0)), 2)


def _weak_concept_payload(record: ConceptMasteryRecord) -> dict[str, Any]:
    return {
        "concept_id": record.concept_id,
        "module_id": record.module_id,
        "material_id": record.material_id,
        "section_id": record.section_id,
        "accuracy": record.accuracy,
        "attempts": record.attempts,
        "repeat_misses": record.repeat_misses,
        "mastery_score": record.mastery_score,
        "priority_score": record.priority_score,
    }


def _weak_question_type_payload(record: QuestionTypeMasteryRecord) -> dict[str, Any]:
    return {
        "question_type": record.question_type,
        "concept_id": record.concept_id,
        "accuracy": record.accuracy,
        "attempts": record.attempts,
        "priority_score": record.priority_score,
    }


def _aggregate_question_type_accuracy(records: list[QuestionTypeMasteryRecord]) -> dict[str, float]:
    grouped: dict[str, list[QuestionTypeMasteryRecord]] = defaultdict(list)
    for record in records:
        grouped[record.question_type].append(record)
    return {
        question_type: _ratio(
            sum(record.correct_attempts for record in values),
            sum(record.attempts for record in values),
        )
        for question_type, values in grouped.items()
    }


def _difficulty_bucket(value: object) -> str:
    try:
        difficulty = float(value)
    except (TypeError, ValueError):
        return "unknown"
    if difficulty < 0.4:
        return "easy"
    if difficulty < 0.7:
        return "medium"
    return "hard"


def _recent_improvement_trend(attempts: list[dict[str, Any]]) -> float:
    if len(attempts) < 4:
        return 0.0
    midpoint = len(attempts) // 2
    early = attempts[:midpoint]
    recent = attempts[midpoint:]
    early_accuracy = _ratio(sum(1 for row in early if row["is_correct"]), len(early))
    recent_accuracy = _ratio(sum(1 for row in recent if row["is_correct"]), len(recent))
    return round(recent_accuracy - early_accuracy, 4)


def _exam_readiness_score(
    *,
    accuracy: float,
    concept_records: list[ConceptMasteryRecord],
    module_records: list[ModuleMasteryRecord],
    question_type_records: list[QuestionTypeMasteryRecord],
) -> float:
    if not concept_records and not module_records and not question_type_records:
        return 0.0
    concept_score = mean([record.mastery_score for record in concept_records]) if concept_records else accuracy * 100
    module_score = mean([record.mastery_score for record in module_records]) if module_records else concept_score
    type_accuracy = (
        mean([record.accuracy * 100 for record in question_type_records])
        if question_type_records
        else accuracy * 100
    )
    weak_penalty = min(
        25.0,
        sum(1 for record in concept_records if record.repeat_misses >= 2 or record.accuracy < 0.6) * 5,
    )
    return round(max(0.0, min(100.0, concept_score * 0.45 + module_score * 0.3 + type_accuracy * 0.25 - weak_penalty)), 2)


def _least_reviewed_weak_materials(
    *,
    concept_records: list[ConceptMasteryRecord],
    study_time_by_material: dict[str, int],
) -> list[dict[str, Any]]:
    weak_materials: dict[str, float] = defaultdict(float)
    for record in concept_records:
        if not record.material_id or (record.accuracy >= 0.75 and record.repeat_misses < 2):
            continue
        weak_materials[record.material_id] += record.priority_score
    ranked = sorted(
        weak_materials.items(),
        key=lambda item: (study_time_by_material.get(item[0], 0), -item[1]),
    )
    return [
        {
            "material_id": material_id,
            "review_seconds": study_time_by_material.get(material_id, 0),
            "priority_score": round(priority, 2),
        }
        for material_id, priority in ranked[:5]
    ]


def _recommended_action(
    *,
    accuracy: float,
    repeat_misses: int,
    review_seconds: int,
    weak_question_type: str | None,
) -> str:
    if accuracy < 0.7 and review_seconds < 60:
        return "Review material first, then practice targeted questions."
    if accuracy < 0.7 and review_seconds >= 60:
        return "Practice targeted questions from this concept."
    if repeat_misses >= 2:
        return "Take a focused remediation quiz on this concept."
    if weak_question_type:
        return f"Practice {weak_question_type} questions for this concept."
    return "Review this concept and confirm it with a short quiz."


def _recommendation_title(record: ConceptMasteryRecord) -> str:
    concept = record.concept_id.replace("_", " ").replace("-", " ").strip()
    title = " ".join(part.capitalize() for part in concept.split()) or "Weak Concept"
    return f"Review {title}"
