from pydantic import BaseModel, ConfigDict, Field

from exam_prep.schemas.graph import ExamPrepGraphState


class WorkflowCourseSelectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    course_id: str | None = None
    module_id: str | None = None


class CurrentWorkflowResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_id: str
    course_id: str | None = None
    module_id: str | None = None
    graph_state: ExamPrepGraphState
    material_count: int = 0
    has_active_course: bool = False
    available_course_ids: list[str] = Field(default_factory=list)
