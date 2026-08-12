import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from exam_prep.analytics.service import AnalyticsService
from exam_prep.core.config import Settings
from exam_prep.core.exceptions import (
    LLMProviderError,
    LLMResponseSchemaError,
    LLMTransportError,
    MaterialIngestionError,
)
from exam_prep.llm.base import LLMClient
from exam_prep.ml.inference import QuestionQualityInferenceService
from exam_prep.repositories.activity_store import ActivityStore
from exam_prep.schemas.ml import QuestionQualityLabel
from exam_prep.repositories.material_store import MaterialStore
from exam_prep.repositories.quiz_store import QuizStore
from exam_prep.repositories.vector_store import VectorStore
from exam_prep.schemas.config import UserLLMConfig
from exam_prep.schemas.activity import ActivityEventCreate, ActivityEventType, QuestionAttemptCreate
from exam_prep.schemas.materials import ContentLabel, SourceChunk, SourceSection, SourceLocator
from exam_prep.schemas.quiz import (
    GeneratedExplanationPayload,
    GeneratedQuestionPayload,
    GeneratedShortAnswerGradePayload,
    QuestionGenerationAttempt,
    QuestionGenerationMode,
    QuestionGradeResult,
    QuestionType,
    QuizBundle,
    QuizGenerationRequest,
    QuizGenerationResponse,
    QuizGradeRequest,
    QuizGradeResponse,
    QuizQuestion,
    QuizQuestionOption,
    RetryHistoryEntry,
    RemediationConceptBundle,
    RemediationConceptRequest,
    RemediationRequest,
    RemediationResponse,
    QuizSubmissionAnswer,
    StudyRecordType,
    StoredQuestionKey,
    StoredQuizSession,
)
from exam_prep.schemas.retrieval import RetrievalHit
from exam_prep.services.llm_service import StructuredLLMService
from exam_prep.services.question_pipeline import (
    QuestionValidationResult,
    SectionKnowledge,
    classifyChunk,
    cleanSectionDisplayTitle,
    extractKnowledge,
    generateExamStyleQuestion,
    hasWorkbookModuleQuiz,
    sanitizeExplanationText,
    sanitizeOptionText,
    sanitizeQuestionText,
    validateQuestion,
    workbookStyleProfiles,
    workbookStyleExcerpt,
)
from exam_prep.services.retrieval_service import RetrievalService

logger = logging.getLogger(__name__)
MAX_LIVE_QUIZ_GRADING_CALLS_PER_REQUEST = 1
LO_DISTRIBUTION_RE = re.compile(
    r"\bLO\s*(?P<number>\d+)\s*(?:\.|\s)\s*(?P<letter>[a-z])\b",
    re.IGNORECASE,
)
SERIOUS_QUALITY_NOTE_FRAGMENTS = (
    "administrative",
    "answer choices are duplicated",
    "book-level module quiz format",
    "clipped or fragmentary",
    "generic quiz filler",
    "source metadata",
)


@dataclass(slots=True)
class QuizGenerationPlan:
    request: QuizGenerationRequest
    selected_hits: list[RetrievalHit]


@dataclass(slots=True)
class GeneratedQuestionOutcome:
    question: QuizQuestion
    answer_key: StoredQuestionKey
    generation_mode: QuestionGenerationMode
    attempt: QuestionGenerationAttempt | None


@dataclass(slots=True)
class QuizUniquenessState:
    prompt_signatures: set[str]
    correct_answer_signatures: set[str]
    option_set_signatures: set[str]


