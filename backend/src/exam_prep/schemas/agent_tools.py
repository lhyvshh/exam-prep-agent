from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


AgentActionType = Literal[
    "review_material",
    "generate_quiz",
    "missed_questions",
    "study_section",
    "open_materials",
]

AgentButtonActionType = Literal[
    "review_material",
    "practice_concept",
    "generate_quiz",
    "retake_missed_questions",
    "view_source_pdf_page",
    "study_similar_questions",
    "study_section",
    "open_materials",
]


class AgentWeakAreaSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    id: str
    name: str
    accuracy: float | None = None
    attempts: int = 0
    recent_trend: str = Field(default="Not enough data", alias="recentTrend")
    priority_score: float = Field(default=0.0, alias="priorityScore")


class AgentRecommendationButton(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    label: str
    action_type: AgentButtonActionType = Field(alias="actionType")
    target_url: str = Field(alias="targetUrl")
    target_material_id: str | None = Field(default=None, alias="targetMaterialId")
    target_section_id: str | None = Field(default=None, alias="targetSectionId")
    target_concept_id: str | None = Field(default=None, alias="targetConceptId")
    target_module_id: str | None = Field(default=None, alias="targetModuleId")
    source_page: int | None = Field(default=None, alias="sourcePage")
    question_type: str | None = Field(default=None, alias="questionType")


class AgentToolRecommendationCard(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    title: str
    reason: str
    action_type: AgentActionType = Field(alias="actionType")
    button_text: str = Field(alias="buttonText")
    target_url: str = Field(alias="targetUrl")
    target_material_id: str | None = Field(default=None, alias="targetMaterialId")
    target_section_id: str | None = Field(default=None, alias="targetSectionId")
    target_concept_id: str | None = Field(default=None, alias="targetConceptId")
    target_module_id: str | None = Field(default=None, alias="targetModuleId")
    source_page: int | None = Field(default=None, alias="sourcePage")
    question_type: str | None = Field(default=None, alias="questionType")
    priority_score: float = Field(default=0.0, alias="priorityScore")
    weak_area_name: str = Field(default="", alias="weakAreaName")
    accuracy: float | None = None
    attempts: int = 0
    recent_trend: str = Field(default="Not enough data", alias="recentTrend")
    why_it_matters: str = Field(default="", alias="whyItMatters")
    recommended_action: str = Field(default="", alias="recommendedAction")
    buttons: list[AgentRecommendationButton] = Field(default_factory=list)


class SmartAgentStudyPlanResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    summary: str
    readiness_score: int = Field(alias="readinessScore", ge=0, le=100)
    recommendations: list[AgentToolRecommendationCard] = Field(default_factory=list)
    top_weak_modules: list[AgentWeakAreaSummary] = Field(default_factory=list, alias="topWeakModules")
    top_weak_concepts: list[AgentWeakAreaSummary] = Field(default_factory=list, alias="topWeakConcepts")
    weakest_question_types: list[AgentWeakAreaSummary] = Field(default_factory=list, alias="weakestQuestionTypes")
    recommended_next_action: str = Field(default="", alias="recommendedNextAction")
