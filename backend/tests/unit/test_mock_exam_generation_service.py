import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from exam_prep.api.routes.exams import generate_mock_exam
from exam_prep.core.config import Settings
from exam_prep.core.exceptions import LLMProviderError, MaterialIngestionError
from exam_prep.llm.base import LLMClient
from exam_prep.llm.models import LLMRequest, LLMResponse
from exam_prep.llm.registry import LLMClientRegistry
from exam_prep.ml.inference import QuestionQualityInferenceService
from exam_prep.repositories.local.exam_store import LocalExamStore
from exam_prep.repositories.local.material_store import LocalMaterialStore
from exam_prep.repositories.local.vector_store import LocalVectorStore
from exam_prep.schemas.exam import ExamBlueprint, MockExamGenerationRequest, MockExamSourceQuestion
from exam_prep.schemas.config import LLMProvider, UserLLMConfig
from exam_prep.schemas.ml import QuestionQualityLabel, QuestionQualityValidation
from exam_prep.schemas.quiz import ExamQuestionCategory, QuizQuestion
from exam_prep.services.exam_service import ExamService
from exam_prep.services.mock_exam_generation_service import MockExamGenerationService
from exam_prep.services.mock_exam_source_service import MockExamSourceService
from backend.tests.unit.mock_exam_source_fixtures import exam_source_text, ingest_book_material


class _DeterministicLLMClient:
    supports_json_schema_response_format = True
    enable_response_format = True

    def __init__(
        self,
        initial_payloads: list[dict[str, object]] | None = None,
        *,
        add_extra_field_once: bool = False,
        mismatch_numeric_answer_once: bool = False,
    ) -> None:
        self.initial_payloads = list(initial_payloads or [])
        self.add_extra_field_once = add_extra_field_once
        self.mismatch_numeric_answer_once = mismatch_numeric_answer_once
        self.requests: list[LLMRequest] = []

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        payload = (
            self.initial_payloads.pop(0)
            if self.initial_payloads
            else self._grounded_payload(request, len(self.requests))
        )
        if self.add_extra_field_once and len(self.requests) == 1:
            payload = {**payload, "unexpected_field": "must be rejected, not normalized"}
        if self.mismatch_numeric_answer_once and len(self.requests) == 1:
            payload = {
                **payload,
                "correct_answer": "Risk appetite applies for 9 years.",
                "correct_option_id": "A",
                "options": [
                    {"option_id": "A", "text": "Risk appetite applies for 10 years."},
                    {"option_id": "B", "text": "Limits are reviewed for 2 months."},
                    {"option_id": "C", "text": "Controls are delegated for 3 quarters."},
                    {"option_id": "D", "text": "Insurance is renewed for 4 weeks."},
                ],
            }
        return LLMResponse(
            model_name=request.model_name,
            provider_name="fake-parser",
            raw_text=json.dumps(payload),
        )

    def _grounded_payload(self, request: LLMRequest, call_number: int) -> dict[str, object]:
        angle = f"angle{_alphabetic_token(call_number)}"
        if "LO 1.a" in request.user_prompt:
            options = [
                {
                    "option_id": "A",
                    "text": "The board should remove measurable controls after setting appetite.",
                },
                {
                    "option_id": "B",
                    "text": "The board should treat insurance as the only governance mechanism.",
                },
                {
                    "option_id": "C",
                    "text": (
                        "The board should translate its willingness to retain risk into "
                        "measurable business-unit limits."
                    ),
                },
                {
                    "option_id": "D",
                    "text": "Each business unit should define risk appetite without board delegation.",
                },
            ]
            return {
                "prompt": (
                    f"During the {angle} planning review, which governance response best applies "
                    "the board's risk appetite to a changed business-unit mandate?"
                ),
                "correct_answer": options[2]["text"],
                "correct_option_id": "C",
                "options": options,
                "rationale": (
                    "A: Distractor A is wrong because the book defines risk appetite as retained risk "
                    "and says limits remain measurable controls.\n"
                    "B: Distractor B is wrong because the book explains that limits translate risk "
                    "appetite into business-unit controls.\n"
                    "C: Correct because the book says limits translate the amount and type of risk a "
                    "firm is willing to retain into measurable controls.\n"
                    "D: Distractor D is wrong because the book says the board sets risk appetite and "
                    "delegates limits to business units."
                ),
            }

        options = [
            {
                "option_id": "A",
                "text": "The maturity change guarantees that the exposure has no remaining risk.",
            },
            {
                "option_id": "B",
                "text": "The hedge can offset the exposure while leaving basis risk from mismatch.",
            },
            {
                "option_id": "C",
                "text": "The futures hedge transfers downside risk exactly like insurance.",
            },
            {
                "option_id": "D",
                "text": "The hedge removes opportunity cost and preserves every upside outcome.",
            },
        ]
        return {
            "prompt": (
                f"During the {angle} hedge review, which conclusion follows after the desk changes "
                "the futures contract maturity?"
            ),
            "correct_answer": options[1]["text"],
            "correct_option_id": "B",
            "options": options,
            "rationale": (
                "A: Distractor A is wrong because the book says a hedge offsets exposure but can "
                "still introduce basis risk.\n"
                "B: Correct because the book explains that a hedge offsets an exposure while an "
                "imperfect match can leave basis risk.\n"
                "C: Distractor C is wrong because the book distinguishes a hedge from insurance, "
                "which transfers downside risk.\n"
                "D: Distractor D is wrong because the book says hedging can introduce opportunity "
                "cost rather than remove it."
            ),
        }


