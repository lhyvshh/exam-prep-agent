from pydantic import BaseModel, ConfigDict, Field


class LLMRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_name: str
    system_prompt: str
    user_prompt: str
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1200, ge=1, le=8192)
    request_name: str | None = None
    response_format: dict[str, object] | None = None
    request_context: dict[str, str] = Field(default_factory=dict)


class LLMResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_name: str
    raw_text: str
    provider_name: str
    latency_ms: float | None = None
    request_id: str | None = None
    response_phase: str | None = None
