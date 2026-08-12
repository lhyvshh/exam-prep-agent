from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ReminderType(StrEnum):
    DAILY = "daily"
    FINAL_WEEK = "final_week"
    WEAK_CONCEPT = "weak_concept"


class NotificationDraftStatus(StrEnum):
    DRAFT = "draft"
    BLOCKED = "blocked"
    SIMULATED_SENT = "simulated_sent"
    SENT = "sent"


class NotificationPreference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    course_id: str
    email_enabled: bool = False
    email_address: str | None = None
    daily_reminder_enabled: bool = False
    final_week_enabled: bool = False
    weak_concept_enabled: bool = True
    exam_date: str | None = None
    preferred_reminder_time: str = "19:00"
    busy_windows: list[str] = Field(default_factory=list)
    updated_at: str | None = None


class NotificationPreferenceUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email_enabled: bool = False
    email_address: str | None = None
    daily_reminder_enabled: bool = False
    final_week_enabled: bool = False
    weak_concept_enabled: bool = True
    exam_date: str | None = None
    preferred_reminder_time: str = "19:00"
    busy_windows: list[str] = Field(default_factory=list)


class ReminderDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reminder_type: ReminderType = ReminderType.WEAK_CONCEPT


class ReminderDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_id: str
    course_id: str
    reminder_type: ReminderType
    subject: str
    body: str
    recipient_email: str | None = None
    quality_reviewed: bool = True
    quality_notes: list[str] = Field(default_factory=list)
    status: NotificationDraftStatus = NotificationDraftStatus.DRAFT
    created_at: str
    sent_at: str | None = None


class ReminderDraftSendResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft: ReminderDraft
    delivery_message: str
