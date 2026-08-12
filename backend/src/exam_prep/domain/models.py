from dataclasses import dataclass, field

from exam_prep.domain.enums import CourseStatus


@dataclass(slots=True)
class Course:
    course_id: str
    title: str
    status: CourseStatus = CourseStatus.DRAFT
    section_ids: list[str] = field(default_factory=list)
