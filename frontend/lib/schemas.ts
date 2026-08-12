export type AppSection = {
  slug: string;
  label: string;
  description: string;
};

export const appSections: AppSection[] = [
  {
    slug: "courses",
    label: "Courses",
    description: "Open course workspaces for book libraries, mock exams, and reviews."
  },
  {
    slug: "config",
    label: "Model Hub",
    description: "Choose provider settings, task routing, model selection, and demo mode."
  },
  {
    slug: "notifications",
    label: "Reminders",
    description: "Manage opt-in Study Coach reminders and email drafts."
  }
];

export type HealthResponse = {
  status: string;
  service: string;
};

export type LLMProvider =
  | "nvidia"
  | "openai"
  | "anthropic"
  | "google"
  | "groq"
  | "openrouter"
  | "ollama"
  | "azure_openai"
  | "other";

export type UserLLMConfig = {
  provider: LLMProvider;
  model: string;
  api_key: string | null;
  demo_mode: boolean;
};

export type RuntimeConfigResponse = {
  config: UserLLMConfig;
  butler_config?: UserLLMConfig;
  parser_config?: UserLLMConfig;
  source: string;
};

export type ConfigValidationRequest = UserLLMConfig;

export type ConfigValidationStatus = "valid" | "invalid" | "demo_ready";

export type ConfigValidationResponse = {
  is_valid: boolean;
  status: ConfigValidationStatus;
  message: string;
  config: UserLLMConfig;
  can_proceed: boolean;
};

export type ConfigHealthResponse = {
  ok: boolean;
  status: string;
  config_present: boolean;
};

export type SourceType = "study_material" | "lecture" | "notes" | "past_exam" | "practice_exam";

export type StudyScope = {
  course_id: string;
  module_ids: string[];
  material_ids: string[];
  section_ids: string[];
  source_type: SourceType;
};

export type AgentPageQuestionOption = {
  option_id: string;
  text: string;
};

export type AgentPageQuestionContext = {
  question_number?: number | null;
  question_id?: string | null;
  prompt: string;
  selected_option_id?: string | null;
  correct_option_id?: string | null;
  correct_answer?: string | null;
  explanation?: string | null;
  concept?: string | null;
  source_page?: number | null;
  options: AgentPageQuestionOption[];
};

export type AgentPageContext = {
  page_type: string;
  route: string;
  title: string;
  visible_text: string;
  source_ids: string[];
  material_ids: string[];
  section_ids: string[];
  question: AgentPageQuestionContext | null;
};

export type MaterialParseStatus = "pending" | "processing" | "completed" | "failed";
export type MaterialProcessingStage =
  | "registered"
  | "extracting"
  | "outlining"
  | "normalizing"
  | "enriching"
  | "ready"
  | "failed";
export type MaterialStageStatus = "pending" | "processing" | "completed" | "failed";
export type SectionKind = "session" | "instructional" | "logistics" | "reference";
export type ContentLabel = "testable_content" | "administrative_content" | "weak_content";
export type StudyDifficulty = "easy" | "medium" | "hard";
export type StudiedStatus = "not_started" | "studied";
export type ContentOrigin = "original_book" | "ai_generated" | "ai_generated_from_original";

export type CourseRecord = {
  course_id: string;
  course_code: string;
  display_name: string;
  description: string | null;
};

export type ModuleRecord = {
  module_id: string;
  course_id: string;
  module_number: string;
  display_name: string;
  description: string | null;
};

export type CreateCourseRequest = {
  course_code: string;
  display_name: string;
  description?: string | null;
};

export type UpdateCourseRequest = {
  course_code: string;
  display_name: string;
  description?: string | null;
};

export type CreateModuleRequest = {
  course_id: string;
  module_number: string;
  display_name: string;
  description?: string | null;
};

export type UpdateModuleRequest = {
  module_number: string;
  display_name: string;
  description?: string | null;
};

export type ScopeUsageSummary = {
  material_count: number;
  section_count: number;
  quiz_count: number;
  attempt_count: number;
  wrong_question_count: number;
};

export type SourceLocator = {
  section_index: number;
  page_number: number | null;
  slide_number: number | null;
  paragraph_index: number | null;
  char_start: number | null;
  char_end: number | null;
};