class _QualityStub(QuestionQualityInferenceService):
    def __init__(self, validations: list[QuestionQualityValidation]) -> None:
        super().__init__(checkpoint_path=Path("unused-quality-checkpoint.pt"), enable_torch=False)
        self.validations = validations
        self.call_count = 0

    def score_generated_question(self, question: QuizQuestion) -> QuestionQualityValidation:
        self.call_count += 1
        if self.validations:
            return self.validations.pop(0)
        return _pytorch_quality()


class _ThreeChoiceLLMClient(_DeterministicLLMClient):
    def _grounded_payload(self, request: LLMRequest, call_number: int) -> dict[str, object]:
        angle = _alphabetic_token(call_number)
        options = [
            {
                "option_id": "A",
                "text": f"The board retains measurable risk limits for review {angle}.",
            },
            {
                "option_id": "B",
                "text": f"The board removes every retained-risk control for review {angle}.",
            },
            {
                "option_id": "C",
                "text": f"The board delegates risk appetite without limits for review {angle}.",
            },
        ]
        return {
            "prompt": (
                f"During governance review {angle}, which action best translates retained risk "
                "appetite into a measurable control?"
            ),
            "correct_answer": options[0]["text"],
            "correct_option_id": "A",
            "options": options,
            "rationale": (
                "A: Correct because the book translates retained risk appetite into measurable limits.\n"
                "B: Incorrect because removing controls conflicts with measurable retained-risk limits.\n"
                "C: Incorrect because delegation still requires limits tied to retained risk appetite."
            ),
        }


class _ParserRegistryStub(LLMClientRegistry):
    def __init__(
        self,
        client: LLMClient,
        *,
        failure: LLMProviderError | None = None,
    ) -> None:
        super().__init__(Settings())
        self.client = client
        self.failure = failure
        self.requested_model: str | None = None
        self.requested_profile: str | None = None

    def get_or_create_for_profile(
        self,
        config: UserLLMConfig,
        *,
        profile: str,
    ) -> LLMClient | None:
        self.requested_model = config.model
        self.requested_profile = profile
        if self.failure is not None:
            raise self.failure
        return self.client


