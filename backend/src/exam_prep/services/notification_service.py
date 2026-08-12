from __future__ import annotations

import smtplib
from datetime import UTC, datetime
from email.message import EmailMessage
from uuid import uuid4

from exam_prep.core.config import Settings
from exam_prep.repositories.agent_store import AgentStore
from exam_prep.repositories.notification_store import NotificationStore
from exam_prep.repositories.quiz_store import QuizStore
from exam_prep.schemas.agent import AgentMemoryProfile
from exam_prep.schemas.notifications import (
    NotificationDraftStatus,
    NotificationPreference,
    NotificationPreferenceUpdateRequest,
    ReminderDraft,
    ReminderDraftRequest,
    ReminderDraftSendResponse,
    ReminderType,
)


class NotificationService:
    def __init__(
        self,
        *,
        settings: Settings,
        notification_store: NotificationStore,
        agent_store: AgentStore,
        quiz_store: QuizStore,
    ) -> None:
        self.settings = settings
        self.notification_store = notification_store
        self.agent_store = agent_store
        self.quiz_store = quiz_store

    def get_preference(self, course_id: str) -> NotificationPreference:
        existing = self.notification_store.get_preference(course_id)
        if existing is not None:
            return existing
        return NotificationPreference(course_id=course_id, updated_at=datetime.now(UTC).isoformat())

    def save_preference(
        self,
        course_id: str,
        request: NotificationPreferenceUpdateRequest,
    ) -> NotificationPreference:
        preference = NotificationPreference(
            course_id=course_id,
            email_enabled=request.email_enabled,
            email_address=request.email_address,
            daily_reminder_enabled=request.daily_reminder_enabled,
            final_week_enabled=request.final_week_enabled,
            weak_concept_enabled=request.weak_concept_enabled,
            exam_date=request.exam_date,
            preferred_reminder_time=request.preferred_reminder_time or "19:00",
            busy_windows=self._clean_list(request.busy_windows),
            updated_at=datetime.now(UTC).isoformat(),
        )
        return self.notification_store.save_preference(preference)

    def list_drafts(self, course_id: str) -> list[ReminderDraft]:
        return self.notification_store.list_drafts(course_id)

    def draft_reminder(self, course_id: str, request: ReminderDraftRequest) -> ReminderDraft:
        preference = self.get_preference(course_id)
        memory = self.agent_store.get_memory(course_id) or AgentMemoryProfile(course_id=course_id)
        recommendations = self.agent_store.list_recommendations(course_id)
        mastery = self.quiz_store.get_mastery_snapshot(course_id, None)
        weak_concepts = memory.focus_areas or mastery.wrong_concepts
        top_recommendation = recommendations[0] if recommendations else None
        subject = self._subject(request.reminder_type, weak_concepts)
        body = self._body(
            reminder_type=request.reminder_type,
            memory=memory,
            preference=preference,
            weak_concepts=weak_concepts,
            top_action=top_recommendation.title if top_recommendation else None,
        )
        notes = self._quality_notes(subject, body)
        draft = ReminderDraft(
            draft_id=uuid4().hex,
            course_id=course_id,
            reminder_type=request.reminder_type,
            subject=subject,
            body=body,
            recipient_email=preference.email_address,
            quality_reviewed=True,
            quality_notes=notes,
            status=NotificationDraftStatus.DRAFT,
            created_at=datetime.now(UTC).isoformat(),
        )
        return self.notification_store.save_draft(draft)

    def send_draft(self, draft_id: str) -> ReminderDraftSendResponse:
        draft = self.notification_store.get_draft(draft_id)
        if draft is None:
            raise ValueError("Reminder draft not found.")
        preference = self.get_preference(draft.course_id)
        if not preference.email_enabled or not preference.email_address:
            blocked = draft.model_copy(update={"status": NotificationDraftStatus.BLOCKED})
            self.notification_store.save_draft(blocked)
            return ReminderDraftSendResponse(
                draft=blocked,
                delivery_message="Email delivery is blocked until reminders are enabled with a recipient email.",
            )

        sent_at = datetime.now(UTC).isoformat()
        if self.settings.enable_email_delivery and self.settings.smtp_host:
            self._send_email(draft=draft, recipient=preference.email_address)
            sent = draft.model_copy(
                update={
                    "recipient_email": preference.email_address,
                    "status": NotificationDraftStatus.SENT,
                    "sent_at": sent_at,
                }
            )
            self.notification_store.save_draft(sent)
            return ReminderDraftSendResponse(draft=sent, delivery_message="Reminder email sent.")

        simulated = draft.model_copy(
            update={
                "recipient_email": preference.email_address,
                "status": NotificationDraftStatus.SIMULATED_SENT,
                "sent_at": sent_at,
            }
        )
        self.notification_store.save_draft(simulated)
        return ReminderDraftSendResponse(
            draft=simulated,
            delivery_message="Reminder marked sent in demo mode. Configure SMTP and enable delivery for real email.",
        )

    def _send_email(self, *, draft: ReminderDraft, recipient: str) -> None:
        message = EmailMessage()
        message["Subject"] = draft.subject
        message["From"] = self.settings.smtp_from_email
        message["To"] = recipient
        message.set_content(draft.body)

        with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=15) as smtp:
            if self.settings.smtp_use_tls:
                smtp.starttls()
            if self.settings.smtp_username and self.settings.smtp_password:
                smtp.login(self.settings.smtp_username, self.settings.smtp_password)
            smtp.send_message(message)

    def _subject(self, reminder_type: ReminderType, weak_concepts: list[str]) -> str:
        lead = weak_concepts[0] if weak_concepts else "your next study step"
        if reminder_type == ReminderType.FINAL_WEEK:
            return f"Final-week focus: {lead}"
        if reminder_type == ReminderType.DAILY:
            return f"Today’s study plan: {lead}"
        return f"Reinforce before the exam: {lead}"

    def _body(
        self,
        *,
        reminder_type: ReminderType,
        memory: AgentMemoryProfile,
        preference: NotificationPreference,
        weak_concepts: list[str],
        top_action: str | None,
    ) -> str:
        concepts = ", ".join(weak_concepts[:4]) if weak_concepts else "one ready section from your book library"
        action = top_action or "review one section, then take a short focused quiz"
        timing = preference.preferred_reminder_time or "your preferred study time"
        exam_line = f"Exam date on file: {preference.exam_date}." if preference.exam_date else "No exam date is set yet."
        if reminder_type == ReminderType.FINAL_WEEK:
            opening = "You are in final-week mode. Keep the plan small and high-yield."
        elif reminder_type == ReminderType.DAILY:
            opening = "Here is a calm study nudge for today."
        else:
            opening = "This is a weak-concept reinforcement reminder."
        return (
            f"{opening}\n\n"
            f"Focus: {concepts}.\n"
            f"Next action: {action}.\n"
            f"Suggested time: {timing}.\n"
            f"{exam_line}\n\n"
            f"Study style memory: {memory.preferred_study_style}; quiz format: "
            f"{memory.preferred_quiz_format}; default quiz length: {memory.default_question_count}.\n\n"
            "Tiny encouragement: one focused pass is enough to make the next quiz more useful."
        )

    def _quality_notes(self, subject: str, body: str) -> list[str]:
        notes = ["Quality Agent reviewed reminder for concise, non-alarming wording."]
        if len(subject) <= 90:
            notes.append("Subject is short enough for email.")
        if "source_id" not in body and "material_id" not in body:
            notes.append("No raw internal IDs exposed.")
        return notes

    def _clean_list(self, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for value in values:
            normalized = " ".join(value.split())
            if normalized and normalized not in cleaned:
                cleaned.append(normalized)
            if len(cleaned) >= 6:
                break
        return cleaned
