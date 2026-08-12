from fastapi import APIRouter, Depends, HTTPException, Query, status

from exam_prep.api.deps import get_activity_store
from exam_prep.repositories.activity_store import ActivityStore
from exam_prep.schemas.activity import (
    ActivityEventCreate,
    ActivityEventRecord,
    ActivityEventsResponse,
    ActivityEventType,
    FlashcardReviewCreate,
    FlashcardReviewRecord,
    FlashcardReviewsResponse,
    GeneratedContentQualityFlagCreate,
    GeneratedContentQualityFlagRecord,
    GeneratedContentQualityFlagsResponse,
    GeneratedContentQualityFlagType,
    QuestionAttemptsResponse,
    StudySessionEndRequest,
    StudySessionRecord,
    StudySessionsResponse,
    StudySessionStartRequest,
)

router = APIRouter(tags=["activity"])


@router.post("/activity/events", response_model=ActivityEventRecord, status_code=status.HTTP_201_CREATED)
def record_event(
    payload: ActivityEventCreate,
    activity_store: ActivityStore = Depends(get_activity_store),
) -> ActivityEventRecord:
    return activity_store.record_event(payload)


@router.get("/activity/events", response_model=ActivityEventsResponse)
def list_events(
    user_id: str | None = None,
    course_id: str | None = None,
    quiz_id: str | None = None,
    event_type: ActivityEventType | None = Query(default=None),
    activity_store: ActivityStore = Depends(get_activity_store),
) -> ActivityEventsResponse:
    return ActivityEventsResponse(
        events=activity_store.list_events(
            user_id=user_id,
            course_id=course_id,
            quiz_id=quiz_id,
            event_type=event_type,
        )
    )


@router.post(
    "/activity/study-sessions/start",
    response_model=StudySessionRecord,
    status_code=status.HTTP_201_CREATED,
)
def start_study_session(
    payload: StudySessionStartRequest,
    activity_store: ActivityStore = Depends(get_activity_store),
) -> StudySessionRecord:
    return activity_store.start_study_session(payload)


@router.post("/activity/study-sessions/{session_id}/end", response_model=StudySessionRecord)
def end_study_session(
    session_id: str,
    payload: StudySessionEndRequest,
    activity_store: ActivityStore = Depends(get_activity_store),
) -> StudySessionRecord:
    record = activity_store.end_study_session(session_id, payload)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Study session not found.")
    return record


@router.get("/activity/study-sessions", response_model=StudySessionsResponse)
def list_study_sessions(
    user_id: str | None = None,
    course_id: str | None = None,
    activity_store: ActivityStore = Depends(get_activity_store),
) -> StudySessionsResponse:
    return StudySessionsResponse(
        study_sessions=activity_store.list_study_sessions(user_id=user_id, course_id=course_id)
    )


@router.get("/activity/question-attempts", response_model=QuestionAttemptsResponse)
def list_question_attempts(
    user_id: str | None = None,
    course_id: str | None = None,
    quiz_id: str | None = None,
    activity_store: ActivityStore = Depends(get_activity_store),
) -> QuestionAttemptsResponse:
    return QuestionAttemptsResponse(
        question_attempts=activity_store.list_question_attempts(
            user_id=user_id,
            course_id=course_id,
            quiz_id=quiz_id,
        )
    )


@router.post(
    "/activity/flashcard-reviews",
    response_model=FlashcardReviewRecord,
    status_code=status.HTTP_201_CREATED,
)
def record_flashcard_review(
    payload: FlashcardReviewCreate,
    activity_store: ActivityStore = Depends(get_activity_store),
) -> FlashcardReviewRecord:
    return activity_store.record_flashcard_review(payload)


@router.get("/activity/flashcard-reviews", response_model=FlashcardReviewsResponse)
def list_flashcard_reviews(
    user_id: str | None = None,
    course_id: str | None = None,
    material_id: str | None = None,
    concept_id: str | None = None,
    flashcard_id: str | None = None,
    activity_store: ActivityStore = Depends(get_activity_store),
) -> FlashcardReviewsResponse:
    return FlashcardReviewsResponse(
        flashcard_reviews=activity_store.list_flashcard_reviews(
            user_id=user_id,
            course_id=course_id,
            material_id=material_id,
            concept_id=concept_id,
            flashcard_id=flashcard_id,
        )
    )


@router.post(
    "/activity/generated-content-quality-flags",
    response_model=GeneratedContentQualityFlagRecord,
    status_code=status.HTTP_201_CREATED,
)
def record_generated_content_quality_flag(
    payload: GeneratedContentQualityFlagCreate,
    activity_store: ActivityStore = Depends(get_activity_store),
) -> GeneratedContentQualityFlagRecord:
    return activity_store.record_generated_content_quality_flag(payload)


@router.get(
    "/activity/generated-content-quality-flags",
    response_model=GeneratedContentQualityFlagsResponse,
)
def list_generated_content_quality_flags(
    course_id: str | None = None,
    material_id: str | None = None,
    section_id: str | None = None,
    concept_id: str | None = None,
    content_id: str | None = None,
    flag_type: GeneratedContentQualityFlagType | None = Query(default=None),
    activity_store: ActivityStore = Depends(get_activity_store),
) -> GeneratedContentQualityFlagsResponse:
    return GeneratedContentQualityFlagsResponse(
        quality_flags=activity_store.list_generated_content_quality_flags(
            course_id=course_id,
            material_id=material_id,
            section_id=section_id,
            concept_id=concept_id,
            content_id=content_id,
            flag_type=flag_type,
        )
    )
