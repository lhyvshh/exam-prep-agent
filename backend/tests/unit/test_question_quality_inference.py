import hashlib
import shutil
from pathlib import Path

import pytest

from exam_prep.ml import inference as inference_module
from exam_prep.ml.inference import QuestionQualityInferenceService
from exam_prep.schemas.ml import QuestionQualityInput

CHECKPOINT = Path("backend/artifacts/question_quality_classifier.pt")


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


def test_portable_export_matches_bundled_pytorch_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    pytorch_score = QuestionQualityInferenceService(
        checkpoint_path=CHECKPOINT,
        enable_torch=True,
    ).score_input(question)

    monkeypatch.setattr(inference_module, "_import_torch", lambda: None)
    portable_score = QuestionQualityInferenceService(
        checkpoint_path=CHECKPOINT,
        enable_torch=True,
    ).score_input(question)

    assert portable_score.model_source == "pytorch_portable_export"
    assert portable_score.score == pytest.approx(pytorch_score.score, abs=1e-4)
    assert portable_score.label == pytorch_score.label
    assert portable_score.accepted_for_delivery == pytorch_score.accepted_for_delivery


def test_portable_export_is_bound_to_checkpoint_hash() -> None:
    metadata = inference_module._load_portable_metadata(CHECKPOINT)  # noqa: SLF001
    _, weights_path = inference_module._portable_paths(CHECKPOINT)  # noqa: SLF001

    assert metadata.source_checkpoint_sha256 == hashlib.sha256(CHECKPOINT.read_bytes()).hexdigest()
    assert metadata.weights_sha256 == hashlib.sha256(weights_path.read_bytes()).hexdigest()


def test_portable_export_rejects_modified_weights(tmp_path: Path) -> None:
    copied_checkpoint = tmp_path / CHECKPOINT.name
    copied_metadata, copied_weights = inference_module._portable_paths(copied_checkpoint)  # noqa: SLF001
    metadata, weights = inference_module._portable_paths(CHECKPOINT)  # noqa: SLF001
    shutil.copy2(CHECKPOINT, copied_checkpoint)
    shutil.copy2(metadata, copied_metadata)
    shutil.copy2(weights, copied_weights)
    copied_weights.write_bytes(copied_weights.read_bytes() + b"modified")

    with pytest.raises(RuntimeError, match="integrity check"):
        inference_module._load_portable_runtime(copied_checkpoint)  # noqa: SLF001


@pytest.mark.parametrize("failure", ["missing_metadata", "missing_weights", "modified_weights"])
def test_required_model_failures_block_delivery(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failure: str,
) -> None:
    copied_checkpoint = tmp_path / CHECKPOINT.name
    copied_metadata, copied_weights = inference_module._portable_paths(copied_checkpoint)  # noqa: SLF001
    metadata, weights = inference_module._portable_paths(CHECKPOINT)  # noqa: SLF001
    shutil.copy2(CHECKPOINT, copied_checkpoint)
    shutil.copy2(metadata, copied_metadata)
    shutil.copy2(weights, copied_weights)
    if failure == "missing_metadata":
        copied_metadata.unlink()
    elif failure == "missing_weights":
        copied_weights.unlink()
    else:
        copied_weights.write_bytes(copied_weights.read_bytes() + b"modified")
    monkeypatch.setattr(inference_module, "_import_torch", lambda: None)
    service = QuestionQualityInferenceService(
        checkpoint_path=copied_checkpoint,
        enable_torch=True,
    )
    question = QuestionQualityInput(
        prompt="Which organelle produces most cellular ATP during aerobic respiration?",
        question_type="mcq",
        concept="Cellular respiration",
        section_title="Mitochondria and energy conversion",
        difficulty=0.62,
        options=["The mitochondrion", "The lysosome", "The Golgi apparatus"],
        rationale="The cited chapter identifies mitochondria as the main ATP source.",
        citation_count=1,
    )

    score = service.score_input(question)

    assert score.model_source == "heuristic_fallback"
    assert score.accepted_for_delivery is False
    assert any("delivery is blocked" in note for note in score.notes)
