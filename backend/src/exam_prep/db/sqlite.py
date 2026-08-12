import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class SQLiteDatabase:
    path: Path

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS courses (
                    course_id TEXT PRIMARY KEY,
                    course_code TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    description TEXT,
                    is_deleted INTEGER NOT NULL DEFAULT 0,
                    deleted_at TEXT
                );

                CREATE TABLE IF NOT EXISTS modules (
                    module_id TEXT PRIMARY KEY,
                    course_id TEXT NOT NULL,
                    module_number TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    description TEXT,
                    is_deleted INTEGER NOT NULL DEFAULT 0,
                    deleted_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_modules_course
                    ON modules(course_id);

                CREATE TABLE IF NOT EXISTS llm_config (
                    config_id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    api_key TEXT,
                    demo_mode INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS workflow_state (
                    workflow_id TEXT PRIMARY KEY,
                    course_id TEXT,
                    module_id TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS material_records (
                    material_id TEXT PRIMARY KEY,
                    course_id TEXT NOT NULL,
                    module_id TEXT,
                    file_name TEXT NOT NULL,
                    display_name TEXT,
                    file_path TEXT,
                    uploaded_at TEXT,
                    content_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    page_count INTEGER,
                    processing_status TEXT,
                    processing_progress INTEGER NOT NULL DEFAULT 0,
                    outline_status TEXT,
                    enrichment_status TEXT,
                    last_processed_at TEXT,
                    content_hash TEXT,
                    raw_text_path TEXT,
                    chunk_count INTEGER NOT NULL,
                    section_count INTEGER NOT NULL,
                    error_message TEXT,
                    parse_debug_report TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_material_records_course
                    ON material_records(course_id);

                CREATE TABLE IF NOT EXISTS material_sections (
                    source_id TEXT PRIMARY KEY,
                    material_id TEXT NOT NULL,
                    course_id TEXT NOT NULL,
                    module_id TEXT,
                    file_name TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    section_title TEXT NOT NULL,
                    clean_title TEXT,
                    summary TEXT,
                    source_text TEXT,
                    citation_label TEXT NOT NULL,
                    section_index INTEGER NOT NULL,
                    section_order INTEGER,
                    start_page INTEGER,
                    end_page INTEGER,
                    key_terms_json TEXT,
                    key_concepts_json TEXT,
                    formulas_json TEXT,
                    exam_weight REAL,
                    is_junk INTEGER NOT NULL DEFAULT 0,
                    source_text_hash TEXT,
                    enhancement_cache_key TEXT,
                    enhancement_prompt_version TEXT,
                    enhancement_input_excerpt TEXT,
                    enhancement_input_token_limit INTEGER,
                    created_at TEXT,
                    updated_at TEXT,
                    page_number INTEGER,
                    slide_number INTEGER,
                    paragraph_index INTEGER
                );

                CREATE INDEX IF NOT EXISTS idx_material_sections_course
                    ON material_sections(course_id);

                CREATE INDEX IF NOT EXISTS idx_material_sections_material
                    ON material_sections(material_id);

                CREATE TABLE IF NOT EXISTS material_chunks (
                    id TEXT PRIMARY KEY,
                    material_id TEXT NOT NULL,
                    section_id TEXT NOT NULL,
                    course_id TEXT NOT NULL,
                    module_id TEXT,
                    page_number INTEGER,
                    chunk_order INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    embedding_id TEXT,
                    token_count INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_material_chunks_material
                    ON material_chunks(material_id);

                CREATE INDEX IF NOT EXISTS idx_material_chunks_section
                    ON material_chunks(section_id);

                CREATE TABLE IF NOT EXISTS concepts (
                    id TEXT PRIMARY KEY,
                    course_id TEXT NOT NULL,
                    module_id TEXT,
                    material_id TEXT NOT NULL,
                    section_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    normalized_name TEXT NOT NULL,
                    description TEXT,
                    keywords_json TEXT NOT NULL,
                    source_page INTEGER,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_concepts_course
                    ON concepts(course_id);

                CREATE INDEX IF NOT EXISTS idx_concepts_section
                    ON concepts(section_id);

                CREATE TABLE IF NOT EXISTS study_packages (
                    package_id TEXT PRIMARY KEY,
                    course_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    exam_name TEXT NOT NULL,
                    exam_part TEXT NOT NULL,
                    status TEXT NOT NULL,
                    active_version INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    record_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_study_packages_course_updated
                    ON study_packages(course_id, updated_at DESC);

                CREATE TABLE IF NOT EXISTS package_versions (
                    package_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    source_fingerprint TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    PRIMARY KEY (package_id, version)
                );

                CREATE TABLE IF NOT EXISTS generation_jobs (
                    job_id TEXT PRIMARY KEY,
                    package_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    current_step TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT,
                    error_message TEXT,
                    snapshot_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_generation_jobs_package
                    ON generation_jobs(package_id, version, created_at DESC);

                CREATE TABLE IF NOT EXISTS generation_job_steps (
                    job_id TEXT NOT NULL,
                    step_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    input_fingerprint TEXT NOT NULL,
                    accepted_count INTEGER NOT NULL DEFAULT 0,
                    rejected_count INTEGER NOT NULL DEFAULT 0,
                    checkpoint_json TEXT NOT NULL DEFAULT '{}',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    error_message TEXT,
                    provider_usage_json TEXT NOT NULL DEFAULT '{}',
                    output_version INTEGER,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (job_id, step_name)
                );

                CREATE TABLE IF NOT EXISTS validation_results (
                    package_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    passed INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    report_json TEXT NOT NULL,
                    PRIMARY KEY (package_id, version)
                );

                CREATE TABLE IF NOT EXISTS export_files (
                    package_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    file_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    file_name TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    sha256 TEXT NOT NULL,
                    content_count INTEGER NOT NULL DEFAULT 0,
                    artifact_path TEXT,
                    snapshot_json TEXT NOT NULL,
                    PRIMARY KEY (package_id, version, file_id),
                    UNIQUE (package_id, version, file_name)
                );

                CREATE INDEX IF NOT EXISTS idx_export_files_package_version
                    ON export_files(package_id, version, kind);

                CREATE TABLE IF NOT EXISTS package_exam_attempts (
                    attempt_id TEXT PRIMARY KEY,
                    package_id TEXT NOT NULL,
                    package_version INTEGER NOT NULL,
                    file_id TEXT NOT NULL,
                    exam_id TEXT NOT NULL,
                    completed_at TEXT NOT NULL,
                    imported_at TEXT NOT NULL,
                    record_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_package_exam_attempts_package
                    ON package_exam_attempts(package_id, completed_at DESC);

                CREATE TABLE IF NOT EXISTS quiz_generation_jobs (
                    job_id TEXT PRIMARY KEY,
                    dedupe_key TEXT NOT NULL,
                    status TEXT NOT NULL,
                    request_payload_json TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    total_questions INTEGER NOT NULL,
                    completed_questions INTEGER NOT NULL,
                    fallback_questions INTEGER NOT NULL,
                    error_count INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    last_heartbeat_at TEXT,
                    failure_reason TEXT,
                    cancel_requested INTEGER NOT NULL DEFAULT 0
                );

                CREATE INDEX IF NOT EXISTS idx_quiz_generation_jobs_dedupe
                    ON quiz_generation_jobs(dedupe_key);

                CREATE TABLE IF NOT EXISTS quiz_generation_results (
                    job_id TEXT NOT NULL,
                    question_id TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    source_id TEXT NOT NULL,
                    section_title TEXT NOT NULL,
                    generation_mode TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (job_id, question_id)
                );

                CREATE INDEX IF NOT EXISTS idx_quiz_generation_results_job_ordinal
                    ON quiz_generation_results(job_id, ordinal);

                CREATE TABLE IF NOT EXISTS question_generation_attempts (
                    attempt_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    question_id TEXT NOT NULL,
                    attempt_number INTEGER NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    latency_ms REAL,
                    response_phase TEXT,
                    timeout_hit INTEGER NOT NULL,
                    error_type TEXT,
                    request_id TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_question_generation_attempts_job
                    ON question_generation_attempts(job_id, question_id, attempt_number);

                CREATE TABLE IF NOT EXISTS agent_runs (
                    run_id TEXT PRIMARY KEY,
                    course_id TEXT NOT NULL,
                    intent TEXT NOT NULL,
                    scope_json TEXT NOT NULL,
                    node_statuses_json TEXT NOT NULL,
                    agent_messages_json TEXT NOT NULL,
                    recommendations_json TEXT NOT NULL,
                    quality_summary_json TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_agent_runs_course_created
                    ON agent_runs(course_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS agent_recommendations (
                    id TEXT PRIMARY KEY,
                    course_id TEXT NOT NULL,
                    scope_json TEXT NOT NULL,
                    agent_name TEXT NOT NULL,
                    recommendation_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    target_action TEXT NOT NULL,
                    target_payload_json TEXT NOT NULL,
                    priority INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    dismissed_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_agent_recommendations_course
                    ON agent_recommendations(course_id, dismissed_at, priority DESC, created_at DESC);

                CREATE TABLE IF NOT EXISTS user_events (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    course_id TEXT,
                    module_id TEXT,
                    material_id TEXT,
                    section_id TEXT,
                    concept_id TEXT,
                    quiz_id TEXT,
                    question_id TEXT,
                    question_type TEXT,
                    difficulty REAL,
                    event_type TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_user_events_context
                    ON user_events(user_id, course_id, timestamp DESC);

                CREATE INDEX IF NOT EXISTS idx_user_events_quiz
                    ON user_events(quiz_id, question_id);

                CREATE INDEX IF NOT EXISTS idx_user_events_type
                    ON user_events(event_type, timestamp DESC);

                CREATE TABLE IF NOT EXISTS study_sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    course_id TEXT NOT NULL,
                    module_id TEXT,
                    material_id TEXT,
                    section_id TEXT,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    duration_seconds INTEGER,
                    metadata_json TEXT NOT NULL,
                    session_type TEXT,
                    title TEXT,
                    reading_number INTEGER,
                    source_page_start INTEGER,
                    source_page_end INTEGER,
                    status TEXT,
                    created_at TEXT,
                    updated_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_study_sessions_context
                    ON study_sessions(user_id, course_id, started_at DESC);

                CREATE TABLE IF NOT EXISTS flashcards (
                    id TEXT PRIMARY KEY,
                    course_id TEXT NOT NULL,
                    material_id TEXT NOT NULL,
                    module_id TEXT,
                    section_id TEXT,
                    learning_outcome_id TEXT,
                    concept_id TEXT,
                    formula_id TEXT,
                    front TEXT NOT NULL,
                    back_concise TEXT NOT NULL,
                    back TEXT,
                    source_excerpt TEXT,
                    source_page INTEGER,
                    card_type TEXT NOT NULL,
                    difficulty TEXT,
                    confidence_group TEXT NOT NULL DEFAULT 'new',
                    interval_days INTEGER NOT NULL DEFAULT 0,
                    ease_factor REAL NOT NULL DEFAULT 2.5,
                    repetitions INTEGER NOT NULL DEFAULT 0,
                    due_at TEXT,
                    last_reviewed_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    archived INTEGER NOT NULL DEFAULT 0,
                    needs_more_source INTEGER NOT NULL DEFAULT 0,
                    quality_score REAL
                );

                CREATE TABLE IF NOT EXISTS question_attempts (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    quiz_id TEXT NOT NULL,
                    question_id TEXT NOT NULL,
                    course_id TEXT NOT NULL,
                    module_id TEXT,
                    material_id TEXT,
                    section_id TEXT,
                    concept_id TEXT,
                    selected_answer TEXT NOT NULL,
                    correct_answer TEXT NOT NULL,
                    is_correct INTEGER NOT NULL,
                    time_spent_seconds INTEGER,
                    question_type TEXT,
                    difficulty REAL,
                    attempt_number INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_question_attempts_context
                    ON question_attempts(user_id, course_id, quiz_id, created_at DESC);

                CREATE INDEX IF NOT EXISTS idx_question_attempts_source
                    ON question_attempts(course_id, module_id, material_id, section_id, concept_id);

                CREATE TABLE IF NOT EXISTS flashcard_reviews (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    course_id TEXT NOT NULL,
                    module_id TEXT,
                    material_id TEXT,
                    section_id TEXT,
                    concept_id TEXT,
                    flashcard_id TEXT NOT NULL,
                    rating TEXT NOT NULL,
                    previous_interval_days INTEGER NOT NULL,
                    new_interval_days INTEGER NOT NULL,
                    previous_confidence_group TEXT NOT NULL,
                    new_confidence_group TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    reviewed_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_flashcard_reviews_context
                    ON flashcard_reviews(user_id, course_id, reviewed_at DESC);

                CREATE INDEX IF NOT EXISTS idx_flashcard_reviews_card
                    ON flashcard_reviews(flashcard_id, reviewed_at DESC);

                CREATE TABLE IF NOT EXISTS generated_content_quality_flags (
                    id TEXT PRIMARY KEY,
                    course_id TEXT,
                    material_id TEXT,
                    section_id TEXT,
                    concept_id TEXT,
                    content_id TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    flag_type TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_generated_quality_flags_context
                    ON generated_content_quality_flags(course_id, material_id, section_id, concept_id, created_at DESC);

                CREATE INDEX IF NOT EXISTS idx_generated_quality_flags_content
                    ON generated_content_quality_flags(content_id, content_type, created_at DESC);

                CREATE TABLE IF NOT EXISTS concept_mastery (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    course_id TEXT NOT NULL,
                    module_id TEXT,
                    material_id TEXT,
                    section_id TEXT,
                    concept_id TEXT NOT NULL,
                    attempts INTEGER NOT NULL,
                    correct_attempts INTEGER NOT NULL,
                    accuracy REAL NOT NULL,
                    repeat_misses INTEGER NOT NULL,
                    average_time_seconds REAL,
                    mastery_score REAL NOT NULL,
                    last_attempt_at TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_concept_mastery_course
                    ON concept_mastery(user_id, course_id, mastery_score ASC, attempts DESC);

                CREATE INDEX IF NOT EXISTS idx_concept_mastery_source
                    ON concept_mastery(course_id, module_id, material_id, section_id, concept_id);

                CREATE TABLE IF NOT EXISTS module_mastery (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    course_id TEXT NOT NULL,
                    module_id TEXT NOT NULL,
                    attempts INTEGER NOT NULL,
                    correct_attempts INTEGER NOT NULL,
                    accuracy REAL NOT NULL,
                    average_time_seconds REAL,
                    mastery_score REAL NOT NULL,
                    weak_concepts_json TEXT NOT NULL,
                    weak_question_types_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_module_mastery_course
                    ON module_mastery(user_id, course_id, mastery_score ASC, attempts DESC);

                CREATE TABLE IF NOT EXISTS question_type_mastery (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    course_id TEXT NOT NULL,
                    module_id TEXT,
                    concept_id TEXT,
                    question_type TEXT NOT NULL,
                    attempts INTEGER NOT NULL,
                    correct_attempts INTEGER NOT NULL,
                    accuracy REAL NOT NULL,
                    average_time_seconds REAL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_question_type_mastery_course
                    ON question_type_mastery(user_id, course_id, accuracy ASC, attempts DESC);

                CREATE TABLE IF NOT EXISTS recommendation_history (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    course_id TEXT NOT NULL,
                    recommendation_type TEXT NOT NULL,
                    target_module_id TEXT,
                    target_section_id TEXT,
                    target_concept_id TEXT,
                    reason TEXT NOT NULL,
                    priority_score REAL NOT NULL,
                    clicked INTEGER NOT NULL DEFAULT 0,
                    completed INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    recommended_action TEXT NOT NULL DEFAULT ''
                );

                CREATE INDEX IF NOT EXISTS idx_recommendation_history_course
                    ON recommendation_history(user_id, course_id, completed ASC, clicked ASC, priority_score DESC);

                CREATE TABLE IF NOT EXISTS agent_memory (
                    course_id TEXT PRIMARY KEY,
                    preferred_study_style TEXT NOT NULL,
                    preferred_quiz_format TEXT NOT NULL,
                    default_question_count INTEGER NOT NULL,
                    focus_areas_json TEXT NOT NULL,
                    encouragement_style TEXT NOT NULL,
                    progress_notes_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS notification_preferences (
                    course_id TEXT PRIMARY KEY,
                    email_enabled INTEGER NOT NULL DEFAULT 0,
                    email_address TEXT,
                    daily_reminder_enabled INTEGER NOT NULL DEFAULT 0,
                    final_week_enabled INTEGER NOT NULL DEFAULT 0,
                    weak_concept_enabled INTEGER NOT NULL DEFAULT 1,
                    exam_date TEXT,
                    preferred_reminder_time TEXT NOT NULL DEFAULT '19:00',
                    busy_windows_json TEXT NOT NULL DEFAULT '[]',
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS notification_drafts (
                    draft_id TEXT PRIMARY KEY,
                    course_id TEXT NOT NULL,
                    reminder_type TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    body TEXT NOT NULL,
                    recipient_email TEXT,
                    quality_reviewed INTEGER NOT NULL DEFAULT 1,
                    quality_notes_json TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    sent_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_notification_drafts_course_created
                    ON notification_drafts(course_id, created_at DESC);
                """
            )
            self._ensure_column(connection, "workflow_state", "module_id", "TEXT")
            self._ensure_column(connection, "generation_jobs", "completed_at", "TEXT")
            self._ensure_column(
                connection,
                "generation_jobs",
                "snapshot_json",
                "TEXT NOT NULL DEFAULT '{}'",
            )
            self._ensure_column(connection, "material_records", "module_id", "TEXT")
            self._ensure_column(connection, "material_records", "display_name", "TEXT")
            self._ensure_column(connection, "material_records", "file_path", "TEXT")
            self._ensure_column(connection, "material_records", "uploaded_at", "TEXT")
            self._ensure_column(connection, "material_records", "page_count", "INTEGER")
            self._ensure_column(connection, "material_records", "processing_status", "TEXT")
            self._ensure_column(connection, "material_records", "processing_progress", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(connection, "material_records", "outline_status", "TEXT")
            self._ensure_column(connection, "material_records", "enrichment_status", "TEXT")
            self._ensure_column(connection, "material_records", "last_processed_at", "TEXT")
            self._ensure_column(connection, "material_records", "content_hash", "TEXT")
            self._ensure_column(connection, "material_records", "raw_text_path", "TEXT")
            self._ensure_column(connection, "material_records", "parse_debug_report", "TEXT")
            self._ensure_column(connection, "material_sections", "module_id", "TEXT")
            self._ensure_column(connection, "material_sections", "clean_title", "TEXT")
            self._ensure_column(connection, "material_sections", "summary", "TEXT")
            self._ensure_column(connection, "material_sections", "source_text", "TEXT")
            self._ensure_column(connection, "material_sections", "section_order", "INTEGER")
            self._ensure_column(connection, "material_sections", "start_page", "INTEGER")
            self._ensure_column(connection, "material_sections", "end_page", "INTEGER")
            self._ensure_column(connection, "material_sections", "key_terms_json", "TEXT")
            self._ensure_column(connection, "material_sections", "key_concepts_json", "TEXT")
            self._ensure_column(connection, "material_sections", "formulas_json", "TEXT")
            self._ensure_column(connection, "material_sections", "exam_weight", "REAL")
            self._ensure_column(connection, "material_sections", "is_junk", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(connection, "material_sections", "source_text_hash", "TEXT")
            self._ensure_column(connection, "material_sections", "enhancement_cache_key", "TEXT")
            self._ensure_column(connection, "material_sections", "enhancement_prompt_version", "TEXT")
            self._ensure_column(connection, "material_sections", "enhancement_input_excerpt", "TEXT")
            self._ensure_column(connection, "material_sections", "enhancement_input_token_limit", "INTEGER")
            self._ensure_column(connection, "material_sections", "created_at", "TEXT")
            self._ensure_column(connection, "material_sections", "updated_at", "TEXT")
            self._ensure_column(connection, "courses", "is_deleted", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(connection, "courses", "deleted_at", "TEXT")
            self._ensure_column(connection, "modules", "is_deleted", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(connection, "modules", "deleted_at", "TEXT")
            self._ensure_column(connection, "agent_memory", "preferred_study_style", "TEXT NOT NULL DEFAULT 'balanced'")
            self._ensure_column(connection, "agent_memory", "preferred_quiz_format", "TEXT NOT NULL DEFAULT 'mcq'")
            self._ensure_column(connection, "agent_memory", "default_question_count", "INTEGER NOT NULL DEFAULT 3")
            self._ensure_column(connection, "agent_memory", "focus_areas_json", "TEXT NOT NULL DEFAULT '[]'")
            self._ensure_column(connection, "agent_memory", "encouragement_style", "TEXT NOT NULL DEFAULT 'steady'")
            self._ensure_column(connection, "agent_memory", "progress_notes_json", "TEXT NOT NULL DEFAULT '[]'")
            self._ensure_column(connection, "agent_memory", "updated_at", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, "notification_preferences", "email_enabled", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(connection, "notification_preferences", "email_address", "TEXT")
            self._ensure_column(connection, "notification_preferences", "daily_reminder_enabled", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(connection, "notification_preferences", "final_week_enabled", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(connection, "notification_preferences", "weak_concept_enabled", "INTEGER NOT NULL DEFAULT 1")
            self._ensure_column(connection, "notification_preferences", "exam_date", "TEXT")
            self._ensure_column(connection, "notification_preferences", "preferred_reminder_time", "TEXT NOT NULL DEFAULT '19:00'")
            self._ensure_column(connection, "notification_preferences", "busy_windows_json", "TEXT NOT NULL DEFAULT '[]'")
            self._ensure_column(connection, "notification_preferences", "updated_at", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, "recommendation_history", "title", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, "recommendation_history", "recommended_action", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, "study_sessions", "session_type", "TEXT")
            self._ensure_column(connection, "study_sessions", "title", "TEXT")
            self._ensure_column(connection, "study_sessions", "reading_number", "INTEGER")
            self._ensure_column(connection, "study_sessions", "source_page_start", "INTEGER")
            self._ensure_column(connection, "study_sessions", "source_page_end", "INTEGER")
            self._ensure_column(connection, "study_sessions", "status", "TEXT")
            self._ensure_column(connection, "study_sessions", "created_at", "TEXT")
            self._ensure_column(connection, "study_sessions", "updated_at", "TEXT")
            self._ensure_column(connection, "flashcards", "course_id", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, "flashcards", "material_id", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, "flashcards", "module_id", "TEXT")
            self._ensure_column(connection, "flashcards", "section_id", "TEXT")
            self._ensure_column(connection, "flashcards", "learning_outcome_id", "TEXT")
            self._ensure_column(connection, "flashcards", "concept_id", "TEXT")
            self._ensure_column(connection, "flashcards", "formula_id", "TEXT")
            self._ensure_column(connection, "flashcards", "front", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, "flashcards", "back_concise", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, "flashcards", "back", "TEXT")
            self._ensure_column(connection, "flashcards", "source_excerpt", "TEXT")
            self._ensure_column(connection, "flashcards", "source_page", "INTEGER")
            self._ensure_column(connection, "flashcards", "card_type", "TEXT NOT NULL DEFAULT 'short_answer_recall'")
            self._ensure_column(connection, "flashcards", "difficulty", "TEXT")
            self._ensure_column(connection, "flashcards", "confidence_group", "TEXT NOT NULL DEFAULT 'new'")
            self._ensure_column(connection, "flashcards", "interval_days", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(connection, "flashcards", "ease_factor", "REAL NOT NULL DEFAULT 2.5")
            self._ensure_column(connection, "flashcards", "repetitions", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(connection, "flashcards", "due_at", "TEXT")
            self._ensure_column(connection, "flashcards", "last_reviewed_at", "TEXT")
            self._ensure_column(connection, "flashcards", "created_at", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, "flashcards", "updated_at", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, "flashcards", "archived", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(connection, "flashcards", "needs_more_source", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(connection, "flashcards", "quality_score", "REAL")
            connection.executescript(
                """
                CREATE INDEX IF NOT EXISTS idx_study_sessions_content
                    ON study_sessions(course_id, material_id, session_type, reading_number);

                CREATE INDEX IF NOT EXISTS idx_flashcards_course_due
                    ON flashcards(course_id, archived, due_at);

                CREATE INDEX IF NOT EXISTS idx_flashcards_source
                    ON flashcards(course_id, material_id, module_id, learning_outcome_id);

                CREATE INDEX IF NOT EXISTS idx_flashcards_concept
                    ON flashcards(concept_id, archived);

                CREATE INDEX IF NOT EXISTS idx_flashcards_formula
                    ON flashcards(formula_id, archived);
                """
            )
            connection.execute(
                """
                INSERT INTO courses(course_id, course_code, display_name, description)
                SELECT DISTINCT material_records.course_id, material_records.course_id, material_records.course_id, NULL
                FROM material_records
                WHERE material_records.course_id IS NOT NULL
                  AND material_records.course_id NOT IN (SELECT course_id FROM courses)
                """
            )

    def _ensure_column(
        self,
        connection: sqlite3.Connection,
        table_name: str,
        column_name: str,
        column_type: str,
    ) -> None:
        rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        existing_columns = {row["name"] if isinstance(row, sqlite3.Row) else row[1] for row in rows}
        if column_name in existing_columns:
            return
        connection.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
        )