def test_source_exam_generation_is_one_to_one_unique_and_high_quality(tmp_path: Path) -> None:
    material_store = LocalMaterialStore(tmp_path / "materials")
    vector_store = LocalVectorStore(tmp_path / "materials")
    exam_store = LocalExamStore(tmp_path / "materials")
    ingest_book_material(material_store)
    bank = MockExamSourceService(
        material_store=material_store,
        exam_store=exam_store,
    ).ingest_source_bank(
        course_id="frm-course",
        file_name="frm-practice-exams.txt",
        content_type="text/plain",
        data=exam_source_text(100).encode("utf-8"),
    )
    category_cycle = [
        ExamQuestionCategory.CALCULATION,
        ExamQuestionCategory.SCENARIO,
        ExamQuestionCategory.MODEL_INTERPRETATION,
        ExamQuestionCategory.ETHICS,
        ExamQuestionCategory.APPLIED_CONCEPTUAL,
    ]
    source_exam = bank.exams[0].model_copy(
        update={
            "questions": [
                question.model_copy(
                    update={
                        "frm_question_type": category_cycle[
                            (question.question_number - 1) % len(category_cycle)
                        ]
                    }
                )
                for question in bank.exams[0].questions
            ]
        }
    )
    exam_store.save_source_bank(bank.model_copy(update={"exams": [source_exam]}))
    quality_service = _QualityStub([])
    llm_client = _DeterministicLLMClient()
    service = ExamService(
        material_store=material_store,
        vector_store=vector_store,
        exam_store=exam_store,
        question_quality_service=quality_service,
        llm_client=llm_client,
        llm_model="gpt-parser-test",
    )
    request = MockExamGenerationRequest(
        course_id="frm-course",
        source_exam_id=source_exam.source_exam_id,
        blueprint=ExamBlueprint(
            title="FRM practice exam clone",
            instructions="Answer all questions.",
            topic_coverage=[],
            target_difficulty=0.7,
            style_example="Mirror the uploaded FRM exam format without repeating source questions.",
        ),
    )

    first = service.generate_exam(request).exam
    second = service.generate_exam(request).exam
    stored = exam_store.get_exam_session(first.exam_id)

    assert len(first.questions) == 100
    assert len(llm_client.requests) == 200
    assert stored is not None
    assert len(stored.answer_keys) == 100
    assert len({question.prompt for question in first.questions}) == 100
    assert {question.prompt for question in second.questions}.isdisjoint(
        {question.prompt for question in first.questions}
    )
    for source_question, generated_question, answer_key in zip(
        source_exam.questions,
        first.questions,
        stored.answer_keys,
        strict=True,
    ):
        assert generated_question.question_id.rsplit("-q", 1)[-1] == str(
            source_question.question_number
        )
        assert generated_question.concept == (
            source_question.learning_objective or source_question.topic
        )
        assert generated_question.frm_question_type == source_question.frm_question_type
        assert generated_question.difficulty == source_question.difficulty
        assert generated_question.section_id == source_question.matched_source_id
        assert generated_question.material_id == source_question.matched_material_id
        assert generated_question.citations
        assert generated_question.citations[0].chunk_id == source_question.matched_chunk_id
        assert answer_key.section_id == source_question.matched_source_id
        assert answer_key.material_id == source_question.matched_material_id
        assert answer_key.citations
        assert answer_key.citations[0].chunk_id == source_question.matched_chunk_id
        assert generated_question.options and len(generated_question.options) == 4
        assert generated_question.correct_answer in {
            option.text for option in generated_question.options
        }
        assert generated_question.explanation is not None
        assert "case " not in generated_question.prompt.casefold()
        assert "source question" not in generated_question.prompt.casefold()
        assert "source question" not in generated_question.explanation.casefold()
        assert "Correct because" in generated_question.explanation
        assert "Distractor " in generated_question.explanation
        assert generated_question.source_evidence
        assert generated_question.source_evidence in generated_question.explanation
        quality = generated_question.quality_validation
        assert quality is not None
        assert quality.label == QuestionQualityLabel.HIGH_QUALITY
        assert quality.accepted_for_delivery
        assert quality.model_source.startswith("pytorch")
        assert quality.model_version
        assert quality.confidence >= 0.5

    first_request = llm_client.requests[0]
    first_source = source_exam.questions[0]
    assert first_request.model_name == "gpt-parser-test"
    assert first_request.request_name == "GeneratedQuestionPayload"
    assert first_request.response_format is not None
    match first_request.response_format.get("json_schema"):
        case {"strict": True}:
            pass
        case unexpected_schema:
            pytest.fail(f"Expected strict JSON schema response format, got {unexpected_schema!r}")
    assert first_source.prompt in first_request.user_prompt
    assert all(option.text in first_request.user_prompt for option in first_source.options)
    assert first_source.correct_answer in first_request.user_prompt
    assert first_source.explanation in first_request.user_prompt
    assert first_source.learning_objective is not None
    assert first_source.learning_objective in first_request.user_prompt
    assert first_source.topic in first_request.user_prompt
    assert first_source.matched_citation_label is not None
    assert first_source.matched_citation_label in first_request.user_prompt
    assert "Risk appetite is the amount and type of risk" in first_request.user_prompt
    system_prompt = first_request.system_prompt.casefold()
    assert "same cognitive operation" in system_prompt
    assert "exactly four" in system_prompt
    assert "every distractor" in system_prompt
    assert "different content" in system_prompt


