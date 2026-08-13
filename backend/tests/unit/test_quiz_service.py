from pathlib import Path

from exam_prep.core.config import Settings
from exam_prep.core.exceptions import LLMProviderError, LLMTransportError
from exam_prep.ingestion.pipeline import IngestionPipeline
from exam_prep.llm.models import LLMResponse
from exam_prep.ml.inference import QuestionQualityInferenceService
from exam_prep.repositories.local.material_store import LocalMaterialStore
from exam_prep.repositories.local.quiz_store import LocalQuizStore
from exam_prep.repositories.local.vector_store import LocalVectorStore
from exam_prep.schemas.config import LLMProvider, UserLLMConfig
from exam_prep.schemas.ml import QuestionQualityLabel, QuestionQualityValidation
from exam_prep.schemas.materials import SourceChunk, SourceLocator
from exam_prep.schemas.quiz import (
    QuestionGenerationMode,
    QuestionType,
    QuizBundle,
    QuizGenerationJobProgress,
    QuizGenerationJobResponse,
    QuizGenerationJobStatus,
    QuizGenerationRequest,
    QuizGenerationResultItem,
    QuizGradeRequest,
    QuizQuestion,
    QuizQuestionOption,
    QuizSubmissionAnswer,
    StoredQuestionKey,
)
from exam_prep.schemas.retrieval import RetrievalHit, RetrievalQueryResponse
from exam_prep.services.quiz_job_runner import QuizJobRunner
from exam_prep.services.quiz_service import GeneratedQuestionOutcome, QuizService
from exam_prep.services.question_pipeline import (
    QuestionValidationResult,
    extractKnowledge,
    validateQuestion,
)


class FailingLLMClient:
    def generate(self, request) -> LLMResponse:
        raise LLMProviderError("Synthetic provider failure for fallback testing.")


class FlakyLLMClient:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, request) -> LLMResponse:
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(
                model_name=request.model_name,
                provider_name="test",
                raw_text=(
                    '{"prompt":"What is the key idea?","correct_answer":"Gradient descent updates '
                    'parameters using the learning rate.","rationale":"Grounded.","options":['
                    '{"option_id":"A","value":"Wrong one"},'
                    '{"option_id":"B","value":"Gradient descent updates parameters using the learning rate."},'
                    '{"option_id":"C","value":"Wrong two"},'
                    '{"option_id":"D","value":"Wrong three"}],'
                    '"correct_option_id":"B"}'
                ),
            )
        raise LLMTransportError("Synthetic timeout after first question.")


class AlternatingLLMClient:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, request) -> LLMResponse:
        self.calls += 1
        if self.calls == 2:
            raise LLMTransportError("Synthetic one-off timeout.")
        prompt = f"What grounded question number {self.calls}?"
        return LLMResponse(
            model_name=request.model_name,
            provider_name="test",
            raw_text=(
                f'{{"prompt":"{prompt}","correct_answer":"Grounded answer {self.calls}",'
                f'"rationale":"Grounded.","options":['
                '{"option_id":"A","text":"Wrong one"},'
                f'{{"option_id":"B","text":"Grounded answer {self.calls}"}},'
                '{"option_id":"C","text":"Wrong two"},'
                '{"option_id":"D","text":"Wrong three"}],'
                '"correct_option_id":"B"}'
            ),
        )


class RepeatedTimeoutLLMClient:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, request) -> LLMResponse:
        self.calls += 1
        raise LLMTransportError(f"Synthetic timeout {self.calls}.")


class CountingLLMClient:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, request) -> LLMResponse:
        self.calls += 1
        raise LLMTransportError("Grading should not call the live provider by default.")


class RejectFirstQualityService(QuestionQualityInferenceService):
    def __init__(self, checkpoint_path: Path) -> None:
        super().__init__(checkpoint_path=checkpoint_path, enable_torch=False)
        self.calls = 0

    def score_generated_question(self, question: QuizQuestion) -> QuestionQualityValidation:
        self.calls += 1
        if self.calls == 1:
            return QuestionQualityValidation(
                score=0.19,
                confidence=0.62,
                label=QuestionQualityLabel.LOW_QUALITY,
                accepted_for_delivery=False,
                model_version="question-quality-test",
                model_source="pytorch_checkpoint",
                notes=["Synthetic low-quality rejection."],
            )
        return QuestionQualityValidation(
            score=0.88,
            confidence=0.76,
            label=QuestionQualityLabel.HIGH_QUALITY,
            accepted_for_delivery=True,
            model_version="question-quality-test",
            model_source="pytorch_checkpoint",
            notes=["Synthetic retry accepted."],
        )


class StaticQualityService(QuestionQualityInferenceService):
    def __init__(
        self,
        checkpoint_path: Path,
        *,
        model_source: str,
        enable_torch: bool = True,
    ) -> None:
        super().__init__(checkpoint_path=checkpoint_path, enable_torch=enable_torch)
        self.model_source = model_source

    def score_generated_question(self, question: QuizQuestion) -> QuestionQualityValidation:
        del question
        return QuestionQualityValidation(
            score=0.88,
            confidence=0.76,
            label=QuestionQualityLabel.HIGH_QUALITY,
            accepted_for_delivery=True,
            model_version="question-quality-test",
            model_source=self.model_source,
            notes=[],
        )


class _ImmediateRegistry:
    def get_or_create_for_profile(self, runtime_config, *, profile):  # type: ignore[no-untyped-def]
        del runtime_config, profile
        return None


class _StaticConfigStore:
    def __init__(self, config: UserLLMConfig) -> None:
        self.config = config

    def get(self, profile: str = "current") -> UserLLMConfig:
        del profile
        return self.config


