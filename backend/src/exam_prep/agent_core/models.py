from pydantic import BaseModel, ConfigDict, Field, model_validator


class AgentRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_name: str = "course_workspace"
    intent: str = "workflow_snapshot"
    course_id: str | None = None
    module_id: str | None = None
    module_ids: list[str] = Field(default_factory=list)
    material_ids: list[str] = Field(default_factory=list)
    section_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _normalize_scope(self) -> "AgentRunRequest":
        normalized = [module_id for module_id in self.module_ids if module_id]
        if not normalized and self.module_id:
            normalized = [self.module_id]
        self.module_ids = list(dict.fromkeys(normalized))
        self.module_id = self.module_ids[0] if len(self.module_ids) == 1 else None
        self.material_ids = list(dict.fromkeys(item for item in self.material_ids if item))
        self.section_ids = list(dict.fromkeys(item for item in self.section_ids if item))
        return self