def test_source_exam_generation_preserves_non_frm_length_and_choice_count(
    tmp_path: Path,
) -> None:
    material_store = LocalMaterialStore(tmp_path / "materials")
    exam_store = LocalExamStore(tmp_path / "materials")
    ingest_book_material(material_store)
    bank = MockExamSourceService(
        material_store=material_store,
        exam_store=exam_store,
    ).ingest_source_bank(
        course_id="frm-course",
        file_name="governance-certification-exam.txt",
        content_type="text/plain",
        data=(
            "Practice Exam 1\n"
            "1. Which action translates risk appetite into controls?\n"
            "A. Set limits.\nB. Remove oversight.\nC. Ignore retained risk.\n"
            "2. Which body sets the firm's risk appetite?\n"
            "A. The board.\nB. Each vendor.\nC. No governing body.\n"
            "3. Which statement best describes retained risk?\n"
            "A. Risk the firm accepts.\nB. Risk that cannot be measured.\nC. Risk removed by definition.\n"
            "Answer Key for Practice Exam 1\n"
            "1. A. Limits translate risk appetite into measurable controls.\n"
            "2. A. The board sets the firm's risk appetite.\n"
            "3. A. Retained risk is the amount and type of risk the firm accepts.\n"
        ).encode("utf-8"),
    )
    client = _ThreeChoiceLLMClient()
    service = MockExamGenerationService(
        material_store=material_store,
        exam_store=exam_store,
        question_quality_service=_QualityStub([]),
        llm_client=client,
        llm_model="gpt-parser-test",
    )

    exam, answer_keys = service.generate_from_source(
        MockExamGenerationRequest(
            course_id="frm-course",
            source_exam_id=bank.exams[0].source_exam_id,
            blueprint=ExamBlueprint(
                title="Governance certification practice exam",
                instructions="Choose the best answer.",
                topic_coverage=[],
                target_difficulty=0.65,
                style_example="Governance certification sample",
            ),
        )
    )

    assert len(exam.questions) == 3
    assert len(answer_keys) == 3
    assert [len(question.options) for question in exam.questions] == [3, 3, 3]
    assert len({question.prompt for question in exam.questions}) == 3


def test_source_generation_requires_live_parser_llm(tmp_path: Path) -> None:
    material_store = LocalMaterialStore(tmp_path / "materials")
    exam_store = LocalExamStore(tmp_path / "materials")
    ingest_book_material(material_store)
    bank = MockExamSourceService(
        material_store=material_store,
        exam_store=exam_store,
    ).ingest_source_bank(
        course_id="frm-course",
        file_name="frm-practice-exams.txt",
        content_type="text/plain",
        data=exam_source_text(100).encode("utf-8"),
    )
    service = MockExamGenerationService(
        material_store=material_store,
        exam_store=exam_store,
        question_quality_service=_QualityStub([]),
    )

    with pytest.raises(LLMProviderError, match="parser-agent LLM client and model"):
        service.generate_from_source(
            MockExamGenerationRequest(
                course_id="frm-course",
                source_exam_id=bank.exams[0].source_exam_id,
                blueprint=ExamBlueprint(
                    title="FRM practice exam clone",
                    instructions="Answer all questions.",
                    topic_coverage=[],
                    target_difficulty=0.7,
                    style_example="Mirror the uploaded FRM exam format.",
                ),
            )
        )


def test_source_generation_rejects_exam_from_another_course(tmp_path: Path) -> None:
    material_store = LocalMaterialStore(tmp_path / "materials")
    exam_store = LocalExamStore(tmp_path / "materials")
    bank = MockExamSourceService(
        material_store=material_store,
        exam_store=exam_store,
    ).ingest_source_bank(
        course_id="frm-course",
        file_name="frm-practice-exams.txt",
        content_type="text/plain",
        data=exam_source_text(100).encode("utf-8"),
    )
    service = MockExamGenerationService(
        material_store=material_store,
        exam_store=exam_store,
        question_quality_service=_QualityStub([]),
        llm_client=_DeterministicLLMClient(),
        llm_model="gpt-parser-test",
    )

    with pytest.raises(MaterialIngestionError, match="source not found"):
        service.generate_from_source(
            MockExamGenerationRequest(
                course_id="another-course",
                source_exam_id=bank.exams[0].source_exam_id,
                blueprint=ExamBlueprint(
                    title="FRM practice exam clone",
                    instructions="Answer all questions.",
                    topic_coverage=[],
                    target_difficulty=0.7,
                    style_example="Mirror the uploaded FRM exam format.",
                ),
            )
        )


