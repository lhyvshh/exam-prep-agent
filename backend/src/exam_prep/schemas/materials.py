from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MaterialParseStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class MaterialProcessingStage(StrEnum):
    REGISTERED = "registered"
    EXTRACTING = "extracting"
    OUTLINING = "outlining"
    NORMALIZING = "normalizing"
    ENRICHING = "enriching"
    READY = "ready"
    FAILED = "failed"


class MaterialStageStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class StudyDifficulty(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class StudiedStatus(StrEnum):
    NOT_STARTED = "not_started"
    STUDIED = "studied"


class ContentOrigin(StrEnum):
    ORIGINAL_BOOK = "original_book"
    AI_GENERATED = "ai_generated"
    AI_GENERATED_FROM_ORIGINAL = "ai_generated_from_original"


class SectionKind(StrEnum):
    SESSION = "session"
    INSTRUCTIONAL = "instructional"
    LOGISTICS = "logistics"
    REFERENCE = "reference"


class ContentLabel(StrEnum):
    TESTABLE_CONTENT = "testable_content"
    ADMINISTRATIVE_CONTENT = "administrative_content"
    WEAK_CONTENT = "weak_content"


class SourceLocator(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_index: int
    page_number: int | None = None
    slide_number: int | None = None
    paragraph_index: int | None = None
    char_start: int | None = None
    char_end: int | None = None


class FormulaAsset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_page: int
    path: str
    label: str
    source_type: str = "pdf_crop"
    confidence: float = 0.5
    reading_number: int | None = None
    extracted_text: str | None = None
    extracted_latex: str | None = None
    extracted_latex_blocks: list[str] = Field(default_factory=list)
    ocr_engine: str | None = None
    ocr_confidence: float | None = None
    needs_review: bool = False


class SourceSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    material_id: str
    course_id: str
    module_id: str | None = None
    file_name: str
    content_type: str
    section_title: str
    text: str
    page_end: int | None = None
    section_kind: SectionKind = SectionKind.INSTRUCTIONAL
    content_label: ContentLabel = ContentLabel.TESTABLE_CONTENT
    priority_score: float = 1.0
    is_default: bool = True
    formula_assets: list[FormulaAsset] = Field(default_factory=list)
    locator: SourceLocator
    citation_label: str


class SourceChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    source_id: str
    material_id: str
    course_id: str
    module_id: str | None = None
    file_name: str
    content_type: str
    section_title: str
    text: str
    page_end: int | None = None
    token_count: int = 0
    section_kind: SectionKind = SectionKind.INSTRUCTIONAL
    content_label: ContentLabel = ContentLabel.TESTABLE_CONTENT
    priority_score: float = 1.0
    is_default: bool = True
    workbook_block_type: str | None = None
    workbook_module_number: str | None = None
    learning_outcome_ids: list[str] = Field(default_factory=list)
    module_quiz_question_numbers: list[int] = Field(default_factory=list)
    module_quiz_answer_numbers: list[int] = Field(default_factory=list)
    module_quiz_style_profiles: list[str] = Field(default_factory=list)
    locator: SourceLocator
    citation_label: str


class MaterialUploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    course_id: str
    file_name: str
    content_type: str


class MaterialRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    material_id: str
    course_id: str
    module_id: str | None = None
    file_name: str
    display_name: str | None = None
    file_path: str | None = None
    uploaded_at: str | None = None
    content_type: str
    status: MaterialParseStatus = MaterialParseStatus.PENDING
    page_count: int | None = None
    processing_status: MaterialProcessingStage = MaterialProcessingStage.REGISTERED
    processing_progress: int = Field(default=0, ge=0, le=100)
    outline_status: MaterialStageStatus = MaterialStageStatus.PENDING
    enrichment_status: MaterialStageStatus = MaterialStageStatus.PENDING
    last_processed_at: str | None = None
    content_hash: str | None = None
    raw_text_path: str | None = None
    chunk_count: int = Field(default=0)
    section_count: int = Field(default=0)
    error_message: str | None = None
    parse_debug_report: dict[str, object] | None = None

    @model_validator(mode="after")
    def populate_defaults(self) -> "MaterialRecord":
        if self.display_name is None:
            self.display_name = self.file_name
        return self


class ParsedMaterialDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record: MaterialRecord
    sections: list[SourceSection] = Field(default_factory=list)
    chunks: list[SourceChunk] = Field(default_factory=list)


class MaterialStudyGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group_id: str
    material_id: str
    title: str
    page_start: int | None = None
    page_end: int | None = None
    display_order: int = 0
    section_count: int = 0
    ready_count: int = 0
    studied_count: int = 0


class OriginalBookItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    title: str
    content: str
    source_pages: list[int] = Field(default_factory=list)
    original_order: int = 0
    content_origin: ContentOrigin = ContentOrigin.ORIGINAL_BOOK
    source_block_ids: list[str] = Field(default_factory=list)


class OriginalBookContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key_concepts: list[OriginalBookItem] = Field(default_factory=list)
    module_quiz: list[OriginalBookItem] = Field(default_factory=list)
    answers: list[OriginalBookItem] = Field(default_factory=list)


class StudyFormulaCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    formula_id: str
    course_id: str | None = None
    material_id: str
    module_id: str | None = None
    concept_id: str | None = None
    reading_number: int | None = None
    formula_name: str | None = None
    formula_text: str
    formula_latex: str | None = None
    variables_json: dict[str, str] = Field(default_factory=dict)
    source_page: int | None = None
    formula_section_page: int | None = None
    source_excerpt: str = ""
    source_image_crop_path: str | None = None
    parse_confidence: str = "high"
    needs_review: bool = False
    usage_note: str = ""
    example_if_available: str | None = None
    content_origin: ContentOrigin = ContentOrigin.ORIGINAL_BOOK


class StudyFlashcard(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    flashcard_id: str
    book_id: str | None = Field(default=None, alias="bookId")
    course_id: str | None = None
    material_id: str
    module_id: str | None = None
    learning_outcome_id: str | None = None
    concept_id: str | None = None
    formula_id: str | None = None
    study_session: str | None = Field(default=None, alias="studySession")
    reading_number: int | None = Field(default=None, alias="readingNumber")
    module_number: str | None = Field(default=None, alias="moduleNumber")
    lo_code: str | None = Field(default=None, alias="loCode")
    page_start: int | None = Field(default=None, alias="pageStart")
    page_end: int | None = Field(default=None, alias="pageEnd")
    anchor_type: str | None = Field(default=None, alias="anchorType")
    anchor_text: str | None = Field(default=None, alias="anchorText")
    source_text_snippet: str = Field(default="", alias="sourceTextSnippet")
    front: str
    back: str
    back_concise: str | None = None
    card_type: str
    explanation: str = ""
    formula_latex: str | None = Field(default=None, alias="formulaLatex")
    tags: list[str] = Field(default_factory=list)
    quality_score: float = Field(default=0.0, alias="qualityScore")
    source_hash: str = Field(default="", alias="sourceHash")
    source_page: int | None = None
    source_excerpt: str = ""
    difficulty: StudyDifficulty = StudyDifficulty.MEDIUM
    confidence_group: str = "new"
    interval_days: int = 0
    ease_factor: float = 2.5
    repetitions: int = 0
    due_at: str | None = None
    last_reviewed_at: str | None = None
    archived: bool = False
    content_origin: ContentOrigin = ContentOrigin.AI_GENERATED_FROM_ORIGINAL
    needs_more_source: bool = False


class StudyConceptCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    concept_id: str
    material_id: str
    module_id: str | None = None
    title: str
    learning_outcome: str | None = None
    related_original_key_concept_id: str | None = None
    source_pages: list[int] = Field(default_factory=list)
    source_excerpt: str = ""
    simplified_explanation: str = ""
    key_terms: list[str] = Field(default_factory=list)
    formulas: list[StudyFormulaCard] = Field(default_factory=list)
    exam_focus: str = ""
    common_traps: list[str] = Field(default_factory=list)
    difficulty_level: StudyDifficulty = StudyDifficulty.MEDIUM
    mastery_score: float = 0.0
    content_origin: ContentOrigin = ContentOrigin.AI_GENERATED_FROM_ORIGINAL


class StudyLearningOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome_id: str
    outcome_title: str
    content_origin: ContentOrigin = ContentOrigin.ORIGINAL_BOOK
    related_original_key_concept_ids: list[str] = Field(default_factory=list)
    concepts: list[StudyConceptCard] = Field(default_factory=list)
    completion_status: str = "not_started"
    confidence_score: float = 0.0


class MaterialStudySection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_id: str
    material_id: str
    parent_group_id: str | None = None
    title: str
    normalized_title: str
    page_start: int | None = None
    page_end: int | None = None
    source_anchor: str
    summary: str
    key_points: list[str] = Field(default_factory=list)
    memorize_keywords: list[str] = Field(default_factory=list)
    memorize_functions_or_formulas: list[str] = Field(default_factory=list)
    traps: list[str] = Field(default_factory=list)
    workbook_key_concepts: list[str] = Field(default_factory=list)
    workbook_module_quiz: list[str] = Field(default_factory=list)
    workbook_answer_key: list[str] = Field(default_factory=list)
    original_book_content: OriginalBookContent = Field(default_factory=OriginalBookContent)
    learning_outcomes: list[StudyLearningOutcome] = Field(default_factory=list)
    concepts: list[StudyConceptCard] = Field(default_factory=list)
    formulas: list[StudyFormulaCard] = Field(default_factory=list)
    flashcards: list[StudyFlashcard] = Field(default_factory=list)
    due_flashcard_count: int = 0
    mastery_percent: float = 0.0
    weakest_concepts: list[str] = Field(default_factory=list)
    difficulty: StudyDifficulty = StudyDifficulty.MEDIUM
    studied_status: StudiedStatus = StudiedStatus.NOT_STARTED
    quiz_ready: bool = True
    display_order: int = 0
    enrichment_status: MaterialStageStatus = MaterialStageStatus.COMPLETED
    source_ids: list[str] = Field(default_factory=list)


class MaterialStudyDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    material_id: str
    content_hash: str | None = None
    pipeline_version: int = 1
    generated_at: str | None = None
    groups: list[MaterialStudyGroup] = Field(default_factory=list)
    sections: list[MaterialStudySection] = Field(default_factory=list)


class MaterialStudyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record: MaterialRecord
    groups: list[MaterialStudyGroup] = Field(default_factory=list)
    sections: list[MaterialStudySection] = Field(default_factory=list)
    total_sections: int = 0
    ready_sections: int = 0
    studied_sections: int = 0
    offset: int = 0
    limit: int = 20
    has_more: bool = False


class MaterialStudySectionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section: MaterialStudySection


class MaterialStudySectionUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    studied_status: StudiedStatus


class MaterialUploadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record: MaterialRecord


class MaterialStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record: MaterialRecord


class MaterialPreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record: MaterialRecord
    sections: list[SourceSection] = Field(default_factory=list)
    chunks: list[SourceChunk] = Field(default_factory=list)


class MaterialListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    records: list[MaterialRecord] = Field(default_factory=list)


class MaterialDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record: MaterialRecord


class StructuredConcept(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    course_id: str
    module_id: str | None = None
    material_id: str
    section_id: str
    name: str
    normalized_name: str
    description: str = ""
    keywords: list[str] = Field(default_factory=list)
    source_page: int | None = None
    created_at: str | None = None


class StructuredMaterialSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    material_id: str
    course_id: str
    module_id: str | None = None
    title: str
    clean_title: str
    summary: str
    source_text: str
    start_page: int | None = None
    end_page: int | None = None
    section_order: int = 0
    key_terms: list[str] = Field(default_factory=list)
    key_concepts: list[str] = Field(default_factory=list)
    formulas: list[str] = Field(default_factory=list)
    exam_weight: float = 0.5
    is_junk: bool = False
    source_text_hash: str | None = None
    enhancement_cache_key: str | None = None
    enhancement_prompt_version: str | None = None
    enhancement_input_excerpt: str | None = None
    enhancement_input_token_limit: int | None = None
    created_at: str | None = None
    updated_at: str | None = None
    concepts: list[StructuredConcept] = Field(default_factory=list)


class StructuredMaterialChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    material_id: str
    section_id: str
    course_id: str
    module_id: str | None = None
    page_number: int | None = None
    chunk_order: int = 0
    text: str
    embedding_id: str | None = None
    token_count: int = 0
    created_at: str | None = None


class MaterialSectionsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record: MaterialRecord
    sections: list[StructuredMaterialSection] = Field(default_factory=list)


class SectionDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section: StructuredMaterialSection


class SectionChunksResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_id: str
    chunks: list[StructuredMaterialChunk] = Field(default_factory=list)


class ConceptSourceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    concept: StructuredConcept
    source: dict[str, object]


class MaterialSectionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    material_id: str
    course_id: str
    module_id: str | None = None
    file_name: str
    content_type: str
    section_title: str
    section_kind: SectionKind = SectionKind.INSTRUCTIONAL
    content_label: ContentLabel = ContentLabel.TESTABLE_CONTENT
    priority_score: float = 1.0
    is_default: bool = True
    citation_label: str
    locator: SourceLocator


class QuizSourceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quiz_source_id: str
    material_id: str
    course_id: str
    module_id: str | None = None
    file_name: str
    title: str
    summary: str
    source_ids: list[str] = Field(default_factory=list)
    section_count: int = 1
    section_kind: SectionKind = SectionKind.INSTRUCTIONAL
    content_label: ContentLabel = ContentLabel.TESTABLE_CONTENT
    priority_score: float = 1.0
    is_default: bool = True
    citation_label: str
    location_label: str
    locator: SourceLocator


class CourseMaterialsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    course_id: str
    records: list[MaterialRecord] = Field(default_factory=list)
    sections: list[MaterialSectionSummary] = Field(default_factory=list)
    quiz_sources: list[QuizSourceSummary] = Field(default_factory=list)
    default_source_ids: list[str] = Field(default_factory=list)
    default_quiz_source_ids: list[str] = Field(default_factory=list)


class MaterialDeleteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    material_id: str
    course_id: str
    removed: bool
    remaining_material_count: int = 0
    current_course_id: str | None = None
