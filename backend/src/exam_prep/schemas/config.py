from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class LLMProvider(StrEnum):
    NVIDIA = "nvidia"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    GROQ = "groq"
    OPENROUTER = "openrouter"
    OLLAMA = "ollama"
    AZURE_OPENAI = "azure_openai"
    OTHER = "other"


class ConfigValidationStatus(StrEnum):
    VALID = "valid"
    INVALID = "invalid"
    DEMO_READY = "demo_ready"


class UserLLMConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: LLMProvider
    model: str = Field(min_length=1)
    api_key: str | None = None
    demo_mode: bool = True


class ConfigValidationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: LLMProvider
    model: str = Field(min_length=1)
    api_key: str | None = None
    demo_mode: bool = True


class ConfigValidationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_valid: bool
    status: ConfigValidationStatus
    message: str
    config: UserLLMConfig
    can_proceed: bool


class RuntimeConfigResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config: UserLLMConfig
    butler_config: UserLLMConfig
    parser_config: UserLLMConfig
    source: str


class PublicAppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    app_name: str
    app_env: str
    debug: bool
    demo_mode: bool
    sqlite_path: str
    default_llm_provider: str
    default_llm_model: str
    has_api_key: bool
    enable_web_search: bool
    frontend_origin: str


class ConfigHealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    status: str
    config_present: bool