export type SourceSection = {
  source_id: string;
  material_id: string;
  course_id: string;
  module_id?: string | null;
  file_name: string;
  content_type: string;
  section_title: string;
  text: string;
  section_kind: SectionKind;
  content_label: ContentLabel;
  priority_score: number;
  is_default: boolean;
  locator: SourceLocator;
  citation_label: string;
};

export type SourceChunk = {
  chunk_id: string;
  source_id: string;
  material_id: string;
  course_id: string;
  module_id?: string | null;
  file_name: string;
  content_type: string;
  section_title: string;
  text: string;
  section_kind: SectionKind;
  content_label: ContentLabel;
  priority_score: number;
  is_default: boolean;
  locator: SourceLocator;
  citation_label: string;
};

export type MaterialRecord = {
  material_id: string;
  course_id: string;
  module_id?: string | null;
  file_name: string;
  display_name?: string | null;
  file_path?: string | null;
  uploaded_at?: string | null;
  content_type: string;
  status: MaterialParseStatus;
  page_count?: number | null;
  processing_status?: MaterialProcessingStage;
  processing_progress?: number;
  outline_status?: MaterialStageStatus;
  enrichment_status?: MaterialStageStatus;
  last_processed_at?: string | null;
  content_hash?: string | null;
  chunk_count: number;
  section_count: number;
  error_message: string | null;
  parse_debug_report?: Record<string, unknown> | null;
};

export type MaterialUploadResponse = {
  record: MaterialRecord;
};

export type MaterialStatusResponse = {
  record: MaterialRecord;
};

export type MaterialPreviewResponse = {
  record: MaterialRecord;
  sections: SourceSection[];
  chunks: SourceChunk[];
};

export type MaterialSectionSummary = {
  source_id: string;
  material_id: string;
  course_id: string;
  module_id?: string | null;
  file_name: string;
  content_type: string;
  section_title: string;
  section_kind: SectionKind;
  content_label: ContentLabel;
  priority_score: number;
  is_default: boolean;
  citation_label: string;
  locator: SourceLocator;
};

export type QuizSourceSummary = {
  quiz_source_id: string;
  material_id: string;
  course_id: string;
  module_id?: string | null;
  file_name: string;
  title: string;
  summary: string;
  source_ids: string[];
  section_count: number;
  section_kind: SectionKind;
  content_label: ContentLabel;
  priority_score: number;
  is_default: boolean;
  citation_label: string;
  location_label: string;
  locator: SourceLocator;
};

export type CourseMaterialsResponse = {
  course_id: string;
  records: MaterialRecord[];
  sections: MaterialSectionSummary[];
  quiz_sources: QuizSourceSummary[];
  default_source_ids: string[];
  default_quiz_source_ids: string[];
};

export type ModuleLibraryItem = {
  module: ModuleRecord;
  materials: MaterialRecord[];
  usage: ScopeUsageSummary;
};

export type CourseLibraryItem = {
  course: CourseRecord;
  root_materials: MaterialRecord[];
  modules: ModuleLibraryItem[];
  usage: ScopeUsageSummary;
};

export type MaterialLibraryResponse = {
  courses: CourseLibraryItem[];
};

export type DeleteScopeResponse = {
  deleted: boolean;
  deleted_id: string;
  deleted_kind: string;
  fallback_course_id: string | null;
  fallback_module_id: string | null;
};

export type CourseListResponse = {
  courses: CourseRecord[];
};

export type ModuleListResponse = {
  course_id: string;
  modules: ModuleRecord[];
};

export type MaterialDeleteResponse = {
  material_id: string;
  course_id: string;
  removed: boolean;
  remaining_material_count: number;
  current_course_id: string | null;
};

export type MaterialStudyGroup = {
  group_id: string;
  material_id: string;
  title: string;
  page_start?: number | null;
  page_end?: number | null;
  display_order: number;
  section_count: number;
  ready_count: number;
  studied_count: number;
};