class _MemoryQuizJobStore:
    def __init__(self, request: QuizGenerationRequest) -> None:
        self.request = request
        self.results: list[QuizGenerationResultItem] = []
        self.status = QuizGenerationJobStatus.QUEUED
        self.progress = QuizGenerationJobProgress(
            total_questions=request.question_count,
            completed_questions=0,
            fallback_questions=0,
            current_question_index=0,
        )
        self.failure_reason: str | None = None
        self.attempts = []

    def get_job(self, job_id: str) -> QuizGenerationJobResponse:
        quiz = None
        if self.results:
            quiz = QuizBundle(
                quiz_id=job_id,
                course_id=self.request.course_id,
                module_id=self.request.module_id,
                query=self.request.query,
                questions=[item.question for item in self.results],
            )
        return QuizGenerationJobResponse(
            job_id=job_id,
            dedupe_key="dedupe",
            status=self.status,
            provider="openai",
            model="gpt-5.4-mini",
            request_payload=self.request,
            progress=self.progress,
            quiz=quiz,
            partial_results=self.results,
            error_summary=self.failure_reason,
            created_at="2026-01-01T00:00:00+00:00",
            started_at=None,
            completed_at=None,
            last_heartbeat_at=None,
        )

    def mark_running(self, job_id: str) -> None:
        del job_id
        self.status = QuizGenerationJobStatus.RUNNING

    def update_progress(
        self,
        job_id: str,
        *,
        completed_questions: int,
        fallback_questions: int,
        current_question_index: int,
    ) -> None:
        del job_id
        self.progress = QuizGenerationJobProgress(
            total_questions=self.request.question_count,
            completed_questions=completed_questions,
            fallback_questions=fallback_questions,
            current_question_index=current_question_index,
        )

    def append_result(self, result: QuizGenerationResultItem) -> None:
        self.results.append(result)

    def append_attempt(self, attempt) -> None:  # type: ignore[no-untyped-def]
        self.attempts.append(attempt)

    def mark_completed(
        self,
        job_id: str,
        *,
        status: QuizGenerationJobStatus,
        failure_reason: str | None = None,
    ) -> None:
        del job_id
        self.status = status
        self.failure_reason = failure_reason

    def increment_error_count(self, job_id: str, *, failure_reason: str | None = None) -> None:
        del job_id
        self.failure_reason = failure_reason

    def request_cancel(self, job_id: str) -> QuizGenerationJobStatus | None:
        del job_id
        return None

    def is_cancel_requested(self, job_id: str) -> bool:
        del job_id
        return False

    def list_incomplete_jobs(self) -> list[str]:
        return []


def _source_chunk(index: int, *, text: str | None = None) -> SourceChunk:
    return SourceChunk(
        chunk_id=f"chunk-{index}",
        source_id=f"source-{index}",
        material_id="material-1",
        course_id="course-cost",
        module_id=None,
        file_name="notes.txt",
        content_type="text/plain",
        section_title=f"Section {index}",
        text=text or f"Grounded section {index} explains a testable concept.",
        token_count=len((text or "Grounded section explains a testable concept.").split()),
        locator=SourceLocator(section_index=index, page_number=index),
        citation_label=f"notes.txt | Section {index}",
    )


def test_quiz_quality_gate_accepts_portable_pytorch_export(tmp_path: Path) -> None:
    service = QuizService(
        material_store=LocalMaterialStore(tmp_path / "materials"),
        vector_store=LocalVectorStore(tmp_path / "materials"),
        quiz_store=LocalQuizStore(tmp_path / "materials"),
        question_quality_service=StaticQualityService(
            tmp_path / "unused.pt",
            model_source="pytorch_portable_export",
        ),
        runtime_config=UserLLMConfig(
            provider=LLMProvider.OPENAI,
            model="gpt-5.4-mini",
            demo_mode=True,
        ),
        settings=Settings(),
    )
    question = QuizQuestion(
        question_id="portable-quality",
        question_type=QuestionType.MCQ,
        concept="Liquidity risk",
        section_title="Liquidity risk measurement",
        difficulty=0.6,
        prompt="Which statement best explains liquidity risk under stressed markets?",
        options=[
            QuizQuestionOption(option_id="A", text="Trading costs can rise as depth declines."),
            QuizQuestionOption(option_id="B", text="Market depth is guaranteed to remain fixed."),
            QuizQuestionOption(option_id="C", text="Bid-ask spreads always narrow during stress."),
            QuizQuestionOption(option_id="D", text="Funding needs disappear during stress."),
        ],
        citations=[_source_chunk(1)],
        rationale="The source explains that declining market depth raises liquidation costs.",
    )

    annotated = service._annotate_question_quality(
        question,
        QuestionValidationResult(accepted=True, score=0.9),
    )

    assert annotated.quality_validation is not None
    assert annotated.quality_validation.accepted_for_delivery is True


def test_quiz_quality_gate_rejects_heuristic_fallback(tmp_path: Path) -> None:
    service = QuizService(
        material_store=LocalMaterialStore(tmp_path / "materials"),
        vector_store=LocalVectorStore(tmp_path / "materials"),
        quiz_store=LocalQuizStore(tmp_path / "materials"),
        question_quality_service=StaticQualityService(
            tmp_path / "unused.pt",
            model_source="heuristic_fallback",
        ),
        runtime_config=UserLLMConfig(
            provider=LLMProvider.OPENAI,
            model="gpt-5.4-mini",
            demo_mode=True,
        ),
        settings=Settings(),
    )
    question = QuizQuestion(
        question_id="heuristic-quality",
        question_type=QuestionType.MCQ,
        concept="Liquidity risk",
        section_title="Liquidity risk measurement",
        difficulty=0.6,
        prompt="Which statement best explains liquidity risk under stressed markets?",
        options=[
            QuizQuestionOption(option_id="A", text="Trading costs can rise as depth declines."),
            QuizQuestionOption(option_id="B", text="Market depth is guaranteed to remain fixed."),
            QuizQuestionOption(option_id="C", text="Bid-ask spreads always narrow during stress."),
            QuizQuestionOption(option_id="D", text="Funding needs disappear during stress."),
        ],
        citations=[_source_chunk(1)],
        rationale="The source explains that declining market depth raises liquidation costs.",
    )

    annotated = service._annotate_question_quality(
        question,
        QuestionValidationResult(accepted=True, score=0.9),
    )

    assert annotated.quality_validation is not None
    assert annotated.quality_validation.accepted_for_delivery is False
    assert any("model is unavailable" in note for note in annotated.quality_validation.notes)


