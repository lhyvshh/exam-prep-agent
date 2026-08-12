import logging

from exam_prep.core.config import Settings, get_settings
from exam_prep.core.exceptions import LLMProviderError, LLMTransportError
from exam_prep.llm.models import LLMRequest
from exam_prep.llm.registry import LLMClientRegistry
from exam_prep.repositories.config_store import ConfigStore
from exam_prep.schemas.config import (
    ConfigHealthResponse,
    ConfigValidationRequest,
    ConfigValidationResponse,
    ConfigValidationStatus,
    LLMProvider,
    PublicAppConfig,
    RuntimeConfigResponse,
    UserLLMConfig,
)

logger = logging.getLogger(__name__)


class ConfigService:
    def get_public_config(self, settings: Settings) -> PublicAppConfig:
        return PublicAppConfig(
            app_name=settings.app_name,
            app_env=settings.app_env,
            debug=settings.debug,
            demo_mode=settings.demo_mode,
            sqlite_path=str(settings.sqlite_path),
            default_llm_provider=settings.default_llm_provider,
            default_llm_model=settings.default_llm_model,
            has_api_key=bool(settings.llm_api_key),
            enable_web_search=settings.enable_web_search,
            frontend_origin=settings.frontend_origin,
        )

    def get_runtime_config(
        self,
        settings: Settings,
        store: ConfigStore,
    ) -> RuntimeConfigResponse:
        default_config = UserLLMConfig(
            provider=LLMProvider(settings.default_llm_provider),
            model=settings.default_llm_model,
            api_key=settings.llm_api_key,
            demo_mode=settings.demo_mode,
        )
        stored_config = store.get("current")
        butler_config = store.get("butler")
        parser_config = store.get("parser")
        runtime_config = stored_config or default_config
        parser_default = runtime_config.model_copy(update={"model": settings.effective_parse_model})
        return RuntimeConfigResponse(
            config=runtime_config,
            butler_config=butler_config or runtime_config,
            parser_config=parser_config or parser_default,
            source="sqlite_store" if stored_config is not None else "settings_default",
        )

    def validate_and_store(
        self,
        request: ConfigValidationRequest,
        store: ConfigStore,
        settings: Settings | None = None,
        llm_client_registry: LLMClientRegistry | None = None,
        profile: str = "current",
    ) -> ConfigValidationResponse:
        normalized_model = request.model.strip()
        normalized_api_key = (request.api_key or "").strip() or None
        if not normalized_model:
            return ConfigValidationResponse(
                is_valid=False,
                status=ConfigValidationStatus.INVALID,
                message="Model is required.",
                config=UserLLMConfig(
                    provider=request.provider,
                    model="placeholder-model",
                    api_key=normalized_api_key,
                    demo_mode=request.demo_mode,
                ),
                can_proceed=False,
            )

        config = UserLLMConfig(
            provider=request.provider,
            model=normalized_model,
            api_key=normalized_api_key,
            demo_mode=request.demo_mode,
        )

        if not config.demo_mode and not config.api_key:
            return ConfigValidationResponse(
                is_valid=False,
                status=ConfigValidationStatus.INVALID,
                message="API key is required when demo mode is disabled.",
                config=config,
                can_proceed=False,
            )

        if config.demo_mode:
            store.save(config, profile=profile)
            return ConfigValidationResponse(
                is_valid=True,
                status=ConfigValidationStatus.DEMO_READY,
                message="Demo mode is enabled. The system can proceed without a live API key.",
                config=config,
                can_proceed=True,
            )

        logger.info(
            "Validating live provider configuration provider=%s model=%s",
            config.provider.value,
            config.model,
        )
        registry = llm_client_registry or LLMClientRegistry(settings or get_settings())
        client = registry.get_or_create_for_profile(config, profile="config_validation")
        if client is None:
            return ConfigValidationResponse(
                is_valid=False,
                status=ConfigValidationStatus.INVALID,
                message="Demo mode is enabled and no live provider was created.",
                config=config,
                can_proceed=False,
            )
        try:
            response = client.generate(
                LLMRequest(
                    model_name=config.model,
                    system_prompt=(
                        "You are a provider connectivity check. Reply with exactly OK. "
                        "Do not add markdown, commentary, or extra tokens."
                    ),
                    user_prompt="Reply with OK.",
                    temperature=0.0,
                    max_tokens=32,
                    request_name="ConfigValidationPing",
                    request_context={
                        "provider": config.provider.value,
                        "validation_mode": "connectivity_check",
                    },
                )
            )
        except LLMTransportError as exc:
            raise LLMProviderError(
                "Validation timed out before the model produced a reply. "
                "Try a faster NVIDIA chat model or retry once."
            ) from exc

        if not response.raw_text.strip():
            raise ValueError("Provider returned an empty validation response.")

        store.save(config, profile=profile)
        return ConfigValidationResponse(
            is_valid=True,
            status=ConfigValidationStatus.VALID,
            message="Live provider validation succeeded.",
            config=config,
            can_proceed=True,
        )

    def get_config_health(self, store: ConfigStore) -> ConfigHealthResponse:
        config = store.get()
        if config is None:
            return ConfigHealthResponse(ok=False, status="missing_config", config_present=False)

        if config.demo_mode:
            return ConfigHealthResponse(ok=True, status="demo_mode", config_present=True)

        if config.api_key:
            return ConfigHealthResponse(ok=True, status="ready", config_present=True)

        return ConfigHealthResponse(ok=False, status="missing_api_key", config_present=True)
