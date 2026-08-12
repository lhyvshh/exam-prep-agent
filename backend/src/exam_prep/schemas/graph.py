from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from exam_prep.schemas.quiz import QuizBundle


class NodeExecutionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_name: str | None = None
    node_name: str
    status: str
    details: str | None = None


class GroundingContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    material_id: str
    excerpt: str
    score: float = 0.0


class AgentMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_name: str
    message: str


class QualityCheckSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gate_enabled: bool = True
    uses_torch: bool = False
    accepted_for_delivery: bool = False
    notes: list[str] = Field(default_factory=list)


class ExamPrepGraphState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str | None = None
    intent: str | None = None
    course_id: str | None = None
    module_id: str | None = None
    requested_module_ids: list[str] = Field(default_factory=list)
    requested_material_ids: list[str] = Field(default_factory=list)
    requested_section_ids: list[str] = Field(default_factory=list)
    material_ids: list[str] = Field(default_factory=list)
    scope_source_ids: list[str] = Field(default_factory=list)
    grounding_context: list[GroundingContext] = Field(default_factory=list)
    active_quiz: QuizBundle | None = None
    active_exam_scope_label: str | None = None
    mastery_by_concept: dict[str, float] = Field(default_factory=dict)
    wrong_concepts: list[str] = Field(default_factory=list)
    quality_summary: QualityCheckSummary | None = None
    agent_recommendations: list[dict[str, Any]] = Field(default_factory=list)
    agent_messages: list[AgentMessage] = Field(default_factory=list)
    execution_trace: list[NodeExecutionRecord] = Field(default_factory=list)
