from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).parents[2]
CHECKPOINT = ROOT / "backend" / "artifacts" / "question_quality_classifier.pt"
METADATA = CHECKPOINT.with_name("question_quality_classifier.portable.json")
WEIGHTS = CHECKPOINT.with_name("question_quality_classifier.portable.npz")


def write_deterministic_weights(path: Path, arrays: dict[str, np.ndarray]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(arrays):
            buffer = io.BytesIO()
            np.lib.format.write_array(buffer, arrays[name], allow_pickle=False)
            info = zipfile.ZipInfo(f"{name}.npy", date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, buffer.getvalue())


def main() -> None:
    checkpoint = torch.load(CHECKPOINT, map_location="cpu", weights_only=True)
    state = checkpoint["state_dict"]
    digest = hashlib.sha256(CHECKPOINT.read_bytes()).hexdigest()
    arrays = {
        "embedding_weight": state["embedding.weight"].detach().cpu().numpy(),
        "hidden_weight": state["classifier.0.weight"].detach().cpu().numpy(),
        "hidden_bias": state["classifier.0.bias"].detach().cpu().numpy(),
        "output_weight": state["classifier.3.weight"].detach().cpu().numpy(),
        "output_bias": state["classifier.3.bias"].detach().cpu().numpy(),
    }
    write_deterministic_weights(WEIGHTS, arrays)
    metadata = {
        "embedding_dim": int(checkpoint["embedding_dim"]),
        "format": "exam-prep-pytorch-embedding-classifier-v1",
        "hidden_dim": int(checkpoint["hidden_dim"]),
        "numeric_feature_dim": int(checkpoint["numeric_feature_dim"]),
        "source_checkpoint_sha256": digest,
        "version": str(checkpoint.get("version", "question-quality-v1")),
        "vocabulary": dict(checkpoint["vocabulary"]),
        "weights_sha256": hashlib.sha256(WEIGHTS.read_bytes()).hexdigest(),
    }
    METADATA.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(digest)


if __name__ == "__main__":
    main()
