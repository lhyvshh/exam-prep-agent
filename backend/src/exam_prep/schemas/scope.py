from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SourceType(StrEnum):
    STUDY_MATERIAL = "study_material"
    LECTURE = "lecture"
    NOTES = "notes"
    PAST_EXAM = "past_exam"
    PRACTICE_EXAM = "practice_exam"


class StudyScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    course_id: str
    module_ids: list[str] = Field(default_factory=list)
    material_ids: list[str] = Field(default_factory=list)
    section_ids: list[str] = Field(default_factory=list)
    source_type: SourceType = SourceType.STUDY_MATERIAL

    @model_validator(mode="after")
    def _normalize_ids(self) -> "StudyScope":
        self.module_ids = list(dict.fromkeys(item.strip() for item in self.module_ids if item.strip()))
        self.material_ids = list(dict.fromkeys(item.strip() for item in self.material_ids if item.strip()))
        self.section_ids = list(dict.fromkeys(item.strip() for item in self.section_ids if item.strip()))
        return self