export type MaterialStudySection = {
  section_id: string;
  material_id: string;
  parent_group_id?: string | null;
  title: string;
  normalized_title: string;
  page_start?: number | null;
  page_end?: number | null;
  source_anchor: string;
  summary: string;
  key_points: string[];
  memorize_keywords: string[];
  memorize_functions_or_formulas: string[];
  traps: string[];
  workbook_key_concepts?: string[];
  workbook_module_quiz?: string[];
  workbook_answer_key?: string[];
  original_book_content?: OriginalBookContent;
  learning_outcomes?: StudyLearningOutcome[];
  concepts?: StudyConceptCard[];
  formulas?: StudyFormulaCard[];
  flashcards?: StudyFlashcard[];
  due_flashcard_count?: number;
  mastery_percent?: number;
  weakest_concepts?: string[];
  difficulty: StudyDifficulty;
  studied_status: StudiedStatus;
  quiz_ready: boolean;
  display_order: number;
  enrichment_status: MaterialStageStatus;
  source_ids: string[];
};

export type OriginalBookItem = {
  item_id: string;
  title: string;
  content: string;
  source_pages: number[];
  original_order: number;
  content_origin: ContentOrigin;
  source_block_ids: string[];
};

export type OriginalBookContent = {
  key_concepts: OriginalBookItem[];
  module_quiz: OriginalBookItem[];
  answers: OriginalBookItem[];
};

export type StudyFormulaCard = {
  formula_id: string;
  course_id?: string | null;
  material_id: string;
  module_id?: string | null;
  concept_id?: string | null;
  reading_number?: number | null;
  formula_name?: string | null;
  formula_text: string;
  formula_latex?: string | null;
  variables_json: Record<string, string>;
  source_page?: number | null;
  formula_section_page?: number | null;
  source_excerpt: string;
  source_image_crop_path?: string | null;
  parse_confidence?: string | null;
  needs_review?: boolean;
  usage_note: string;
  example_if_available?: string | null;
  content_origin: ContentOrigin;
};

export type StudyConceptCard = {
  concept_id: string;
  material_id: string;
  module_id?: string | null;
  title: string;
  learning_outcome?: string | null;
  related_original_key_concept_id?: string | null;
  source_pages: number[];
  source_excerpt: string;
  simplified_explanation: string;
  key_terms: string[];
  formulas: StudyFormulaCard[];
  exam_focus: string;
  common_traps: string[];
  difficulty_level: StudyDifficulty;
  mastery_score: number;
  content_origin: ContentOrigin;
};

export type StudyLearningOutcome = {
  outcome_id: string;
  outcome_title: string;
  content_origin: ContentOrigin;
  related_original_key_concept_ids: string[];
  concepts: StudyConceptCard[];
  completion_status: string;
  confidence_score: number;
};

export type StudyFlashcard = {
  flashcard_id: string;
  course_id?: string | null;
  material_id: string;
  module_id?: string | null;
  learning_outcome_id?: string | null;
  concept_id?: string | null;
  formula_id?: string | null;
  front: string;
  back: string;
  back_concise?: string | null;
  card_type: string;
  source_page?: number | null;
  source_excerpt: string;
  difficulty: StudyDifficulty;
  confidence_group: string;
  interval_days: number;
  ease_factor: number;
  repetitions: number;
  due_at?: string | null;
  last_reviewed_at?: string | null;
  archived: boolean;
  content_origin: ContentOrigin;
  needs_more_source?: boolean;
};

export type FlashcardReviewRating = "forgot" | "hard" | "good" | "easy";

export type FlashcardReviewPayload = {
  user_id?: string;
  course_id: string;
  module_id?: string | null;
  material_id?: string | null;
  section_id?: string | null;
  concept_id?: string | null;
  flashcard_id: string;
  rating: FlashcardReviewRating;
  previous_interval_days: number;
  new_interval_days: number;
  previous_confidence_group: string;
  new_confidence_group: string;
  metadata_json?: Record<string, unknown>;
};

export type FlashcardReviewRecord = FlashcardReviewPayload & {
  id: string;
  reviewed_at: string;
};

export type FlashcardReviewsResponse = {
  flashcard_reviews: FlashcardReviewRecord[];
};

export type MaterialStudyResponse = {
  record: MaterialRecord;
  groups: MaterialStudyGroup[];
  sections: MaterialStudySection[];
  total_sections: number;
  ready_sections: number;
  studied_sections: number;
  offset: number;
  limit: number;
  has_more: boolean;
};

export type MaterialStudySectionResponse = {
  section: MaterialStudySection;
};

