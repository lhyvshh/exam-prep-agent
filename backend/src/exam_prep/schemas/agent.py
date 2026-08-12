from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from exam_prep.schemas.graph import AgentMessage, NodeExecutionRecord, QualityCheckSummary
from exam_prep.schemas.materials import MaterialRecord, MaterialStudySection
from exam_prep.schemas.scope import StudyScope


class SourceTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    material_id: str
    section_id: str | None = None
    source_id: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    anchor_text: str | None = None
    asset_id: str | None = None
    return_origin: dict[str, Any] = Field(default_factory=dict)


class SourceResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: SourceTarget


class SourceResolveResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: SourceTarget
    material: MaterialRecord
    section: MaterialStudySection | None = None
    page_start: int | None = None
    page_end: int | None = None
    file_url: str
    page_image_url: str | None = None
    embedded_images_url: str | None = None
    fallback_notice: str | None = None


class AgentRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    course_id: str
    scope: StudyScope
    agent_name: str
    recommendation_type: str
    title: str
    reason: str
    target_action: str
    target_payload: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=50, ge=0, le=100)
    created_at: str
    dismissed_at: str | None = None


class AgentProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_name: str
    display_name: str
    role: str
    personality: str
    skills: list[str] = Field(default_factory=list)
    operating_rules: list[str] = Field(default_factory=list)
    sample_line: str | None = None


class AgentRunRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    intent: str
    course_id: str
    scope: StudyScope
    node_statuses: list[NodeExecutionRecord] = Field(default_factory=list)
    agent_messages: list[AgentMessage] = Field(default_factory=list)
    recommendations: list[AgentRecommendation] = Field(default_factory=list)
    quality_summary: QualityCheckSummary | None = None
    agent_profiles: list[AgentProfile] = Field(default_factory=list)
    created_at: str


class AgentRunRequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: str = "progress_check"
    scope: StudyScope


class AgentRecommendationListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    course_id: str
    recommendations: list[AgentRecommendation] = Field(default_factory=list)
    latest_run: AgentRunRecord | None = None
    agent_profiles: list[AgentProfile] = Field(default_factory=list)


class AgentRecommendationDismissResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    dismissed: bool


class AgentMemoryProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    course_id: str
    preferred_study_style: str = "balanced"
    preferred_quiz_format: str = "mcq"
    default_question_count: int = Field(default=3, ge=1, le=10)
    focus_areas: list[str] = Field(default_factory=list)
    encouragement_style: str = "steady"
    progress_notes: list[str] = Field(default_factory=list)
    updated_at: str | None = None


class AgentMemoryUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preferred_study_style: str = "balanced"
    preferred_quiz_format: str = "mcq"
    default_question_count: int = Field(default=3, ge=1, le=10)
    focus_areas: list[str] = Field(default_factory=list)
    encouragement_style: str = "steady"
    progress_notes: list[str] = Field(default_factory=list)


class AgentActionCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    action: str
    href: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    tone: str = "primary"


class AgentPageQuestionOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    option_id: str
    text: str


class AgentPageQuestionContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_number: int | None = None
    question_id: str | None = None
    prompt: str = ""
    selected_option_id: str | None = None
    correct_option_id: str | None = None
    correct_answer: str | None = None
    explanation: str | None = None
    concept: str | None = None
    source_page: int | None = None
    options: list[AgentPageQuestionOption] = Field(default_factory=list)


class AgentPageContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_type: str = "course"
    route: str = ""
    title: str = ""
    visible_text: str = Field(default="", max_length=5000)
    source_ids: list[str] = Field(default_factory=list)
    material_ids: list[str] = Field(default_factory=list)
    section_ids: list[str] = Field(default_factory=list)
    question: AgentPageQuestionContext | None = None


class AgentChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    course_id: str
    message: str = Field(min_length=1, max_length=800)
    scope: StudyScope | None = None
    page_context: AgentPageContext | None = None


class AgentChatResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    course_id: str
    message: str
    response_mode: str = "grounded_fallback"
    actions: list[AgentActionCard] = Field(default_factory=list)
    memory: AgentMemoryProfile
    recommendations: list[AgentRecommendation] = Field(default_factory=list)
    active_agent_profile: AgentProfile
    agent_profiles: list[AgentProfile] = Field(default_factory=list)
