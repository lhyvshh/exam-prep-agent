from exam_prep.core.config import Settings
from exam_prep.llm.models import LLMResponse
from exam_prep.llm.registry import LLMClientRegistry
from exam_prep.repositories.in_memory.config_store import InMemoryConfigStore
from exam_prep.schemas.config import ConfigValidationRequest, UserLLMConfig
from exam_prep.services.config_service import ConfigService


def test_config_service_hides_secret_presence() -> None:
    settings = Settings(
        app_name="Exam Prep Agent",
        app_env="test",
        debug=True,
        demo_mode=False,
        sqlite_path="data/local.sqlite3",
        default_llm_provider="openai",
        default_llm_model="gpt-4.1-mini",
        llm_api_key="secret-value",
        enable_web_search=False,
        frontend_origin="http://localhost:3000",
    )

    result = ConfigService().get_public_config(settings)

    assert result.has_api_key is True
    assert result.default_llm_model == "gpt-4.1-mini"
    assert result.sqlite_path == "data/local.sqlite3"


def test_config_validation_requires_api_key_when_demo_is_disabled() -> None:
    service = ConfigService()
    store = InMemoryConfigStore()

    result = service.validate_and_store(
        ConfigValidationRequest(
            provider="openai",
            model="gpt-4.1-mini",
            api_key=None,
            demo_mode=False,
        ),
        store,
    )

    assert result.is_valid is False
    assert result.can_proceed is False
    assert store.get() is None


def test_config_validation_uses_fast_profile_and_persists_live_config() -> None:
    used_profiles: list[str] = []

    class FakeClient:
        def generate(self, request):  # type: ignore[no-untyped-def]
            assert request.request_name == "ConfigValidationPing"
            return LLMResponse(
                model_name=request.model_name,
                raw_text="OK",
                provider_name="nvidia",
            )

    class FakeRegistry:
        def get_or_create_for_profile(self, config, *, profile):  # type: ignore[no-untyped-def]
            del config
            used_profiles.append(profile)
            return FakeClient()

    store = InMemoryConfigStore()

    result = ConfigService().validate_and_store(
        ConfigValidationRequest(
            provider="nvidia",
            model="meta/llama-3.1-8b-instruct",
            api_key="nvapi-test-key",
            demo_mode=False,
        ),
        store,
        llm_client_registry=FakeRegistry(),
    )

    assert result.is_valid is True
    assert result.status == "valid"
    assert used_profiles == ["config_validation"]
    assert store.get() is not None


def test_config_service_persists_butler_profile_without_replacing_default() -> None:
    service = ConfigService()
    store = InMemoryConfigStore(
        UserLLMConfig(provider="openai", model="gpt-5.4-mini", api_key=None, demo_mode=True)
    )

    result = service.validate_and_store(
        ConfigValidationRequest(
            provider="openai",
            model="gpt-5.4",
            api_key=None,
            demo_mode=True,
        ),
        store,
        profile="butler",
    )
    runtime = service.get_runtime_config(Settings(), store)

    assert result.is_valid is True
    assert store.get() is not None
    assert store.get().model == "gpt-5.4-mini"
    assert runtime.config.model == "gpt-5.4-mini"
    assert runtime.butler_config.model == "gpt-5.4"


def test_config_service_exposes_parser_profile_with_parse_model_default() -> None:
    service = ConfigService()
    store = InMemoryConfigStore(
        UserLLMConfig(provider="openai", model="gpt-5.4-mini", api_key="sk-current", demo_mode=False)
    )
    settings = Settings(
        default_llm_provider="openai",
        default_llm_model="gpt-5.4-mini",
        llm_parse_model="gpt-5.4-parser",
        llm_api_key="sk-default",
    )

    runtime = service.get_runtime_config(settings, store)

    assert runtime.config.model == "gpt-5.4-mini"
    assert runtime.parser_config.model == "gpt-5.4-parser"
    assert runtime.parser_config.provider == "openai"
    assert runtime.parser_config.api_key == "sk-current"


def test_config_service_persists_parser_profile_without_replacing_butler_or_default() -> None:
    service = ConfigService()
    store = InMemoryConfigStore(
        UserLLMConfig(provider="openai", model="gpt-5.4-mini", api_key=None, demo_mode=True)
    )
    service.validate_and_store(
        ConfigValidationRequest(
            provider="anthropic",
            model="claude-sonnet-4-5",
            api_key=None,
            demo_mode=True,
        ),
        store,
        profile="butler",
    )

    result = service.validate_and_store(
        ConfigValidationRequest(
            provider="openai",
            model="gpt-5.4-parser",
            api_key=None,
            demo_mode=True,
        ),
        store,
        profile="parser",
    )
    runtime = service.get_runtime_config(Settings(), store)

    assert result.is_valid is True
    assert runtime.config.model == "gpt-5.4-mini"
    assert runtime.butler_config.model == "claude-sonnet-4-5"
    assert runtime.parser_config.model == "gpt-5.4-parser"


def test_llm_client_registry_cache_key_includes_model_name() -> None:
    created_models: list[str] = []

    def fake_factory(settings, config, *, profile):  # type: ignore[no-untyped-def]
        del settings, profile
        created_models.append(config.model)
        return None

    registry = LLMClientRegistry(Settings(), factory=fake_factory)
    first = UserLLMConfig(
        provider="openai",
        model="gpt-5.4-mini",
        api_key="sk-test",
        demo_mode=False,
    )
    second = first.model_copy(update={"model": "gpt-5.4"})

    registry.get_or_create_for_profile(first, profile="butler")
    registry.get_or_create_for_profile(second, profile="butler")

    assert created_models == ["gpt-5.4-mini", "gpt-5.4"]


def test_cost_control_settings_default_to_cached_bounded_llm_usage() -> None:
    settings = Settings(default_llm_model="gpt-5.4-mini")

    assert settings.effective_parse_model == "gpt-5.4-mini"
    assert settings.effective_quiz_model == "gpt-5.4-mini"
    assert settings.effective_agent_model == "gpt-5.4-mini"
    assert settings.max_section_tokens_for_parse == 4000
    assert settings.max_chunks_per_retrieval == 3
    assert settings.max_agent_context_tokens == 6000
    assert settings.enable_parse_cache is True
    assert settings.enable_quiz_cache is True
