from enum import StrEnum
from pathlib import PurePath
from typing import Self, assert_never

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PackageModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class PackageStatus(StrEnum):
    DRAFT = "draft"
    BUILDING = "building"
    PARTIALLY_COMPLETE = "partially_complete"
    FAILED = "failed"
    COMPLETE = "complete"
    CANCELLED = "cancelled"


class PackageJobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    PARTIALLY_COMPLETE = "partially_complete"
    FAILED = "failed"
    COMPLETE = "complete"
    CANCELLED = "cancelled"


class PackageFileKind(StrEnum):
    FLASHCARDS = "flashcards"
    MOCK_EXAM = "mock_exam"
    FORMULA_REVIEW = "formula_review"
    EXAM_BLUEPRINT = "exam_blueprint"
    VALIDATION_HTML = "validation_html"
    VALIDATION_JSON = "validation_json"
    MANIFEST = "manifest"
    ZIP = "zip"


class PackageKind(StrEnum):
    COMPLETE = "complete"
    STUDY_CARDS = "study_cards"
    MOCK_EXAM = "mock_exam"


class ExamBlueprintMode(StrEnum):
    SOURCE_EXAM = "source_exam"
    FRM_PART_I = "frm_part_i"


class ValidationSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class PackageCreateRequest(PackageModel):
    course_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    package_kind: PackageKind = PackageKind.COMPLETE
    exam_blueprint_mode: ExamBlueprintMode = ExamBlueprintMode.FRM_PART_I
    exam_name: str = Field(default="Financial Risk Manager", min_length=1)
    exam_part: str = Field(default="Part I", min_length=1)
    mock_exam_count: int = Field(default=3, ge=0, le=10)
    questions_per_exam: int = Field(default=100, ge=1, le=500)
    cards_per_concept: int = Field(default=10, ge=1, le=30)
    timer_minutes: int = Field(default=240, ge=0, le=720)
    include_formula_review: bool = True
    include_source_references: bool = True
    material_ids: tuple[str, ...] = ()
    source_exam_id: str | None = Field(default=None, min_length=1)
    generated_exam_ids: tuple[str, ...] = ()

    @field_validator("material_ids")
    @classmethod
    def _require_unique_materials(
        cls,
        material_ids: tuple[str, ...],
    ) -> tuple[str, ...]:
        if len(material_ids) > 32:
            msg = "Offline packages support at most 32 ordered course materials."
            raise ValueError(msg)
        if len(set(material_ids)) != len(material_ids):
            msg = "Offline package material IDs must be unique."
            raise ValueError(msg)
        return material_ids

    @field_validator("generated_exam_ids")
    @classmethod
    def _require_unique_generated_exams(
        cls,
        generated_exam_ids: tuple[str, ...],
    ) -> tuple[str, ...]:
        if len(set(generated_exam_ids)) != len(generated_exam_ids):
            msg = "Generated exam IDs must be unique."
            raise ValueError(msg)
        return generated_exam_ids

    @model_validator(mode="after")
    def _validate_package_kind(self) -> Self:
        match self.package_kind:
            case PackageKind.COMPLETE:
                if self.exam_blueprint_mode == ExamBlueprintMode.FRM_PART_I:
                    if self.material_ids and len(self.material_ids) != 4:
                        msg = "FRM Part I packages require exactly four course materials."
                        raise ValueError(msg)
                    if self.mock_exam_count != 3:
                        msg = "FRM Part I packages require exactly three mock exams."
                        raise ValueError(msg)
                    if self.questions_per_exam != 100:
                        msg = "FRM Part I packages require exactly 100 questions per mock exam."
                        raise ValueError(msg)
                elif self.mock_exam_count < 1:
                    msg = "Source-defined complete packages require at least one mock exam."
                    raise ValueError(msg)
                if self.generated_exam_ids and len(self.generated_exam_ids) != self.mock_exam_count:
                    msg = "Complete packages must bind every configured generated exam."
                    raise ValueError(msg)
            case PackageKind.STUDY_CARDS:
                if not self.material_ids:
                    msg = "Study-card packages require at least one selected book."
                    raise ValueError(msg)
                if self.mock_exam_count != 0:
                    msg = "Study-card packages cannot include mock exams."
                    raise ValueError(msg)
                if self.source_exam_id is not None or self.generated_exam_ids:
                    msg = "Study-card packages cannot include exam inputs."
                    raise ValueError(msg)
            case PackageKind.MOCK_EXAM:
                if not self.material_ids:
                    msg = "Mock-exam packages require at least one grounding book."
                    raise ValueError(msg)
                if (
                    self.exam_blueprint_mode == ExamBlueprintMode.FRM_PART_I
                    and self.questions_per_exam != 100
                ):
                    msg = "FRM Part I mock exams require exactly 100 questions."
                    raise ValueError(msg)
                if self.mock_exam_count != 1:
                    msg = "Mock-exam packages contain exactly one generated exam."
                    raise ValueError(msg)
                if self.source_exam_id is None:
                    msg = "Mock-exam packages require a source exam."
                    raise ValueError(msg)
                if len(self.generated_exam_ids) != 1:
                    msg = "Mock-exam packages must bind the newly generated exam."
                    raise ValueError(msg)
            case unreachable:
                assert_never(unreachable)
        return self


