from typing import Protocol

from exam_prep.schemas.config import UserLLMConfig


class ConfigStore(Protocol):
    def get(self, profile: str = "current") -> UserLLMConfig | None:
        ...

    def save(self, config: UserLLMConfig, profile: str = "current") -> UserLLMConfig:
        ...