def test_select_hits_preserves_learning_outcome_diversity_within_same_module(
    tmp_path: Path,
) -> None:
    service = QuizService(
        material_store=LocalMaterialStore(tmp_path / "materials"),
        vector_store=LocalVectorStore(tmp_path / "materials"),
        quiz_store=LocalQuizStore(tmp_path / "materials"),
        question_quality_service=QuestionQualityInferenceService(
            checkpoint_path=tmp_path / "missing.pt",
            enable_torch=False,
        ),
        runtime_config=UserLLMConfig(
            provider=LLMProvider.OPENAI,
            model="gpt-5.4-mini",
            demo_mode=True,
        ),
        settings=Settings(),
    )
    hits = [
        RetrievalHit(
            score=0.95 - (index * 0.01),
            chunk=_source_chunk(
                index,
                text=(
                    f"LO 8.{letter}: Enterprise risk management concept {letter} "
                    "contains enough testable body text for a multiple choice question."
                ),
            ).model_copy(
                update={
                    "section_title": "Module 8.1: Enterprise Risk Management",
                    "citation_label": f"Book 1 | Module 8.1 | LO 8.{letter}",
                    "file_name": "FRM 2025 Part 1 KAPLAN Book 1.PDF",
                }
            ),
        )
        for index, letter in enumerate(["a", "b", "c"], start=1)
    ]

    selected = service._select_hits(hits, question_count=3)

    selected_los = [hit.chunk.citation_label.rsplit(" | ", 1)[-1] for hit in selected]
    assert selected_los == ["LO 8.a", "LO 8.b", "LO 8.c"]


def test_attach_source_metadata_adds_book_reference_to_answer_explanation(tmp_path: Path) -> None:
    service = QuizService(
        material_store=LocalMaterialStore(tmp_path / "materials"),
        vector_store=LocalVectorStore(tmp_path / "materials"),
        quiz_store=LocalQuizStore(tmp_path / "materials"),
        question_quality_service=QuestionQualityInferenceService(
            checkpoint_path=tmp_path / "missing.pt",
            enable_torch=False,
        ),
        runtime_config=UserLLMConfig(
            provider=LLMProvider.OPENAI,
            model="gpt-5.4-mini",
            demo_mode=True,
        ),
        settings=Settings(),
    )
    chunk = _source_chunk(
        7,
        text=(
            "Diversification reduces unsystematic risk because firm-specific losses can be "
            "offset by gains or lower losses in other securities."
        ),
    ).model_copy(
        update={
            "citation_label": "FRM 2025 Part 1 KAPLAN Book 3.PDF page 89",
            "section_title": "Module 29.1: Mutual Funds and Exchange-Traded Funds",
        }
    )
    question = QuizQuestion(
        question_id="quiz-q1",
        question_type=QuestionType.MCQ,
        concept="Diversification",
        section_title="Module 29.1: Mutual Funds and Exchange-Traded Funds",
        difficulty=0.6,
        prompt="How does diversification reduce unsystematic risk?",
        options=[
            QuizQuestionOption(option_id="A", text="It offsets firm-specific risks across holdings."),
            QuizQuestionOption(option_id="B", text="It removes marketwide risk."),
            QuizQuestionOption(option_id="C", text="It guarantees positive returns."),
            QuizQuestionOption(option_id="D", text="It eliminates liquidity risk."),
        ],
        citations=[chunk],
        rationale="Diversification offsets firm-specific losses across holdings.",
    )
    answer_key = StoredQuestionKey(
        question_id="quiz-q1",
        question_type=QuestionType.MCQ,
        concept="Diversification",
        correct_answer="It offsets firm-specific risks across holdings.",
        correct_option_id="A",
        expected_keywords=["diversification"],
        difficulty=0.6,
        citations=[chunk],
    )

    annotated, stored_key = service._attach_source_metadata(  # noqa: SLF001
        question=question,
        answer_key=answer_key,
        quiz_id="quiz-1",
        request=QuizGenerationRequest(
            course_id="course-cost",
            query="diversification",
            question_count=1,
            question_types=[QuestionType.MCQ],
        ),
        hit_chunk=chunk,
        sequence_index=1,
        created_at="2026-01-01T00:00:00+00:00",
    )

    assert annotated.explanation is not None
    assert "Correct answer: A. It offsets firm-specific risks across holdings." in annotated.explanation
    assert "Book reference: FRM 2025 Part 1 KAPLAN Book 3.PDF page 89." in annotated.explanation
    assert "firm-specific losses can be offset" in annotated.explanation
    assert stored_key.source_evidence is not None
    assert "firm-specific losses can be offset" in stored_key.source_evidence


def test_prepare_generation_plan_caps_retrieval_to_configured_chunk_limit(
    tmp_path: Path,
) -> None:
    service = QuizService(
        material_store=LocalMaterialStore(tmp_path / "materials"),
        vector_store=LocalVectorStore(tmp_path / "materials"),
        quiz_store=LocalQuizStore(tmp_path / "materials"),
        question_quality_service=QuestionQualityInferenceService(
            checkpoint_path=tmp_path / "missing.pt",
            enable_torch=False,
        ),
        runtime_config=UserLLMConfig(
            provider=LLMProvider.OPENAI,
            model="gpt-5.4-mini",
            demo_mode=True,
        ),
        settings=Settings(max_chunks_per_retrieval=3),
    )
    captured_top_k: list[int] = []

    def fake_query(**kwargs):  # type: ignore[no-untyped-def]
        captured_top_k.append(kwargs["top_k"])
        return RetrievalQueryResponse(
            course_id=kwargs["course_id"],
            module_id=kwargs.get("module_id"),
            module_ids=kwargs.get("module_ids") or [],
            query=kwargs["query"],
            hits=[
                RetrievalHit(score=1.0, chunk=_source_chunk(1)),
                RetrievalHit(score=0.9, chunk=_source_chunk(2)),
                RetrievalHit(score=0.8, chunk=_source_chunk(3)),
            ],
        )

    service.retrieval_service.query = fake_query  # type: ignore[method-assign]

    plan = service.prepare_generation_plan(
        QuizGenerationRequest(
            course_id="course-cost",
            query="variables",
            question_count=5,
            question_types=["mcq"],
            retrieval_top_k=20,
        )
    )

    assert captured_top_k == [3]
    assert len(plan.selected_hits) == 5


