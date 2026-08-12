from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_RUNTIME_ROOT = PROJECT_ROOT.parent / ".exam_prep_agent"


class Settings(BaseSettings):
    app_name: str = Field(default="Exam Prep Agent")
    app_env: str = Field(default="development")
    debug: bool = Field(default=True)
    app_host: str = Field(default="127.0.0.1")
    app_port: int = Field(default=8000)
    demo_mode: bool = Field(default=True)
    sqlite_path: Path = Field(default=DEFAULT_RUNTIME_ROOT / "exam_prep.sqlite3")
    material_storage_path: Path = Field(default=DEFAULT_RUNTIME_ROOT / "materials")
    default_llm_provider: str = Field(default="openai")
    default_llm_model: str = Field(default="gpt-5.4-mini")
    llm_api_key: str | None = Field(default=None)
    nvidia_api_base_url: str = Field(default="https://integrate.api.nvidia.com/v1")
    openai_api_base_url: str = Field(default="https://api.openai.com/v1")
    anthropic_api_base_url: str = Field(default="https://api.anthropic.com/v1")
    openai_reasoning_effort: str = Field(default="none")
    openai_text_verbosity: str = Field(default="low")
    llm_request_timeout_seconds: float = Field(default=60.0)
    llm_connect_timeout_seconds: float = Field(default=10.0)
    llm_read_timeout_seconds: float = Field(default=90.0)
    llm_write_timeout_seconds: float = Field(default=30.0)
    llm_pool_timeout_seconds: float = Field(default=30.0)
    llm_max_retries: int = Field(default=2)
    llm_max_concurrent_requests: int = Field(default=1)
    llm_enable_response_format: bool = Field(default=True)
    llm_parse_model: str | None = Field(default=None)
    llm_quiz_model: str | None = Field(default=None)
    llm_agent_model: str | None = Field(default=None)
    llm_quiz_generation_model: str | None = Field(default=None)
    llm_quiz_explanation_model: str | None = Field(default=None)
    max_section_tokens_for_parse: int = Field(default=4000, ge=1)
    max_chunks_per_retrieval: int = Field(default=3, ge=1)
    max_agent_context_tokens: int = Field(default=6000, ge=1)
    max_sections_per_upload: int | None = Field(default=None)
    enable_parse_cache: bool = Field(default=True)
    enable_quiz_cache: bool = Field(default=True)
    enable_live_quiz_grading: bool = Field(default=False)
    enable_web_search: bool = Field(default=False)
    frontend_origin: str = Field(default="http://localhost:3000")
    enable_torch_inference: bool = Field(default=True)
    question_quality_checkpoint_path: Path = Field(
        default=Path("./backend/artifacts/question_quality_classifier.pt")
    )
    enable_email_delivery: bool = Field(default=False)
    smtp_host: str | None = Field(default=None)
    smtp_port: int = Field(default=587)
    smtp_username: str | None = Field(default=None)
    smtp_password: str | None = Field(default=None)
    smtp_from_email: str = Field(default="study-coach@example.local")
    smtp_use_tls: bool = Field(default=True)

    @property
    def effective_parse_model(self) -> str:
        return self.llm_parse_model or self.default_llm_model

    @property
    def effective_quiz_model(self) -> str:
        return self.llm_quiz_model or self.default_llm_model

    @property
    def effective_agent_model(self) -> str:
        return self.llm_agent_model or self.default_llm_model

    model_config = SettingsConfigDict(
        env_prefix="EXAM_PREP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
