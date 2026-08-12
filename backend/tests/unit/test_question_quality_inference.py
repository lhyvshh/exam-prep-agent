from pathlib import Path

from exam_prep.ml.inference import QuestionQualityInferenceService
from exam_prep.schemas.ml import QuestionQualityInput


def test_question_quality_heuristic_distinguishes_good_and_bad_questions() -> None:
    service = QuestionQualityInferenceService(
        checkpoint_path=Path("backend/artifacts/question_quality_classifier.pt"),
        enable_torch=False,
    )

    strong_question = QuestionQualityInput(
        prompt='Which statement is supported by the section "Gradient Descent"?',
        question_type="mcq",
        concept="Gradient Descent",
        section_title="Gradient Descent",
        difficulty=0.6,
        options=[
            "Gradient descent updates parameters by moving opposite the gradient.",
            "Gradient descent removes all gradients from the model.",
            "Gradient descent prevents convergence in every case.",
            "Gradient descent is unrelated to optimization."
        ],
        rationale="Grounded in the retrieved passage for this section.",
        citation_count=1,
    )
    weak_question = QuestionQualityInput(
        prompt="What?",
        question_type="mcq",
        concept="",
        section_title="",
        difficulty=0.5,
        options=["A", "B"],
        rationale="",
        citation_count=0,
    )

    strong_score = service.score_input(strong_question)
    weak_score = service.score_input(weak_question)

    assert strong_score.score > weak_score.score
    assert strong_score.accepted_for_delivery is True
    assert weak_score.accepted_for_delivery is False


def test_question_quality_heuristic_accepts_grounded_three_choice_exam_format() -> None:
    service = QuestionQualityInferenceService(
        checkpoint_path=Path("backend/artifacts/question_quality_classifier.pt"),
        enable_torch=False,
    )
    question = QuestionQualityInput(
        prompt="Which organelle produces most cellular ATP during aerobic respiration?",
        question_type="mcq",
        concept="Cellular respiration",
        section_title="Mitochondria and energy conversion",
        difficulty=0.62,
        options=[
            "The mitochondrion",
            "The lysosome",
            "The Golgi apparatus",
        ],
        rationale="The cited chapter identifies mitochondria as the main site of aerobic ATP production.",
        citation_count=1,
    )

    score = service.score_input(question)

    assert score.label.value == "high_quality"
    assert score.accepted_for_delivery is True
    assert not any("exactly four" in note.casefold() for note in score.notes)


def test_bundled_pytorch_checkpoint_accepts_grounded_three_choice_exam_format() -> None:
    service = QuestionQualityInferenceService(
        checkpoint_path=Path("backend/artifacts/question_quality_classifier.pt"),
        enable_torch=True,
    )
    question = QuestionQualityInput(
        prompt="Which organelle produces most cellular ATP during aerobic respiration?",
        question_type="mcq",
        concept="Cellular respiration",
        section_title="Mitochondria and energy conversion",
        difficulty=0.62,
        options=["The mitochondrion", "The lysosome", "The Golgi apparatus"],
        rationale=(
            "The cited chapter identifies mitochondria as the main site of aerobic ATP production."
        ),
        citation_count=1,
    )

    score = service.score_input(question)

    assert score.model_source == "pytorch_checkpoint"
    assert score.label.value == "high_quality"
    assert score.accepted_for_delivery is True
