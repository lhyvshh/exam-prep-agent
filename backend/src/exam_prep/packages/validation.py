from collections import Counter
from collections.abc import Mapping
import re
from typing import assert_never

from pydantic import Field

from .curriculum import CurriculumSnapshot
from .frm_policy import FRM_PART_I_POLICY
from .models import (
    ExamBlueprintMode,
    OfflineMockExam,
    PackageCreateRequest,
    PackageKind,
    PackageModel,
    PackageValidationReport,
    ValidationFinding,
    ValidationSeverity,
)


class SourceExamQuestionProfile(PackageModel):
    question_number: int = Field(ge=1, le=500)
    choice_count: int = Field(ge=2, le=8)
    topic: str = Field(min_length=1)
    learning_objective: str = Field(min_length=1)
    question_type: str = Field(min_length=1)
    difficulty: str = Field(min_length=1)


class SourceExamProfile(PackageModel):
    source_exam_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    questions: tuple[SourceExamQuestionProfile, ...] = Field(min_length=1, max_length=500)


class PackageBuildSnapshot(PackageModel):
    package_id: str
    version: int
    title: str
    created_at: str
    configuration: PackageCreateRequest
    curriculum: CurriculumSnapshot
    mock_exams: tuple[OfflineMockExam, ...]
    source_exam_profile: SourceExamProfile | None = None
    model_metadata: dict[str, str] = Field(default_factory=dict)
    prompt_versions: dict[str, str] = Field(default_factory=dict)


