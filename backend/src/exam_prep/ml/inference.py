from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from exam_prep.ml.dataset import encode_text, numeric_features
from exam_prep.schemas.ml import (
    QuestionQualityInput,
    QuestionQualityLabel,
    QuestionQualityScoreResult,
    QuestionQualityValidation,
)
from exam_prep.schemas.quiz import QuizQuestion


@dataclass(slots=True)
class _TorchRuntime:
    torch: Any
    model: Any
    vocabulary: dict[str, int]
    numeric_feature_dim: int
    embedding_dim: int
    hidden_dim: int
    version: str


class QuestionQualityInferenceService:
    def __init__(
        self,
        *,
        checkpoint_path: Path,
        enable_torch: bool = True,
    ) -> None:
        self.checkpoint_path = checkpoint_path
        self.enable_torch = enable_torch
        self._runtime: _TorchRuntime | None = None
        self._load_attempted = False

    def score_batch(self, questions: list[QuestionQualityInput]) -> list[QuestionQualityScoreResult]:
        return [
            QuestionQualityScoreResult(
                question_id=question.question_id,
                **self.score_input(question).model_dump(),
            )
            for question in questions
        ]

    def score_input(self, question: QuestionQualityInput) -> QuestionQualityValidation:
        runtime = self._get_runtime()
        if runtime is None:
            return self._heuristic_score(question)

        encoded = encode_text(question, runtime.vocabulary)
        numeric_values = numeric_features(question)
        torch = runtime.torch
        token_tensor = torch.tensor(encoded, dtype=torch.long)
        offsets = torch.tensor([0], dtype=torch.long)
        numeric_tensor = torch.tensor([numeric_values], dtype=torch.float32)

        runtime.model.eval()
        with torch.no_grad():
            logits = runtime.model(token_tensor, offsets, numeric_tensor)
            probabilities = torch.softmax(logits, dim=1)[0]

        high_quality_probability = float(probabilities[1].item())
        confidence = round(abs(high_quality_probability - 0.5) * 2.0, 4)
        label = self._label_for_score(high_quality_probability)
        return QuestionQualityValidation(
            score=round(high_quality_probability, 4),
            confidence=confidence,
            label=label,
            accepted_for_delivery=high_quality_probability >= 0.5,
            model_version=runtime.version,
            model_source="pytorch_checkpoint",
            notes=self._build_notes(question, label),
        )

    def score_generated_question(self, question: QuizQuestion) -> QuestionQualityValidation:
        return self.score_input(
            QuestionQualityInput(
                question_id=question.question_id,
                prompt=question.prompt,
                question_type=question.question_type.value,
                concept=question.concept,
                section_title=question.section_title,
                difficulty=question.difficulty,
                options=[option.text for option in question.options],
                rationale=question.rationale,
                citation_count=len(question.citations),
            )
        )

    def _get_runtime(self) -> _TorchRuntime | None:
        if not self.enable_torch:
            return None
        if self._runtime is not None:
            return self._runtime
        if self._load_attempted:
            return None

        self._load_attempted = True
        if not self.checkpoint_path.exists():
            return None

        try:
            import torch
            from exam_prep.ml.question_quality_model import QuestionQualityClassifier

            checkpoint = torch.load(self.checkpoint_path, map_location="cpu")
            vocabulary = dict(checkpoint["vocabulary"])
            numeric_feature_dim = int(checkpoint["numeric_feature_dim"])
            embedding_dim = int(checkpoint["embedding_dim"])
            hidden_dim = int(checkpoint["hidden_dim"])
            version = str(checkpoint.get("version", "question-quality-v1"))
            model = QuestionQualityClassifier(
                vocab_size=len(vocabulary),
                embedding_dim=embedding_dim,
                numeric_feature_dim=numeric_feature_dim,
                hidden_dim=hidden_dim,
            )
            model.load_state_dict(checkpoint["state_dict"])
            self._runtime = _TorchRuntime(
                torch=torch,
                model=model,
                vocabulary=vocabulary,
                numeric_feature_dim=numeric_feature_dim,
                embedding_dim=embedding_dim,
                hidden_dim=hidden_dim,
                version=version,
            )
            return self._runtime
        except Exception:
            return None

    def _heuristic_score(self, question: QuestionQualityInput) -> QuestionQualityValidation:
        prompt_token_count = max(len(question.prompt.split()), 1)
        score = 0.2
        if 8 <= prompt_token_count <= 32:
            score += 0.2
        elif prompt_token_count < 5:
            score -= 0.1
        if question.citation_count > 0:
            score += 0.2
        if question.question_type == "mcq":
            score += 0.15 if 2 <= len(question.options) <= 8 else -0.2
        else:
            score += 0.1 if not question.options else -0.1
        if (question.rationale or "").strip():
            score += 0.05
        if question.concept.strip():
            score += 0.05
        if question.section_title.strip():
            score += 0.05
        if 0.25 <= question.difficulty <= 0.9:
            score += 0.05

        bounded_score = round(min(max(score, 0.0), 1.0), 4)
        label = self._label_for_score(bounded_score)
        return QuestionQualityValidation(
            score=bounded_score,
            confidence=round(abs(bounded_score - 0.5) * 2.0, 4),
            label=label,
            accepted_for_delivery=bounded_score >= 0.5,
            model_version="question-quality-heuristic-v1",
            model_source="heuristic_fallback",
            notes=self._build_notes(question, label),
        )

    def _label_for_score(self, score: float) -> QuestionQualityLabel:
        if score >= 0.7:
            return QuestionQualityLabel.HIGH_QUALITY
        if score >= 0.45:
            return QuestionQualityLabel.NEEDS_REVIEW
        return QuestionQualityLabel.LOW_QUALITY

    def _build_notes(
        self,
        question: QuestionQualityInput,
        label: QuestionQualityLabel,
    ) -> list[str]:
        notes: list[str] = []
        if question.citation_count == 0:
            notes.append("Question has no supporting citations.")
        if question.question_type == "mcq" and not 2 <= len(question.options) <= 8:
            notes.append("MCQ should provide two to eight answer options.")
        if question.question_type == "short_answer" and question.options:
            notes.append("Short-answer questions should not include multiple-choice options.")
        if len(question.prompt.split()) < 5:
            notes.append("Prompt is too short to be specific.")
        if not (question.rationale or "").strip():
            notes.append("Rationale is missing.")
        if label == QuestionQualityLabel.HIGH_QUALITY and not notes:
            notes.append("Question structure and grounding signals look strong.")
        return notes
