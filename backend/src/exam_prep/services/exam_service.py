from collections import defaultdict
from datetime import datetime, timezone
from uuid import uuid4

from exam_prep.agent_core.models import AgentRunRequest
from exam_prep.agent_core.orchestrator import AgentOrchestrator, AgentOrchestratorRuntime
from exam_prep.core.config import get_settings
from exam_prep.core.exceptions import MaterialIngestionError
from exam_prep.llm.base import LLMClient
from exam_prep.ml.inference import QuestionQualityInferenceService
from exam_prep.repositories.exam_store import ExamStore
from exam_prep.repositories.material_store import MaterialStore
from exam_prep.repositories.vector_store import VectorStore
from exam_prep.schemas.materials import SourceSection
from exam_prep.schemas.ml import QuestionQualityLabel
from exam_prep.schemas.graph import ExamPrepGraphState, GroundingContext
from exam_prep.schemas.exam import (
    ConceptAnalytics,
    ExamBlueprint,
    ExamTopicCoverage,
    MockExamBundle,
    MockExamGenerationRequest,
    MockExamGenerationResponse,
    MockExamGradeRequest,
    MockExamGradeResponse,
    MockExamReviewResponse,
    StoredMockExamSession,
)
from exam_prep.schemas.quiz import (
    QuestionGradeResult,
    QuestionType,
    QuizQuestionOption,
    QuizQuestion,
    QuizSubmissionAnswer,
    StoredQuestionKey,
)
from exam_prep.schemas.retrieval import RetrievalHit
from exam_prep.services.question_pipeline import (
    QuestionValidationResult,
    SectionKnowledge,
    extractKnowledge,
    generateExamStyleQuestion,
    validateQuestion,
)
from exam_prep.services.retrieval_service import RetrievalService
from exam_prep.services.mock_exam_generation_service import MockExamGenerationService