def test_generate_route_uses_parser_runtime_model_and_client(tmp_path: Path) -> None:
    material_store = LocalMaterialStore(tmp_path / "materials")
    vector_store = LocalVectorStore(tmp_path / "materials")
    exam_store = LocalExamStore(tmp_path / "materials")
    ingest_book_material(material_store)
    bank = MockExamSourceService(
        material_store=material_store,
        exam_store=exam_store,
    ).ingest_source_bank(
        course_id="frm-course",
        file_name="frm-practice-exams.txt",
        content_type="text/plain",
        data=exam_source_text(100).encode("utf-8"),
    )
    payload = MockExamGenerationRequest(
        course_id="frm-course",
        source_exam_id=bank.exams[0].source_exam_id,
        blueprint=ExamBlueprint(
            title="FRM practice exam clone",
            instructions="Answer all questions.",
            topic_coverage=[],
            target_difficulty=0.7,
            style_example="Mirror the uploaded FRM exam format.",
        ),
    )
    llm_client = _DeterministicLLMClient()
    registry = _ParserRegistryStub(llm_client)

    response = generate_mock_exam(
        payload=payload,
        material_store=material_store,
        vector_store=vector_store,
        exam_store=exam_store,
        question_quality_service=_QualityStub([]),
        parser_runtime_config=UserLLMConfig(
            provider=LLMProvider.OPENAI,
            model="gpt-parser-route-test",
            api_key="test-key",
            demo_mode=False,
        ),
        llm_client_registry=registry,
    )

    assert len(response.exam.questions) == 100
    assert registry.requested_profile == "parser"
    assert registry.requested_model == "gpt-parser-route-test"
    assert llm_client.requests[0].model_name == "gpt-parser-route-test"


def test_generate_route_translates_parser_client_failure_to_bad_gateway(tmp_path: Path) -> None:
    payload = MockExamGenerationRequest(
        course_id="frm-course",
        source_exam_id="source-exam",
        blueprint=ExamBlueprint(
            title="FRM practice exam clone",
            instructions="Answer all questions.",
            topic_coverage=[],
            target_difficulty=0.7,
            style_example="Mirror the uploaded FRM exam format.",
        ),
    )
    registry = _ParserRegistryStub(
        _DeterministicLLMClient(),
        failure=LLMProviderError("Parser provider is unavailable."),
    )

    with pytest.raises(HTTPException) as raised:
        generate_mock_exam(
            payload=payload,
            material_store=LocalMaterialStore(tmp_path / "materials"),
            vector_store=LocalVectorStore(tmp_path / "materials"),
            exam_store=LocalExamStore(tmp_path / "materials"),
            question_quality_service=_QualityStub([]),
            parser_runtime_config=UserLLMConfig(
                provider=LLMProvider.OPENAI,
                model="gpt-parser-route-test",
                api_key="test-key",
                demo_mode=False,
            ),
            llm_client_registry=registry,
        )

    assert raised.value.status_code == 502
    assert raised.value.detail == (
        "Parser model generation failed. Verify parser model settings and retry."
    )