def test_generate_quiz_retries_when_generated_question_or_answer_repeats(tmp_path: Path) -> None:
    service = QuizService(
        material_store=LocalMaterialStore(tmp_path / "materials"),
        vector_store=LocalVectorStore(tmp_path / "materials"),
        quiz_store=LocalQuizStore(tmp_path / "materials"),
        question_quality_service=QuestionQualityInferenceService(
            checkpoint_path=tmp_path / "missing.pt",
            enable_torch=False,
        ),
        runtime_config=UserLLMConfig(
            provider=LLMProvider.OPENAI,
            model="gpt-5.4-mini",
            demo_mode=True,
        ),
        settings=Settings(),
    )
    hit = RetrievalHit(
        score=1.0,
        chunk=_source_chunk(
            1,
            text=(
                "LO 34.a A short hedge protects a sale price but can limit upside. "
                "Basis risk remains when spot and futures prices diverge."
            ),
        ),
    )

    def fake_query(**kwargs):  # type: ignore[no-untyped-def]
        return RetrievalQueryResponse(
            course_id=kwargs["course_id"],
            module_id=kwargs.get("module_id"),
            module_ids=kwargs.get("module_ids") or [],
            query=kwargs["query"],
            hits=[hit],
        )

    service.retrieval_service.query = fake_query  # type: ignore[method-assign]
    calls: list[dict[str, object]] = []

    def outcome_for(prompt: str, correct_answer: str, sequence_index: int) -> GeneratedQuestionOutcome:
        question_id = f"quiz-retry-q{sequence_index}"
        question = QuizQuestion(
            question_id=question_id,
            question_type=QuestionType.MCQ,
            concept="Hedging with Futures",
            section_title="Hedging with Futures",
            difficulty=0.6,
            prompt=prompt,
            options=[
                QuizQuestionOption(option_id="A", text=correct_answer),
                QuizQuestionOption(option_id="B", text="It eliminates all basis risk"),
                QuizQuestionOption(option_id="C", text="It guarantees profit"),
                QuizQuestionOption(option_id="D", text="It removes hedge costs"),
            ],
            citations=[hit.chunk],
            rationale="The answer follows from the cited hedge tradeoff.",
        )
        return GeneratedQuestionOutcome(
            question=question,
            answer_key=StoredQuestionKey(
                question_id=question_id,
                question_type=QuestionType.MCQ,
                concept="Hedging with Futures",
                correct_answer=correct_answer,
                correct_option_id="A",
                expected_keywords=["hedge"],
                difficulty=0.6,
                citations=[hit.chunk],
            ),
            generation_mode=QuestionGenerationMode.FALLBACK,
            attempt=None,
        )

    def fake_generate_question_for_hit(**kwargs):  # type: ignore[no-untyped-def]
        calls.append(kwargs)
        sequence_index = int(kwargs["sequence_index"])
        if len(calls) <= 2:
            return outcome_for(
                "Which statement best describes the short hedge tradeoff?",
                "It protects the sale price but can limit upside",
                sequence_index,
            )
        return outcome_for(
            "Which situation best illustrates basis risk in a cross hedge?",
            "Spot and futures prices may diverge",
            sequence_index,
        )

    service.generate_question_for_hit = fake_generate_question_for_hit  # type: ignore[method-assign]

    response = service.generate_quiz(
        QuizGenerationRequest(
            course_id="course-retry",
            query="hedging with futures",
            question_count=2,
            question_types=["mcq"],
            retrieval_top_k=2,
        )
    )

    assert [question.prompt for question in response.quiz.questions] == [
        "Which statement best describes the short hedge tradeoff?",
        "Which situation best illustrates basis risk in a cross hedge?",
    ]
    assert len(calls) == 3
    assert calls[-1]["force_fallback"] is True


def test_generate_quiz_retries_when_quality_gate_rejects_fallback_question(tmp_path: Path) -> None:
    quality_service = RejectFirstQualityService(tmp_path / "missing.pt")
    service = QuizService(
        material_store=LocalMaterialStore(tmp_path / "materials"),
        vector_store=LocalVectorStore(tmp_path / "materials"),
        quiz_store=LocalQuizStore(tmp_path / "materials"),
        question_quality_service=quality_service,
        runtime_config=UserLLMConfig(
            provider=LLMProvider.OPENAI,
            model="gpt-5.4-mini",
            demo_mode=True,
        ),
        settings=Settings(),
    )
    hit = RetrievalHit(
        score=1.0,
        chunk=_source_chunk(
            1,
            text=(
                "Operational risk includes failed internal processes, weak controls, people, "
                "systems, and external events. This is distinct from market risk or strategic risk."
            ),
        ),
    )

    def fake_query(**kwargs):  # type: ignore[no-untyped-def]
        return RetrievalQueryResponse(
            course_id=kwargs["course_id"],
            module_id=kwargs.get("module_id"),
            module_ids=kwargs.get("module_ids") or [],
            query=kwargs["query"],
            hits=[hit],
        )

    service.retrieval_service.query = fake_query  # type: ignore[method-assign]

    response = service.generate_quiz(
        QuizGenerationRequest(
            course_id="course-quality",
            query="operational risk",
            question_count=1,
            question_types=["mcq"],
            retrieval_top_k=1,
        )
    )

    assert quality_service.calls >= 2
    validation = response.quiz.questions[0].quality_validation
    assert validation is not None
    assert validation.accepted_for_delivery is True
    assert not response.quiz.questions[0].question_id.endswith("-q1")


def test_quiz_job_runner_retries_rejected_quality_before_appending_result(tmp_path: Path) -> None:
    material_store = LocalMaterialStore(tmp_path / "materials")
    vector_store = LocalVectorStore(tmp_path / "materials")
    quiz_store = LocalQuizStore(tmp_path / "materials")
    pipeline = IngestionPipeline(store=material_store, vector_store=vector_store)
    pipeline.ingest(
        course_id="course-job-quality",
        module_id=None,
        file_name="notes.txt",
        content_type="text/plain",
        data=(
            b"# Operational Risk Controls\n"
            b"Operational risk includes failed internal processes, weak controls, people, "
            b"systems, and external events. It is distinct from market risk."
        ),
    )
    request = QuizGenerationRequest(
        course_id="course-job-quality",
        query="operational risk",
        question_count=1,
        question_types=["mcq"],
        retrieval_top_k=2,
    )
    quality_service = RejectFirstQualityService(tmp_path / "missing.pt")
    job_store = _MemoryQuizJobStore(request)
    runner = QuizJobRunner(
        settings=Settings(),
        config_store=_StaticConfigStore(
            UserLLMConfig(
                provider=LLMProvider.OPENAI,
                model="gpt-5.4-mini",
                demo_mode=True,
            )
        ),
        job_store=job_store,
        quiz_store=quiz_store,
        material_store=material_store,
        vector_store=vector_store,
        question_quality_service=quality_service,
        llm_client_registry=_ImmediateRegistry(),  # type: ignore[arg-type]
    )

    runner._run_job("job-quality")

    assert quality_service.calls >= 2
    assert job_store.status == QuizGenerationJobStatus.COMPLETED
    assert len(job_store.results) == 1
    validation = job_store.results[0].question.quality_validation
    assert validation is not None
    assert validation.accepted_for_delivery is True
    assert not job_store.results[0].question_id.endswith("-q1")
    session = quiz_store.get_quiz_session("job-quality")
    assert session is not None
    assert session.quiz.questions[0].question_id == job_store.results[0].question_id