class ExamService:
    def __init__(
        self,
        *,
        material_store: MaterialStore,
        vector_store: VectorStore,
        exam_store: ExamStore,
        question_quality_service: QuestionQualityInferenceService,
        llm_client: LLMClient | None = None,
        llm_model: str | None = None,
    ) -> None:
        self.material_store = material_store
        self.retrieval_service = RetrievalService(
            material_store=material_store,
            vector_store=vector_store,
        )
        self.exam_store = exam_store
        self.question_quality_service = question_quality_service
        self.llm_client: LLMClient | None = llm_client
        self.llm_model: str | None = llm_model
        self.settings = get_settings()
        self.agent_orchestrator = AgentOrchestrator(
            AgentOrchestratorRuntime(
                resolve_material_ids=self._resolve_material_ids,
                retrieve_grounding_context=self._retrieve_grounding_context,
                resolve_scope_source_ids=self._resolve_scope_source_ids,
                resolve_mastery=lambda state: ({}, []),
                enable_torch_inference=self.settings.enable_torch_inference,
            )
        )

    def generate_exam(self, request: MockExamGenerationRequest) -> MockExamGenerationResponse:
        blueprint = request.blueprint
        if request.source_exam_id:
            exam, source_answer_keys = MockExamGenerationService(
                material_store=self.material_store,
                exam_store=self.exam_store,
                question_quality_service=self.question_quality_service,
                llm_client=self.llm_client,
                llm_model=self.llm_model,
            ).generate_from_source(request)
            self._validate_answer_key_completeness(exam.questions, source_answer_keys)
            self.exam_store.save_exam_session(
                StoredMockExamSession(exam=exam, answer_keys=source_answer_keys)
            )
            return MockExamGenerationResponse(exam=exam)

        if not blueprint.topic_coverage:
            raise MaterialIngestionError("Exam blueprint must include topic coverage.")

        effective_module_ids = self._normalize_module_ids(request.module_id, request.module_ids)
        plan_state = self.agent_orchestrator.run(
            AgentRunRequest(
                intent="generate_mock_exam",
                course_id=request.course_id,
                module_id=request.module_id,
                module_ids=effective_module_ids,
            )
        )
        if effective_module_ids and not plan_state.scope_source_ids:
            raise MaterialIngestionError("No eligible sources found for the selected modules.")
        exam_id = uuid4().hex
        questions: list[QuizQuestion] = []
        answer_keys: list[StoredQuestionKey] = []
        style_prefix = self._style_prefix(blueprint.style_example)

        for topic_plan in blueprint.topic_coverage:
            topic_questions, topic_keys = self._generate_topic_questions(
                exam_id=exam_id,
                course_id=request.course_id,
                module_id=request.module_id,
                module_ids=effective_module_ids,
                blueprint=blueprint,
                topic_plan=topic_plan,
                retrieval_top_k=request.retrieval_top_k,
                selected_source_ids=plan_state.scope_source_ids,
                style_prefix=style_prefix,
                starting_index=len(questions),
            )
            questions.extend(topic_questions)
            answer_keys.extend(topic_keys)

        self._validate_answer_key_completeness(questions, answer_keys)

        exam = MockExamBundle(
            exam_id=exam_id,
            course_id=request.course_id,
            module_id=effective_module_ids[0] if len(effective_module_ids) == 1 else None,
            module_ids=effective_module_ids,
            created_at=datetime.now(timezone.utc).isoformat(),
            blueprint=blueprint,
            questions=questions,
        )
        self.exam_store.save_exam_session(
            StoredMockExamSession(exam=exam, answer_keys=answer_keys)
        )
        return MockExamGenerationResponse(exam=exam)

    def grade_exam(self, request: MockExamGradeRequest) -> MockExamGradeResponse:
        session = self.exam_store.get_exam_session(request.exam_id)
        if session is None:
            raise MaterialIngestionError("Mock exam session not found.")

        answer_keys = {key.question_id: key for key in session.answer_keys}
        submitted = {answer.question_id: answer for answer in request.answers}
        results: list[QuestionGradeResult] = []
        concept_scores: dict[str, list[float]] = defaultdict(list)

        for question in session.exam.questions:
            key = answer_keys.get(question.question_id)
            if key is None:
                raise MaterialIngestionError("Answer key is incomplete for this mock exam.")
            submission = submitted.get(question.question_id)
            result = self._grade_question(question, key, submission)
            results.append(result)
            concept_scores[result.concept].append(result.score)

        analytics = [
            ConceptAnalytics(
                concept=concept,
                question_count=len(scores),
                correct_count=sum(1 for score in scores if score >= 1.0),
                average_score=round(sum(scores) / len(scores), 4),
            )
            for concept, scores in sorted(concept_scores.items())
        ]

        overall_score = (
            round(sum(result.score for result in results) / len(results) * 100.0, 2)
            if results
            else 0.0
        )
        response = MockExamGradeResponse(
            exam_id=session.exam.exam_id,
            course_id=session.exam.course_id,
            module_id=session.exam.module_id,
            module_ids=session.exam.module_ids,
            completed_at=datetime.now(timezone.utc).isoformat(),
            overall_score=overall_score,
            analytics_by_concept=analytics,
            results=results,
        )
        self.exam_store.save_exam_session(
            session.model_copy(update={"grade_result": response})
        )
        return response

    def get_exam_review(self, exam_id: str) -> MockExamReviewResponse:
        session = self.exam_store.get_exam_session(exam_id)
        if session is None:
            raise MaterialIngestionError("Mock exam session not found.")
        return MockExamReviewResponse(exam=session.exam, grade_result=session.grade_result)

    def validate_answer_key_completeness(
        self,
        questions: list[QuizQuestion],
        answer_keys: list[StoredQuestionKey],
    ) -> None:
        self._validate_answer_key_completeness(questions, answer_keys)

    def _generate_topic_questions(
        self,
        *,
        exam_id: str,
        course_id: str,
        module_id: str | None,
        module_ids: list[str],
        blueprint: ExamBlueprint,
        topic_plan: ExamTopicCoverage,
        retrieval_top_k: int,
        selected_source_ids: list[str],
        style_prefix: str,
        starting_index: int,
    ) -> tuple[list[QuizQuestion], list[StoredQuestionKey]]:
        retrieval = self.retrieval_service.query(
            course_id=course_id,
            module_id=module_id,
            module_ids=module_ids,
            query=topic_plan.topic,
            top_k=self._bounded_retrieval_top_k(retrieval_top_k, topic_plan.question_count),
            selected_source_ids=selected_source_ids,
        )
        if not retrieval.hits:
            raise MaterialIngestionError(f'No relevant materials found for topic "{topic_plan.topic}".')

        questions: list[QuizQuestion] = []
        answer_keys: list[StoredQuestionKey] = []

        for local_index in range(topic_plan.question_count):
            hit = retrieval.hits[local_index % len(retrieval.hits)]
            question_number = starting_index + local_index + 1
            question_id = f"{exam_id}-q{question_number}"
            question_type = QuestionType.MCQ
            difficulty = self._targeted_difficulty(blueprint.target_difficulty, hit.chunk.text)
            section = self._as_source_section(hit)
            knowledge = extractKnowledge(section)
            question, correct_answer, correct_option_id = generateExamStyleQuestion(
                knowledge=knowledge,
                question_type=question_type,
                question_id=question_id,
                concept=topic_plan.topic,
                section_title=hit.chunk.section_title,
                difficulty=difficulty,
                citations=[hit.chunk],
                sequence_index=local_index + 1,
            )
            question.prompt = f"{style_prefix} {question.prompt}".strip()
            validation = validateQuestion(
                question,
                source_text=section.text,
                knowledge=knowledge,
                correct_answer=correct_answer,
            )
            key = StoredQuestionKey(
                question_id=question_id,
                question_type=question_type,
                concept=question.concept,
                correct_answer=correct_answer,
                correct_option_id=correct_option_id,
                expected_keywords=self._keywords_from_text(correct_answer),
                difficulty=difficulty,
                citations=[hit.chunk],
            )
            question = self._annotate_question_quality(question, validation)
            if self._failed_quality_gate(question):
                question, key = self._build_grounded_fallback_question(
                    question_id=question_id,
                    question_type=question_type,
                    topic=topic_plan.topic,
                    section_title=hit.chunk.section_title,
                    difficulty=difficulty,
                    hit=hit,
                    hits=retrieval.hits,
                    source_text=section.text,
                    knowledge=knowledge,
                    style_prefix=style_prefix,
                    sentence_offset=local_index,
                )
            questions.append(question)
            answer_keys.append(key)

        return questions, answer_keys

    def _bounded_retrieval_top_k(self, requested_top_k: int, question_count: int = 1) -> int:
        requested = max(1, requested_top_k, question_count)
        return min(requested, self.settings.max_chunks_per_retrieval)

    def _validate_answer_key_completeness(
        self,
        questions: list[QuizQuestion],
        answer_keys: list[StoredQuestionKey],
    ) -> None:
        if len(questions) != len(answer_keys):
            raise MaterialIngestionError("Answer key is incomplete for this mock exam.")

        keys_by_question = {key.question_id: key for key in answer_keys}
        for question in questions:
            key = keys_by_question.get(question.question_id)
            if key is None or not key.correct_answer.strip():
                raise MaterialIngestionError("Answer key is incomplete for this mock exam.")
            if question.question_type == QuestionType.MCQ and not key.correct_option_id:
                raise MaterialIngestionError("Answer key is incomplete for this mock exam.")

    def _annotate_question_quality(
        self,
        question: QuizQuestion,
        validation: QuestionValidationResult,
    ) -> QuizQuestion:
        try:
            quality = self.question_quality_service.score_generated_question(question)
        except Exception:  # noqa: BLE001
            question.quality_validation = None
            return question

        combined_score = round((quality.score + validation.score) / 2.0, 4)
        if validation.accepted:
            combined_score = max(0.55, combined_score)
        quality.score = combined_score
        quality.confidence = round(min(1.0, (quality.confidence + validation.score) / 2.0), 4)
        quality.accepted_for_delivery = validation.accepted and combined_score >= 0.5
        quality.notes = [*quality.notes, *validation.notes]
        if combined_score >= 0.7:
            quality.label = QuestionQualityLabel.HIGH_QUALITY
        elif combined_score >= 0.45:
            quality.label = QuestionQualityLabel.NEEDS_REVIEW
        else:
            quality.label = QuestionQualityLabel.LOW_QUALITY
        question.quality_validation = quality
        return question

    def _failed_quality_gate(self, question: QuizQuestion) -> bool:
        return (
            question.quality_validation is not None
            and not question.quality_validation.accepted_for_delivery
        )

    def _build_grounded_fallback_question(
        self,
        *,
        question_id: str,
        question_type: QuestionType,
        topic: str,
        section_title: str,
        difficulty: float,
        hit: RetrievalHit,
        hits: list[RetrievalHit],
        source_text: str,
        knowledge: SectionKnowledge,
        style_prefix: str,
        sentence_offset: int,
    ) -> tuple[QuizQuestion, StoredQuestionKey]:
        question_type = QuestionType.MCQ
        correct_answer = self._extract_topic_sentence(topic, source_text, sentence_offset)
        option_texts = [correct_answer, *self._build_distractor_texts(hits, correct_answer)]
        options = [
            QuizQuestionOption(option_id=option_id, text=option_text)
            for option_id, option_text in zip(["A", "B", "C", "D"], option_texts, strict=False)
        ]
        question = QuizQuestion(
            question_id=question_id,
            question_type=question_type,
            concept=topic,
            section_title=section_title,
            difficulty=difficulty,
            prompt=(
                f"{style_prefix} Which statement is best supported by the cited section "
                f"about {topic}?"
            ).strip(),
            options=options,
            citations=[hit.chunk],
            rationale=f"The cited section supports: {correct_answer}",
        )
        correct_option_id = "A"

        validation = validateQuestion(
            question,
            source_text=source_text,
            knowledge=knowledge,
            correct_answer=correct_answer,
        )
        question = self._annotate_question_quality(question, validation)
        if question.quality_validation is not None:
            question.quality_validation.notes = [
                "Regenerated due to weak PyTorch quality or grounding signal.",
                *question.quality_validation.notes,
            ]
        key = StoredQuestionKey(
            question_id=question_id,
            question_type=question_type,
            concept=topic,
            correct_answer=correct_answer,
            correct_option_id=correct_option_id,
            expected_keywords=self._keywords_from_text(correct_answer),
            difficulty=difficulty,
            citations=[hit.chunk],
        )
        return question, key

    def _resolve_material_ids(self, state: ExamPrepGraphState) -> list[str]:
        if state.course_id is None:
            return []
        material_ids: list[str] = []
        scoped_module_ids = state.requested_module_ids or ([state.module_id] if state.module_id else [])
        if not scoped_module_ids:
            return [
                record.material_id
                for record in self.material_store.list_records_by_course(state.course_id, None)
            ]
        for scoped_module_id in scoped_module_ids:
            material_ids.extend(
                record.material_id
                for record in self.material_store.list_records_by_course(
                    state.course_id,
                    scoped_module_id,
                )
            )
        return list(dict.fromkeys(material_ids))

    def _retrieve_grounding_context(self, state: ExamPrepGraphState) -> list[GroundingContext]:
        if state.course_id is None:
            return []
        scoped_module_ids = state.requested_module_ids or ([state.module_id] if state.module_id else [])
        documents = []
        if not scoped_module_ids:
            documents = self.material_store.list_parsed_documents_by_course(state.course_id, None)
        else:
            seen_material_ids: set[str] = set()
            for scoped_module_id in scoped_module_ids:
                for document in self.material_store.list_parsed_documents_by_course(
                    state.course_id,
                    scoped_module_id,
                ):
                    if document.record.material_id in seen_material_ids:
                        continue
                    seen_material_ids.add(document.record.material_id)
                    documents.append(document)
        scored_contexts: list[GroundingContext] = []
        for document in documents:
            for chunk in document.chunks:
                excerpt = " ".join(chunk.text.split())
                if not excerpt:
                    continue
                scored_contexts.append(
                    GroundingContext(
                        material_id=chunk.material_id,
                        excerpt=excerpt,
                        score=chunk.priority_score,
                    )
                )
        scored_contexts.sort(key=lambda item: item.score, reverse=True)
        contexts: list[GroundingContext] = []
        remaining_tokens = self.settings.max_agent_context_tokens
        for context in scored_contexts:
            words = context.excerpt.split()
            allowed_tokens = min(len(words), remaining_tokens)
            if allowed_tokens <= 0:
                break
            contexts.append(
                GroundingContext(
                    material_id=context.material_id,
                    excerpt=" ".join(words[:allowed_tokens]),
                    score=context.score,
                )
            )
            remaining_tokens -= allowed_tokens
            if len(contexts) >= self.settings.max_chunks_per_retrieval:
                break
        return contexts

    def _resolve_scope_source_ids(self, state: ExamPrepGraphState) -> list[str]:
        if state.course_id is None:
            return []
        return self.retrieval_service.resolve_scope_source_ids(
            course_id=state.course_id,
            module_id=state.module_id,
            module_ids=state.requested_module_ids,
        )

    def _normalize_module_ids(
        self,
        module_id: str | None,
        module_ids: list[str] | None,
    ) -> list[str]:
        normalized = [value.strip() for value in (module_ids or []) if value and value.strip()]
        if not normalized and module_id and module_id.strip():
            normalized = [module_id.strip()]
        return list(dict.fromkeys(normalized))

    def _as_source_section(self, hit: RetrievalHit) -> SourceSection:
        return SourceSection.model_validate(
            {
                **hit.chunk.model_dump(
                    exclude={
                        "chunk_id",
                        "token_count",
                        "workbook_block_type",
                        "workbook_module_number",
                        "learning_outcome_ids",
                        "module_quiz_question_numbers",
                        "module_quiz_answer_numbers",
                        "module_quiz_style_profiles",
                    }
                ),
                "text": hit.chunk.text,
            }
        )

    def _grade_question(
        self,
        question: QuizQuestion,
        key: StoredQuestionKey,
        submission: QuizSubmissionAnswer | None,
    ) -> QuestionGradeResult:
        if question.question_type == QuestionType.MCQ:
            submitted_option_id = submission.selected_option_id if submission is not None else None
            submitted_answer = self._resolve_mcq_answer_text(question, submitted_option_id)
            is_correct = submission is not None and submission.selected_option_id == key.correct_option_id
        else:
            submitted_option_id = None
            submitted_answer = (submission.answer_text or "").strip() if submission is not None else ""
            is_correct = self._keyword_overlap_ratio(submitted_answer, key.expected_keywords) >= 0.5

        citation_label = key.citations[0].citation_label if key.citations else "the cited material"
        if is_correct:
            explanation = (
                f'Correct. The response is supported by "{citation_label}". '
                f'Correct answer: {key.correct_answer}'
            )
        else:
            explanation = (
                f'Incorrect. The response is not supported by "{citation_label}". '
                f'Correct answer: {key.correct_answer}'
            )
        return QuestionGradeResult(
            question_id=question.question_id,
            question_type=question.question_type,
            concept=question.concept,
            is_correct=is_correct,
            grading_label="correct" if is_correct else "incorrect",
            score=1.0 if is_correct else 0.0,
            submitted_option_id=submitted_option_id,
            submitted_answer=submitted_answer,
            correct_option_id=key.correct_option_id,
            correct_answer=key.correct_answer,
            explanation=explanation,
            citations=key.citations,
        )

    def _resolve_mcq_answer_text(
        self,
        question: QuizQuestion,
        selected_option_id: str | None,
    ) -> str:
        if not selected_option_id:
            return ""
        for option in question.options:
            if option.option_id == selected_option_id:
                return option.text
        return selected_option_id

    def _extract_key_sentence(self, text: str, sentence_offset: int = 0) -> str:
        sentences = [
            sentence.strip()
            for sentence in text.replace("\n", " ").split(".")
            if sentence.strip()
        ]
        if not sentences:
            return text.strip()
        return f"{sentences[sentence_offset % len(sentences)]}."

    def _extract_topic_sentence(self, topic: str, text: str, sentence_offset: int = 0) -> str:
        sentences = [
            sentence.strip()
            for sentence in text.replace("\n", " ").split(".")
            if sentence.strip()
        ]
        if not sentences:
            return text.strip()

        topic_tokens = set(self._normalize_text(topic).split(" "))
        ordered_sentences = [
            sentence
            for _, _, sentence in sorted(
                (
                    (
                        -sum(
                            1
                            for token in topic_tokens
                            if token and token in self._normalize_text(sentence).split(" ")
                        ),
                        index,
                        sentence,
                    )
                    for index, sentence in enumerate(sentences)
                )
            )
        ]
        return f"{ordered_sentences[sentence_offset % len(ordered_sentences)]}."

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

        fallbacks = [
            "The topic is unrelated to the cited section.",
            "The material says the topic is optional and unsupported.",
            "The passage rejects the main idea described in the topic.",
        ]
        for fallback in fallbacks:
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

    def _normalize_text(self, text: str) -> str:
        cleaned = text.lower()
        for char in [".", ",", ";", ":", "!", "?", "(", ")", '"', "'"]:
            cleaned = cleaned.replace(char, " ")
        return " ".join(cleaned.split())

    def _keyword_overlap_ratio(self, submitted_answer: str, expected_keywords: list[str]) -> float:
        normalized_answer = self._normalize_text(submitted_answer)
        if not normalized_answer or not expected_keywords:
            return 0.0
        hits = sum(1 for keyword in expected_keywords if keyword in normalized_answer)
        return hits / len(expected_keywords)

    def _style_prefix(self, style_example: str) -> str:
        first_line = style_example.strip().splitlines()[0].strip()
        return first_line if first_line.endswith(":") else f"{first_line}:"

    def _targeted_difficulty(self, target_difficulty: float, text: str) -> float:
        token_count = len(self._normalize_text(text).split(" "))
        natural = min(1.0, 0.3 + (token_count / 40.0))
        return round((natural + target_difficulty) / 2.0, 2)
