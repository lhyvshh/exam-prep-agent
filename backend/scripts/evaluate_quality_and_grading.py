from __future__ import annotations

import json
from pathlib import Path

from exam_prep.core.config import get_settings
from exam_prep.evaluation.regression import (
    evaluate_grading_regression_suite,
    evaluate_question_quality_cases,
    load_question_quality_cases,
    load_quiz_grading_suite,
)
from exam_prep.ml.inference import QuestionQualityInferenceService


def main() -> None:
    project_root = Path(__file__).resolve().parents[2]
    settings = get_settings()

    quality_cases = load_question_quality_cases(
        project_root / "backend/tests/fixtures/regression/question_quality_cases.json"
    )
    quality_service = QuestionQualityInferenceService(
        checkpoint_path=settings.question_quality_checkpoint_path,
        enable_torch=True,
    )
    quality_summary = evaluate_question_quality_cases(
        service=quality_service,
        cases=quality_cases,
    )

    grading_suite = load_quiz_grading_suite(
        project_root / "backend/tests/fixtures/regression/grading_consistency_cases.json"
    )
    grading_summary = evaluate_grading_regression_suite(
        suite=grading_suite,
        sample_course_dir=project_root / "backend/tests/fixtures/sample_course",
    )

    report = {
        "question_quality": quality_summary,
        "grading_consistency": grading_summary,
    }

    output_path = project_root / "backend/artifacts/evaluation_report.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
