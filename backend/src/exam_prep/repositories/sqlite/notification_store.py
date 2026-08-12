import json

from exam_prep.db.sqlite import SQLiteDatabase
from exam_prep.repositories.notification_store import NotificationStore
from exam_prep.schemas.notifications import (
    NotificationDraftStatus,
    NotificationPreference,
    ReminderDraft,
    ReminderType,
)


class SQLiteNotificationStore(NotificationStore):
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    def get_preference(self, course_id: str) -> NotificationPreference | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT course_id, email_enabled, email_address, daily_reminder_enabled,
                       final_week_enabled, weak_concept_enabled, exam_date,
                       preferred_reminder_time, busy_windows_json, updated_at
                FROM notification_preferences
                WHERE course_id = ?
                """,
                (course_id,),
            ).fetchone()
        if row is None:
            return None
        return self._preference_from_row(row)

    def save_preference(self, preference: NotificationPreference) -> NotificationPreference:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO notification_preferences(
                    course_id, email_enabled, email_address, daily_reminder_enabled,
                    final_week_enabled, weak_concept_enabled, exam_date,
                    preferred_reminder_time, busy_windows_json, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(course_id) DO UPDATE SET
                    email_enabled = excluded.email_enabled,
                    email_address = excluded.email_address,
                    daily_reminder_enabled = excluded.daily_reminder_enabled,
                    final_week_enabled = excluded.final_week_enabled,
                    weak_concept_enabled = excluded.weak_concept_enabled,
                    exam_date = excluded.exam_date,
                    preferred_reminder_time = excluded.preferred_reminder_time,
                    busy_windows_json = excluded.busy_windows_json,
                    updated_at = excluded.updated_at
                """,
                (
                    preference.course_id,
                    int(preference.email_enabled),
                    preference.email_address,
                    int(preference.daily_reminder_enabled),
                    int(preference.final_week_enabled),
                    int(preference.weak_concept_enabled),
                    preference.exam_date,
                    preference.preferred_reminder_time,
                    json.dumps(preference.busy_windows),
                    preference.updated_at,
                ),
            )
        return preference

    def save_draft(self, draft: ReminderDraft) -> ReminderDraft:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO notification_drafts(
                    draft_id, course_id, reminder_type, subject, body, recipient_email,
                    quality_reviewed, quality_notes_json, status, created_at, sent_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(draft_id) DO UPDATE SET
                    subject = excluded.subject,
                    body = excluded.body,
                    recipient_email = excluded.recipient_email,
                    quality_reviewed = excluded.quality_reviewed,
                    quality_notes_json = excluded.quality_notes_json,
                    status = excluded.status,
                    sent_at = excluded.sent_at
                """,
                (
                    draft.draft_id,
                    draft.course_id,
                    draft.reminder_type.value,
                    draft.subject,
                    draft.body,
                    draft.recipient_email,
                    int(draft.quality_reviewed),
                    json.dumps(draft.quality_notes),
                    draft.status.value,
                    draft.created_at,
                    draft.sent_at,
                ),
            )
        return draft

    def get_draft(self, draft_id: str) -> ReminderDraft | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT draft_id, course_id, reminder_type, subject, body, recipient_email,
                       quality_reviewed, quality_notes_json, status, created_at, sent_at
                FROM notification_drafts
                WHERE draft_id = ?
                """,
                (draft_id,),
            ).fetchone()
        if row is None:
            return None
        return self._draft_from_row(row)

    def list_drafts(self, course_id: str) -> list[ReminderDraft]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT draft_id, course_id, reminder_type, subject, body, recipient_email,
                       quality_reviewed, quality_notes_json, status, created_at, sent_at
                FROM notification_drafts
                WHERE course_id = ?
                ORDER BY created_at DESC
                LIMIT 12
                """,
                (course_id,),
            ).fetchall()
        return [self._draft_from_row(row) for row in rows]

    def _preference_from_row(self, row) -> NotificationPreference:  # noqa: ANN001
        return NotificationPreference(
            course_id=row["course_id"],
            email_enabled=bool(row["email_enabled"]),
            email_address=row["email_address"],
            daily_reminder_enabled=bool(row["daily_reminder_enabled"]),
            final_week_enabled=bool(row["final_week_enabled"]),
            weak_concept_enabled=bool(row["weak_concept_enabled"]),
            exam_date=row["exam_date"],
            preferred_reminder_time=row["preferred_reminder_time"],
            busy_windows=json.loads(row["busy_windows_json"] or "[]"),
            updated_at=row["updated_at"],
        )

    def _draft_from_row(self, row) -> ReminderDraft:  # noqa: ANN001
        return ReminderDraft(
            draft_id=row["draft_id"],
            course_id=row["course_id"],
            reminder_type=ReminderType(row["reminder_type"]),
            subject=row["subject"],
            body=row["body"],
            recipient_email=row["recipient_email"],
            quality_reviewed=bool(row["quality_reviewed"]),
            quality_notes=json.loads(row["quality_notes_json"] or "[]"),
            status=NotificationDraftStatus(row["status"]),
            created_at=row["created_at"],
            sent_at=row["sent_at"],
        )