export type MaterialPageImageItem = {
  image_id: string;
  name: string;
  media_type: string;
  byte_count: number;
  src: string;
};

export type MaterialPageImagesResponse = {
  material_id: string;
  page_number: number;
  images: MaterialPageImageItem[];
};

export type SourceTarget = {
  material_id: string;
  section_id?: string | null;
  source_id?: string | null;
  page_start?: number | null;
  page_end?: number | null;
  anchor_text?: string | null;
  asset_id?: string | null;
  return_origin?: Record<string, unknown>;
};

export type SourceResolveResponse = {
  target: SourceTarget;
  material: MaterialRecord;
  section?: MaterialStudySection | null;
  page_start?: number | null;
  page_end?: number | null;
  file_url: string;
  page_image_url?: string | null;
  embedded_images_url?: string | null;
  fallback_notice?: string | null;
};

export type CurrentWorkflowResponse = {
  workflow_id: string;
  course_id: string | null;
  module_id: string | null;
  graph_state: {
    course_id: string | null;
    module_id: string | null;
    material_ids: string[];
    grounding_context: Array<{
      material_id: string;
      excerpt: string;
      score: number;
    }>;
    active_quiz: QuizBundle | null;
    mastery_by_concept: Record<string, number>;
    wrong_concepts: string[];
    execution_trace: Array<{
      node_name: string;
      status: string;
      details?: string | null;
    }>;
  };
  material_count: number;
  has_active_course: boolean;
  available_course_ids: string[];
};

export type QuestionQualityLabel = "low_quality" | "needs_review" | "high_quality";

export type QuestionQualityValidation = {
  score: number;
  confidence: number;
  label: QuestionQualityLabel;
  accepted_for_delivery: boolean;
  model_version: string;
  model_source: string;
  notes: string[];
};

export type QuestionType = "mcq" | "short_answer";

export type QuizQuestionOption = {
  option_id: string;
  text: string;
};

export type QuizQuestion = {
  question_id: string;
  question_type: QuestionType;
  concept: string;
  section_title: string;
  source_page?: number | null;
  difficulty: number;
  prompt: string;
  options: QuizQuestionOption[];
  citations: SourceChunk[];
  rationale: string | null;
  quality_validation: QuestionQualityValidation | null;
};

export type QuizBundle = {
  quiz_id: string;
  course_id: string;
  module_id?: string | null;
  query: string;
  created_at?: string | null;
  record_type?: "quiz" | "concept_practice";
  questions: QuizQuestion[];
};

export type QuizAttemptSummary = {
  quiz_id: string;
  created_at?: string | null;
  question_count: number;
  overall_score: number | null;
  wrong_question_count: number;
  module_id?: string | null;
};

export type QuizGenerationJobStatus =
  | "queued"
  | "running"
  | "completed"
  | "partial"
  | "failed"
  | "cancelled";

export type QuestionGenerationMode = "live" | "normalized_live" | "fallback";

export type QuizGenerationRequest = {
  user_id?: string;
  course_id: string;
  module_id?: string | null;
  query: string;
  question_count: number;
  question_types: QuestionType[];
  retrieval_top_k: number;
  selected_source_ids: string[];
  scope?: StudyScope | null;
  client_request_id?: string | null;
};

export type QuizGenerationAcceptedResponse = {
  job_id: string;
  status: QuizGenerationJobStatus;
  created_at: string;
  dedupe_key: string;
};

export type QuestionGenerationAttempt = {
  job_id: string;
  question_id: string;
  attempt_number: number;
  provider: string;
  model: string;
  latency_ms?: number | null;
  response_phase?: string | null;
  timeout_hit: boolean;
  error_type?: string | null;
  request_id?: string | null;
  created_at: string;
};

export type QuizGenerationResultItem = {
  job_id: string;
  question_id: string;
  ordinal: number;
  source_id: string;
  section_title: string;
  generation_mode: QuestionGenerationMode;
  question: QuizQuestion;
  answer_key: {
    question_id: string;
    question_type: QuestionType;
    concept: string;
    correct_answer: string;
    correct_option_id?: string | null;
    expected_keywords: string[];
    difficulty: number;
    citations: SourceChunk[];
  };
  created_at: string;
};

export type QuizGenerationJobProgress = {
  total_questions: number;
  completed_questions: number;
  fallback_questions: number;
  current_question_index: number;
};

