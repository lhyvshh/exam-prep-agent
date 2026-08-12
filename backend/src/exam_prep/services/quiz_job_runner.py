import logging
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime

from exam_prep.core.config import Settings
from exam_prep.core.exceptions import MaterialIngestionError
from exam_prep.llm.registry import LLMClientRegistry
from exam_prep.ml.inference import QuestionQualityInferenceService
from exam_prep.repositories.activity_store import ActivityStore
from exam_prep.repositories.config_store import ConfigStore
from exam_prep.repositories.material_store import MaterialStore
from exam_prep.repositories.quiz_job_store import QuizJobStore
from exam_prep.repositories.quiz_store import QuizStore
from exam_prep.repositories.vector_store import VectorStore
from exam_prep.schemas.activity import ActivityEventCreate, ActivityEventType
from exam_prep.schemas.quiz import (
    QuizBundle,
    QuizGenerationJobStatus,
    QuizGenerationRequest,
    QuizGenerationResultItem,
    StoredQuizSession,
)
from exam_prep.services.config_service import ConfigService
from exam_prep.services.quiz_service import QuizService, QuizUniquenessState

logger = logging.getLogger(__name__)


class QuizJobRunner:
    def __init__(
        self,
        *,
        settings: Settings,
        config_store: ConfigStore,
        job_store: QuizJobStore,
        quiz_store: QuizStore,
        material_store: MaterialStore,
        vector_store: VectorStore,
        question_quality_service: QuestionQualityInferenceService,
        llm_client_registry: LLMClientRegistry,
        activity_store: ActivityStore | None = None,
    ) -> None:
        self.settings = settings
        self.config_store = config_store
        self.job_store = job_store
        self.quiz_store = quiz_store
        self.material_store = material_store
        self.vector_store = vector_store
        self.question_quality_service = question_quality_service
        self.llm_client_registry = llm_client_registry
        self.activity_store = activity_store
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="quiz-job")
        self._futures: dict[str, Future[None]] = {}
        self._lock = threading.Lock()

    def enqueue(self, job_id: str) -> None:
        with self._lock:
            existing = self._futures.get(job_id)
            if existing is not None and not existing.done():
                return
            future = self.executor.submit(self._run_job, job_id)
            self._futures[job_id] = future
            future.add_done_callback(lambda _: self._clear_future(job_id))

    def cancel(self, job_id: str) -> QuizGenerationJobStatus | None:
        return self.job_store.request_cancel(job_id)

    def resume_incomplete_jobs(self) -> None:
        for job_id in self.job_store.list_incomplete_jobs():
            self.enqueue(job_id)

    def shutdown(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=False)

    def _clear_future(self, job_id: str) -> None:
        with self._lock:
            self._futures.pop(job_id, None)

    def _run_job(self, job_id: str) -> None:
        try:
            job = self.job_store.get_job(job_id)
            if job is None:
                return

            logger.info(
                "Quiz generation job start job_id=%s status=%s dedupe_key=%s",
                job.job_id,
                job.status.value,
                job.dedupe_key,
            )
            if self.job_store.is_cancel_requested(job_id):
                self.job_store.mark_completed(
                    job_id,
                    status=QuizGenerationJobStatus.CANCELLED,
                    failure_reason="Quiz generation was cancelled before execution.",
                )
                return
            self.job_store.mark_running(job_id)

            runtime_config = ConfigService().get_runtime_config(self.settings, self.config_store).config
            llm_client = self.llm_client_registry.get_or_create_for_profile(
                runtime_config,
                profile="quiz_generation",
            )
            quiz_service = QuizService(
                material_store=self.material_store,
                vector_store=self.vector_store,
                quiz_store=self.quiz_store,
                question_quality_service=self.question_quality_service,
                runtime_config=runtime_config,
                settings=self.settings,
                llm_client=llm_client,
                activity_store=self.activity_store,
            )

            plan = quiz_service.prepare_generation_plan(job.request_payload)
        except MaterialIngestionError as exc:
            logger.warning("Quiz generation job failed before execution job_id=%s error=%s", job_id, str(exc))
            self.job_store.increment_error_count(job_id, failure_reason=str(exc))
            self.job_store.mark_completed(
                job_id,
                status=QuizGenerationJobStatus.FAILED,
                failure_reason=str(exc),
            )
            return
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected quiz generation job setup failure job_id=%s", job_id)
            self.job_store.increment_error_count(job_id, failure_reason=str(exc))
            self.job_store.mark_completed(
                job_id,
                status=QuizGenerationJobStatus.FAILED,
                failure_reason="Unexpected quiz generation job failure.",
            )
            return

        question_results: list[QuizGenerationResultItem] = []
        answer_keys = []
        completed_questions = 0
        fallback_questions = 0
        uniqueness = QuizUniquenessState(
            prompt_signatures=set(),
            correct_answer_signatures=set(),
            option_set_signatures=set(),
        )
        budget_seconds = self._job_budget_seconds(job.request_payload.question_count)
        started = time.monotonic()
        final_status = QuizGenerationJobStatus.COMPLETED
        failure_reason: str | None = None

        try:
            for index, hit in enumerate(plan.selected_hits, start=1):
                if self.job_store.is_cancel_requested(job_id):
                    final_status = QuizGenerationJobStatus.CANCELLED
                    failure_reason = "Quiz generation was cancelled."
                    break

                elapsed_seconds = time.monotonic() - started
                force_fallback = (
                    elapsed_seconds >= budget_seconds
                    or self._should_force_fast_section_generation(job.request_payload)
                )
                if force_fallback and final_status == QuizGenerationJobStatus.COMPLETED:
                    final_status = QuizGenerationJobStatus.PARTIAL
                    failure_reason = (
                        "Whole-job generation budget was exceeded. Remaining questions used deterministic fallback."
                    )
                    logger.warning(
                        "Quiz generation job exceeded budget job_id=%s budget_seconds=%s elapsed_seconds=%.1f",
                        job_id,
                        budget_seconds,
                        elapsed_seconds,
                    )

                logger.info(
                    "Quiz generation question start job_id=%s question_index=%s/%s force_fallback=%s",
                    job_id,
                    index,
                    len(plan.selected_hits),
                    force_fallback,
                )
                outcome = quiz_service.generate_deliverable_question_for_hit(
                    quiz_id=job_id,
                    request=job.request_payload,
                    hit=hit,
                    selected_hits=plan.selected_hits,
                    sequence_index=index,
                    uniqueness=uniqueness,
                    force_fallback=force_fallback,
                )
                if outcome.attempt is not None:
                    self.job_store.append_attempt(outcome.attempt)
                    if outcome.attempt.error_type is not None:
                        self.job_store.increment_error_count(job_id)

                if outcome.generation_mode.value == "fallback":
                    fallback_questions += 1

                completed_questions += 1
                answer_keys.append(outcome.answer_key)
                result_item = QuizGenerationResultItem(
                    job_id=job_id,
                    question_id=outcome.question.question_id,
                    ordinal=index,
                    source_id=hit.chunk.source_id,
                    section_title=hit.chunk.section_title,
                    generation_mode=outcome.generation_mode,
                    question=outcome.question,
                    answer_key=outcome.answer_key,
                    created_at=datetime.now(UTC).isoformat(),
                )
                question_results.append(result_item)
                self.job_store.append_result(result_item)
                self.job_store.update_progress(
                    job_id,
                    completed_questions=completed_questions,
                    fallback_questions=fallback_questions,
                    current_question_index=index,
                )
                logger.info(
                    "Quiz generation question finish job_id=%s question_id=%s mode=%s completed=%s/%s",
                    job_id,
                    outcome.question.question_id,
                    outcome.generation_mode.value,
                    completed_questions,
                    len(plan.selected_hits),
                )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected quiz generation job execution failure job_id=%s", job_id)
            self.job_store.increment_error_count(job_id, failure_reason=str(exc))
            self.job_store.mark_completed(
                job_id,
                status=QuizGenerationJobStatus.FAILED,
                failure_reason="Unexpected quiz generation job failure.",
            )
            return

        if question_results and final_status in {
            QuizGenerationJobStatus.COMPLETED,
            QuizGenerationJobStatus.PARTIAL,
        }:
            quiz = QuizBundle(
                quiz_id=job_id,
                course_id=job.request_payload.course_id,
                module_id=job.request_payload.module_id,
                query=job.request_payload.query.strip(),
                created_at=datetime.now(UTC).isoformat(),
                questions=[item.question for item in question_results],
            )
            self.quiz_store.save_quiz_session(
                StoredQuizSession(
                    quiz=quiz,
                    answer_keys=answer_keys,
                )
            )
            self._record_quiz_generated(
                request=job.request_payload,
                quiz=quiz,
                completed_questions=completed_questions,
                fallback_questions=fallback_questions,
                status=final_status,
            )

        self.job_store.mark_completed(
            job_id,
            status=final_status,
            failure_reason=failure_reason,
        )
        logger.info(
            "Quiz generation job finished job_id=%s status=%s duration_ms=%.1f completed_questions=%s "
            "fallback_questions=%s failure_reason=%s",
            job_id,
            final_status.value,
            (time.monotonic() - started) * 1000.0,
            completed_questions,
            fallback_questions,
            failure_reason,
        )

    def _job_budget_seconds(self, question_count: int) -> int:
        if question_count <= 5:
            return 90
        return 120

    def _should_force_fast_section_generation(self, request: QuizGenerationRequest) -> bool:
        return False

    def _record_quiz_generated(
        self,
        *,
        request: QuizGenerationRequest,
        quiz: QuizBundle,
        completed_questions: int,
        fallback_questions: int,
        status: QuizGenerationJobStatus,
    ) -> None:
        if self.activity_store is None:
            return
        self.activity_store.record_event(
            ActivityEventCreate(
                user_id=request.user_id,
                course_id=request.course_id,
                module_id=request.module_id,
                material_id=request.material_id,
                section_id=request.section_id,
                concept_id=request.concept_id,
                quiz_id=quiz.quiz_id,
                event_type=ActivityEventType.QUIZ_GENERATED,
                metadata_json={
                    "status": status.value,
                    "question_count": len(quiz.questions),
                    "completed_questions": completed_questions,
                    "fallback_questions": fallback_questions,
                    "weak_area_id": request.weak_area_id,
                    "selected_source_ids": request.selected_source_ids,
                },
            )
        )
