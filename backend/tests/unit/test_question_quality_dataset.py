from pathlib import Path

import pytest

from exam_prep.ml.dataset import load_question_quality_examples


def test_load_question_quality_examples_reads_jsonl_fixture() -> None:
    dataset_path = Path("backend/data/question_quality_labeled.jsonl")
    examples = load_question_quality_examples(dataset_path)

    assert len(examples) >= 20
    assert {example.label_index for example in examples} == {0, 1}


def test_load_question_quality_examples_rejects_unknown_labels(tmp_path: Path) -> None:
    dataset_path = tmp_path / "broken.jsonl"
    dataset_path.write_text(
        '{"prompt":"bad","question_type":"mcq","label":"mystery"}\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Unsupported quality label"):
        load_question_quality_examples(dataset_path)