export type QuizGenerationJobResponse = {
  job_id: string;
  dedupe_key: string;
  status: QuizGenerationJobStatus;
  provider: string;
  model: string;
  request_payload: QuizGenerationRequest;
  progress: QuizGenerationJobProgress;
  quiz?: QuizBundle | null;
  partial_results: QuizGenerationResultItem[];
  error_summary?: string | null;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  last_heartbeat_at?: string | null;
};

export type QuizGenerationCancelResponse = {
  job_id: string;
  status: QuizGenerationJobStatus;
};

export type QuizSubmissionAnswer = {
  question_id: string;
  selected_option_id?: string | null;
  answer_text?: string | null;
};

export type QuestionGradeResult = {
  question_id: string;
  question_type: QuestionType;
  concept: string;
  is_correct: boolean;
  grading_label: string;
  score: number;
  submitted_option_id?: string | null;
  submitted_answer: string;
  correct_option_id?: string | null;
  correct_answer: string;
  explanation: string;
  citations: SourceChunk[];
};

export type QuizGradeResponse = {
  quiz_id: string;
  course_id: string;
  module_id?: string | null;
  overall_score: number;
  mastery_by_concept: Record<string, number>;
  wrong_concepts: string[];
  results: QuestionGradeResult[];
};

export type QuizReviewResponse = {
  quiz: QuizBundle;
  results: QuestionGradeResult[];
};

export type ActivityEventType =
  | "material_opened"
  | "material_section_viewed"
  | "pdf_source_clicked"
  | "quiz_generated"
  | "quiz_started"
  | "question_answered"
  | "question_submitted"
  | "answer_explanation_viewed"
  | "missed_question_saved"
  | "practice_concept_clicked"
  | "review_material_clicked"
  | "quiz_completed"
  | "recommendation_clicked"
  | "study_session_started"
  | "study_session_ended";

export type ActivityEventPayload = {
  user_id?: string;
  course_id?: string | null;
  module_id?: string | null;
  material_id?: string | null;
  section_id?: string | null;
  concept_id?: string | null;
  quiz_id?: string | null;
  question_id?: string | null;
  question_type?: string | null;
  difficulty?: number | null;
  event_type: ActivityEventType;
  metadata_json?: Record<string, unknown>;
};

export type RemediationConceptRequest = {
  concept: string;
  question_count: number;
};

export type RemediationRequest = {
  course_id: string;
  module_id?: string | null;
  concepts: RemediationConceptRequest[];
  default_question_count: number;
  retrieval_top_k: number;
};

export type RemediationConceptBundle = {
  concept: string;
  questions: QuizQuestion[];
};

export type RemediationResponse = {
  remediation_id: string;
  course_id: string;
  module_id?: string | null;
  mastery_by_concept: Record<string, number>;
  wrong_concepts: string[];
  concept_bundles: RemediationConceptBundle[];
};

export type QuizHistoryItem = {
  quiz_id: string;
  module_id?: string | null;
  record_type?: "quiz" | "concept_practice";
  query: string;
  question_count: number;
  overall_score: number | null;
  wrong_question_count: number;
  created_at?: string | null;
  attempts: QuizAttemptSummary[];
};

export type MockExamHistoryItem = {
  exam_id: string;
  module_id?: string | null;
  module_ids?: string[];
  title: string;
  question_count: number;
  target_difficulty: number;
  created_at?: string | null;
  completed_at?: string | null;
  score_percent?: number | null;
};

export type RetryHistoryEntry = {
  remediation_id: string;
  course_id: string;
  module_id?: string | null;
  concept: string;
  generated_question_ids: string[];
  prompt_signatures: string[];
  original_question_ids: string[];
};

export type CourseDashboardResponse = {
  course_id: string;
  module_id?: string | null;
  material_count: number;
  section_count: number;
  chunk_count: number;
  mastery_percent: number;
  mastery_by_concept: Record<string, number>;
  wrong_concepts: string[];
  materials: MaterialRecord[];
  quizzes: QuizHistoryItem[];
  mock_exams: MockExamHistoryItem[];
  remediation_history: RetryHistoryEntry[];
  wrong_questions: QuestionGradeResult[];
  exam_readiness_score?: number;
  weak_modules?: Array<Record<string, unknown>>;
  weak_concepts_ranked?: Array<Record<string, unknown>>;
  weak_question_types?: Array<Record<string, unknown>>;
  study_recommendations?: Array<Record<string, unknown>>;
};