def test_workbook_quality_warnings_are_not_deliverable(tmp_path: Path) -> None:
    service = QuizService(
        material_store=LocalMaterialStore(tmp_path / "materials"),
        vector_store=LocalVectorStore(tmp_path / "materials"),
        quiz_store=LocalQuizStore(tmp_path / "materials"),
        question_quality_service=QuestionQualityInferenceService(
            checkpoint_path=tmp_path / "missing.pt",
            enable_torch=False,
        ),
        runtime_config=UserLLMConfig(
            provider=LLMProvider.OPENAI,
            model="gpt-5.4-mini",
            demo_mode=True,
        ),
        settings=Settings(),
    )
    chunk = _source_chunk(
        1,
        text=(
            "MODULE 6.1: Multifactor Model Assumptions and Inputs\n"
            "KEY CONCEPTS\n"
            "LO 6.a The capital asset pricing model explains expected return using market beta. "
            "Arbitrage pricing theory uses multiple systematic risk factors and factor sensitivities.\n"
            "MODULE QUIZ 6.1\n"
            "1. An analyst reviews several statements about multifactor models. Which statement is correct?\n"
            "A. Factor betas can change as exposures change.\n"
            "B. Factor betas are always fixed.\n"
            "C. CAPM and APT use the same single factor.\n"
            "D. Multifactor models ignore macroeconomic factors.\n"
            "ANSWER KEY FOR MODULE QUIZZES\n"
            "MODULE QUIZ 6.1\n"
            "1. A Factor sensitivities should be updated when exposures change. (LO 6.a)\n"
        ),
    )
    question = QuizQuestion(
        question_id="q-workbook-low",
        question_type=QuestionType.MCQ,
        concept="Multifactor Model Assumptions and Inputs",
        section_title="Module 6.1: Multifactor Model Assumptions and Inputs",
        difficulty=0.7,
        prompt="What does capital asset pricing model (capm) measure?",
        options=[
            QuizQuestionOption(option_id="A", text="It measures the expected return of a financial asset with respect to"),
            QuizQuestionOption(option_id="B", text="It are a series of factors that influence the return on a"),
            QuizQuestionOption(option_id="C", text="It is not a set series of macroeconomic factors to consider, which"),
            QuizQuestionOption(option_id="D", text="It is a type of multifactor model that expands upon the CAPM"),
        ],
        citations=[chunk],
        rationale="The answer follows from the module concept.",
    )

    validation = validateQuestion(
        question,
        source_text=chunk.text,
        knowledge=extractKnowledge(service._section_from_chunk(chunk)),
        correct_answer=question.options[0].text,
    )
    annotated = service._annotate_question_quality(question, validation)

    assert validation.accepted is False
    assert any("book-level module quiz format" in note for note in validation.notes)
    assert any("clipped or fragmentary answer choices" in note for note in validation.notes)
    assert annotated.quality_validation is not None
    assert annotated.quality_validation.accepted_for_delivery is False


def test_generate_quiz_falls_back_when_live_provider_question_generation_fails(tmp_path: Path) -> None:
    material_store = LocalMaterialStore(tmp_path / "materials")
    vector_store = LocalVectorStore(tmp_path / "materials")
    quiz_store = LocalQuizStore(tmp_path / "materials")
    pipeline = IngestionPipeline(store=material_store, vector_store=vector_store)
    pipeline.ingest(
        course_id="course-fallback",
        module_id=None,
        file_name="notes.txt",
        content_type="text/plain",
        data=(
            b"# Gradient Descent Basics\n"
            b"Gradient descent updates parameters using the learning rate."
        ),
    )

    service = QuizService(
        material_store=material_store,
        vector_store=vector_store,
        quiz_store=quiz_store,
        question_quality_service=QuestionQualityInferenceService(
            checkpoint_path=tmp_path / "missing.pt",
            enable_torch=False,
        ),
        runtime_config=UserLLMConfig(
            provider=LLMProvider.NVIDIA,
            model="meta/llama-3.1-70b-instruct",
            api_key="test-key",
            demo_mode=False,
        ),
        settings=Settings(),
        llm_client=FailingLLMClient(),
    )

    response = service.generate_quiz(
        QuizGenerationRequest(
            course_id="course-fallback",
            query="learning rate",
            question_count=1,
            question_types=["mcq"],
            retrieval_top_k=4,
        )
    )

    assert len(response.quiz.questions) == 1
    assert response.quiz.questions[0].question_type == "mcq"
    assert response.quiz.questions[0].citations[0].section_title == "Gradient Descent Basics"
    assert response.quiz.questions[0].quality_validation is not None


def test_grade_quiz_does_not_call_live_llm_by_default(tmp_path: Path) -> None:
    material_store = LocalMaterialStore(tmp_path / "materials")
    vector_store = LocalVectorStore(tmp_path / "materials")
    quiz_store = LocalQuizStore(tmp_path / "materials")
    pipeline = IngestionPipeline(store=material_store, vector_store=vector_store)
    pipeline.ingest(
        course_id="course-fast-grade",
        module_id=None,
        file_name="notes.txt",
        content_type="text/plain",
        data=(
            b"# Gradient Descent Basics\n"
            b"Gradient descent updates parameters using the learning rate."
        ),
    )

    question_quality_service = QuestionQualityInferenceService(
        checkpoint_path=tmp_path / "missing.pt",
        enable_torch=False,
    )
    runtime_config = UserLLMConfig(
        provider=LLMProvider.NVIDIA,
        model="meta/llama-3.1-70b-instruct",
        api_key="test-key",
        demo_mode=False,
    )
    generation_service = QuizService(
        material_store=material_store,
        vector_store=vector_store,
        quiz_store=quiz_store,
        question_quality_service=question_quality_service,
        runtime_config=runtime_config,
        settings=Settings(),
        llm_client=None,
    )
    generated = generation_service.generate_quiz(
        QuizGenerationRequest(
            course_id="course-fast-grade",
            query="learning rate",
            question_count=1,
            question_types=["mcq"],
            retrieval_top_k=4,
        )
    )

    live_client = CountingLLMClient()
    grading_service = QuizService(
        material_store=material_store,
        vector_store=vector_store,
        quiz_store=quiz_store,
        question_quality_service=question_quality_service,
        runtime_config=runtime_config,
        settings=Settings(enable_live_quiz_grading=False),
        llm_client=live_client,
    )
    session = quiz_store.get_quiz_session(generated.quiz.quiz_id)
    assert session is not None
    answer_key = session.answer_keys[0]

    response = grading_service.grade_quiz(
        QuizGradeRequest(
            quiz_id=generated.quiz.quiz_id,
            answers=[
                QuizSubmissionAnswer(
                    question_id=answer_key.question_id,
                    selected_option_id=answer_key.correct_option_id,
                )
            ],
        )
    )

    assert response.overall_score == 100.0
    assert "Correct." in response.results[0].explanation
    assert live_client.calls == 0


