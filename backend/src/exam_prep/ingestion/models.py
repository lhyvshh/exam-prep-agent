from pydantic import BaseModel, ConfigDict


class IngestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    course_id: str
    source_name: str
