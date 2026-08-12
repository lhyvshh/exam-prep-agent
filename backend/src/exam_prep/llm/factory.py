from exam_prep.core.exceptions import ConfigurationError
from exam_prep.core.config import Settings
from exam_prep.llm.anthropic import AnthropicMessagesClient
from exam_prep.llm.base import LLMClient
from exam_prep.llm.nvidia import NvidiaOpenAICompatibleClient
from exam_prep.llm.openai import OpenAIResponsesClient
from exam_prep.schemas.config import LLMProvider, UserLLMConfig


def create_llm_client(
    settings: Settings,
    config: UserLLMConfig,
    *,
    profile: str = "default",
) -> LLMClient | None:
    if config.demo_mode:
        return None

    if not config.api_key:
        raise ConfigurationError("An API key is required for live model calls.")

    timeout_seconds = settings.llm_request_timeout_seconds
    connect_timeout = settings.llm_connect_timeout_seconds
    read_timeout = settings.llm_read_timeout_seconds
    write_timeout = settings.llm_write_timeout_seconds
    pool_timeout = settings.llm_pool_timeout_seconds
    max_retries = settings.llm_max_retries

    if profile == "config_validation":
        timeout_seconds = min(timeout_seconds, 15.0)
        read_timeout = min(read_timeout, 12.0)
        write_timeout = min(write_timeout, 15.0)
        pool_timeout = min(pool_timeout, 15.0)
        max_retries = 0

    if profile == "quiz_generation":
        read_timeout = min(read_timeout, 30.0)
        write_timeout = min(write_timeout, 30.0)
        pool_timeout = max(pool_timeout, 30.0)
        max_retries = min(max_retries, 1)

    if config.provider == LLMProvider.OPENAI:
        return OpenAIResponsesClient(
            api_key=config.api_key,
            model_name=config.model,
            base_url=settings.openai_api_base_url,
            timeout_seconds=timeout_seconds,
            connect_timeout_seconds=connect_timeout,
            read_timeout_seconds=read_timeout,
            write_timeout_seconds=write_timeout,
            pool_timeout_seconds=pool_timeout,
            max_retries=max_retries,
            max_concurrent_requests=settings.llm_max_concurrent_requests,
            enable_response_format=settings.llm_enable_response_format,
            reasoning_effort=settings.openai_reasoning_effort,
            text_verbosity=settings.openai_text_verbosity,
        )

    if config.provider == LLMProvider.NVIDIA:
        return NvidiaOpenAICompatibleClient(
            api_key=config.api_key,
            model_name=config.model,
            base_url=settings.nvidia_api_base_url,
            timeout_seconds=timeout_seconds,
            connect_timeout_seconds=connect_timeout,
            read_timeout_seconds=read_timeout,
            write_timeout_seconds=write_timeout,
            pool_timeout_seconds=pool_timeout,
            max_retries=max_retries,
            max_concurrent_requests=settings.llm_max_concurrent_requests,
            enable_response_format=settings.llm_enable_response_format,
        )

    if config.provider == LLMProvider.ANTHROPIC:
        return AnthropicMessagesClient(
            api_key=config.api_key,
            model_name=config.model,
            base_url=settings.anthropic_api_base_url,
            timeout_seconds=timeout_seconds,
            connect_timeout_seconds=connect_timeout,
            read_timeout_seconds=read_timeout,
            write_timeout_seconds=write_timeout,
            pool_timeout_seconds=pool_timeout,
            max_retries=max_retries,
            max_concurrent_requests=settings.llm_max_concurrent_requests,
        )

    raise ConfigurationError(
        f'Live provider "{config.provider.value}" is not implemented in this local build. '
        'Use OpenAI, NVIDIA, Anthropic, or enable demo mode.'
    )
