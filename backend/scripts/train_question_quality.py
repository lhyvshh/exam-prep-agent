from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import TYPE_CHECKING

from exam_prep.ml.dataset import (
    INDEX_TO_TRAINING_LABEL,
    QuestionQualityExample,
    build_vocabulary,
    encode_text,
    load_question_quality_examples,
    numeric_features,
)

if TYPE_CHECKING:
    import torch

    from exam_prep.ml.question_quality_model import QuestionQualityClassifier


def repository_relative_path(path: Path, project_root: Path) -> str:
    return path.resolve().relative_to(project_root.resolve()).as_posix()


def parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[2]
    return argparse.Namespace(
        dataset=project_root / "backend/data/question_quality_labeled.jsonl",
        checkpoint=project_root / "backend/artifacts/question_quality_classifier.pt",
        metrics=project_root / "backend/artifacts/question_quality_eval.json",
        epochs=80,
        embedding_dim=24,
        hidden_dim=24,
        learning_rate=0.03,
        seed=7,
    )


def stratified_split(
    examples: list[QuestionQualityExample],
) -> tuple[list[QuestionQualityExample], list[QuestionQualityExample]]:
    grouped: dict[int, list[QuestionQualityExample]] = {}
    for example in examples:
        grouped.setdefault(example.label_index, []).append(example)

    train_examples: list[QuestionQualityExample] = []
    eval_examples: list[QuestionQualityExample] = []
    for label_examples in grouped.values():
        cutoff = max(1, len(label_examples) // 4)
        eval_examples.extend(label_examples[:cutoff])
        train_examples.extend(label_examples[cutoff:])
    return train_examples, eval_examples


def build_batch(
    examples: list[QuestionQualityExample],
    vocabulary: dict[str, int],
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    import torch

    token_indices: list[int] = []
    offsets: list[int] = []
    numeric_rows: list[list[float]] = []
    labels: list[int] = []

    for example in examples:
        offsets.append(len(token_indices))
        input_data = example.to_input()
        token_indices.extend(encode_text(input_data, vocabulary))
        numeric_rows.append(numeric_features(input_data))
        labels.append(example.label_index)

    return (
        torch.tensor(token_indices, dtype=torch.long),
        torch.tensor(offsets, dtype=torch.long),
        torch.tensor(numeric_rows, dtype=torch.float32),
        torch.tensor(labels, dtype=torch.long),
    )


def evaluate(
    model: QuestionQualityClassifier,
    examples: list[QuestionQualityExample],
    vocabulary: dict[str, int],
) -> dict[str, float]:
    import torch
    from torch import nn

    model.eval()
    token_indices, offsets, numeric_tensor, labels = build_batch(examples, vocabulary)
    with torch.no_grad():
        logits = model(token_indices, offsets, numeric_tensor)
        loss = nn.CrossEntropyLoss()(logits, labels)
        predictions = torch.argmax(logits, dim=1)
    accuracy = float((predictions == labels).float().mean().item())
    return {
        "loss": round(float(loss.item()), 4),
        "accuracy": round(accuracy, 4),
    }


def main() -> None:
    import torch
    from torch import nn
    from torch.optim import Adam

    from exam_prep.ml.question_quality_model import QuestionQualityClassifier

    args = parse_args()
    project_root = Path(__file__).resolve().parents[2]
    random.seed(args.seed)
    torch.manual_seed(args.seed)

    examples = load_question_quality_examples(args.dataset)
    random.shuffle(examples)
    train_examples, eval_examples = stratified_split(examples)
    vocabulary = build_vocabulary(train_examples)
    numeric_feature_dim = len(numeric_features(train_examples[0].to_input()))
    model = QuestionQualityClassifier(
        vocab_size=len(vocabulary),
        embedding_dim=args.embedding_dim,
        numeric_feature_dim=numeric_feature_dim,
        hidden_dim=args.hidden_dim,
    )

    optimizer = Adam(model.parameters(), lr=args.learning_rate)
    loss_fn = nn.CrossEntropyLoss()
    token_indices, offsets, numeric_tensor, labels = build_batch(train_examples, vocabulary)

    model.train()
    train_loss = 0.0
    for _ in range(args.epochs):
        optimizer.zero_grad()
        logits = model(token_indices, offsets, numeric_tensor)
        loss = loss_fn(logits, labels)
        loss.backward()
        optimizer.step()
        train_loss = float(loss.item())

    train_metrics = evaluate(model, train_examples, vocabulary)
    eval_metrics = evaluate(model, eval_examples, vocabulary)
    args.checkpoint.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "state_dict": model.state_dict(),
            "vocabulary": vocabulary,
            "numeric_feature_dim": numeric_feature_dim,
            "embedding_dim": args.embedding_dim,
            "hidden_dim": args.hidden_dim,
            "version": "question-quality-classifier-v2",
            "label_mapping": INDEX_TO_TRAINING_LABEL,
        },
        args.checkpoint,
    )

    metrics_payload = {
        "dataset_path": repository_relative_path(args.dataset, project_root),
        "checkpoint_path": repository_relative_path(args.checkpoint, project_root),
        "train_example_count": len(train_examples),
        "eval_example_count": len(eval_examples),
        "final_train_loss": round(train_loss, 4),
        "train_metrics": train_metrics,
        "eval_metrics": eval_metrics,
    }
    args.metrics.write_text(json.dumps(metrics_payload, indent=2), encoding="utf-8")
    print(json.dumps(metrics_payload, indent=2))


if __name__ == "__main__":
    main()
