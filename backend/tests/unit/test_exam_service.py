from exam_prep.core.exceptions import MaterialIngestionError
from exam_prep.schemas.quiz import QuestionType, QuizQuestion, StoredQuestionKey
from exam_prep.services.exam_service import ExamService


def test_validate_answer_key_completeness_raises_for_missing_key() -> None:
    service = object.__new__(ExamService)
    questions = [
        QuizQuestion(
            question_id="q1",
            question_type=QuestionType.MCQ,
            concept="Gradient Descent",
            section_title="Gradient Descent",
            difficulty=0.5,
            prompt="Question",
            options=[],
            citations=[],
        )
    ]
    answer_keys = [
        StoredQuestionKey(
            question_id="q1",
            question_type=QuestionType.MCQ,
            concept="Gradient Descent",
            correct_answer="Gradient descent updates parameters.",
            correct_option_id=None,
            expected_keywords=["gradient"],
            difficulty=0.5,
            citations=[],
        )
    ]

    try:
        service.validate_answer_key_completeness(questions, answer_keys)
        raise AssertionError("Expected MaterialIngestionError")
    except MaterialIngestionError as exc:
        assert "Answer key is incomplete" in str(exc)