class PackageRecord(PackageModel):
    package_id: str = Field(min_length=1)
    course_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    package_kind: PackageKind = PackageKind.COMPLETE
    exam_name: str = Field(min_length=1)
    exam_part: str = Field(min_length=1)
    status: PackageStatus = PackageStatus.DRAFT
    active_version: int = Field(default=0, ge=0)
    created_at: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)


class PackageVersion(PackageModel):
    package_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    status: PackageStatus
    configuration: PackageCreateRequest
    created_at: str = Field(min_length=1)
    completed_at: str | None = None
    generator_version: str = Field(default="1", min_length=1)
    source_fingerprint: str = Field(min_length=1)
    model_metadata: dict[str, str] = Field(default_factory=dict)
    prompt_versions: dict[str, str] = Field(default_factory=dict)


class PackageGenerationJob(PackageModel):
    job_id: str = Field(min_length=1)
    package_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    status: PackageJobStatus
    current_step: str | None = None
    accepted_flashcards: int = Field(default=0, ge=0)
    expected_flashcards: int = Field(default=0, ge=0)
    accepted_questions: int = Field(default=0, ge=0)
    expected_questions: int = Field(default=0, ge=0)
    artifact_size_bytes: int = Field(default=0, ge=0)
    created_at: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)
    completed_at: str | None = None
    error_message: str | None = None


class PackageGenerationJobStep(PackageModel):
    job_id: str = Field(min_length=1)
    step_name: str = Field(min_length=1)
    status: PackageJobStatus
    input_fingerprint: str = Field(min_length=1)
    accepted_count: int = Field(default=0, ge=0)
    rejected_count: int = Field(default=0, ge=0)
    checkpoint_json: str = "{}"
    attempts: int = Field(default=0, ge=0)
    error_message: str | None = None
    provider_usage_json: str = "{}"
    output_version: int | None = Field(default=None, ge=1)
    updated_at: str = Field(min_length=1)


class PackageFile(PackageModel):
    file_id: str = Field(min_length=1)
    package_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    kind: PackageFileKind
    file_name: str = Field(min_length=1)
    media_type: str = Field(min_length=1)
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    content_count: int = Field(default=0, ge=0)
    artifact_path: str | None = None

    @field_validator("file_name")
    @classmethod
    def _require_basename(cls, file_name: str) -> str:
        if file_name in {".", ".."} or PurePath(file_name).name != file_name:
            msg = "Package file_name must be a basename."
            raise ValueError(msg)
        if "/" in file_name or "\\" in file_name:
            msg = "Package file_name cannot contain path separators."
            raise ValueError(msg)
        return file_name


class ValidationFinding(PackageModel):
    code: str = Field(min_length=1)
    severity: ValidationSeverity
    message: str = Field(min_length=1)
    file_id: str | None = None
    evidence: dict[str, str] = Field(default_factory=dict)


