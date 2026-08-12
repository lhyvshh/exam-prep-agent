from exam_prep.repositories.config_store import ConfigStore
from exam_prep.schemas.config import UserLLMConfig


class InMemoryConfigStore(ConfigStore):
    def __init__(self, initial_config: UserLLMConfig | None = None) -> None:
        self._configs: dict[str, UserLLMConfig] = {}
        if initial_config is not None:
            self._configs["current"] = initial_config

    def get(self, profile: str = "current") -> UserLLMConfig | None:
        return self._configs.get(profile)

    def save(self, config: UserLLMConfig, profile: str = "current") -> UserLLMConfig:
        self._configs[profile] = config
        return config
