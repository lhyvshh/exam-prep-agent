import json
from pathlib import Path

from backend.scripts.train_question_quality import repository_relative_path


def test_training_metadata_uses_repository_relative_paths() -> None:
    project_root = Path("/workspace/exam-prep")

    result = repository_relative_path(
        project_root / "backend/data/question_quality_labeled.jsonl",
        project_root,
    )

    assert result == "backend/data/question_quality_labeled.jsonl"


def test_committed_training_metrics_do_not_contain_local_paths() -> None:
    metrics_path = Path("backend/artifacts/question_quality_eval.json")

    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))

    assert metrics["dataset_path"] == "backend/data/question_quality_labeled.jsonl"
    assert metrics["checkpoint_path"] == "backend/artifacts/question_quality_classifier.pt"