export type AgentNodeStatus = {
  agent_name?: string | null;
  node_name: string;
  status: string;
  details?: string | null;
};

export type AgentMessage = {
  agent_name: string;
  message: string;
};

export type AgentQualitySummary = {
  gate_enabled: boolean;
  uses_torch: boolean;
  accepted_for_delivery: boolean;
  notes: string[];
};

export type AgentProfile = {
  agent_name: string;
  display_name: string;
  role: string;
  personality: string;
  skills: string[];
  operating_rules: string[];
  sample_line?: string | null;
};

export type AgentRecommendation = {
  id: string;
  course_id: string;
  scope: StudyScope;
  agent_name: string;
  recommendation_type: string;
  title: string;
  reason: string;
  target_action: string;
  target_payload: Record<string, unknown>;
  priority: number;
  created_at: string;
  dismissed_at?: string | null;
};

export type AgentRunRecord = {
  run_id: string;
  intent: string;
  course_id: string;
  scope: StudyScope;
  node_statuses: AgentNodeStatus[];
  agent_messages: AgentMessage[];
  recommendations: AgentRecommendation[];
  quality_summary?: AgentQualitySummary | null;
  agent_profiles: AgentProfile[];
  created_at: string;
};

export type AgentRecommendationListResponse = {
  course_id: string;
  recommendations: AgentRecommendation[];
  latest_run?: AgentRunRecord | null;
  agent_profiles: AgentProfile[];
};

export type AgentToolRecommendationCard = {
  title: string;
  reason: string;
  actionType: "review_material" | "generate_quiz" | "missed_questions" | "study_section" | "open_materials";
  buttonText: string;
  targetUrl: string;
  targetMaterialId?: string | null;
  targetSectionId?: string | null;
  targetConceptId?: string | null;
  targetModuleId?: string | null;
  sourcePage?: number | null;
  questionType?: string | null;
  priorityScore: number;
  weakAreaName?: string;
  accuracy?: number | null;
  attempts?: number;
  recentTrend?: string;
  whyItMatters?: string;
  recommendedAction?: string;
  buttons?: AgentRecommendationButton[];
};

export type AgentWeakAreaSummary = {
  id: string;
  name: string;
  accuracy?: number | null;
  attempts: number;
  recentTrend: string;
  priorityScore: number;
};

export type AgentRecommendationButton = {
  label: string;
  actionType:
    | "review_material"
    | "practice_concept"
    | "generate_quiz"
    | "retake_missed_questions"
    | "view_source_pdf_page"
    | "study_similar_questions"
    | "study_section"
    | "open_materials";
  targetUrl: string;
  targetMaterialId?: string | null;
  targetSectionId?: string | null;
  targetConceptId?: string | null;
  targetModuleId?: string | null;
  sourcePage?: number | null;
  questionType?: string | null;
};

export type SmartAgentStudyPlanResponse = {
  summary: string;
  readinessScore: number;
  recommendations: AgentToolRecommendationCard[];
  topWeakModules: AgentWeakAreaSummary[];
  topWeakConcepts: AgentWeakAreaSummary[];
  weakestQuestionTypes: AgentWeakAreaSummary[];
  recommendedNextAction: string;
};

export type AgentMemoryProfile = {
  course_id: string;
  preferred_study_style: string;
  preferred_quiz_format: string;
  default_question_count: number;
  focus_areas: string[];
  encouragement_style: string;
  progress_notes: string[];
  updated_at?: string | null;
};

export type AgentMemoryUpdateRequest = {
  preferred_study_style: string;
  preferred_quiz_format: string;
  default_question_count: number;
  focus_areas: string[];
  encouragement_style: string;
  progress_notes: string[];
};

export type AgentActionCard = {
  label: string;
  action: string;
  href?: string | null;
  payload: Record<string, unknown>;
  tone: string;
};

export type AgentChatResponse = {
  course_id: string;
  message: string;
  response_mode?: "live_llm" | "grounded_fallback" | string;
  actions: AgentActionCard[];
  memory: AgentMemoryProfile;
  recommendations: AgentRecommendation[];
  active_agent_profile: AgentProfile;
  agent_profiles: AgentProfile[];
};