class PackageValidationReport(PackageModel):
    package_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    passed: bool
    created_at: str = Field(min_length=1)
    findings: tuple[ValidationFinding, ...] = ()

    @property
    def is_complete(self) -> bool:
        return self.passed

    @property
    def hard_failures(self) -> tuple[ValidationFinding, ...]:
        return tuple(
            finding for finding in self.findings if finding.severity == ValidationSeverity.ERROR
        )


class PackageContentCounts(PackageModel):
    books: int = Field(ge=0)
    concepts: int = Field(ge=0)
    flashcards: int = Field(ge=0)
    formulas: int = Field(ge=0)
    mock_exams: int = Field(ge=0)
    exam_questions: int = Field(ge=0)


class PackageManifest(PackageModel):
    package_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    title: str = Field(min_length=1)
    created_at: str = Field(min_length=1)
    generator_version: str = Field(min_length=1)
    content_counts: PackageContentCounts
    files: tuple[PackageFile, ...]
    validation: PackageValidationReport
    source_document_versions: dict[str, str] = Field(default_factory=dict)
    model_metadata: dict[str, str] = Field(default_factory=dict)
    prompt_versions: dict[str, str] = Field(default_factory=dict)


class OfflineFlashcard(PackageModel):
    card_id: str = Field(min_length=1)
    book_id: str = Field(min_length=1)
    learning_objective: str = Field(min_length=1)
    learning_objective_title: str = Field(default="", min_length=0)
    concept_id: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    card_type: str = Field(default="short_answer_recall", min_length=1)
    difficulty: str = Field(default="medium", min_length=1)
    source_page: int = Field(ge=1)
    source_reference: str = Field(min_length=1)
    source_excerpt: str | None = None


class OfflineFormula(PackageModel):
    formula_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    expression: str = Field(min_length=1)
    variables: dict[str, str] = Field(default_factory=dict)
    application: str = Field(min_length=1)
    source_page: int = Field(ge=1)
    source_reference: str = Field(min_length=1)


class OfflineExamQuestion(PackageModel):
    question_id: str = Field(min_length=1)
    question_number: int = Field(ge=1, le=500)
    domain: str = Field(min_length=1)
    subtopic: str = Field(min_length=1)
    learning_objective: str = Field(min_length=1)
    question_type: str = Field(min_length=1)
    difficulty: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    choices: tuple[str, ...] = Field(min_length=2, max_length=8)
    correct_choice_index: int = Field(ge=0, le=7)
    explanation: str = Field(min_length=1)
    source_reference: str = Field(min_length=1)
    source_excerpt: str | None = None
    quality_score: float = Field(ge=0.0, le=1.0)
    quality_confidence: float = Field(ge=0.0, le=1.0)
    quality_label: str = Field(min_length=1)
    quality_accepted: bool
    quality_model_version: str = Field(min_length=1)
    quality_model_source: str = Field(min_length=1)

    @model_validator(mode="after")
    def _require_correct_choice_index(self) -> Self:
        if self.correct_choice_index >= len(self.choices):
            msg = "correct_choice_index must identify one of the supplied choices."
            raise ValueError(msg)
        return self


class OfflineMockExam(PackageModel):
    exam_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    timer_minutes: int = Field(default=240, ge=0, le=720)
    questions: tuple[OfflineExamQuestion, ...] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def _require_unique_question_identity(self) -> "OfflineMockExam":
        question_ids = [question.question_id for question in self.questions]
        question_numbers = [question.question_number for question in self.questions]
        if len(set(question_ids)) != len(question_ids):
            msg = "Offline mock exam question IDs must be unique."
            raise ValueError(msg)
        if len(set(question_numbers)) != len(question_numbers):
            msg = "Offline mock exam question numbers must be unique."
            raise ValueError(msg)
        return self


class PackageResponse(PackageModel):
    package: PackageRecord


class PackageListResponse(PackageModel):
    packages: tuple[PackageRecord, ...] = ()


class PackageFileListResponse(PackageModel):
    files: tuple[PackageFile, ...] = ()


class PackageVersionResponse(PackageModel):
    package: PackageRecord
    version: PackageVersion
    files: tuple[PackageFile, ...] = ()
    validation: PackageValidationReport | None = None


class PackageVersionListResponse(PackageModel):
    versions: tuple[PackageVersion, ...] = ()
