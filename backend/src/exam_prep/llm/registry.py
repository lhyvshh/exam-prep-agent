from typing import Protocol

from exam_prep.core.config import Settings
from exam_prep.llm.base import LLMClient
from exam_prep.llm.factory import create_llm_client
from exam_prep.schemas.config import UserLLMConfig


class LLMClientFactory(Protocol):
    def __call__(
        self,
        settings: Settings,
        config: UserLLMConfig,
        *,
        profile: str = "default",
    ) -> LLMClient | None:
        ...


class LLMClientRegistry:
    def __init__(
        self,
        settings: Settings,
        *,
        factory: LLMClientFactory = create_llm_client,
    ) -> None:
        self.settings = settings
        self.factory = factory
        self._clients: dict[str, LLMClient | None] = {}

    def get_or_create(self, config: UserLLMConfig) -> LLMClient | None:
        return self.get_or_create_for_profile(config, profile="default")

    def get_or_create_for_profile(
        self,
        config: UserLLMConfig,
        *,
        profile: str,
    ) -> LLMClient | None:
        cache_key = self._cache_key(config, profile)
        if cache_key not in self._clients:
            self._clients[cache_key] = self.factory(self.settings, config, profile=profile)
        return self._clients[cache_key]

    def close_all(self) -> None:
        for client in self._clients.values():
            close = getattr(client, "close", None)
            if callable(close):
                close()
        self._clients.clear()

    def _cache_key(self, config: UserLLMConfig, profile: str) -> str:
        api_key = config.api_key or ""
        return (
            f"{profile}:{config.provider.value}:{config.model}:{api_key}:"
            f"{self.settings.nvidia_api_base_url}:{config.demo_mode}"
        )