export type ReminderType = "daily" | "final_week" | "weak_concept";

export type NotificationDraftStatus = "draft" | "blocked" | "simulated_sent" | "sent";

export type NotificationPreference = {
  course_id: string;
  email_enabled: boolean;
  email_address?: string | null;
  daily_reminder_enabled: boolean;
  final_week_enabled: boolean;
  weak_concept_enabled: boolean;
  exam_date?: string | null;
  preferred_reminder_time: string;
  busy_windows: string[];
  updated_at?: string | null;
};

export type NotificationPreferenceUpdateRequest = {
  email_enabled: boolean;
  email_address?: string | null;
  daily_reminder_enabled: boolean;
  final_week_enabled: boolean;
  weak_concept_enabled: boolean;
  exam_date?: string | null;
  preferred_reminder_time: string;
  busy_windows: string[];
};

export type ReminderDraft = {
  draft_id: string;
  course_id: string;
  reminder_type: ReminderType;
  subject: string;
  body: string;
  recipient_email?: string | null;
  quality_reviewed: boolean;
  quality_notes: string[];
  status: NotificationDraftStatus;
  created_at: string;
  sent_at?: string | null;
};

export type ReminderDraftSendResponse = {
  draft: ReminderDraft;
  delivery_message: string;
};

export type ExamTopicCoverage = {
  topic: string;
  question_count: number;
  question_types: QuestionType[];
};

export type ExamBlueprint = {
  title: string;
  instructions: string;
  topic_coverage: ExamTopicCoverage[];
  target_difficulty: number;
  style_example: string;
};

export type MockExamBundle = {
  exam_id: string;
  course_id: string;
  module_id?: string | null;
  module_ids?: string[];
  created_at?: string | null;
  blueprint: ExamBlueprint;
  questions: QuizQuestion[];
};

export type MockExamSourceOption = {
  option_id: string;
  text: string;
};

export type MockExamSourceQuestion = {
  source_question_id: string;
  source_exam_id: string;
  question_number: number;
  prompt: string;
  options: MockExamSourceOption[];
  correct_option_id?: string | null;
  correct_answer: string;
  explanation: string;
  topic: string;
  learning_objective?: string | null;
  difficulty: number;
  source_page?: number | null;
  matched_material_id?: string | null;
  matched_source_id?: string | null;
  matched_chunk_id?: string | null;
  matched_citation_label?: string | null;
  source_evidence?: string | null;
};

export type MockExamSourceExam = {
  source_exam_id: string;
  title: string;
  question_count: number;
  answer_count: number;
  questions: MockExamSourceQuestion[];
};

export type MockExamSourceBank = {
  bank_id: string;
  course_id: string;
  file_name: string;
  content_type?: string | null;
  uploaded_at: string;
  extraction_mode: string;
  exams: MockExamSourceExam[];
  warnings: string[];
};

export type MockExamSourceIngestResponse = {
  bank: MockExamSourceBank;
};

export type MockExamSourceSummary = {
  source_exam_id: string;
  title: string;
  question_count: number;
  answer_count: number;
  average_difficulty: number;
};

export type MockExamSourceBankSummary = {
  bank_id: string;
  course_id: string;
  file_name: string;
  uploaded_at: string;
  exam_count: number;
  question_count: number;
  exams: MockExamSourceSummary[];
  warnings: string[];
};

export type MockExamSourceListResponse = {
  sources: MockExamSourceBankSummary[];
};

export type MockExamGenerationRequest = {
  course_id: string;
  module_id?: string | null;
  module_ids?: string[];
  scope?: StudyScope | null;
  source_exam_id?: string | null;
  blueprint: ExamBlueprint;
  retrieval_top_k: number;
};

export type MockExamGenerationResponse = {
  exam: MockExamBundle;
};

export type ConceptAnalytics = {
  concept: string;
  question_count: number;
  correct_count: number;
  average_score: number;
};

export type MockExamGradeResponse = {
  exam_id: string;
  course_id: string;
  module_id?: string | null;
  module_ids?: string[];
  completed_at?: string | null;
  overall_score: number;
  analytics_by_concept: ConceptAnalytics[];
  results: QuestionGradeResult[];
};

