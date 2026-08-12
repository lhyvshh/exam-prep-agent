from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import torch
from torch import Tensor, nn


class QuestionQualityClassifier(nn.Module):
    def __init__(
        self,
        *,
        vocab_size: int,
        embedding_dim: int,
        numeric_feature_dim: int,
        hidden_dim: int,
    ) -> None:
        super().__init__()
        self.embedding = nn.EmbeddingBag(vocab_size, embedding_dim, mode="mean")
        self.classifier = nn.Sequential(
            nn.Linear(embedding_dim + numeric_feature_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(p=0.1),
            nn.Linear(hidden_dim, 2),
        )

    def forward(
        self,
        token_indices: Tensor,
        offsets: Tensor,
        numeric_tensor: Tensor,
    ) -> Tensor:
        embedded = self.embedding(token_indices, offsets)
        combined = torch.cat((embedded, numeric_tensor), dim=1)
        return cast(Tensor, self.classifier(combined))


@dataclass(slots=True)
class EncodedBatch:
    token_indices: Tensor
    offsets: Tensor
    numeric_tensor: Tensor
    labels: Tensor
