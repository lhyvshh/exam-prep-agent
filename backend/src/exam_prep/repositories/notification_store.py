from typing import Protocol

from exam_prep.schemas.notifications import NotificationPreference, ReminderDraft


class NotificationStore(Protocol):
    def get_preference(self, course_id: str) -> NotificationPreference | None:
        ...

    def save_preference(self, preference: NotificationPreference) -> NotificationPreference:
        ...

    def save_draft(self, draft: ReminderDraft) -> ReminderDraft:
        ...

    def get_draft(self, draft_id: str) -> ReminderDraft | None:
        ...

    def list_drafts(self, course_id: str) -> list[ReminderDraft]:
        ...
