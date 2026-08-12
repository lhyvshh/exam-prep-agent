from pydantic import BaseModel, ConfigDict, Field

from exam_prep.schemas.materials import MaterialRecord


class CourseRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    course_id: str
    course_code: str
    display_name: str
    description: str | None = None


class ModuleRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module_id: str
    course_id: str
    module_number: str
    display_name: str
    description: str | None = None


class CreateCourseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    course_code: str
    display_name: str
    description: str | None = None


class UpdateCourseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    course_code: str
    display_name: str
    description: str | None = None


class CreateModuleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    course_id: str
    module_number: str
    display_name: str
    description: str | None = None


class UpdateModuleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module_number: str
    display_name: str
    description: str | None = None


class ScopeUsageSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    material_count: int = 0
    section_count: int = 0
    quiz_count: int = 0
    attempt_count: int = 0
    wrong_question_count: int = 0


class ModuleLibraryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module: ModuleRecord
    materials: list[MaterialRecord] = Field(default_factory=list)
    usage: ScopeUsageSummary = Field(default_factory=ScopeUsageSummary)


class CourseLibraryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    course: CourseRecord
    root_materials: list[MaterialRecord] = Field(default_factory=list)
    modules: list[ModuleLibraryItem] = Field(default_factory=list)
    usage: ScopeUsageSummary = Field(default_factory=ScopeUsageSummary)


class CourseListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    courses: list[CourseRecord] = Field(default_factory=list)


class ModuleListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    course_id: str
    modules: list[ModuleRecord] = Field(default_factory=list)


class MaterialLibraryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    courses: list[CourseLibraryItem] = Field(default_factory=list)


class DeleteScopeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deleted: bool
    deleted_id: str
    deleted_kind: str
    fallback_course_id: str | None = None
    fallback_module_id: str | None = None
