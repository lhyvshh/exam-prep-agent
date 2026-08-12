from pathlib import Path

from exam_prep.core.config import Settings
from exam_prep.evaluation.regression import (
    evaluate_grading_regression_suite,
    evaluate_question_quality_cases,
    load_question_quality_cases,
    load_quiz_grading_suite,
)
from exam_prep.ml.inference import QuestionQualityInferenceService


def test_question_quality_regression_fixture_passes(settings: Settings) -> None:
    fixture_path = Path("backend/tests/fixtures/regression/question_quality_cases.json")
    cases = load_question_quality_cases(fixture_path)
    service = QuestionQualityInferenceService(
        checkpoint_path=settings.question_quality_checkpoint_path,
        enable_torch=False,
    )

    summary = evaluate_question_quality_cases(service=service, cases=cases)

    assert summary["case_count"] == 4
    assert summary["passed_count"] == 4
    assert summary["accuracy"] == 1.0


def test_grading_regression_fixture_passes() -> None:
    fixture_path = Path("backend/tests/fixtures/regression/grading_consistency_cases.json")
    sample_course_dir = Path("backend/tests/fixtures/sample_course")
    suite = load_quiz_grading_suite(fixture_path)

    summary = evaluate_grading_regression_suite(
        suite=suite,
        sample_course_dir=sample_course_dir,
    )

    assert summary["scenario_count"] == 3
    assert summary["passed_count"] == 3
    assert summary["accuracy"] == 1.0