def test_source_generation_rejects_copied_candidate_and_regenerates(tmp_path: Path) -> None:
    material_store = LocalMaterialStore(tmp_path / "materials")
    exam_store = LocalExamStore(tmp_path / "materials")
    ingest_book_material(material_store)
    bank = MockExamSourceService(
        material_store=material_store,
        exam_store=exam_store,
    ).ingest_source_bank(
        course_id="frm-course",
        file_name="frm-practice-exams.txt",
        content_type="text/plain",
        data=exam_source_text(100).encode("utf-8"),
    )
    copied_source = bank.exams[0].questions[0]
    copied_options = [option.model_dump() for option in copied_source.options]
    copied_payload: dict[str, object] = {
        "prompt": copied_source.prompt,
        "correct_answer": copied_source.options[2].text,
        "correct_option_id": "C",
        "options": copied_options,
        "rationale": (
            "A: Distractor A conflicts with the book's retained risk and measurable limits.\n"
            "B: Distractor B conflicts with the book's retained risk and measurable limits.\n"
            "C: Correct because the book connects retained risk appetite to measurable limits.\n"
            "D: Distractor D conflicts with the board's delegated business-unit limits."
        ),
    }
    llm_client = _DeterministicLLMClient([copied_payload])
    quality_service = _QualityStub([])
    service = MockExamGenerationService(
        material_store=material_store,
        exam_store=exam_store,
        question_quality_service=quality_service,
        llm_client=llm_client,
        llm_model="gpt-parser-test",
    )

    exam, answer_keys = service.generate_from_source(
        MockExamGenerationRequest(
            course_id="frm-course",
            source_exam_id=bank.exams[0].source_exam_id,
            blueprint=ExamBlueprint(
                title="FRM practice exam clone",
                instructions="Answer all questions.",
                topic_coverage=[],
                target_difficulty=0.7,
                style_example="Mirror the uploaded FRM exam format.",
            ),
        )
    )

    assert len(exam.questions) == 100
    assert len(answer_keys) == 100
    assert len(llm_client.requests) == 101
    assert quality_service.call_count == 100
    assert exam.questions[0].prompt != copied_source.prompt


def test_source_generation_rejects_payload_that_needed_schema_repair(tmp_path: Path) -> None:
    material_store = LocalMaterialStore(tmp_path / "materials")
    exam_store = LocalExamStore(tmp_path / "materials")
    ingest_book_material(material_store)
    bank = MockExamSourceService(
        material_store=material_store,
        exam_store=exam_store,
    ).ingest_source_bank(
        course_id="frm-course",
        file_name="frm-practice-exams.txt",
        content_type="text/plain",
        data=exam_source_text(100).encode("utf-8"),
    )
    llm_client = _DeterministicLLMClient(add_extra_field_once=True)
    quality_service = _QualityStub([])
    service = MockExamGenerationService(
        material_store=material_store,
        exam_store=exam_store,
        question_quality_service=quality_service,
        llm_client=llm_client,
        llm_model="gpt-parser-test",
    )

    exam, answer_keys = service.generate_from_source(
        MockExamGenerationRequest(
            course_id="frm-course",
            source_exam_id=bank.exams[0].source_exam_id,
            blueprint=ExamBlueprint(
                title="FRM practice exam clone",
                instructions="Answer all questions.",
                topic_coverage=[],
                target_difficulty=0.7,
                style_example="Mirror the uploaded FRM exam format.",
            ),
        )
    )

    assert len(exam.questions) == 100
    assert len(answer_keys) == 100
    assert len(llm_client.requests) == 101
    assert quality_service.call_count == 100


def test_source_generation_rejects_numeric_answer_that_does_not_match_option(
    tmp_path: Path,
) -> None:
    material_store = LocalMaterialStore(tmp_path / "materials")
    exam_store = LocalExamStore(tmp_path / "materials")
    ingest_book_material(material_store)
    bank = MockExamSourceService(
        material_store=material_store,
        exam_store=exam_store,
    ).ingest_source_bank(
        course_id="frm-course",
        file_name="frm-practice-exams.txt",
        content_type="text/plain",
        data=exam_source_text(100).encode("utf-8"),
    )
    llm_client = _DeterministicLLMClient(mismatch_numeric_answer_once=True)
    quality_service = _QualityStub([])
    service = MockExamGenerationService(
        material_store=material_store,
        exam_store=exam_store,
        question_quality_service=quality_service,
        llm_client=llm_client,
        llm_model="gpt-parser-test",
    )

    exam, _ = service.generate_from_source(
        MockExamGenerationRequest(
            course_id="frm-course",
            source_exam_id=bank.exams[0].source_exam_id,
            blueprint=ExamBlueprint(
                title="FRM practice exam clone",
                instructions="Answer all questions.",
                topic_coverage=[],
                target_difficulty=0.7,
                style_example="Mirror the uploaded FRM exam format.",
            ),
        )
    )

    assert len(llm_client.requests) == 101
    assert quality_service.call_count == 100
    assert exam.questions[0].correct_answer == exam.questions[0].options[2].text


