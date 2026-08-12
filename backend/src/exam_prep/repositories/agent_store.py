from typing import Protocol

from exam_prep.schemas.agent import AgentMemoryProfile, AgentRecommendation, AgentRunRecord


class AgentStore(Protocol):
    def save_run(self, run: AgentRunRecord) -> None:
        ...

    def get_latest_run(self, course_id: str) -> AgentRunRecord | None:
        ...

    def upsert_recommendations(self, recommendations: list[AgentRecommendation]) -> None:
        ...

    def list_recommendations(
        self,
        course_id: str,
        *,
        include_dismissed: bool = False,
    ) -> list[AgentRecommendation]:
        ...

    def dismiss_recommendation(self, recommendation_id: str) -> bool:
        ...

    def get_memory(self, course_id: str) -> AgentMemoryProfile | None:
        ...

    def save_memory(self, memory: AgentMemoryProfile) -> AgentMemoryProfile:
        ...
