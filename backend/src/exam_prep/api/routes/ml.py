from fastapi import APIRouter, Depends

from exam_prep.api.deps import get_question_quality_service
from exam_prep.ml.inference import QuestionQualityInferenceService
from exam_prep.schemas.ml import QuestionQualityScoreRequest, QuestionQualityScoreResponse

router = APIRouter(tags=["ml"])


@router.post("/ml/question-quality/score", response_model=QuestionQualityScoreResponse)
def score_question_quality(
    payload: QuestionQualityScoreRequest,
    question_quality_service: QuestionQualityInferenceService = Depends(get_question_quality_service),
) -> QuestionQualityScoreResponse:
    return QuestionQualityScoreResponse(
        results=question_quality_service.score_batch(payload.questions)
    )