def test_source_generation_rejects_heuristic_quality_even_when_accepted(tmp_path: Path) -> None:
    material_store = LocalMaterialStore(tmp_path / "materials")
    exam_store = LocalExamStore(tmp_path / "materials")
    ingest_book_material(material_store)
    bank = MockExamSourceService(
        material_store=material_store,
        exam_store=exam_store,
    ).ingest_source_bank(
        course_id="frm-course",
        file_name="frm-practice-exams.txt",
        content_type="text/plain",
        data=exam_source_text(100).encode("utf-8"),
    )
    quality_service = _QualityStub(
        [
            _quality(model_source="heuristic_fallback", model_version="heuristic-v1")
            for _ in range(8)
        ]
    )
    service = MockExamGenerationService(
        material_store=material_store,
        exam_store=exam_store,
        question_quality_service=quality_service,
        llm_client=_DeterministicLLMClient(),
        llm_model="gpt-parser-test",
    )

    with pytest.raises(MaterialIngestionError, match="PyTorch quality gate"):
        service.generate_from_source(
            MockExamGenerationRequest(
                course_id="frm-course",
                source_exam_id=bank.exams[0].source_exam_id,
                blueprint=ExamBlueprint(
                    title="FRM practice exam clone",
                    instructions="Answer all questions.",
                    topic_coverage=[],
                    target_difficulty=0.7,
                    style_example="Mirror the uploaded FRM exam format.",
                ),
            )
        )

    assert quality_service.call_count == 1


def test_semantic_signature_normalizes_case_labels_numbers_and_boilerplate(
    tmp_path: Path,
) -> None:
    service = MockExamGenerationService(
        material_store=LocalMaterialStore(tmp_path / "materials"),
        exam_store=LocalExamStore(tmp_path / "materials"),
        question_quality_service=_QualityStub([]),
    )

    assert service._signature(
        "Which statement correctly extends source question 17's concept to a new setting? "
        "Case 17.2."
    ) == service._signature(
        "Which statement correctly extends source question 93's concept to a new setting? "
        "Case 93.7."
    )
    assert service._signature(
        "A portfolio has 12 assets and 3 hedges. Which statement is best supported?"
    ) == service._signature(
        "A portfolio has 99 assets and 14 hedges. Which statement is best supported?"
    )
    assert service._signature(
        "Which interpretation of hedge effectiveness is best supported by the FRM book excerpt?"
    ) != service._signature(
        "Which answer best reflects the book's treatment of hedge effectiveness?"
    )


def test_source_question_classifier_preserves_specialized_frm_formats() -> None:
    calculation = MockExamSourceQuestion(
        source_question_id="source-q1",
        source_exam_id="source-exam",
        question_number=1,
        prompt="A bond has duration 4.2. Calculate its approximate price change for a 20 bp move.",
    )
    model_interpretation = calculation.model_copy(
        update={
            "source_question_id": "source-q2",
            "question_number": 2,
            "prompt": "Which limitation is most important when interpreting this regression model output?",
        }
    )
    ethics = calculation.model_copy(
        update={
            "source_question_id": "source-q3",
            "question_number": 3,
            "prompt": "Which action is consistent with professional conduct and the FRM ethical principles?",
        }
    )
    explicit_source_category = calculation.model_copy(
        update={"frm_question_type": ExamQuestionCategory.SCENARIO}
    )

    assert (
        MockExamGenerationService.classify_source_question(calculation)
        == ExamQuestionCategory.CALCULATION
    )
    assert (
        MockExamGenerationService.classify_source_question(model_interpretation)
        == ExamQuestionCategory.MODEL_INTERPRETATION
    )
    assert MockExamGenerationService.classify_source_question(ethics) == ExamQuestionCategory.ETHICS
    assert (
        MockExamGenerationService.classify_source_question(explicit_source_category)
        == ExamQuestionCategory.SCENARIO
    )


def _pytorch_quality() -> QuestionQualityValidation:
    return _quality(model_source="pytorch_checkpoint", model_version="qq-v2")


def _quality(*, model_source: str, model_version: str) -> QuestionQualityValidation:
    return QuestionQualityValidation(
        score=0.95,
        confidence=0.9,
        label=QuestionQualityLabel.HIGH_QUALITY,
        accepted_for_delivery=True,
        model_version=model_version,
        model_source=model_source,
        notes=["Question structure and grounding signals look strong."],
    )


def _alphabetic_token(number: int) -> str:
    characters: list[str] = []
    remaining = number
    while remaining:
        remaining, offset = divmod(remaining - 1, 26)
        characters.append(chr(ord("a") + offset))
    return "".join(reversed(characters))