def test_generate_quiz_uses_per_question_fallback_without_collapsing_remaining_questions(
    tmp_path: Path,
) -> None:
    material_store = LocalMaterialStore(tmp_path / "materials")
    vector_store = LocalVectorStore(tmp_path / "materials")
    quiz_store = LocalQuizStore(tmp_path / "materials")
    pipeline = IngestionPipeline(store=material_store, vector_store=vector_store)
    pipeline.ingest(
        course_id="course-flaky",
        module_id=None,
        file_name="notes.txt",
        content_type="text/plain",
        data=(
            b"# Gradient Descent Basics\n"
            b"Gradient descent updates parameters using the learning rate.\n"
            b"# Worked Example\n"
            b"A smaller learning rate takes more steps but can improve stability."
        ),
    )

    llm_client = AlternatingLLMClient()
    service = QuizService(
        material_store=material_store,
        vector_store=vector_store,
        quiz_store=quiz_store,
        question_quality_service=QuestionQualityInferenceService(
            checkpoint_path=tmp_path / "missing.pt",
            enable_torch=False,
        ),
        runtime_config=UserLLMConfig(
            provider=LLMProvider.NVIDIA,
            model="meta/llama-3.1-70b-instruct",
            api_key="test-key",
            demo_mode=False,
        ),
        settings=Settings(),
        llm_client=llm_client,
    )

    response = service.generate_quiz(
        QuizGenerationRequest(
            course_id="course-flaky",
            query="learning rate gradient descent",
            question_count=3,
            question_types=["mcq", "mcq", "mcq"],
            retrieval_top_k=4,
        )
    )

    assert len(response.quiz.questions) == 3
    assert llm_client.calls == 3
    assert response.quiz.questions[0].prompt == "What grounded question number 1?"
    assert response.quiz.questions[1].citations[0].section_title in {
        "Gradient Descent Basics",
        "Worked Example",
    }
    assert response.quiz.questions[2].prompt == "What grounded question number 3?"


def test_generate_quiz_falls_back_per_question_on_repeated_transport_failures(
    tmp_path: Path,
) -> None:
    material_store = LocalMaterialStore(tmp_path / "materials")
    vector_store = LocalVectorStore(tmp_path / "materials")
    quiz_store = LocalQuizStore(tmp_path / "materials")
    pipeline = IngestionPipeline(store=material_store, vector_store=vector_store)
    pipeline.ingest(
        course_id="course-retry-threshold",
        module_id=None,
        file_name="notes.txt",
        content_type="text/plain",
        data=(
            b"# Gradient Descent Basics\n"
            b"Gradient descent updates parameters using the learning rate.\n"
            b"# Worked Example\n"
            b"A smaller learning rate takes more steps but can improve stability."
        ),
    )

    llm_client = RepeatedTimeoutLLMClient()
    service = QuizService(
        material_store=material_store,
        vector_store=vector_store,
        quiz_store=quiz_store,
        question_quality_service=QuestionQualityInferenceService(
            checkpoint_path=tmp_path / "missing.pt",
            enable_torch=False,
        ),
        runtime_config=UserLLMConfig(
            provider=LLMProvider.NVIDIA,
            model="meta/llama-3.1-70b-instruct",
            api_key="test-key",
            demo_mode=False,
        ),
        settings=Settings(),
        llm_client=llm_client,
    )

    response = service.generate_quiz(
        QuizGenerationRequest(
            course_id="course-retry-threshold",
            query="learning rate gradient descent",
            question_count=3,
            question_types=["mcq", "mcq", "mcq"],
            retrieval_top_k=4,
        )
    )

    assert len(response.quiz.questions) == 3
    assert llm_client.calls == 3
    assert response.quiz.questions[0].citations[0].section_title in {
        "Gradient Descent Basics",
        "Worked Example",
    }
    assert response.quiz.questions[1].citations[0].section_title in {
        "Gradient Descent Basics",
        "Worked Example",
    }
    assert response.quiz.questions[2].citations[0].section_title in {
        "Gradient Descent Basics",
        "Worked Example",
    }


def test_fallback_mcq_is_exam_style_and_not_raw_slide_copy(tmp_path: Path) -> None:
    material_store = LocalMaterialStore(tmp_path / "materials")
    vector_store = LocalVectorStore(tmp_path / "materials")
    quiz_store = LocalQuizStore(tmp_path / "materials")
    pipeline = IngestionPipeline(store=material_store, vector_store=vector_store)
    pipeline.ingest(
        course_id="course-style",
        module_id=None,
        file_name="notes.txt",
        content_type="text/plain",
        data=(
            b"# Expressions vs Statements\n"
            b"An expression produces a value.\n"
            b"A statement performs an action and does not itself produce a value.\n"
            b"Office hours are posted on Canvas."
        ),
    )

    service = QuizService(
        material_store=material_store,
        vector_store=vector_store,
        quiz_store=quiz_store,
        question_quality_service=QuestionQualityInferenceService(
            checkpoint_path=tmp_path / "missing.pt",
            enable_torch=False,
        ),
        runtime_config=UserLLMConfig(
            provider=LLMProvider.NVIDIA,
            model="meta/llama-3.1-70b-instruct",
            api_key="test-key",
            demo_mode=False,
        ),
        settings=Settings(),
        llm_client=FailingLLMClient(),
    )

    response = service.generate_quiz(
        QuizGenerationRequest(
            course_id="course-style",
            query="expressions statements",
            question_count=1,
            question_types=["mcq"],
            retrieval_top_k=4,
        )
    )

    question = response.quiz.questions[0]
    assert "supported by the section" not in question.prompt.lower()
    assert all(len(option.text.split()) <= 20 for option in question.options)
    assert all("office hours" not in option.text.lower() for option in question.options)
    assert all("logistics" not in option.text.lower() for option in question.options)
    assert question.quality_validation is not None
    assert question.quality_validation.score >= 0.5
    assert question.quality_validation.accepted_for_delivery is True


