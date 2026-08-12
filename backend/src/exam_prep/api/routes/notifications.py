from fastapi import APIRouter, Depends, HTTPException, status

from exam_prep.api.deps import (
    get_agent_store,
    get_app_settings,
    get_notification_store,
    get_quiz_store,
)
from exam_prep.core.config import Settings
from exam_prep.repositories.agent_store import AgentStore
from exam_prep.repositories.notification_store import NotificationStore
from exam_prep.repositories.quiz_store import QuizStore
from exam_prep.schemas.notifications import (
    NotificationPreference,
    NotificationPreferenceUpdateRequest,
    ReminderDraft,
    ReminderDraftRequest,
    ReminderDraftSendResponse,
)
from exam_prep.services.notification_service import NotificationService

router = APIRouter(tags=["notifications"])


def _notification_service(
    settings: Settings = Depends(get_app_settings),
    notification_store: NotificationStore = Depends(get_notification_store),
    agent_store: AgentStore = Depends(get_agent_store),
    quiz_store: QuizStore = Depends(get_quiz_store),
) -> NotificationService:
    return NotificationService(
        settings=settings,
        notification_store=notification_store,
        agent_store=agent_store,
        quiz_store=quiz_store,
    )


@router.get("/notifications/courses/{course_id}/preferences", response_model=NotificationPreference)
def get_preferences(
    course_id: str,
    service: NotificationService = Depends(_notification_service),
) -> NotificationPreference:
    return service.get_preference(course_id)


@router.put("/notifications/courses/{course_id}/preferences", response_model=NotificationPreference)
def save_preferences(
    course_id: str,
    payload: NotificationPreferenceUpdateRequest,
    service: NotificationService = Depends(_notification_service),
) -> NotificationPreference:
    return service.save_preference(course_id, payload)


@router.get("/notifications/courses/{course_id}/drafts", response_model=list[ReminderDraft])
def list_drafts(
    course_id: str,
    service: NotificationService = Depends(_notification_service),
) -> list[ReminderDraft]:
    return service.list_drafts(course_id)


@router.post("/notifications/courses/{course_id}/drafts", response_model=ReminderDraft)
def create_draft(
    course_id: str,
    payload: ReminderDraftRequest,
    service: NotificationService = Depends(_notification_service),
) -> ReminderDraft:
    return service.draft_reminder(course_id, payload)


@router.post("/notifications/drafts/{draft_id}/send", response_model=ReminderDraftSendResponse)
def send_draft(
    draft_id: str,
    service: NotificationService = Depends(_notification_service),
) -> ReminderDraftSendResponse:
    try:
        return service.send_draft(draft_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
