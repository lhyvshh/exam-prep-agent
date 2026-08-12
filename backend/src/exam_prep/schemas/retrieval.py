from pydantic import BaseModel, ConfigDict, Field

from exam_prep.schemas.materials import SourceChunk


class IndexedChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk: SourceChunk
    vector: dict[str, float] = Field(default_factory=dict)


class LocalVectorIndex(BaseModel):
    model_config = ConfigDict(extra="forbid")

    course_id: str
    chunk_count: int = 0
    document_frequency: dict[str, int] = Field(default_factory=dict)
    entries: list[IndexedChunk] = Field(default_factory=list)


class RetrievalQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    course_id: str
    module_id: str | None = None
    module_ids: list[str] = Field(default_factory=list)
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)
    selected_source_ids: list[str] = Field(default_factory=list)


class RetrievalHit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: float
    chunk: SourceChunk


class RetrievalQueryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    course_id: str
    module_id: str | None = None
    module_ids: list[str] = Field(default_factory=list)
    query: str
    hits: list[RetrievalHit] = Field(default_factory=list)
