from typing import Protocol

from exam_prep.schemas.analytics import (
    AgentAnalyticsContextResponse,
    AnalyticsOverviewResponse,
    ConceptMasteryRecord,
    ModuleMasteryRecord,
    QuestionTypeMasteryRecord,
    RecommendationHistoryRecord,
)


class AnalyticsStore(Protocol):
    def refresh_course(self, *, user_id: str, course_id: str) -> AnalyticsOverviewResponse:
        """Recompute materialized mastery rows and recommendations for a course."""

    def get_overview(self, *, user_id: str, course_id: str) -> AnalyticsOverviewResponse:
        """Return current analytics overview, refreshing it from telemetry first."""

    def list_modules(self, *, user_id: str, course_id: str) -> list[ModuleMasteryRecord]:
        """Return modules ranked by weakness priority."""

    def list_concepts(self, *, user_id: str, course_id: str) -> list[ConceptMasteryRecord]:
        """Return concepts ranked by weakness priority."""

    def list_question_types(self, *, user_id: str, course_id: str) -> list[QuestionTypeMasteryRecord]:
        """Return question type mastery ranked by weakness priority."""

    def list_recommendations(self, *, user_id: str, course_id: str) -> list[RecommendationHistoryRecord]:
        """Return persisted recommendations ranked by priority."""

    def get_agent_context(self, *, user_id: str, course_id: str) -> AgentAnalyticsContextResponse:
        """Return the compact analytics context that agents can reason over."""