class QuizService:
    def __init__(
        self,
        *,
        material_store: MaterialStore,
        vector_store: VectorStore,
        quiz_store: QuizStore,
        question_quality_service: QuestionQualityInferenceService,
        runtime_config: UserLLMConfig,
        settings: Settings,
        llm_client: LLMClient | None = None,
        activity_store: ActivityStore | None = None,
    ) -> None:
        self.retrieval_service = RetrievalService(
            material_store=material_store,
            vector_store=vector_store,
        )
        self.material_store = material_store
        self.quiz_store = quiz_store
        self.analytics_service = AnalyticsService()
        self.question_quality_service = question_quality_service
        self.runtime_config = runtime_config
        self.settings = settings
        self.activity_store = activity_store
        self.structured_llm = StructuredLLMService(llm_client, runtime_config.model)
        self.generation_model = (
            settings.llm_quiz_generation_model
            or settings.llm_quiz_model
            or runtime_config.model
        )
        self.explanation_model = (
            settings.llm_quiz_explanation_model
            or settings.llm_quiz_model
            or runtime_config.model
        )

    def generate_quiz(self, request: QuizGenerationRequest) -> QuizGenerationResponse:
        plan = self.prepare_generation_plan(request)
        quiz_id = uuid4().hex
        questions: list[QuizQuestion] = []
        answer_keys: list[StoredQuestionKey] = []
        uniqueness = QuizUniquenessState(
            prompt_signatures=set(),
            correct_answer_signatures=set(),
            option_set_signatures=set(),
        )
        for index, hit in enumerate(plan.selected_hits, start=1):
            outcome = self.generate_deliverable_question_for_hit(
                quiz_id=quiz_id,
                request=request,
                hit=hit,
                selected_hits=plan.selected_hits,
                sequence_index=index,
                uniqueness=uniqueness,
            )
            questions.append(outcome.question)
            answer_keys.append(outcome.answer_key)

        quiz = QuizBundle(
            quiz_id=quiz_id,
            course_id=request.course_id,
            module_id=request.module_id,
            query=request.query.strip(),
            created_at=datetime.now(UTC).isoformat(),
            record_type=(
                StudyRecordType.CONCEPT_PRACTICE
                if request.query.strip().lower().startswith("practice:")
                else StudyRecordType.QUIZ
            ),
            questions=questions,
        )
        self.quiz_store.save_quiz_session(StoredQuizSession(quiz=quiz, answer_keys=answer_keys))
        return QuizGenerationResponse(quiz=quiz)

    def generate_deliverable_question_for_hit(
        self,
        *,
        quiz_id: str,
        request: QuizGenerationRequest,
        hit: RetrievalHit,
        selected_hits: list[RetrievalHit],
        sequence_index: int,
        uniqueness: QuizUniquenessState,
        force_fallback: bool = False,
    ) -> GeneratedQuestionOutcome:
        return self._generate_unique_question_for_hit(
            quiz_id=quiz_id,
            request=request,
            hit=hit,
            selected_hits=selected_hits,
            sequence_index=sequence_index,
            uniqueness=uniqueness,
            force_fallback=force_fallback,
        )

    def _generate_unique_question_for_hit(
        self,
        *,
        quiz_id: str,
        request: QuizGenerationRequest,
        hit: RetrievalHit,
        selected_hits: list[RetrievalHit],
        sequence_index: int,
        uniqueness: QuizUniquenessState,
        force_fallback: bool = False,
    ) -> GeneratedQuestionOutcome:
        variant_stride = max(len(selected_hits), 1)
        last_outcome: GeneratedQuestionOutcome | None = None
        for attempt_index in range(4):
            effective_sequence_index = sequence_index + (attempt_index * variant_stride)
            outcome = self.generate_question_for_hit(
                quiz_id=quiz_id,
                request=request,
                hit=hit,
                selected_hits=selected_hits,
                sequence_index=effective_sequence_index,
                force_fallback=force_fallback or attempt_index > 0,
            )
            last_outcome = outcome
            if self._quality_rejection_reason(outcome) is not None:
                continue
            if self._is_repeated_quiz_outcome(outcome, uniqueness):
                continue
            self._remember_quiz_outcome(outcome, uniqueness)
            return outcome
        if (
            last_outcome is not None
            and not self._hit_uses_workbook_context(hit)
            and self._quality_rejection_reason(last_outcome) is None
        ):
            self._remember_quiz_outcome(last_outcome, uniqueness)
            return last_outcome
        raise MaterialIngestionError(
            "Quiz generation could not produce a deliverable, non-repeated question after multiple grounded retries."
        )

    def _hit_uses_workbook_context(self, hit: RetrievalHit) -> bool:
        return bool(getattr(hit.chunk, "workbook_block_type", None)) or hasWorkbookModuleQuiz(hit.chunk.text)

    def _quality_rejection_reason(self, outcome: GeneratedQuestionOutcome) -> str | None:
        validation = outcome.question.quality_validation
        if validation is None or validation.accepted_for_delivery:
            return None
        if validation.label == QuestionQualityLabel.LOW_QUALITY:
            return "Question quality validation rejected delivery."
        lowered_notes = " ".join(validation.notes).lower()
        if any(fragment in lowered_notes for fragment in SERIOUS_QUALITY_NOTE_FRAGMENTS):
            return "Question quality validation rejected delivery."
        return None

    def _is_repeated_quiz_outcome(
        self,
        outcome: GeneratedQuestionOutcome,
        uniqueness: QuizUniquenessState,
    ) -> bool:
        prompt_signature = self._normalize_text(outcome.question.prompt)
        if prompt_signature in uniqueness.prompt_signatures:
            return True

        option_set_signature = self._option_set_signature(outcome.question)
        if option_set_signature in uniqueness.option_set_signatures:
            return True

        correct_answer_signature = self._normalize_text(outcome.answer_key.correct_answer)
        if len(correct_answer_signature.split()) >= 3 and (
            correct_answer_signature in uniqueness.correct_answer_signatures
        ):
            return True
        return False

    def _remember_quiz_outcome(
        self,
        outcome: GeneratedQuestionOutcome,
        uniqueness: QuizUniquenessState,
    ) -> None:
        prompt_signature = self._normalize_text(outcome.question.prompt)
        if prompt_signature:
            uniqueness.prompt_signatures.add(prompt_signature)
        option_set_signature = self._option_set_signature(outcome.question)
        if option_set_signature:
            uniqueness.option_set_signatures.add(option_set_signature)
        correct_answer_signature = self._normalize_text(outcome.answer_key.correct_answer)
        if len(correct_answer_signature.split()) >= 3:
            uniqueness.correct_answer_signatures.add(correct_answer_signature)

    def _option_set_signature(self, question: QuizQuestion) -> str:
        return " | ".join(self._normalize_text(option.text) for option in question.options)

    def prepare_generation_plan(self, request: QuizGenerationRequest) -> QuizGenerationPlan:
        if not request.question_types:
            raise MaterialIngestionError("At least one question type is required.")

        selected_source_ids = self._selected_source_ids_for_request(request)
        scoped_module_ids = request.scope.module_ids if request.scope else None
        retrieval = self.retrieval_service.query(
            course_id=request.course_id,
            module_id=request.module_id,
            query=request.query,
            top_k=self._bounded_retrieval_top_k(request.retrieval_top_k, request.question_count),
            selected_source_ids=selected_source_ids,
            module_ids=scoped_module_ids,
        )
        if not retrieval.hits:
            raise MaterialIngestionError("No relevant materials found for quiz generation.")

        selected_hits = self._select_hits(
            retrieval.hits,
            request.question_count,
            strict_testable=bool(selected_source_ids),
        )
        if not selected_hits:
            raise MaterialIngestionError("No relevant materials found for quiz generation.")
        return QuizGenerationPlan(request=request, selected_hits=selected_hits)

    def _selected_source_ids_for_request(self, request: QuizGenerationRequest) -> list[str]:
        explicit_source_ids = [source_id for source_id in request.selected_source_ids if source_id]
        if explicit_source_ids:
            return list(dict.fromkeys(explicit_source_ids))
        if request.scope is None:
            return []
        if request.scope.section_ids:
            return list(dict.fromkeys(request.scope.section_ids))
        if not request.scope.material_ids:
            return []

        source_ids: list[str] = []
        for document in self.material_store.list_parsed_documents_by_course(request.course_id, None):
            if document.record.material_id not in request.scope.material_ids:
                continue
            source_ids.extend(section.source_id for section in document.sections)
        return list(dict.fromkeys(source_ids))

    def _bounded_retrieval_top_k(self, requested_top_k: int, question_count: int = 1) -> int:
        requested = max(1, requested_top_k, question_count)
        return min(requested, self.settings.max_chunks_per_retrieval)

    def generate_question_for_hit(
        self,
        *,
        quiz_id: str,
        request: QuizGenerationRequest,
        hit: RetrievalHit,
        selected_hits: list[RetrievalHit],
        sequence_index: int,
        force_fallback: bool = False,
    ) -> GeneratedQuestionOutcome:
        question_type = QuestionType.MCQ
        question_id = f"{quiz_id}-q{sequence_index}"
        hit_chunk = self._hydrate_full_source_chunk(hit.chunk)
        source_section = self._section_from_chunk(hit_chunk)
        source_section = source_section.model_copy(
            update={"section_title": cleanSectionDisplayTitle(source_section.section_title)}
        )
        concept = source_section.section_title
        key_sentence = self._extract_key_sentence(hit_chunk.text, sentence_offset=sequence_index - 1)
        difficulty = self._estimate_difficulty(hit_chunk.text)
        attempt_created_at = datetime.now(UTC).isoformat()
        knowledge = extractKnowledge(source_section)

        if self.structured_llm.available() and not force_fallback:
            try:
                question, answer_key = self._build_live_question(
                    question_id=question_id,
                    question_type=question_type,
                    concept=concept,
                    difficulty=difficulty,
                    hit_chunk=hit_chunk,
                    knowledge=knowledge,
                )
                validation = validateQuestion(
                    question,
                    source_text=hit_chunk.text,
                    knowledge=knowledge,
                    correct_answer=answer_key.correct_answer,
                )
                if not validation.accepted:
                    raise LLMProviderError(
                        validation.rejection_reason or "Generated question did not pass quality validation."
                    )
                question, answer_key = self._attach_source_metadata(
                    question=question,
                    answer_key=answer_key,
                    quiz_id=quiz_id,
                    request=request,
                    hit_chunk=hit_chunk,
                    sequence_index=sequence_index,
                    created_at=attempt_created_at,
                )
                generation_mode = (
                    QuestionGenerationMode.NORMALIZED_LIVE
                    if self.structured_llm.last_call_metadata is not None
                    and self.structured_llm.last_call_metadata.normalization_applied
                    else QuestionGenerationMode.LIVE
                )
                attempt = QuestionGenerationAttempt(
                    job_id=quiz_id,
                    question_id=question_id,
                    attempt_number=1,
                    provider=self.runtime_config.provider.value,
                    model=self.generation_model,
                    latency_ms=(
                        self.structured_llm.last_llm_response.latency_ms
                        if self.structured_llm.last_llm_response is not None
                        else None
                    ),
                    response_phase=(
                        self.structured_llm.last_llm_response.response_phase
                        if self.structured_llm.last_llm_response is not None
                        else None
                    ),
                    timeout_hit=False,
                    error_type=None,
                    request_id=(
                        self.structured_llm.last_llm_response.request_id
                        if self.structured_llm.last_llm_response is not None
                        else None
                    ),
                    created_at=attempt_created_at,
                )
                annotated_question = self._annotate_question_quality(question, validation)
                if (
                    annotated_question.quality_validation is not None
                    and not annotated_question.quality_validation.accepted_for_delivery
                ):
                    raise LLMProviderError(
                        "PyTorch quality gate rejected the live question; using grounded fallback."
                    )
                return GeneratedQuestionOutcome(
                    question=annotated_question,
                    answer_key=answer_key,
                    generation_mode=generation_mode,
                    attempt=attempt,
                )
            except (LLMTransportError, LLMResponseSchemaError, LLMProviderError) as exc:
                logger.warning(
                    "Live quiz question generation failed; falling back for this question. "
                    "question_id=%s concept=%s section=%s error=%s",
                    question_id,
                    concept,
                    hit_chunk.section_title,
                    str(exc),
                )
                attempt = QuestionGenerationAttempt(
                    job_id=quiz_id,
                    question_id=question_id,
                    attempt_number=1,
                    provider=self.runtime_config.provider.value,
                    model=self.generation_model,
                    latency_ms=(
                        self.structured_llm.last_llm_response.latency_ms
                        if self.structured_llm.last_llm_response is not None
                        else None
                    ),
                    response_phase=(
                        self.structured_llm.last_llm_response.response_phase
                        if self.structured_llm.last_llm_response is not None
                        else None
                    ),
                    timeout_hit=isinstance(exc, LLMTransportError),
                    error_type=type(exc).__name__,
                    request_id=(
                        self.structured_llm.last_llm_response.request_id
                        if self.structured_llm.last_llm_response is not None
                        else None
                    ),
                    created_at=attempt_created_at,
                )
                question, answer_key = self._build_demo_question(
                    question_id=question_id,
                    question_type=question_type,
                    concept=concept,
                    difficulty=difficulty,
                    hit_chunk=hit_chunk,
                    selected_hits=selected_hits,
                    key_sentence=key_sentence,
                    sequence_index=sequence_index,
                    knowledge=knowledge,
                )
                validation = validateQuestion(
                    question,
                    source_text=hit_chunk.text,
                    knowledge=knowledge,
                    correct_answer=answer_key.correct_answer,
                )
                question, answer_key = self._attach_source_metadata(
                    question=question,
                    answer_key=answer_key,
                    quiz_id=quiz_id,
                    request=request,
                    hit_chunk=hit_chunk,
                    sequence_index=sequence_index,
                    created_at=attempt_created_at,
                )
                return GeneratedQuestionOutcome(
                    question=self._annotate_question_quality(question, validation),
                    answer_key=answer_key,
                    generation_mode=QuestionGenerationMode.FALLBACK,
                    attempt=attempt,
                )

        question, answer_key = self._build_demo_question(
            question_id=question_id,
            question_type=question_type,
            concept=concept,
            difficulty=difficulty,
            hit_chunk=hit_chunk,
            selected_hits=selected_hits,
            key_sentence=key_sentence,
            sequence_index=sequence_index,
            knowledge=knowledge,
        )
        validation = validateQuestion(
            question,
            source_text=hit_chunk.text,
            knowledge=knowledge,
            correct_answer=answer_key.correct_answer,
        )
        question, answer_key = self._attach_source_metadata(
            question=question,
            answer_key=answer_key,
            quiz_id=quiz_id,
            request=request,
            hit_chunk=hit_chunk,
            sequence_index=sequence_index,
            created_at=attempt_created_at,
        )
        return GeneratedQuestionOutcome(
            question=self._annotate_question_quality(question, validation),
            answer_key=answer_key,
            generation_mode=QuestionGenerationMode.FALLBACK,
            attempt=None,
        )

    def grade_quiz(self, request: QuizGradeRequest) -> QuizGradeResponse:
        session = self.quiz_store.get_quiz_session(request.quiz_id)
        if session is None:
            raise MaterialIngestionError("Quiz session not found.")

        answers_by_question = {
            answer.question_id: answer
            for answer in request.answers
        }
        answer_keys = {key.question_id: key for key in session.answer_keys}
        progress = self.quiz_store.get_mastery_snapshot(session.quiz.course_id, session.quiz.module_id)
        results: list[QuestionGradeResult] = []
        remaining_live_grading_calls = (
            MAX_LIVE_QUIZ_GRADING_CALLS_PER_REQUEST
            if self.settings.enable_live_quiz_grading and self.structured_llm.available()
            else 0
        )

        for question in session.quiz.questions:
            key = answer_keys[question.question_id]
            submission = answers_by_question.get(question.question_id)
            use_live_llm = remaining_live_grading_calls > 0
            if use_live_llm:
                remaining_live_grading_calls -= 1
            result = self._grade_question(question, key, submission, allow_live_llm=use_live_llm)
            results.append(result)
            self._record_question_activity(
                user_id=request.user_id,
                quiz_id=session.quiz.quiz_id,
                question=question,
                key=key,
                result=result,
            )
            progress = self.analytics_service.update_mastery(
                progress,
                concept=key.concept,
                is_correct=result.is_correct,
            )

        self.quiz_store.save_mastery_snapshot(progress)
        self.quiz_store.save_grade_results(session.quiz.quiz_id, results)
        overall_score = (
            round(sum(result.score for result in results) / len(results) * 100.0, 2)
            if results
            else 0.0
        )
        self._record_quiz_completed_activity(
            user_id=request.user_id,
            quiz=session.quiz,
            overall_score=overall_score,
            results=results,
        )
        return QuizGradeResponse(
            quiz_id=session.quiz.quiz_id,
            course_id=session.quiz.course_id,
            module_id=session.quiz.module_id,
            overall_score=overall_score,
            mastery_by_concept=progress.mastery_by_concept,
            wrong_concepts=progress.wrong_concepts,
            results=results,
        )

    def _record_question_activity(
        self,
        *,
        user_id: str,
        quiz_id: str,
        question: QuizQuestion,
        key: StoredQuestionKey,
        result: QuestionGradeResult,
    ) -> None:
        if self.activity_store is None:
            return

        selected_answer = result.submitted_option_id or result.submitted_answer
        correct_answer = result.correct_option_id or result.correct_answer
        course_id = key.course_id or question.course_id or ""
        module_id = key.module_id or question.module_id
        material_id = key.material_id or question.material_id
        section_id = key.section_id or question.section_id
        concept_id = key.concept_id or question.concept_id

        self.activity_store.record_question_attempt(
            QuestionAttemptCreate(
                user_id=user_id,
                quiz_id=quiz_id,
                question_id=question.question_id,
                course_id=course_id,
                module_id=module_id,
                material_id=material_id,
                section_id=section_id,
                concept_id=concept_id,
                selected_answer=selected_answer,
                correct_answer=correct_answer,
                is_correct=result.is_correct,
                question_type=question.question_type.value,
                difficulty=key.difficulty,
            )
        )
        self.activity_store.record_event(
            ActivityEventCreate(
                user_id=user_id,
                course_id=course_id,
                module_id=module_id,
                material_id=material_id,
                section_id=section_id,
                concept_id=concept_id,
                quiz_id=quiz_id,
                question_id=question.question_id,
                question_type=question.question_type.value,
                difficulty=key.difficulty,
                event_type=ActivityEventType.QUESTION_SUBMITTED,
                metadata_json={
                    "score": result.score,
                    "concept": result.concept,
                    "submitted_answer": result.submitted_answer,
                    "correct_answer": result.correct_answer,
                },
            )
        )
        if not result.is_correct:
            self.activity_store.record_event(
                ActivityEventCreate(
                    user_id=user_id,
                    course_id=course_id,
                    module_id=module_id,
                    material_id=material_id,
                    section_id=section_id,
                    concept_id=concept_id,
                    quiz_id=quiz_id,
                    question_id=question.question_id,
                    question_type=question.question_type.value,
                    difficulty=key.difficulty,
                    event_type=ActivityEventType.MISSED_QUESTION_SAVED,
                    metadata_json={
                        "concept": result.concept,
                        "source_page": key.source_page or question.source_page,
                    },
                )
            )

    def _record_quiz_completed_activity(
        self,
        *,
        user_id: str,
        quiz: QuizBundle,
        overall_score: float,
        results: list[QuestionGradeResult],
    ) -> None:
        if self.activity_store is None:
            return
        self.activity_store.record_event(
            ActivityEventCreate(
                user_id=user_id,
                course_id=quiz.course_id,
                module_id=quiz.module_id,
                quiz_id=quiz.quiz_id,
                event_type=ActivityEventType.QUIZ_COMPLETED,
                metadata_json={
                    "overall_score": overall_score,
                    "question_count": len(results),
                    "wrong_question_count": sum(1 for result in results if not result.is_correct),
                },
            )
        )

    def generate_remediation(self, request: RemediationRequest) -> RemediationResponse:
        progress = self.quiz_store.get_mastery_snapshot(request.course_id, request.module_id)
        requested_concepts = (
            request.concepts
            if request.concepts
            else [
                RemediationConceptRequest(
                concept=concept,
                question_count=request.default_question_count,
                )
                for concept in progress.wrong_concepts
            ]
        )
        if not requested_concepts:
            raise MaterialIngestionError("No wrong concepts available for remediation.")

        retry_history = self.quiz_store.list_retry_history(request.course_id, request.module_id)
        prior_prompt_keys = {
            signature
            for entry in retry_history
            for signature in entry.prompt_signatures
        }

        concept_bundles: list[RemediationConceptBundle] = []
        remediation_id = uuid4().hex

        for concept_request in requested_concepts:
            concept = concept_request.concept.strip()
            if not concept:
                continue

            supporting_keys = self._find_supporting_question_keys(
                course_id=request.course_id,
                module_id=request.module_id,
                concept=concept,
            )
            if not supporting_keys:
                continue

            retrieval = self.retrieval_service.query(
                course_id=request.course_id,
                module_id=request.module_id,
                query=concept,
                top_k=self._bounded_retrieval_top_k(
                    request.retrieval_top_k,
                    concept_request.question_count,
                ),
            )
            if not retrieval.hits:
                continue

            questions: list[QuizQuestion] = []
            answer_keys: list[StoredQuestionKey] = []
            duplicate_keys: set[str] = set(prior_prompt_keys)
            desired_count = concept_request.question_count
            source_index = 0

            max_attempts = max(len(retrieval.hits), 1) * max(len(supporting_keys), 1) * 12
            while len(questions) < desired_count and source_index < max_attempts:
                hit = retrieval.hits[source_index % len(retrieval.hits)]
                seed_key = supporting_keys[source_index % len(supporting_keys)]
                question_number = len(questions) + 1
                question_id = f"{remediation_id}-{concept.lower().replace(' ', '-')}-q{question_number}"
                difficulty = seed_key.difficulty
                key_sentence = self._extract_key_sentence(hit.chunk.text, sentence_offset=source_index)
                source_index += 1

                question = self._build_remediation_question(
                    question_id=question_id,
                    concept=concept,
                    seed_key=seed_key,
                    key_sentence=key_sentence,
                    difficulty=difficulty,
                    hit_chunk=hit.chunk,
                    sibling_hits=retrieval.hits,
                    sequence_index=source_index,
                )
                if question is None:
                    continue

                prompt_signature = self._question_signature(question[0])
                if prompt_signature in duplicate_keys:
                    continue

                duplicate_keys.add(prompt_signature)
                remediation_validation = validateQuestion(
                    question[0],
                    source_text=hit.chunk.text,
                    knowledge=extractKnowledge(self._section_from_chunk(hit.chunk)),
                    correct_answer=question[1].correct_answer,
                )
                annotated_question = self._annotate_question_quality(question[0], remediation_validation)
                questions.append(annotated_question)
                answer_keys.append(question[1])

            if questions:
                concept_bundles.append(
                    RemediationConceptBundle(
                        concept=concept,
                        questions=questions,
                    )
                )
                self.quiz_store.save_retry_history(
                    RetryHistoryEntry(
                        remediation_id=remediation_id,
                        course_id=request.course_id,
                        module_id=request.module_id,
                        concept=concept,
                        generated_question_ids=[question.question_id for question in questions],
                        prompt_signatures=[self._question_signature(question) for question in questions],
                        original_question_ids=[key.question_id for key in supporting_keys],
                    )
                )
                remediation_quiz = QuizBundle(
                    quiz_id=f"{remediation_id}-{concept.lower().replace(' ', '-')}",
                    course_id=request.course_id,
                    module_id=request.module_id,
                    query=f"remediation:{concept}",
                    questions=questions,
                )
                self.quiz_store.save_quiz_session(
                    StoredQuizSession(quiz=remediation_quiz, answer_keys=answer_keys)
                )

        if not concept_bundles:
            raise MaterialIngestionError("No remediation questions could be generated.")

        return RemediationResponse(
            remediation_id=remediation_id,
            course_id=request.course_id,
            module_id=request.module_id,
            mastery_by_concept=progress.mastery_by_concept,
            wrong_concepts=progress.wrong_concepts,
            concept_bundles=concept_bundles,
        )

    def _build_demo_question(
        self,
        *,
        question_id: str,
        question_type: QuestionType,
        concept: str,
        difficulty: float,
        hit_chunk: SourceChunk,
        selected_hits: list[RetrievalHit],
        key_sentence: str,
        sequence_index: int,
        knowledge: SectionKnowledge,
    ) -> tuple[QuizQuestion, StoredQuestionKey]:
        question_type = QuestionType.MCQ
        question, generated_answer, correct_option_id = generateExamStyleQuestion(
            knowledge=knowledge,
            question_type=question_type,
            question_id=question_id,
            concept=concept,
            section_title=hit_chunk.section_title,
            difficulty=difficulty,
            citations=[hit_chunk],
            sequence_index=sequence_index,
        )
        key = StoredQuestionKey(
            question_id=question_id,
            question_type=question.question_type,
            concept=question.concept,
            correct_answer=generated_answer,
            correct_option_id=correct_option_id,
            expected_keywords=self._keywords_from_text(generated_answer or key_sentence),
            difficulty=difficulty,
            citations=[hit_chunk],
        )
        return question, key

    def _build_live_question(
        self,
        *,
        question_id: str,
        question_type: QuestionType,
        concept: str,
        difficulty: float,
        hit_chunk: SourceChunk,
        knowledge: SectionKnowledge,
    ) -> tuple[QuizQuestion, StoredQuestionKey]:
        question_type = QuestionType.MCQ
        prompt_type = "multiple-choice"
        options_instruction = """
Return exactly four options with option_id values A, B, C, and D.
Exactly one option must be correct.
Set correct_option_id to the supported option.
"""
        knowledge_json = knowledge.model_dump_json(indent=2)
        source_excerpt = workbookStyleExcerpt(hit_chunk.text, max_chars=3600)
        workbook_context = self._workbook_generation_context(hit_chunk)
        payload = self.structured_llm.generate_model(
            GeneratedQuestionPayload,
            model_name=self.generation_model,
            system_prompt=(
                "You create grounded exam-style study questions from structured course knowledge. "
                "Use only the provided excerpt. Return only valid JSON that matches the required schema exactly. "
                "Do not wrap the response in markdown. Do not include commentary. Do not include extra keys. "
                "Never ask whether a statement is supported by the section. "
                "Do not include office hours, schedules, announcements, or logistics. "
                "When the excerpt contains module quizzes and answer keys, use them as a style guide "
                "for question format, answer type, and explanation style. Generate a fresh question from "
                "different module content or a different learning-objective point; do not copy exact stems, "
                "named scenarios, answer choices, correct answers, or answer-key rationales. "
                "Infer the original module quiz pattern first, such as scenario application, roman statement "
                "evaluation, least-likely selection, or definition distinction, then reuse that pattern with "
                "a different sourced fact. Reject generic grammar-template stems such as 'Which statement "
                "best describes firms?' or choices that are sentence fragments. "
                "Make the stem concise and make all options concise."
            ),
            user_prompt=(
                f"Create one {prompt_type} exam-style question grounded only in this structured knowledge.\n"
                f"Concept: {concept}\n"
                f"Section title: {hit_chunk.section_title}\n"
                f"Target difficulty: {difficulty}\n"
                f"Citation label: {hit_chunk.citation_label}\n"
                f"Workbook RAG context:\n{workbook_context}\n\n"
                f"Structured knowledge JSON:\n{knowledge_json}\n\n"
                f"Source excerpt:\n{source_excerpt}\n\n"
                "Question requirements:\n"
                "- concise stem\n"
                "- no option over 20 words\n"
                "- no copied slide paragraphs\n"
                "- do not copy module quiz questions, answer choices, scenarios, or rationales\n"
                "- if module quiz and answer key text is present, mirror the same answer format, cognitive operation, and reasoning style while testing a different module fact\n"
                "- avoid generic subject-only stems like 'Which statement best describes firms?'\n"
                "- avoid answer fragments, dangling numbers, and options that read like clipped source text\n"
                "- every answer choice must be a concrete module concept, mechanism, tradeoff, or distinction\n"
                "- do not use vague filler such as 'depends on the exposure' unless the source defines the exact dependency\n"
                "- no administrative or schedule content\n"
                "- test concept understanding, distinction, application, or interpretation\n\n"
                "Return a JSON object with keys: prompt, correct_answer, rationale, options, correct_option_id.\n"
                "The field names must match exactly.\n"
                "Return only JSON.\n"
                f"{options_instruction}"
            ),
            temperature=0.2,
            max_tokens=900,
            allow_repair_with_llm=False,
            request_name=f"quiz_question:{question_id}",
            request_context={
                "question_id": question_id,
                "source_id": hit_chunk.source_id,
                "section_title": hit_chunk.section_title,
                "citation_label": hit_chunk.citation_label,
            },
        )
        options = [
            QuizQuestionOption(
                option_id=option.option_id.strip().upper(),
                text=sanitizeOptionText(option.text),
            )
            for option in payload.options
        ]
        normalized_correct_option_id = payload.correct_option_id.strip().upper() if payload.correct_option_id else None
        if len(options) != 4 or normalized_correct_option_id not in {option.option_id for option in options}:
            raise LLMProviderError(
                "The live provider returned an invalid multiple-choice question payload."
            )
        if len({self._normalize_text(option.text) for option in options}) != 4:
            raise LLMProviderError(
                "The live provider returned duplicate or malformed answer choices."
            )

        question = QuizQuestion(
            question_id=question_id,
            question_type=question_type,
            concept=cleanSectionDisplayTitle(concept),
            section_title=cleanSectionDisplayTitle(hit_chunk.section_title),
            difficulty=difficulty,
            prompt=sanitizeQuestionText(payload.prompt),
            options=options,
            citations=[hit_chunk],
            rationale=sanitizeExplanationText(payload.rationale),
        )
        key = StoredQuestionKey(
            question_id=question_id,
            question_type=question_type,
            concept=cleanSectionDisplayTitle(knowledge.concepts[0].name if knowledge.concepts else concept),
            correct_answer=sanitizeOptionText(payload.correct_answer),
            correct_option_id=normalized_correct_option_id,
            expected_keywords=self._keywords_from_text(sanitizeOptionText(payload.correct_answer)),
            difficulty=difficulty,
            citations=[hit_chunk],
        )
        return question, key

    def _workbook_generation_context(self, hit_chunk: SourceChunk) -> str:
        if not hasWorkbookModuleQuiz(hit_chunk.text) and not getattr(hit_chunk, "workbook_block_type", None):
            return "No original module quiz context was detected for this source chunk."

        learning_outcomes = list(getattr(hit_chunk, "learning_outcome_ids", []) or [])
        if not learning_outcomes:
            learning_outcomes = self._learning_outcomes_from_text(hit_chunk.text)
        style_profiles = list(getattr(hit_chunk, "module_quiz_style_profiles", []) or [])
        if not style_profiles:
            style_profiles = workbookStyleProfiles(hit_chunk.text)
        quiz_numbers = list(getattr(hit_chunk, "module_quiz_question_numbers", []) or [])
        answer_numbers = list(getattr(hit_chunk, "module_quiz_answer_numbers", []) or [])

        context_lines = [
            "Original module quiz and answer key are source exemplars, not reusable question text.",
            f"Workbook block type: {getattr(hit_chunk, 'workbook_block_type', None) or 'full_module'}",
            f"Workbook module number: {getattr(hit_chunk, 'workbook_module_number', None) or 'detected_from_section'}",
            f"Linked learning outcomes: {', '.join(learning_outcomes) if learning_outcomes else 'not explicit'}",
            f"Detected quiz style profiles: {', '.join(style_profiles) if style_profiles else 'not explicit'}",
            f"Original quiz question numbers: {', '.join(str(number) for number in quiz_numbers) if quiz_numbers else 'not explicit'}",
            f"Original answer-key numbers: {', '.join(str(number) for number in answer_numbers) if answer_numbers else 'not explicit'}",
            "Generation rule: preserve the original answer format and cognitive operation while testing a different sourced LO fact.",
            "Repetition rule: do not reuse original stems, scenarios, answer choices, correct answers, or answer-key rationales.",
        ]
        return "\n".join(context_lines)

    def _learning_outcomes_from_text(self, text: str) -> list[str]:
        learning_outcomes: list[str] = []
        for match in LO_DISTRIBUTION_RE.finditer(text):
            value = f"LO {int(match.group('number'))}.{match.group('letter').lower()}"
            if value not in learning_outcomes:
                learning_outcomes.append(value)
        return learning_outcomes

    def _build_mcq_explanation(
        self,
        question: QuizQuestion,
        key: StoredQuestionKey,
        submitted_option_id: str | None,
        submitted_answer: str,
        is_correct: bool,
        allow_live_llm: bool,
    ) -> str:
        if not self.structured_llm.available() or not allow_live_llm:
            return self._build_fallback_mcq_explanation(
                key=key,
                submitted_option_id=submitted_option_id,
                submitted_answer=submitted_answer,
                is_correct=is_correct,
            )

        try:
            payload = self.structured_llm.generate_model(
                GeneratedExplanationPayload,
                model_name=self.explanation_model,
                system_prompt=(
                    "You explain quiz grading using only the provided citation. "
                    "Return only valid JSON with the exact required keys. "
                    "Do not wrap in markdown or add commentary."
                ),
                user_prompt=(
                    f"Question: {question.prompt}\n"
                    f"Options: {[f'{option.option_id}. {option.text}' for option in question.options]}\n"
                    f"Submitted answer: {submitted_answer or 'No answer provided'}\n"
                    f"Submitted option id: {submitted_option_id or 'none'}\n"
                    f"Correct answer: {key.correct_answer}\n"
                    f"Correct option id: {key.correct_option_id or 'none'}\n"
                    f"Was the submission correct? {is_correct}\n"
                    f"Citation label: {key.citations[0].citation_label}\n"
                    f"Citation excerpt:\n{key.citations[0].text}\n\n"
                    "Return JSON with a single key: explanation.\n"
                    "Return only JSON.\n"
                    "If the submission is correct, explain why the chosen answer is supported by the citation.\n"
                    "If the submission is incorrect, explain briefly why the submitted answer is not supported, "
                    "why the correct answer is right, and why the other options are weaker."
                ),
                temperature=0.0,
                max_tokens=250,
                allow_repair_with_llm=False,
                request_name=f"quiz_explanation:{question.question_id}",
                request_context={
                    "question_id": question.question_id,
                    "source_id": key.citations[0].source_id if key.citations else "unknown",
                    "section_title": key.citations[0].section_title if key.citations else key.concept,
                    "citation_label": key.citations[0].citation_label if key.citations else "unknown",
                },
            )
            return sanitizeExplanationText(payload.explanation)
        except LLMProviderError as exc:
            logger.warning(
                "Live MCQ explanation generation failed; falling back to deterministic explanation. "
                "question_id=%s concept=%s error=%s",
                question.question_id,
                key.concept,
                str(exc),
            )
            return self._build_fallback_mcq_explanation(
                key=key,
                submitted_option_id=submitted_option_id,
                submitted_answer=submitted_answer,
                is_correct=is_correct,
            )

    def _build_live_short_answer_grade(
        self,
        question: QuizQuestion,
        key: StoredQuestionKey,
        submitted_answer: str,
    ) -> GeneratedShortAnswerGradePayload:
        return self.structured_llm.generate_model(
            GeneratedShortAnswerGradePayload,
            model_name=self.explanation_model,
            system_prompt=(
                "You grade short-answer questions using only the provided citation. "
                "Return only valid JSON with the exact required keys. "
                "Do not wrap in markdown or add commentary."
            ),
            user_prompt=(
                f"Question: {question.prompt}\n"
                f"Submitted answer: {submitted_answer or 'No answer provided'}\n"
                f"Expected answer: {key.correct_answer}\n"
                f"Citation label: {key.citations[0].citation_label}\n"
                f"Citation excerpt:\n{key.citations[0].text}\n\n"
                "Return JSON with keys: is_correct, score, explanation.\n"
                "Return only JSON.\n"
                "Use score 1.0 for correct answers and 0.0 for incorrect answers.\n"
                "Always include a concise explanation. For correct answers, explain why they are supported. For incorrect answers, explain why they miss the citation and what the correct answer should cover."
            ),
            temperature=0.0,
            max_tokens=300,
            allow_repair_with_llm=False,
            request_name=f"quiz_short_answer_grade:{question.question_id}",
            request_context={
                "question_id": question.question_id,
                "source_id": key.citations[0].source_id if key.citations else "unknown",
                "section_title": key.citations[0].section_title if key.citations else key.concept,
                "citation_label": key.citations[0].citation_label if key.citations else "unknown",
            },
        )

    def _select_hits(
        self,
        hits: list[RetrievalHit],
        question_count: int,
        *,
        strict_testable: bool = False,
    ) -> list[RetrievalHit]:
        selected: list[RetrievalHit] = []
        seen_sections: set[str] = set()
        for hit in hits:
            source_section = self._section_from_chunk(hit.chunk)
            content_label = classifyChunk(source_section)
            if strict_testable and content_label != ContentLabel.TESTABLE_CONTENT:
                continue
            if content_label == ContentLabel.ADMINISTRATIVE_CONTENT:
                continue
            section_key = self._distribution_key_for_hit(hit)
            if section_key in seen_sections:
                continue
            selected.append(hit)
            seen_sections.add(section_key)
            if len(selected) >= question_count:
                break
        if not selected:
            return []
        reuse_index = 0
        while len(selected) < question_count:
            selected.append(selected[reuse_index % len(selected)])
            reuse_index += 1
        return selected

    def _distribution_key_for_hit(self, hit: RetrievalHit) -> str:
        chunk = hit.chunk
        base_key = f"{chunk.file_name}:{chunk.section_title}"
        lo_code = self._extract_lo_code_for_distribution(chunk)
        if lo_code:
            return f"{base_key}:{lo_code}"
        return base_key

    def _extract_lo_code_for_distribution(self, chunk: SourceChunk) -> str | None:
        haystack_parts = [
            getattr(chunk, "section_title", "") or "",
            getattr(chunk, "citation_label", "") or "",
            (getattr(chunk, "text", "") or "")[:1200],
        ]
        match = LO_DISTRIBUTION_RE.search("\n".join(haystack_parts))
        if not match:
            return None
        return f"LO {int(match.group('number'))}.{match.group('letter').lower()}"

    def _extract_key_sentence(self, text: str, sentence_offset: int = 0) -> str:
        sentences = self._extract_sentences(text)
        if not sentences:
            return text.strip()
        selected_sentence = sentences[sentence_offset % len(sentences)]
        return f"{selected_sentence}."

    def _extract_sentences(self, text: str) -> list[str]:
        return [
            sentence.strip()
            for sentence in text.replace("\n", " ").split(".")
            if sentence.strip()
        ]

    def _build_distractor_texts(self, hits: list[RetrievalHit], correct_text: str) -> list[str]:
        distractors: list[str] = []
        for hit in hits:
            sentence = self._extract_key_sentence(hit.chunk.text)
            if sentence == correct_text:
                continue
            if sentence not in distractors:
                distractors.append(sentence)
            if len(distractors) >= 3:
                break

        fallback_candidates = [
            "The material focuses on a different concept than the cited section.",
            "The passage says the concept is optional and not central to the section.",
            "The section states there is no relationship between the main concept and the result.",
        ]
        for fallback in fallback_candidates:
            if len(distractors) >= 3:
                break
            if fallback not in distractors:
                distractors.append(fallback)
        return distractors[:3]

    def _keywords_from_text(self, text: str) -> list[str]:
        tokens = [token for token in self._normalize_text(text).split(" ") if token]
        unique_tokens: list[str] = []
        for token in tokens:
            if len(token) < 4:
                continue
            if token not in unique_tokens:
                unique_tokens.append(token)
        return unique_tokens[:6]

    def _attach_source_metadata(
        self,
        *,
        question: QuizQuestion,
        answer_key: StoredQuestionKey,
        quiz_id: str,
        request: QuizGenerationRequest,
        hit_chunk: SourceChunk,
        sequence_index: int,
        created_at: str,
    ) -> tuple[QuizQuestion, StoredQuestionKey]:
        source_page = hit_chunk.locator.page_number
        source_evidence = self._bounded_source_evidence(hit_chunk.text)
        question_style = request.question_styles[(sequence_index - 1) % len(request.question_styles)]
        explanation = self._source_referenced_explanation(
            question=question,
            answer_key=answer_key,
            hit_chunk=hit_chunk,
            source_evidence=source_evidence,
        )
        question = question.model_copy(
            update={
                "id": question.question_id,
                "quiz_id": quiz_id,
                "course_id": request.course_id,
                "module_id": request.module_id or hit_chunk.module_id,
                "material_id": request.material_id or hit_chunk.material_id,
                "section_id": request.section_id or hit_chunk.source_id,
                "concept_id": request.concept_id,
                "source_page": source_page,
                "question_style": question_style,
                "question_text": question.prompt,
                "answer_choices_json": question.options,
                "correct_answer": answer_key.correct_answer,
                "explanation": explanation,
                "source_evidence": source_evidence,
                "created_at": created_at,
            }
        )
        answer_key = answer_key.model_copy(
            update={
                "course_id": request.course_id,
                "module_id": request.module_id or hit_chunk.module_id,
                "material_id": request.material_id or hit_chunk.material_id,
                "section_id": request.section_id or hit_chunk.source_id,
                "concept_id": request.concept_id,
                "source_page": source_page,
                "source_evidence": source_evidence,
            }
        )
        return question, answer_key

    def _source_referenced_explanation(
        self,
        *,
        question: QuizQuestion,
        answer_key: StoredQuestionKey,
        hit_chunk: SourceChunk,
        source_evidence: str,
    ) -> str:
        correct_answer = sanitizeExplanationText(answer_key.correct_answer)
        correct_prefix = (
            f"Correct answer: {answer_key.correct_option_id}. {correct_answer}."
            if answer_key.correct_option_id
            else f"Correct answer: {correct_answer}."
        )
        rationale = sanitizeExplanationText(question.rationale or "")
        citation = hit_chunk.citation_label.strip()
        if citation and not citation.endswith("."):
            citation = f"{citation}."
        evidence = sanitizeExplanationText(source_evidence)
        parts = [
            correct_prefix,
            rationale,
            f"Book reference: {citation}" if citation else "",
            f"Source evidence: {evidence}" if evidence else "",
        ]
        cleaned_parts = [part for part in parts if part]
        return " ".join(dict.fromkeys(cleaned_parts))

    def _bounded_source_evidence(self, text: str, *, max_words: int = 90) -> str:
        words = " ".join(text.split()).split(" ")
        if len(words) <= max_words:
            return " ".join(words)
        return " ".join(words[:max_words]).rstrip(" .,;:") + "..."

    def _grade_question(
        self,
        question: QuizQuestion,
        key: StoredQuestionKey,
        submission: QuizSubmissionAnswer | None,
        allow_live_llm: bool,
    ) -> QuestionGradeResult:
        submitted_option_id = submission.selected_option_id if submission is not None else None
        submitted_answer = self._submitted_answer_text(question, submission)
        if question.question_type == QuestionType.MCQ:
            is_correct = submission is not None and submission.selected_option_id == key.correct_option_id
            explanation = self._build_mcq_explanation(
                question,
                key,
                submitted_option_id,
                submitted_answer,
                is_correct,
                allow_live_llm,
            )
            score = 1.0 if is_correct else 0.0
        else:
            if self.structured_llm.available() and allow_live_llm:
                try:
                    grade_payload = self._build_live_short_answer_grade(question, key, submitted_answer)
                    is_correct = grade_payload.is_correct
                    score = grade_payload.score
                    explanation = sanitizeExplanationText(grade_payload.explanation)
                except LLMProviderError as exc:
                    logger.warning(
                        "Live short-answer grading failed; falling back to keyword grading. "
                        "question_id=%s concept=%s error=%s",
                        question.question_id,
                        key.concept,
                        str(exc),
                    )
                    overlap_score = self._keyword_overlap_ratio(
                        submitted_answer,
                        key.expected_keywords,
                    )
                    is_correct = overlap_score >= 0.5
                    score = 1.0 if is_correct else 0.0
                    explanation = self._build_fallback_short_answer_explanation(
                        key=key,
                        submitted_answer=submitted_answer,
                        is_correct=is_correct,
                    )
            else:
                overlap_score = self._keyword_overlap_ratio(
                    submitted_answer,
                    key.expected_keywords,
                )
                is_correct = overlap_score >= 0.5
                score = 1.0 if is_correct else 0.0
                explanation = self._build_fallback_short_answer_explanation(
                    key=key,
                    submitted_answer=submitted_answer,
                    is_correct=is_correct,
                )
        return QuestionGradeResult(
            question_id=question.question_id,
            question_type=question.question_type,
            concept=key.concept,
            is_correct=is_correct,
            grading_label="correct" if is_correct else "incorrect",
            score=score,
            submitted_option_id=submitted_option_id,
            submitted_answer=submitted_answer,
            correct_option_id=key.correct_option_id,
            correct_answer=key.correct_answer,
            explanation=sanitizeExplanationText(explanation),
            citations=key.citations,
        )

    def _submitted_answer_text(
        self,
        question: QuizQuestion,
        submission: QuizSubmissionAnswer | None,
    ) -> str:
        if submission is None:
            return ""
        if question.question_type == QuestionType.MCQ:
            selected_option_id = submission.selected_option_id or ""
            for option in question.options:
                if option.option_id == selected_option_id:
                    return option.text
            return selected_option_id
        return (submission.answer_text or "").strip()

    def _build_fallback_mcq_explanation(
        self,
        *,
        key: StoredQuestionKey,
        submitted_option_id: str | None,
        submitted_answer: str,
        is_correct: bool,
    ) -> str:
        if is_correct:
            return sanitizeExplanationText(
                f"Correct. The answer matches the core idea: {key.correct_answer}."
            )
        chosen = submitted_answer or submitted_option_id or "No answer provided"
        return sanitizeExplanationText(
            f'Incorrect. "{chosen}" does not match this section. '
            f"The correct answer is {key.correct_answer}."
        )

    def _build_fallback_short_answer_explanation(
        self,
        *,
        key: StoredQuestionKey,
        submitted_answer: str,
        is_correct: bool,
    ) -> str:
        if is_correct:
            return sanitizeExplanationText(
                f"Correct. The response matches the expected idea: {key.correct_answer}"
            )
        return sanitizeExplanationText(
            f"Incorrect. The response does not match the expected idea. Correct answer: {key.correct_answer}"
        )

    def _keyword_overlap_ratio(self, submitted_answer: str, expected_keywords: list[str]) -> float:
        normalized_answer = self._normalize_text(submitted_answer)
        if not normalized_answer or not expected_keywords:
            return 0.0
        hits = sum(1 for keyword in expected_keywords if keyword in normalized_answer)
        return hits / len(expected_keywords)

    def _normalize_text(self, text: str) -> str:
        cleaned = text.lower()
        for char in [".", ",", ";", ":", "!", "?", "(", ")", '"', "'"]:
            cleaned = cleaned.replace(char, " ")
        return " ".join(cleaned.split())

    def _hydrate_full_source_chunk(self, chunk: SourceChunk) -> SourceChunk:
        document = self.material_store.get_parsed_document(chunk.material_id)
        if document is None:
            return chunk
        for section in document.sections:
            if section.source_id != chunk.source_id:
                continue
            if not hasWorkbookModuleQuiz(section.text):
                return chunk
            return chunk.model_copy(
                update={
                    "section_title": section.section_title,
                    "text": section.text,
                    "page_end": section.page_end,
                    "token_count": len(section.text.split()),
                    "section_kind": section.section_kind,
                    "content_label": section.content_label,
                    "priority_score": section.priority_score,
                    "is_default": section.is_default,
                    "locator": section.locator,
                    "citation_label": section.citation_label,
                }
            )
        return chunk

    def _section_from_chunk(self, chunk: SourceChunk) -> SourceSection:
        return SourceSection(
            source_id=chunk.source_id,
            material_id=chunk.material_id,
            course_id=chunk.course_id,
            module_id=chunk.module_id,
            file_name=chunk.file_name,
            content_type=chunk.content_type,
            section_title=chunk.section_title,
            text=chunk.text,
            section_kind=chunk.section_kind,
            content_label=chunk.content_label,
            priority_score=chunk.priority_score,
            is_default=chunk.is_default,
            locator=SourceLocator.model_validate(chunk.locator.model_dump()),
            citation_label=chunk.citation_label,
        )

    def _estimate_difficulty(self, text: str) -> float:
        token_count = max(len(self._normalize_text(text).split(" ")), 1)
        return round(min(1.0, 0.3 + (token_count / 40.0)), 2)

    def _find_supporting_question_keys(
        self,
        *,
        course_id: str,
        module_id: str | None,
        concept: str,
    ) -> list[StoredQuestionKey]:
        progress = self.quiz_store.get_mastery_snapshot(course_id, module_id)
        if concept not in progress.wrong_concepts:
            return []

        supporting_keys: list[StoredQuestionKey] = []
        for quiz_file in self.quiz_store.list_quiz_sessions_by_course(course_id, module_id):
            for answer_key in quiz_file.answer_keys:
                if answer_key.concept == concept:
                    supporting_keys.append(answer_key)
        return supporting_keys

    def _build_remediation_question(
        self,
        *,
        question_id: str,
        concept: str,
        seed_key: StoredQuestionKey,
        key_sentence: str,
        difficulty: float,
        hit_chunk: SourceChunk,
        sibling_hits: list[RetrievalHit],
        sequence_index: int,
    ) -> tuple[QuizQuestion, StoredQuestionKey] | None:
        if self.structured_llm.available():
            return self._build_live_question(
                question_id=question_id,
                question_type=QuestionType.MCQ,
                concept=concept,
                difficulty=difficulty,
                hit_chunk=hit_chunk,
                knowledge=extractKnowledge(self._section_from_chunk(hit_chunk)),
            )

        focus_phrase = key_sentence.rstrip(".")
        mcq_templates = [
            'Which statement best reinforces the concept "{concept}" given this focus: "{focus}"?',
            'Select the grounded statement that matches the concept "{concept}" around "{focus}".',
            'Which option stays closest to the retrieved material for "{concept}" and "{focus}"?',
            'Choose the statement that best matches the cited idea "{focus}" for "{concept}".',
        ]
        distractor_texts = self._build_distractor_texts(sibling_hits, key_sentence)
        if len(distractor_texts) < 3:
            return None
        insertion_index = (sequence_index - 1) % 4
        option_texts = distractor_texts[:]
        option_texts.insert(insertion_index, key_sentence)
        option_texts = option_texts[:4]
        options = [
            QuizQuestionOption(option_id=option_id, text=option_text)
            for option_id, option_text in zip(["A", "B", "C", "D"], option_texts, strict=True)
        ]
        correct_option = options[insertion_index]
        question = QuizQuestion(
            question_id=question_id,
            question_type=QuestionType.MCQ,
            concept=concept,
            section_title=hit_chunk.section_title,
            difficulty=difficulty,
            prompt=mcq_templates[(sequence_index - 1) % len(mcq_templates)].format(
                concept=concept,
                focus=focus_phrase,
            ),
            options=options,
            citations=[hit_chunk],
            rationale="Remediation question generated from a missed concept.",
        )
        key = StoredQuestionKey(
            question_id=question_id,
            question_type=QuestionType.MCQ,
            concept=concept,
            correct_answer=key_sentence,
            correct_option_id=correct_option.option_id,
            expected_keywords=self._keywords_from_text(key_sentence),
            difficulty=difficulty,
            citations=[hit_chunk],
        )
        return question, key

    def _annotate_question_quality(
        self,
        question: QuizQuestion,
        validation: QuestionValidationResult,
    ) -> QuizQuestion:
        try:
            quality = self.question_quality_service.score_generated_question(question)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Question quality scoring failed; continuing without ML score. "
                "question_id=%s concept=%s error=%s",
                question.question_id,
                question.concept,
                str(exc),
            )
            question.quality_validation = None
            return question

        raw_ml_score = quality.score
        combined_score = round((quality.score + validation.score) / 2.0, 4)
        if validation.accepted and quality.model_source != "pytorch_checkpoint":
            combined_score = max(0.55, combined_score)
        quality.score = combined_score
        quality.confidence = round(min(1.0, (quality.confidence + validation.score) / 2.0), 4)
        torch_gate_passed = quality.model_source != "pytorch_checkpoint" or raw_ml_score >= 0.45
        quality.notes = [*quality.notes, *validation.notes]
        has_serious_quality_note = any(
            fragment in " ".join(quality.notes).lower()
            for fragment in SERIOUS_QUALITY_NOTE_FRAGMENTS
        )
        quality.accepted_for_delivery = (
            torch_gate_passed
            and not has_serious_quality_note
            and (
                validation.accepted and combined_score >= 0.5
                or combined_score >= 0.7
            )
        )
        if not torch_gate_passed:
            quality.label = QuestionQualityLabel.LOW_QUALITY
        elif combined_score >= 0.7:
            quality.label = QuestionQualityLabel.HIGH_QUALITY
        elif combined_score >= 0.45:
            quality.label = QuestionQualityLabel.NEEDS_REVIEW
        else:
            quality.label = QuestionQualityLabel.LOW_QUALITY
        question.quality_validation = quality
        return question

    def _question_signature(self, question: QuizQuestion) -> str:
        return self._normalize_text(
            f"{question.concept}|{question.question_type}|{question.prompt}|{question.difficulty}"
        )
