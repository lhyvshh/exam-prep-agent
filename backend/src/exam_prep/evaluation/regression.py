from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Literal

from fastapi.testclient import TestClient

from exam_prep.core.config import Settings
from exam_prep.main import create_app
from exam_prep.ml.inference import QuestionQualityInferenceService
from exam_prep.schemas.ml import QuestionQualityInput, QuestionQualityLabel
from exam_prep.schemas.quiz import QuizSubmissionAnswer, StoredQuizSession

AnswerMode = Literal["all_correct", "all_incorrect", "alternating"]


@dataclass(slots=True)
class QuestionQualityRegressionCase:
    name: str
    input_data: QuestionQualityInput
    expected_label: QuestionQualityLabel
    accepted_for_delivery: bool
    min_score: float
    max_score: float


@dataclass(slots=True)
class GradingRegressionScenario:
    name: str
    answer_mode: AnswerMode
    expected_overall_score: float
    expected_result_correctness: list[bool]
    expected_wrong_concepts: list[str]


@dataclass(slots=True)
class QuizGradingRegressionSuite:
    course_id: str
    source_fixture: str
    source_content_type: str
    quiz_request: dict[str, Any]
    scenarios: list[GradingRegressionScenario]


def load_question_quality_cases(path: Path) -> list[QuestionQualityRegressionCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [
        QuestionQualityRegressionCase(
            name=item["name"],
            input_data=QuestionQualityInput.model_validate(item["input"]),
            expected_label=QuestionQualityLabel(item["expected_label"]),
            accepted_for_delivery=bool(item["accepted_for_delivery"]),
            min_score=float(item["min_score"]),
            max_score=float(item["max_score"]),
        )
        for item in payload["cases"]
    ]


def load_quiz_grading_suite(path: Path) -> QuizGradingRegressionSuite:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return QuizGradingRegressionSuite(
        course_id=payload["course_id"],
        source_fixture=payload["source_fixture"],
        source_content_type=payload["source_content_type"],
        quiz_request=dict(payload["quiz_request"]),
        scenarios=[
            GradingRegressionScenario(
                name=item["name"],
                answer_mode=item["answer_mode"],
                expected_overall_score=float(item["expected_overall_score"]),
                expected_result_correctness=list(item["expected_result_correctness"]),
                expected_wrong_concepts=list(item["expected_wrong_concepts"]),
            )
            for item in payload["scenarios"]
        ],
    )


def evaluate_question_quality_cases(
    *,
    service: QuestionQualityInferenceService,
    cases: list[QuestionQualityRegressionCase],
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    passed_count = 0

    for case in cases:
        prediction = service.score_input(case.input_data)
        passed = (
            prediction.label == case.expected_label
            and prediction.accepted_for_delivery == case.accepted_for_delivery
            and case.min_score <= prediction.score <= case.max_score
        )
        if passed:
            passed_count += 1
        results.append(
            {
                "name": case.name,
                "score": prediction.score,
                "label": prediction.label.value,
                "accepted_for_delivery": prediction.accepted_for_delivery,
                "model_source": prediction.model_source,
                "passed": passed,
            }
        )

    return {
        "case_count": len(cases),
        "passed_count": passed_count,
        "accuracy": round(passed_count / len(cases), 4) if cases else 0.0,
        "results": results,
    }


def evaluate_grading_regression_suite(
    *,
    suite: QuizGradingRegressionSuite,
    sample_course_dir: Path,
) -> dict[str, Any]:
    with TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        settings = Settings(
            app_name="Exam Prep Agent Regression Eval",
            app_env="test",
            debug=False,
            demo_mode=True,
            sqlite_path=tmp_path / "eval.sqlite3",
            material_storage_path=tmp_path / "materials",
            default_llm_provider="openai",
            default_llm_model="gpt-4.1-mini",
            llm_api_key=None,
            enable_web_search=False,
            frontend_origin="http://localhost:3000",
        )
        app = create_app(settings)
        with TestClient(app) as client:
            upload_response = client.post(
                "/api/v1/materials/upload",
                data={"course_id": suite.course_id},
                files={
                    "file": (
                        suite.source_fixture,
                        (sample_course_dir / suite.source_fixture).read_bytes(),
                        suite.source_content_type,
                    )
                },
            )
            if upload_response.status_code != 201:
                raise RuntimeError(
                    f"Regression upload failed with status {upload_response.status_code}: "
                    f"{upload_response.text}"
                )

            generate_response = client.post("/api/v1/quiz/generate", json=suite.quiz_request)
            if generate_response.status_code != 200:
                raise RuntimeError(
                    f"Regression quiz generation failed with status {generate_response.status_code}: "
                    f"{generate_response.text}"
                )

            quiz_payload = _wait_for_quiz_payload(client, generate_response.json()["job_id"])
            quiz_id = str(quiz_payload["quiz_id"])
            session: StoredQuizSession | None = app.state.quiz_store.get_quiz_session(quiz_id)
            if session is None:
                raise RuntimeError("Regression suite could not load the stored quiz session.")

            scenario_results: list[dict[str, Any]] = []
            passed_count = 0

            for scenario in suite.scenarios:
                submission = _build_submission_answers(session, scenario.answer_mode)
                grade_response = client.post(
                    "/api/v1/quiz/grade",
                    json={
                        "quiz_id": quiz_id,
                        "answers": [answer.model_dump(mode="json") for answer in submission],
                    },
                )
                if grade_response.status_code != 200:
                    raise RuntimeError(
                        f"Regression grading failed with status {grade_response.status_code}: "
                        f"{grade_response.text}"
                    )

                payload = grade_response.json()
                actual_correctness = [bool(item["is_correct"]) for item in payload["results"]]
                actual_wrong_concepts = list(payload["wrong_concepts"])
                passed = (
                    payload["overall_score"] == scenario.expected_overall_score
                    and actual_correctness == scenario.expected_result_correctness
                    and actual_wrong_concepts == scenario.expected_wrong_concepts
                )
                if passed:
                    passed_count += 1

                scenario_results.append(
                    {
                        "name": scenario.name,
                        "overall_score": payload["overall_score"],
                        "result_correctness": actual_correctness,
                        "wrong_concepts": actual_wrong_concepts,
                        "passed": passed,
                    }
                )

    return {
        "scenario_count": len(suite.scenarios),
        "passed_count": passed_count,
        "accuracy": round(passed_count / len(suite.scenarios), 4) if suite.scenarios else 0.0,
        "results": scenario_results,
    }


def _wait_for_quiz_payload(client: TestClient, job_id: str) -> dict[str, Any]:
    for _ in range(60):
        status_response = client.get(f"/api/v1/quiz/jobs/{job_id}")
        if status_response.status_code != 200:
            raise RuntimeError(
                f"Regression quiz job polling failed with status {status_response.status_code}: "
                f"{status_response.text}"
            )
        payload = status_response.json()
        if payload["status"] in {"completed", "partial"}:
            return payload["quiz"]
        if payload["status"] in {"failed", "cancelled"}:
            raise RuntimeError(f"Regression quiz job failed: {payload.get('error_summary')}")
        time.sleep(0.05)
    raise RuntimeError(f"Regression quiz job {job_id} did not complete in time.")


def _build_submission_answers(
    session: StoredQuizSession,
    mode: AnswerMode,
) -> list[QuizSubmissionAnswer]:
    answers: list[QuizSubmissionAnswer] = []
    keys_by_question = {key.question_id: key for key in session.answer_keys}

    for index, question in enumerate(session.quiz.questions):
        key = keys_by_question[question.question_id]
        should_answer_correctly = _select_correctness(mode=mode, index=index)

        if question.question_type.value == "mcq":
            selected_option_id = key.correct_option_id if should_answer_correctly else _incorrect_option_id(
                key.correct_option_id
            )
            answers.append(
                QuizSubmissionAnswer(
                    question_id=question.question_id,
                    selected_option_id=selected_option_id,
                    answer_text=None,
                )
            )
        else:
            answer_text = (
                key.correct_answer
                if should_answer_correctly
                else "This response does not match the grounded concept."
            )
            answers.append(
                QuizSubmissionAnswer(
                    question_id=question.question_id,
                    selected_option_id=None,
                    answer_text=answer_text,
                )
            )

    return answers


def _select_correctness(*, mode: AnswerMode, index: int) -> bool:
    if mode == "all_correct":
        return True
    if mode == "all_incorrect":
        return False
    return index % 2 == 0


def _incorrect_option_id(correct_option_id: str | None) -> str:
    for option_id in ["A", "B", "C", "D"]:
        if option_id != correct_option_id:
            return option_id
    return "A"
