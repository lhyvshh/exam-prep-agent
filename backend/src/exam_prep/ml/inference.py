from __future__ import annotations

import hashlib
import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

import numpy as np
from pydantic import BaseModel, ConfigDict

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


class _PortableMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    format: Literal["exam-prep-pytorch-embedding-classifier-v1"]
    source_checkpoint_sha256: str
    weights_sha256: str
    vocabulary: dict[str, int]
    numeric_feature_dim: int
    embedding_dim: int
    hidden_dim: int
    version: str


@dataclass(slots=True)
class _PortableRuntime:
    embedding_weight: np.ndarray[Any, np.dtype[np.float32]]
    hidden_weight: np.ndarray[Any, np.dtype[np.float32]]
    hidden_bias: np.ndarray[Any, np.dtype[np.float32]]
    output_weight: np.ndarray[Any, np.dtype[np.float32]]
    output_bias: np.ndarray[Any, np.dtype[np.float32]]
    vocabulary: dict[str, int]
    numeric_feature_dim: int
    embedding_dim: int
    hidden_dim: int
    version: str


def _import_torch() -> Any | None:
    try:
        module = importlib.import_module("torch")
    except (ImportError, OSError):
        return None
    if not all(hasattr(module, attribute) for attribute in ("load", "no_grad", "softmax")):
        return None
    return module


def _portable_paths(checkpoint_path: Path) -> tuple[Path, Path]:
    stem = checkpoint_path.with_suffix("")
    return stem.with_name(f"{stem.name}.portable.json"), stem.with_name(
        f"{stem.name}.portable.npz"
    )


def _load_portable_metadata(checkpoint_path: Path) -> _PortableMetadata:
    metadata_path, _ = _portable_paths(checkpoint_path)
    metadata = _PortableMetadata.model_validate_json(metadata_path.read_text(encoding="utf-8"))
    checkpoint_sha256 = hashlib.sha256(checkpoint_path.read_bytes()).hexdigest()
    if metadata.source_checkpoint_sha256 != checkpoint_sha256:
        raise RuntimeError("Portable quality export does not match its PyTorch checkpoint.")
    return metadata


def _load_portable_runtime(checkpoint_path: Path) -> _PortableRuntime:
    metadata = _load_portable_metadata(checkpoint_path)
    _, weights_path = _portable_paths(checkpoint_path)
    weights_sha256 = hashlib.sha256(weights_path.read_bytes()).hexdigest()
    if metadata.weights_sha256 != weights_sha256:
        raise RuntimeError("Portable quality weights failed their integrity check.")
    with np.load(weights_path, allow_pickle=False) as weights:
        runtime = _PortableRuntime(
            embedding_weight=weights["embedding_weight"].astype(np.float32, copy=True),
            hidden_weight=weights["hidden_weight"].astype(np.float32, copy=True),
            hidden_bias=weights["hidden_bias"].astype(np.float32, copy=True),
            output_weight=weights["output_weight"].astype(np.float32, copy=True),
            output_bias=weights["output_bias"].astype(np.float32, copy=True),
            vocabulary=metadata.vocabulary,
            numeric_feature_dim=metadata.numeric_feature_dim,
            embedding_dim=metadata.embedding_dim,
            hidden_dim=metadata.hidden_dim,
            version=metadata.version,
        )
    expected_shapes = {
        "embedding_weight": (len(runtime.vocabulary), runtime.embedding_dim),
        "hidden_weight": (
            runtime.hidden_dim,
            runtime.embedding_dim + runtime.numeric_feature_dim,
        ),
        "hidden_bias": (runtime.hidden_dim,),
        "output_weight": (2, runtime.hidden_dim),
        "output_bias": (2,),
    }
    for name, expected_shape in expected_shapes.items():
        if getattr(runtime, name).shape != expected_shape:
            raise RuntimeError(f"Portable quality array {name} has an invalid shape.")
    if sorted(runtime.vocabulary.values()) != list(range(len(runtime.vocabulary))):
        raise RuntimeError("Portable quality vocabulary indices are invalid.")
    return runtime


class QuestionQualityInferenceService:
    def __init__(
        self,
        *,
        checkpoint_path: Path,
        enable_torch: bool = True,
    ) -> None:
        self.checkpoint_path = checkpoint_path
        self.enable_torch = enable_torch
        self._runtime: _TorchRuntime | _PortableRuntime | None = None
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
            validation = self._heuristic_score(question)
            if self.enable_torch:
                validation.accepted_for_delivery = False
                validation.notes.append(
                    "Required PyTorch quality model is unavailable; delivery is blocked."
                )
            return validation

        encoded = encode_text(question, runtime.vocabulary)
        numeric_values = numeric_features(question)
        if isinstance(runtime, _PortableRuntime):
            probabilities = self._portable_probabilities(runtime, encoded, numeric_values)
            high_quality_probability = float(probabilities[1])
            model_source = "pytorch_portable_export"
        else:
            torch = runtime.torch
            token_tensor = torch.tensor(encoded, dtype=torch.long)
            offsets = torch.tensor([0], dtype=torch.long)
            numeric_tensor = torch.tensor([numeric_values], dtype=torch.float32)

            runtime.model.eval()
            with torch.no_grad():
                logits = runtime.model(token_tensor, offsets, numeric_tensor)
                probabilities = torch.softmax(logits, dim=1)[0]

            high_quality_probability = float(probabilities[1].item())
            model_source = "pytorch_checkpoint"
        confidence = round(abs(high_quality_probability - 0.5) * 2.0, 4)
        label = self._label_for_score(high_quality_probability)
        return QuestionQualityValidation(
            score=round(high_quality_probability, 4),
            confidence=confidence,
            label=label,
            accepted_for_delivery=high_quality_probability >= 0.5,
            model_version=runtime.version,
            model_source=model_source,
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

    def _get_runtime(self) -> _TorchRuntime | _PortableRuntime | None:
        if not self.enable_torch:
            return None
        if self._runtime is not None:
            return self._runtime
        if self._load_attempted:
            return None

        self._load_attempted = True
        if not self.checkpoint_path.exists():
            return None

        torch = _import_torch()
        if torch is not None:
            try:
                from exam_prep.ml.question_quality_model import QuestionQualityClassifier

                checkpoint = torch.load(
                    self.checkpoint_path,
                    map_location="cpu",
                    weights_only=True,
                )
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
                pass

        try:
            self._runtime = _load_portable_runtime(self.checkpoint_path)
            return self._runtime
        except Exception:
            return None

    def _portable_probabilities(
        self,
        runtime: _PortableRuntime,
        encoded: list[int],
        numeric_values: list[float],
    ) -> np.ndarray[Any, np.dtype[np.float32]]:
        embedded = runtime.embedding_weight[np.asarray(encoded, dtype=np.int64)].mean(axis=0)
        combined = np.concatenate((embedded, np.asarray(numeric_values, dtype=np.float32)))
        hidden = np.maximum(runtime.hidden_weight @ combined + runtime.hidden_bias, 0.0)
        logits = runtime.output_weight @ hidden + runtime.output_bias
        shifted = logits - np.max(logits)
        exponentials = np.exp(shifted)
        probabilities = (exponentials / np.sum(exponentials)).astype(np.float32, copy=False)
        return cast(np.ndarray[Any, np.dtype[np.float32]], probabilities)

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
