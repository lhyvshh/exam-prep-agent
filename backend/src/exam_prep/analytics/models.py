from pydantic import BaseModel, ConfigDict, Field


class MasterySnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    course_id: str
    module_id: str | None = None
    percent_mastery: float = 0.0
    mastery_by_concept: dict[str, float] = Field(default_factory=dict)
    attempt_count_by_concept: dict[str, int] = Field(default_factory=dict)
    wrong_concepts: list[str] = Field(default_factory=list)