def test_material_section_jobs_do_not_force_immediate_fallback() -> None:
    runner = QuizJobRunner.__new__(QuizJobRunner)

    should_force = runner._should_force_fast_section_generation(
        QuizGenerationRequest(
            course_id="course-style",
            query="Module 2.2",
            question_count=3,
            question_types=["mcq"],
            client_request_id="material-section-section-5-request",
        )
    )

    assert should_force is False


def test_workbook_fallback_uses_module_quiz_style_without_duplicate_prompts(tmp_path: Path) -> None:
    material_store = LocalMaterialStore(tmp_path / "materials")
    vector_store = LocalVectorStore(tmp_path / "materials")
    quiz_store = LocalQuizStore(tmp_path / "materials")
    pipeline = IngestionPipeline(store=material_store, vector_store=vector_store)
    pipeline.ingest(
        course_id="course-workbook-style",
        module_id=None,
        file_name="frm-book.txt",
        content_type="text/plain",
        data=(
            b"STUDY SESSION 1-Risk Management Overview\n"
            b"READING 2\n"
            b"How Do Firms Manage Financial Risk?\n"
            b"MODULE 2.2: Risk Management Methods and Instruments\n"
            b"EXAM FOCUS\n"
            b"This module covers risk acceptance, avoidance, mitigation, and transfer.\n"
            b"KEY CONCEPTS\n"
            b"LO 2.a\n"
            b"Firms can pick from four risk management strategies: accept, avoid, mitigate, or transfer risk.\n"
            b"MODULE QUIZ 2.2\n"
            b"1. Jasmine Cellars uses grapes from France to make wine in California, "
            b"which it sells around the world. Which of the following risks does Jasmine Cellars face?\n"
            b"A. Financial position risk and operational risk.\n"
            b"B. Operational risk and pricing risk.\n"
            b"C. Pricing risk and model risk.\n"
            b"D. Model risk and financial position risk.\n"
            b"2. Johnson Controllers plans to hedge a Brazilian real exposure and asks which instrument "
            b"a risk manager would least likely recommend. Which choice is least appropriate?\n"
            b"A. Futures contracts.\n"
            b"B. Forward contracts.\n"
            b"C. Options.\n"
            b"D. Swaps.\n"
            b"ANSWER KEY FOR MODULE QUIZZES\n"
            b"MODULE QUIZ 2.2\n"
            b"1. B Operational risk and pricing risk are relevant because production and input prices matter.\n"
            b"2. A Futures contracts are less customizable than forwards, options, or swaps. "
            b"(LO 2.e) The following is a review of the principles designed to address learning objectives.\n"
        ),
    )
    parsed = material_store.list_parsed_documents_by_course("course-workbook-style", None)[0]
    source_id = parsed.sections[0].source_id

    service = QuizService(
        material_store=material_store,
        vector_store=vector_store,
        quiz_store=quiz_store,
        question_quality_service=QuestionQualityInferenceService(
            checkpoint_path=tmp_path / "missing.pt",
            enable_torch=False,
        ),
        runtime_config=UserLLMConfig(
            provider=LLMProvider.NVIDIA,
            model="meta/llama-3.1-70b-instruct",
            api_key="test-key",
            demo_mode=False,
        ),
        settings=Settings(max_chunks_per_retrieval=6),
        llm_client=FailingLLMClient(),
    )

    response = service.generate_quiz(
        QuizGenerationRequest(
            course_id="course-workbook-style",
            query="Module 2.2 risk management methods and instruments",
            question_count=3,
            question_types=["mcq", "short_answer"],
            retrieval_top_k=6,
            selected_source_ids=[source_id],
        )
    )

    prompts = [question.prompt for question in response.quiz.questions]
    normalized_prompts = {" ".join(prompt.lower().split()) for prompt in prompts}
    option_signatures = {
        " | ".join(option.text.lower() for option in question.options)
        for question in response.quiz.questions
    }
    option_text = " ".join(
        option.text.lower()
        for question in response.quiz.questions
        for option in question.options
    )

    assert len(response.quiz.questions) == 3
    assert len(normalized_prompts) == 3
    assert len(option_signatures) == 3
    assert all(question.question_type == "mcq" for question in response.quiz.questions)
    assert all("best defines" not in prompt.lower() for prompt in prompts)
    assert all("jasmine cellars" not in prompt.lower() for prompt in prompts)
    assert "random output label" not in option_text
    assert "unrelated preprocessing step" not in option_text
    assert "fixed reporting format" not in option_text
    assert "operational risk and pricing risk" not in option_text
    assert "futures contracts" not in option_text
    assert any(
        question.correct_answer
        in {
            "Accept the exposure",
            "Avoid the exposure",
            "Mitigate the exposure",
            "Transfer the exposure",
        }
        for question in response.quiz.questions
    )
    assert all("jasmine cellars" not in question.rationale.lower() for question in response.quiz.questions)
    assert all("the following is a review" not in question.rationale.lower() for question in response.quiz.questions)
    assert all("module quiz answer key" not in question.rationale.lower() for question in response.quiz.questions)
    assert (
        "accept, avoid, mitigate, or transfer risk" in option_text
        or "risk responses" in " ".join(question.rationale.lower() for question in response.quiz.questions)
    )


