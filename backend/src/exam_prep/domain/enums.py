from enum import StrEnum


class CourseStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"


class MaterialType(StrEnum):
    DOCUMENT = "document"
    NOTE = "note"
    EXAMPLE = "example"
