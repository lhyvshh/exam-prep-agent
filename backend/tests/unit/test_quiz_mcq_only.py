from exam_prep.schemas.exam import ExamTopicCoverage
from exam_prep.schemas.quiz import (
    QuestionType,
    QuizFromModuleRequest,
    QuizFromWeakAreaRequest,
    QuizGenerationRequest,
)


def test_quiz_generation_request_forces_mcq_only() -> None:
    request = QuizGenerationRequest(
        course_id="course-1",
        query="Risk management",
        question_types=[QuestionType.SHORT_ANSWER],
    )

    assert request.question_types == [QuestionType.MCQ]


def test_structured_module_request_forces_mcq_only() -> None:
    request = QuizFromModuleRequest(
        course_id="course-1",
        module_id="module-1",
        question_types=[QuestionType.SHORT_ANSWER],
    )

    assert request.question_types == [QuestionType.MCQ]


def test_weak_area_prefer_short_answer_forces_mcq() -> None:
    request = QuizFromWeakAreaRequest(
        course_id="course-1",
        weak_area_id="weak-1",
        prefer_question_type=QuestionType.SHORT_ANSWER,
        question_types=[QuestionType.SHORT_ANSWER],
    )

    assert request.prefer_question_type == QuestionType.MCQ
    assert request.question_types == [QuestionType.MCQ]


def test_mock_exam_topic_coverage_forces_mcq_only() -> None:
    topic = ExamTopicCoverage(topic="Enterprise risk management", question_types=[QuestionType.SHORT_ANSWER])

    assert topic.question_types == [QuestionType.MCQ]
