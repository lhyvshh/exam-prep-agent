class ExamPrepError(Exception):
    """Base application error."""


class ConfigurationError(ExamPrepError):
    """Raised when configuration is invalid."""


class MaterialIngestionError(ExamPrepError):
    """Raised when material ingestion fails."""


class LLMProviderError(ExamPrepError):
    """Raised when a live LLM provider call fails."""


class LLMTransportError(LLMProviderError):
    """Raised when a live LLM provider call fails because of a transport issue."""


class LLMResponseSchemaError(LLMProviderError):
    """Raised when a live LLM provider returns a payload that cannot be validated."""


class WorkflowStateError(ExamPrepError):
    """Raised when workflow state cannot be resolved."""