export type MockExamReviewResponse = {
  exam: MockExamBundle;
  grade_result?: MockExamGradeResponse | null;
};

export type StudyPackageStatus =
  | "draft"
  | "building"
  | "partially_complete"
  | "failed"
  | "complete"
  | "cancelled";

export type StudyPackageKind = "complete" | "study_cards" | "mock_exam";
export type ExamBlueprintMode = "source_exam" | "frm_part_i";

export type StudyPackageJobStatus =
  | "queued"
  | "running"
  | "paused"
  | "partially_complete"
  | "failed"
  | "complete"
  | "cancelled";

export type StudyPackageFileKind =
  | "flashcards"
  | "mock_exam"
  | "formula_review"
  | "exam_blueprint"
  | "validation_html"
  | "validation_json"
  | "manifest"
  | "zip";

export type StudyPackageCreateRequest = {
  course_id: string;
  title: string;
  package_kind: StudyPackageKind;
  exam_blueprint_mode: ExamBlueprintMode;
  exam_name: string;
  exam_part: string;
  mock_exam_count: number;
  questions_per_exam: number;
  cards_per_concept: number;
  timer_minutes: number;
  include_formula_review: boolean;
  include_source_references: boolean;
  material_ids: string[];
  source_exam_id: string | null;
  generated_exam_ids: string[];
};

export type StudyPackageRecord = {
  package_id: string;
  course_id: string;
  title: string;
  package_kind: StudyPackageKind;
  exam_name: string;
  exam_part: string;
  status: StudyPackageStatus;
  active_version: number;
  created_at: string;
  updated_at: string;
};

export type StudyPackageListResponse = {
  packages: StudyPackageRecord[];
};

export type StudyPackageVersion = {
  package_id: string;
  version: number;
  status: StudyPackageStatus;
  configuration: StudyPackageCreateRequest;
  created_at: string;
  completed_at: string | null;
  generator_version: string;
  source_fingerprint: string;
  model_metadata: Record<string, string>;
  prompt_versions: Record<string, string>;
};

export type StudyPackageVersionListResponse = {
  versions: StudyPackageVersion[];
};

export type StudyPackageGenerationJob = {
  job_id: string;
  package_id: string;
  version: number;
  status: StudyPackageJobStatus;
  current_step: string | null;
  accepted_flashcards: number;
  expected_flashcards: number;
  accepted_questions: number;
  expected_questions: number;
  artifact_size_bytes: number;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  error_message: string | null;
};

export type StudyPackageFile = {
  file_id: string;
  package_id: string;
  version: number;
  kind: StudyPackageFileKind;
  file_name: string;
  media_type: string;
  size_bytes: number;
  sha256: string;
  content_count: number;
  artifact_path: string | null;
};

export type StudyPackageFileListResponse = {
  files: StudyPackageFile[];
};

export type StudyPackageValidationSeverity = "info" | "warning" | "error";

export type StudyPackageValidationFinding = {
  code: string;
  severity: StudyPackageValidationSeverity;
  message: string;
  file_id: string | null;
  evidence: Record<string, string>;
};

export type StudyPackageValidationReport = {
  package_id: string;
  version: number;
  passed: boolean;
  created_at: string;
  findings: StudyPackageValidationFinding[];
};

export type StudyPackageVersionResponse = {
  package: StudyPackageRecord;
  version: StudyPackageVersion;
  files: StudyPackageFile[];
  validation: StudyPackageValidationReport | null;
};

export type CompletedExamAttempt = {
  schema_version: "1";
  attempt_id: string;
  package_id: string;
  package_version: number;
  file_id: string;
  exam_id: string;
  content_sha256: string;
  started_at: string;
  completed_at: string;
  remaining_seconds: number;
  answers: Record<string, number>;
  flags: Record<string, boolean>;
};

export type ImportedExamAttemptRecord = {
  attempt: CompletedExamAttempt;
  imported_at: string;
  grade: MockExamGradeResponse;
};

export type CompletedExamImportResponse = {
  record: ImportedExamAttemptRecord;
  duplicate: boolean;
};

export type ImportedExamAttemptListResponse = {
  attempts: ImportedExamAttemptRecord[];
};