def test_workbook_fallback_preserves_module_quiz_prompt_structure(tmp_path: Path) -> None:
    material_store = LocalMaterialStore(tmp_path / "materials")
    vector_store = LocalVectorStore(tmp_path / "materials")
    quiz_store = LocalQuizStore(tmp_path / "materials")
    pipeline = IngestionPipeline(store=material_store, vector_store=vector_store)
    pipeline.ingest(
        course_id="course-workbook-prompt-style",
        module_id=None,
        file_name="frm-book.txt",
        content_type="text/plain",
        data=(
            b"STUDY SESSION 1-Risk Management Overview\n"
            b"READING 2\n"
            b"How Do Firms Manage Financial Risk?\n"
            b"MODULE 2.1: Corporate Risk Management\n"
            b"KEY CONCEPTS\n"
            b"LO 2.a\n"
            b"Firms can pick from four different risk management strategies: accept, avoid, mitigate, or transfer risk.\n"
            b"LO 2.b\n"
            b"A firm's risk appetite is its willingness to retain risk.\n"
            b"MODULE QUIZ 2.1\n"
            b"1. Bank Y has decided to use currency futures and forward to offset its entire estimated foreign sales exposure. "
            b"Which high-level risk mitigation strategy does this description represent?\n"
            b"A. Retain risk.\n"
            b"B. Avoid risk.\n"
            b"C. Mitigate risk.\n"
            b"D. Transfer risk.\n"
            b"2. The involvement of the board of directors is important within the context of a firm's decision to hedge specific risk factors. "
            b"Which of the following statements regarding the setting of risk appetite is correct?\n"
            b"I. Risk appetite may be conveyed strictly in a qualitative manner.\n"
            b"II. Debtholders and shareholders are both likely to desire minimizing the firm's risk appetite.\n"
            b"A. I only.\n"
            b"B. II only.\n"
            b"C. Both I and II.\n"
            b"D. Neither I nor II.\n"
            b"ANSWER KEY FOR MODULE QUIZZES\n"
            b"MODULE QUIZ 2.1\n"
            b"1. D Bank Y chose to transfer foreign currency risk to a third party. (LO 2.a)\n"
            b"2. A Risk appetite may be conveyed in qualitative and/or quantitative terms. (LO 2.b)\n"
        ),
    )
    parsed = material_store.list_parsed_documents_by_course("course-workbook-prompt-style", None)[0]
    source_id = parsed.sections[0].source_id

    service = QuizService(
        material_store=material_store,
        vector_store=vector_store,
        quiz_store=quiz_store,
        question_quality_service=QuestionQualityInferenceService(
            checkpoint_path=tmp_path / "missing.pt",
            enable_torch=False,
        ),
        runtime_config=UserLLMConfig(
            provider=LLMProvider.NVIDIA,
            model="meta/llama-3.1-70b-instruct",
            api_key="test-key",
            demo_mode=False,
        ),
        settings=Settings(max_chunks_per_retrieval=6),
        llm_client=FailingLLMClient(),
    )

    response = service.generate_quiz(
        QuizGenerationRequest(
            course_id="course-workbook-prompt-style",
            query="Module 2.1 corporate risk management",
            question_count=2,
            question_types=["mcq"],
            retrieval_top_k=6,
            selected_source_ids=[source_id],
        )
    )

    prompts = [question.prompt for question in response.quiz.questions]
    joined_prompts = " ".join(prompts).lower()

    assert len(response.quiz.questions) == 2
    assert "study session" not in joined_prompts
    assert "bank y" not in joined_prompts
    assert "currency futures" not in joined_prompts
    assert "foreign sales exposure" not in joined_prompts
    assert "risk appetite may be conveyed" not in joined_prompts
    assert "debtholders and shareholders" not in joined_prompts
    assert "risk appetite" in prompts[1].lower()
    assert "I." in prompts[1]
    assert "II." in prompts[1]
    assert [option.text for option in response.quiz.questions[1].options] == [
        "I only",
        "II only",
        "Both I and II",
        "Neither I nor II",
    ]


def test_workbook_fallback_uses_module_quiz_as_style_without_copying_questions(tmp_path: Path) -> None:
    material_store = LocalMaterialStore(tmp_path / "materials")
    vector_store = LocalVectorStore(tmp_path / "materials")
    quiz_store = LocalQuizStore(tmp_path / "materials")
    pipeline = IngestionPipeline(store=material_store, vector_store=vector_store)
    pipeline.ingest(
        course_id="course-workbook-variant-style",
        module_id=None,
        file_name="frm-book.txt",
        content_type="text/plain",
        data=(
            b"STUDY SESSION 8-Financial Markets and Products\n"
            b"READING 34\n"
            b"Futures Markets\n"
            b"MODULE 34.1: Hedging with Futures\n"
            b"KEY CONCEPTS\n"
            b"LO 34.a\n"
            b"A short hedge locks in a sale price but can limit upside if the asset price increases. "
            b"Basis risk remains when spot and futures prices do not move together. "
            b"A cross hedge uses a futures contract on a related but different asset, which can increase basis risk.\n"
            b"MODULE QUIZ 34.1\n"
            b"1. Which statement best describes the primary disadvantage of implementing a short hedge?\n"
            b"A. It eliminates all uncertainty regarding future profitability without any cost.\n"
            b"B. It guarantees a profit regardless of whether spot prices rise or fall.\n"
            b"C. It limits potential profitability if the price of the hedged asset increases.\n"
            b"D. It creates basis risk only when the maturity dates perfectly match.\n"
            b"ANSWER KEY FOR MODULE QUIZZES\n"
            b"MODULE QUIZ 34.1\n"
            b"1. C A short hedge protects the sale price but sacrifices upside when the asset price rises. (LO 34.a)\n"
        ),
    )
    parsed = material_store.list_parsed_documents_by_course("course-workbook-variant-style", None)[0]
    source_id = parsed.sections[0].source_id

    service = QuizService(
        material_store=material_store,
        vector_store=vector_store,
        quiz_store=quiz_store,
        question_quality_service=QuestionQualityInferenceService(
            checkpoint_path=tmp_path / "missing.pt",
            enable_torch=False,
        ),
        runtime_config=UserLLMConfig(
            provider=LLMProvider.NVIDIA,
            model="meta/llama-3.1-70b-instruct",
            api_key="test-key",
            demo_mode=False,
        ),
        settings=Settings(max_chunks_per_retrieval=6),
        llm_client=FailingLLMClient(),
    )

    response = service.generate_quiz(
        QuizGenerationRequest(
            course_id="course-workbook-variant-style",
            query="Module 34.1 hedging with futures",
            question_count=2,
            question_types=["mcq"],
            retrieval_top_k=6,
            selected_source_ids=[source_id],
        )
    )

    prompts = [" ".join(question.prompt.lower().split()) for question in response.quiz.questions]
    option_signatures = {
        " | ".join(option.text.lower() for option in question.options)
        for question in response.quiz.questions
    }

    assert len(response.quiz.questions) == 2
    assert len(set(prompts)) == 2
    assert len(option_signatures) == 2
    assert any(prompt.startswith("which statement") for prompt in prompts)
    assert all(
        "primary disadvantage of implementing a short hedge" not in prompt
        for prompt in prompts
    )
    assert all(
        "eliminates all uncertainty regarding future profitability" not in " ".join(
            option.text.lower() for option in question.options
        )
        for question in response.quiz.questions
    )
    assert any("basis risk" in prompt or "cross hedge" in prompt for prompt in prompts)