class PackageValidator:
    def validate(self, snapshot: PackageBuildSnapshot) -> PackageValidationReport:
        findings: list[ValidationFinding] = []
        self._validate_curriculum(snapshot, findings)
        self._validate_exam_inventory(snapshot, findings)
        self._validate_questions(snapshot, findings)
        if snapshot.configuration.exam_blueprint_mode == ExamBlueprintMode.FRM_PART_I:
            self._validate_frm_blueprint(snapshot, findings)
        else:
            self._validate_source_blueprint(snapshot, findings)
        return PackageValidationReport(
            package_id=snapshot.package_id,
            version=snapshot.version,
            passed=not any(item.severity == ValidationSeverity.ERROR for item in findings),
            created_at=snapshot.created_at,
            findings=tuple(findings),
        )

    def _validate_curriculum(
        self,
        snapshot: PackageBuildSnapshot,
        findings: list[ValidationFinding],
    ) -> None:
        match snapshot.configuration.package_kind:
            case PackageKind.COMPLETE:
                if (
                    snapshot.configuration.exam_blueprint_mode == ExamBlueprintMode.FRM_PART_I
                    and len(snapshot.curriculum.books) != 4
                ):
                    self._error(
                        findings,
                        "source_book_count",
                        "Complete FRM Part I packages must contain exactly four source books.",
                        {"expected": "4", "actual": str(len(snapshot.curriculum.books))},
                    )
            case PackageKind.STUDY_CARDS | PackageKind.MOCK_EXAM:
                pass
            case unreachable:
                assert_never(unreachable)
        if not snapshot.curriculum.books:
            self._error(
                findings,
                "source_books_empty",
                "Offline packages require at least one source book.",
                {},
            )
        if snapshot.configuration.package_kind == PackageKind.MOCK_EXAM:
            return
        for book in snapshot.curriculum.books:
            if not book.concepts:
                self._error(
                    findings,
                    "book_concepts_empty",
                    f"Source book {book.material_id} must contain at least one key concept.",
                    {"material_id": book.material_id},
                )
            for concept in book.concepts:
                if not concept.title or not concept.learning_outcome:
                    self._error(
                        findings,
                        "concept_empty",
                        f"Concept {concept.concept_id} must contain a title and learning outcome.",
                        {"concept_id": concept.concept_id},
                    )
                if len(concept.flashcards) != snapshot.configuration.cards_per_concept:
                    self._error(
                        findings,
                        "concept_card_count",
                        (
                            f"Concept {concept.concept_id} must contain exactly "
                            f"{snapshot.configuration.cards_per_concept} grounded cards."
                        ),
                        {
                            "concept_id": concept.concept_id,
                            "expected": str(snapshot.configuration.cards_per_concept),
                            "count": str(len(concept.flashcards)),
                        },
                    )
                if not concept.source_pages or not concept.source_anchors:
                    self._error(
                        findings,
                        "concept_source",
                        f"Concept {concept.concept_id} is missing book source linkage.",
                        {"concept_id": concept.concept_id},
                    )
        if snapshot.curriculum.rejected_flashcard_count:
            self._error(
                findings,
                "ungrounded_flashcards",
                "One or more flashcards were rejected because source linkage was incomplete.",
                {"count": str(snapshot.curriculum.rejected_flashcard_count)},
            )
        formula_count = sum(len(book.formulas) for book in snapshot.curriculum.books)
        if snapshot.configuration.include_formula_review and formula_count == 0:
            self._error(
                findings,
                "formula_review_empty",
                "Formula review was requested but no grounded formulas are available.",
                {},
            )
        if snapshot.curriculum.rejected_formula_count:
            self._error(
                findings,
                "ungrounded_formulas",
                "One or more formulas were rejected because source linkage was incomplete.",
                {"count": str(snapshot.curriculum.rejected_formula_count)},
            )

    def _validate_exam_inventory(
        self,
        snapshot: PackageBuildSnapshot,
        findings: list[ValidationFinding],
    ) -> None:
        if len(snapshot.mock_exams) != snapshot.configuration.mock_exam_count:
            self._error(
                findings,
                "mock_exam_count",
                "The package does not contain the configured number of mock exams.",
                {
                    "expected": str(snapshot.configuration.mock_exam_count),
                    "actual": str(len(snapshot.mock_exams)),
                },
            )
        for exam in snapshot.mock_exams:
            if len(exam.questions) != snapshot.configuration.questions_per_exam:
                self._error(
                    findings,
                    "exam_question_count",
                    f"Exam {exam.exam_id} does not contain the configured question count.",
                    {
                        "exam_id": exam.exam_id,
                        "expected": str(snapshot.configuration.questions_per_exam),
                        "actual": str(len(exam.questions)),
                    },
                )

    def _validate_questions(
        self,
        snapshot: PackageBuildSnapshot,
        findings: list[ValidationFinding],
    ) -> None:
        prompt_owners: dict[str, str] = {}
        template_owners: dict[str, tuple[str, str]] = {}
        answer_owners: dict[str, str] = {}
        question_ids: set[str] = set()
        for exam in snapshot.mock_exams:
            for question in exam.questions:
                if question.question_id in question_ids:
                    self._duplicate(findings, "question_id_duplicate", question.question_id)
                question_ids.add(question.question_id)
                prompt = self._normalize(question.prompt)
                if owner := prompt_owners.get(prompt):
                    self._duplicate(
                        findings, "question_duplicate", f"{owner}, {question.question_id}"
                    )
                prompt_owners[prompt] = question.question_id
                template = self._template_fingerprint(question.prompt)
                if prior := template_owners.get(template):
                    owner, owner_prompt = prior
                    if owner_prompt != prompt:
                        self._duplicate(
                            findings,
                            "question_template_duplicate",
                            f"{owner}, {question.question_id}",
                        )
                else:
                    template_owners[template] = (question.question_id, prompt)
                choices = [self._normalize(choice) for choice in question.choices]
                if len(set(choices)) != len(choices):
                    self._error(
                        findings,
                        "choice_duplicate",
                        f"Question {question.question_id} contains repeated answer choices.",
                        {"question_id": question.question_id},
                    )
                answer = choices[question.correct_choice_index]
                if owner := answer_owners.get(answer):
                    self._duplicate(
                        findings, "answer_duplicate", f"{owner}, {question.question_id}"
                    )
                answer_owners[answer] = question.question_id
                if not (question.source_excerpt or "").strip():
                    self._error(
                        findings,
                        "question_source_evidence",
                        f"Question {question.question_id} has no persisted source evidence.",
                        {"question_id": question.question_id},
                    )
                if not question.quality_model_source.casefold().startswith("pytorch"):
                    self._error(
                        findings,
                        "question_quality_source",
                        f"Question {question.question_id} was not validated by PyTorch.",
                        {
                            "question_id": question.question_id,
                            "model_source": question.quality_model_source,
                        },
                    )
                if not question.quality_accepted:
                    self._error(
                        findings,
                        "question_quality",
                        f"Question {question.question_id} failed the PyTorch quality gate.",
                        {
                            "question_id": question.question_id,
                            "score": str(question.quality_score),
                        },
                    )
                if question.quality_label != "high_quality":
                    self._error(
                        findings,
                        "question_quality_label",
                        f"Question {question.question_id} is not classified as high quality.",
                        {
                            "question_id": question.question_id,
                            "label": question.quality_label,
                        },
                    )
                if question.quality_confidence < 0.5:
                    self._error(
                        findings,
                        "question_quality_confidence",
                        f"Question {question.question_id} has insufficient quality confidence.",
                        {
                            "question_id": question.question_id,
                            "confidence": str(question.quality_confidence),
                        },
                    )
                if question.quality_score < 0.7:
                    self._error(
                        findings,
                        "question_quality_low",
                        f"Question {question.question_id} is below the delivery quality threshold.",
                        {
                            "question_id": question.question_id,
                            "score": str(question.quality_score),
                            "label": question.quality_label,
                        },
                    )

    def _validate_frm_blueprint(
        self,
        snapshot: PackageBuildSnapshot,
        findings: list[ValidationFinding],
    ) -> None:
        source_defined = snapshot.source_exam_profile is not None
        remaining_difficulties = list(FRM_PART_I_POLICY.difficulty_counts)
        for exam in snapshot.mock_exams:
            actual_domains = Counter(question.domain for question in exam.questions)
            actual_difficulties = Counter(question.difficulty for question in exam.questions)
            self._require_counts(
                findings,
                "frm_domain_allocation",
                exam.exam_id,
                actual_domains,
                FRM_PART_I_POLICY.domain_weights,
            )
            if not source_defined:
                profile_index = next(
                    (
                        index
                        for index, difficulties in enumerate(remaining_difficulties)
                        if dict(actual_difficulties) == dict(difficulties)
                    ),
                    None,
                )
                if profile_index is None:
                    self._error(
                        findings,
                        "frm_difficulty_allocation",
                        f"Exam {exam.exam_id} does not match an unused FRM difficulty profile.",
                        {
                            "exam_id": exam.exam_id,
                            "difficulties": str(dict(actual_difficulties)),
                        },
                    )
                else:
                    remaining_difficulties.pop(profile_index)
                self._require_counts(
                    findings,
                    "question_type_allocation",
                    exam.exam_id,
                    Counter(question.question_type for question in exam.questions),
                    FRM_PART_I_POLICY.question_type_counts,
                )
        if source_defined:
            self._validate_source_blueprint(snapshot, findings)

    def _validate_source_blueprint(
        self,
        snapshot: PackageBuildSnapshot,
        findings: list[ValidationFinding],
    ) -> None:
        if not snapshot.mock_exams:
            return
        profile = snapshot.source_exam_profile
        if profile is None:
            self._error(
                findings,
                "source_exam_profile_missing",
                "Source-defined packages require the selected exam's parsed blueprint.",
                {},
            )
            return
        expected_by_number = {
            question.question_number: question for question in profile.questions
        }
        for exam in snapshot.mock_exams:
            actual_numbers = [question.question_number for question in exam.questions]
            if actual_numbers != list(expected_by_number):
                self._error(
                    findings,
                    "source_exam_numbering",
                    f"Exam {exam.exam_id} does not preserve the source exam's question order.",
                    {
                        "exam_id": exam.exam_id,
                        "expected": str(list(expected_by_number)),
                        "actual": str(actual_numbers),
                    },
                )
                continue
            for question in exam.questions:
                expected = expected_by_number[question.question_number]
                actual = (
                    len(question.choices),
                    question.domain,
                    question.learning_objective,
                    question.question_type,
                    question.difficulty,
                )
                required = (
                    expected.choice_count,
                    expected.topic,
                    expected.learning_objective,
                    expected.question_type,
                    expected.difficulty,
                )
                if actual != required:
                    self._error(
                        findings,
                        "source_exam_question_profile",
                        (
                            f"Question {question.question_number} does not preserve its source "
                            "choice count, topic, learning objective, question type, and difficulty."
                        ),
                        {
                            "question_id": question.question_id,
                            "expected": str(required),
                            "actual": str(actual),
                        },
                    )

    def _require_counts(
        self,
        findings: list[ValidationFinding],
        code: str,
        exam_id: str,
        actual: Counter[str],
        expected: Mapping[str, int],
    ) -> None:
        expected_counts = dict(expected)
        if dict(actual) != expected_counts:
            self._error(
                findings,
                code,
                f"Exam {exam_id} does not match the required {code.replace('_', ' ')}.",
                {"exam_id": exam_id, "expected": str(expected_counts), "actual": str(dict(actual))},
            )

    @staticmethod
    def _duplicate(findings: list[ValidationFinding], code: str, identity: str) -> None:
        PackageValidator._error(
            findings,
            code,
            f"Duplicate package content detected: {identity}.",
            {"identity": identity},
        )

    @staticmethod
    def _error(
        findings: list[ValidationFinding],
        code: str,
        message: str,
        evidence: dict[str, str],
    ) -> None:
        findings.append(
            ValidationFinding(
                code=code,
                severity=ValidationSeverity.ERROR,
                message=message,
                evidence=evidence,
            )
        )

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(value.casefold().split())

    @staticmethod
    def _template_fingerprint(value: str) -> str:
        normalized = value.casefold()
        normalized = re.sub(r"\b(?:case|scenario)\s+\d+(?:\.\d+)*\b", " ", normalized)
        normalized = re.sub(r"\d+(?:\.\d+)?", " number ", normalized)
        return " ".join(re.sub(r"[^a-z0-9\s]", " ", normalized).split())
