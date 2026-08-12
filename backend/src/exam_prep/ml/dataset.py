from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from exam_prep.schemas.ml import QuestionQualityInput

TRAINING_LABEL_TO_INDEX = {
    "low_quality": 0,
    "high_quality": 1,
}
INDEX_TO_TRAINING_LABEL = {index: label for label, index in TRAINING_LABEL_TO_INDEX.items()}
UNKNOWN_TOKEN = "<unk>"
TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


@dataclass(slots=True)
class QuestionQualityExample:
    prompt: str
    question_type: str
    concept: str
    section_title: str
    difficulty: float
    options: list[str]
    rationale: str | None
    citation_count: int
    label_index: int

    def to_input(self) -> QuestionQualityInput:
        return QuestionQualityInput(
            prompt=self.prompt,
            question_type=self.question_type,
            concept=self.concept,
            section_title=self.section_title,
            difficulty=self.difficulty,
            options=self.options,
            rationale=self.rationale,
            citation_count=self.citation_count,
        )


def load_question_quality_examples(path: Path) -> list[QuestionQualityExample]:
    examples: list[QuestionQualityExample] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        payload = json.loads(line)
        label = payload["label"]
        if label not in TRAINING_LABEL_TO_INDEX:
            raise ValueError(
                f"Unsupported quality label '{label}' at line {line_number}. "
                f"Expected one of {sorted(TRAINING_LABEL_TO_INDEX)}."
            )
        examples.append(
            QuestionQualityExample(
                prompt=payload["prompt"],
                question_type=payload["question_type"],
                concept=payload.get("concept", ""),
                section_title=payload.get("section_title", ""),
                difficulty=float(payload.get("difficulty", 0.5)),
                options=[str(option) for option in payload.get("options", [])],
                rationale=payload.get("rationale"),
                citation_count=int(payload.get("citation_count", 0)),
                label_index=TRAINING_LABEL_TO_INDEX[label],
            )
        )
    if not examples:
        raise ValueError(f"No training examples were found in {path}.")
    return examples


def build_example_text(input_data: QuestionQualityInput) -> str:
    parts = [
        input_data.prompt,
        input_data.question_type,
        input_data.concept,
        input_data.section_title,
        input_data.rationale or "",
        " ".join(input_data.options),
    ]
    return " ".join(part for part in parts if part).strip()


def tokenize(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(text.lower())


def build_vocabulary(
    examples: list[QuestionQualityExample],
    *,
    min_frequency: int = 1,
    max_tokens: int = 2048,
) -> dict[str, int]:
    token_counts: Counter[str] = Counter()
    for example in examples:
        token_counts.update(tokenize(build_example_text(example.to_input())))

    vocabulary: dict[str, int] = {UNKNOWN_TOKEN: 0}
    for token, count in token_counts.most_common():
        if count < min_frequency:
            continue
        if token in vocabulary:
            continue
        vocabulary[token] = len(vocabulary)
        if len(vocabulary) >= max_tokens:
            break
    return vocabulary


def encode_text(input_data: QuestionQualityInput, vocabulary: dict[str, int]) -> list[int]:
    encoded = [vocabulary.get(token, 0) for token in tokenize(build_example_text(input_data))]
    return encoded or [0]


def numeric_features(input_data: QuestionQualityInput) -> list[float]:
    prompt_tokens = max(len(tokenize(input_data.prompt)), 1)
    average_option_tokens = (
        sum(len(tokenize(option)) for option in input_data.options) / len(input_data.options)
        if input_data.options
        else 0.0
    )
    return [
        min(1.0, prompt_tokens / 40.0),
        1.0 if input_data.question_type == "mcq" else 0.0,
        1.0 if 2 <= len(input_data.options) <= 8 else 0.0,
        min(1.0, float(input_data.citation_count) / 3.0),
        min(1.0, average_option_tokens / 20.0),
        float(input_data.difficulty),
        1.0 if (input_data.rationale or "").strip() else 0.0,
    ]
