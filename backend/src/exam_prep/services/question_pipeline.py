from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from exam_prep.schemas.materials import ContentLabel, SectionKind, SourceChunk, SourceSection
from exam_prep.schemas.quiz import QuestionType, QuizQuestion, QuizQuestionOption

ADMIN_KEYWORDS = [
    "office hours",
    "logistics",
    "schedule",
    "calendar",
    "announcement",
    "canvas",
    "attendance",
    "contact",
    "email",
    "zoom",
    "syllabus",
    "gradebook",
    "exam date",
    "due date",
    "week of",
    "no class",
    "thanksgiving break",
    "final exam",
]
TESTABLE_KEYWORDS = [
    "definition",
    "concept",
    "example",
    "examples",
    "formula",
    "method",
    "algorithm",
    "principle",
    "variable",
    "variables",
    "expression",
    "statement",
    "loop",
    "loops",
    "condition",
    "function",
    "class",
    "type",
    "types",
    "gradient",
    "descent",
    "learning rate",
    "parameter",
    "parameters",
    "step size",
    "compare",
    "difference",
    "because",
    "means",
    "refers to",
    "risk",
    "risk management",
    "expected loss",
    "unexpected loss",
    "market risk",
    "credit risk",
    "liquidity",
    "operational risk",
    "governance",
    "regulation",
    "valuation",
    "interest rate",
    "foreign exchange",
    "hedge",
    "derivative",
    "portfolio",
    "volatility",
]
ACADEMIC_SIGNAL_RE = re.compile(
    r"\b(?:variable|variables|expression|expressions|statement|statements|function|functions|method|"
    r"class|type conversion|data type|operator|comparison|logical|boolean|string|integer|float|"
    r"loop|iteration|list|dictionary|pandas|syntax|return|argument|parameter|algorithm|formula|"
    r"gradient|learning rate|objective|convergence|descent|ascent|risk|risk management|"
    r"expected loss|unexpected loss|market risk|credit risk|liquidity|operational risk|"
    r"governance|regulation|valuation|interest rate|foreign exchange|hedge|derivative|"
    r"portfolio|volatility)\b",
    re.IGNORECASE,
)
CODE_SIGNAL_RE = re.compile(
    r"(?:==|!=|<=|>=|\b[a-z_][a-z0-9_]*\s*\(|\b(?:int|float|str|print|input|type|len|range)\s*\()",
    re.IGNORECASE,
)
WEAK_KEYWORDS = [
    "reading",
    "summary",
    "overview",
    "intro",
    "introduction",
    "topic",
]
GENERIC_SECTION_TITLES = {
    "overview",
    "introduction",
    "notes",
    "optimization notes",
    "lecture notes",
    "session notes",
    "continued",
    "lecture",
    "slide",
    "slides",
    "page",
    "session content",
    "untitled section",
    "document overview",
    "python basics",
    "course introduction",
    "title page",
}
DATE_ONLY_RE = re.compile(
    r"^(?:mon|tue|wed|thu|fri|sat|sun)?\.?,?\s*"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)?\.?\s*"
    r"\d{1,2}(?:[/-]\d{1,2})?(?:[/-]\d{2,4})?$",
    re.IGNORECASE,
)
PAGE_JUNK_RE = re.compile(r"^(?:page\s+\d+|\d+\s*/\s*\d+|\d+)$", re.IGNORECASE)


@dataclass(slots=True)
class CleanedTextResult:
    cleaned_text: str
    kept_lines: list[str]
    removed_lines: list[str]
    duplicate_ratio: float


class KnowledgeConcept(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    definition: str
    key_points: list[str] = Field(default_factory=list)
    common_confusions: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    testable_facts: list[str] = Field(default_factory=list)


class SectionKnowledge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_title: str
    content_label: ContentLabel
    concepts: list[KnowledgeConcept] = Field(default_factory=list)
    summary: str


class QuestionValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accepted: bool
    score: float = Field(ge=0.0, le=1.0)
    notes: list[str] = Field(default_factory=list)
    rejection_reason: str | None = None


class GeneratedExamQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str
    options: list[str] = Field(default_factory=list)
    correct_answer: str
    correct_option_id: str | None = None
    rationale: str
    incorrect_rationales: list[str] = Field(default_factory=list)


@dataclass(slots=True)
class _ModuleQuizExample:
    number: int
    prompt: str
    options: dict[str, str]
    correct_option_id: str | None = None
    rationale: str = ""


@dataclass(slots=True)
class _WorkbookQuestionFact:
    subject: str
    prompt: str
    answer: str
    rationale: str


METADATA_LEAK_PATTERNS = [
    re.compile(r"\b(?:page|pages|slide|slides)\s+\d+(?:-\d+)?\b", re.IGNORECASE),
    re.compile(r"\b[a-z0-9_\-]+\.(?:pdf|pptx|docx|txt)\b", re.IGNORECASE),
    re.compile(r"\bcitation label\b", re.IGNORECASE),
    re.compile(r"\bsource excerpt\b", re.IGNORECASE),
]
LOW_QUALITY_QUIZ_PHRASES = [
    "the best response depends",
    "all risks should be eliminated",
    "the same response works for every exposure",
    "risk management ignores implementation tradeoffs",
    "module quiz answer key",
    "which statement best describes firms",
    "which statement best describes it",
    "which statement best describes they",
]

MODULE_QUIZ_HEADING_RE = re.compile(r"\bMODULE\s+QUIZ\s+(?P<number>\d+\.\d+)\b", re.IGNORECASE)
ANSWER_KEY_HEADING_RE = re.compile(r"\bANSWER\s+KEY\s+FOR\s+MODULE\s+QUIZZES\b", re.IGNORECASE)


def hasWorkbookModuleQuiz(text: str) -> bool:
    return MODULE_QUIZ_HEADING_RE.search(text or "") is not None


def workbookStyleExcerpt(text: str, *, max_chars: int = 3600) -> str:
    normalized = text or ""
    quiz_match = MODULE_QUIZ_HEADING_RE.search(normalized)
    if quiz_match is None:
        return " ".join(normalized.split())[:max_chars]
    start = max(0, quiz_match.start() - 1200)
    answer_match = ANSWER_KEY_HEADING_RE.search(normalized, quiz_match.end())
    if answer_match is not None:
        end = min(len(normalized), answer_match.end() + 2400)
    else:
        end = min(len(normalized), quiz_match.end() + 3000)
    excerpt = " ".join(normalized[start:end].split())
    return excerpt[:max_chars]


def workbookStyleProfiles(text: str) -> list[str]:
    examples = _parse_module_quiz_examples(text)
    profiles: set[str] = set()
    for example in examples:
        profiles.update(_workbook_style_profile(example.prompt))
    if not profiles:
        profiles.update(_workbook_style_profile(text))
    return sorted(profiles)


def cleanExtractedText(
    text: str,
    *,
    title: str = "",
) -> CleanedTextResult:
    raw_lines = [line.strip() for line in text.splitlines()]
    normalized_lines: list[str] = []
    removed_lines: list[str] = []
    fingerprints: list[str] = []
    duplicate_count = 0

    for raw_line in raw_lines:
        line = _normalize_line(raw_line)
        if not line:
            continue
        if _should_remove_line(line, title=title):
            removed_lines.append(line)
            continue
        fingerprint = _fingerprint(line)
        if any(_near_duplicate(fingerprint, previous) for previous in fingerprints):
            duplicate_count += 1
            removed_lines.append(line)
            continue
        normalized_lines.append(line)
        fingerprints.append(fingerprint)

    duplicate_ratio = duplicate_count / max(len([line for line in raw_lines if line.strip()]), 1)
    return CleanedTextResult(
        cleaned_text="\n".join(normalized_lines).strip(),
        kept_lines=normalized_lines,
        removed_lines=removed_lines,
        duplicate_ratio=round(duplicate_ratio, 4),
    )


def classifyChunk(section: SourceSection) -> ContentLabel:
    text = f"{section.section_title}\n{section.text}".lower()
    admin_hits = sum(1 for keyword in ADMIN_KEYWORDS if keyword in text)
    testable_hits = sum(1 for keyword in TESTABLE_KEYWORDS if keyword in text)
    weak_hits = sum(1 for keyword in WEAK_KEYWORDS if keyword in text)
    sentence_count = len(_extract_sentences(section.text))
    month_hits = len(re.findall(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)\b", text))
    teaching_signal = _teaching_signal_score(section.text)

    if admin_hits >= 2 and month_hits >= 2:
        return ContentLabel.ADMINISTRATIVE_CONTENT
    if admin_hits >= 2 and testable_hits == 0:
        return ContentLabel.ADMINISTRATIVE_CONTENT
    if admin_hits >= 1 and testable_hits == 0 and sentence_count <= 4:
        return ContentLabel.ADMINISTRATIVE_CONTENT
    if admin_hits == 0 and teaching_signal >= 2 and any(
        token in text for token in ["updates", "controls", "stores", "returns", "creates", "uses", "means"]
    ):
        return ContentLabel.TESTABLE_CONTENT
    if sentence_count < 2 and testable_hits == 0:
        return ContentLabel.WEAK_CONTENT
    if testable_hits == 0 and weak_hits > 0:
        return ContentLabel.WEAK_CONTENT
    if testable_hits > 0 and (teaching_signal >= 1 or sentence_count >= 2):
        return ContentLabel.TESTABLE_CONTENT
    if len(section.text.split()) >= 35 and teaching_signal >= 2:
        return ContentLabel.TESTABLE_CONTENT
    return ContentLabel.WEAK_CONTENT


def buildSemanticSections(
    sections: list[SourceSection],
    *,
    file_name: str,
    content_type: str,
    file_suffix: str,
) -> list[SourceSection]:
    prepared: list[SourceSection] = []
    for index, section in enumerate(sections, start=1):
        cleaned = cleanExtractedText(section.text, title=section.section_title)
        if not cleaned.cleaned_text:
            continue
        semantic_title = _derive_semantic_title(
            cleaned.kept_lines,
            fallback_title=section.section_title,
            file_name=file_name,
            section_index=index,
        )
        updated = section.model_copy(
            update={
                "section_title": semantic_title,
                "text": cleaned.cleaned_text,
                "citation_label": f"{section.file_name} | {semantic_title}",
            }
        )
        content_label = classifyChunk(updated)
        if _should_drop_semantic_section(updated, content_label, file_suffix=file_suffix):
            continue
        section_kind = _kind_for_label(content_label, file_suffix=file_suffix)
        updated = updated.model_copy(
            update={
                "content_label": content_label,
                "section_kind": section_kind,
                "priority_score": _priority_score(updated, content_label),
                "is_default": content_label == ContentLabel.TESTABLE_CONTENT,
            }
        )
        prepared.append(updated)

    if not prepared:
        return []

    if file_suffix == ".pdf" and _should_build_single_session(prepared):
        return [_build_session_section(prepared, file_name=file_name, content_type=content_type)]

    if file_suffix == ".pdf":
        prepared = _aggregate_pdf_sections(prepared, file_name=file_name, content_type=content_type)

    return _merge_semantic_neighbors(prepared, file_name=file_name)


def extractKnowledge(section: SourceSection) -> SectionKnowledge:
    sentences = _extract_sentences(section.text)
    if not sentences:
        return SectionKnowledge(
            section_title=section.section_title,
            content_label=section.content_label,
            concepts=[],
            summary="No usable teaching content was extracted.",
        )

    concept_name = _best_concept_name(section.section_title, sentences)
    definition = _pick_definition(sentences, concept_name)
    key_points = _unique_trimmed(
        _pick_key_points(sentences, skip=definition),
        limit=4,
    )
    confusions = _unique_trimmed(_pick_confusions(sentences, concept_name), limit=3)
    examples = _unique_trimmed(_pick_examples(sentences), limit=3)
    facts = _unique_trimmed(_pick_testable_facts(sentences, definition, key_points), limit=4)
    summary = key_points[0] if key_points else definition or (facts[0] if facts else sentences[0])

    return SectionKnowledge(
        section_title=section.section_title,
        content_label=section.content_label,
        summary=_limit_words(summary, 22),
        concepts=[
            KnowledgeConcept(
                name=concept_name,
                definition=_limit_words(definition or sentences[0], 28),
                key_points=[_limit_words(point, 22) for point in key_points],
                common_confusions=[_limit_words(item, 18) for item in confusions],
                examples=[_limit_words(item, 22) for item in examples],
                testable_facts=[_limit_words(item, 20) for item in facts],
            )
        ],
    )


def generateExamStyleQuestion(
    *,
    knowledge: SectionKnowledge,
    question_type: QuestionType,
    question_id: str,
    concept: str,
    section_title: str,
    difficulty: float,
    citations: list[SourceChunk],
    sequence_index: int,
) -> tuple[QuizQuestion, str, str | None]:
    concept_knowledge = knowledge.concepts[0] if knowledge.concepts else None
    concept_name = concept_knowledge.name if concept_knowledge else concept or section_title
    workbook_question = _build_workbook_module_quiz_question(
        question_id=question_id,
        concept=concept_name,
        section_title=section_title,
        difficulty=difficulty,
        citations=citations,
        sequence_index=sequence_index,
    )
    if workbook_question is not None:
        return workbook_question

    if question_type == QuestionType.SHORT_ANSWER:
        focus_candidates = (
            concept_knowledge.testable_facts
            if concept_knowledge and concept_knowledge.testable_facts
            else concept_knowledge.key_points
            if concept_knowledge
            else []
        )
        focus = (
            focus_candidates[(sequence_index - 1) % len(focus_candidates)]
            if focus_candidates
            else concept_knowledge.definition
            if concept_knowledge
            else knowledge.summary
        )
        prompt = (
            f"In one or two sentences, explain {concept_name.lower()}."
            if not focus
            else f"Briefly explain {concept_name.lower()} and include {focus.lower()}."
        )
        question = QuizQuestion(
            question_id=question_id,
            question_type=question_type,
            concept=cleanSectionDisplayTitle(concept_name),
            section_title=cleanSectionDisplayTitle(section_title),
            difficulty=difficulty,
            prompt=sanitizeQuestionText(_limit_words(prompt, 18)),
            options=[],
            citations=list(citations),
            rationale=sanitizeExplanationText(
                f"Correct answer: {_limit_words((focus or knowledge.summary), 24)}."
            ),
        )
        return question, sanitizeOptionText(_limit_words(focus or knowledge.summary, 24)), None

    exam_question = _build_mcq_from_knowledge(knowledge, sequence_index)
    options = [
        QuizQuestionOption(option_id=option_id, text=sanitizeOptionText(option_text))
        for option_id, option_text in zip(["A", "B", "C", "D"], exam_question.options, strict=True)
    ]
    question = QuizQuestion(
        question_id=question_id,
        question_type=question_type,
        concept=cleanSectionDisplayTitle(concept_name),
        section_title=cleanSectionDisplayTitle(section_title),
        difficulty=difficulty,
        prompt=sanitizeQuestionText(exam_question.prompt),
        options=options,
        citations=list(citations),
        rationale=sanitizeExplanationText(exam_question.rationale),
    )
    return question, sanitizeOptionText(exam_question.correct_answer), exam_question.correct_option_id


def _build_workbook_module_quiz_question(
    *,
    question_id: str,
    concept: str,
    section_title: str,
    difficulty: float,
    citations: list[SourceChunk],
    sequence_index: int,
) -> tuple[QuizQuestion, str, str | None] | None:
    source_text = "\n".join(getattr(citation, "text", "") or "" for citation in citations)
    examples = _module_quiz_examples_from_citations(citations)
    if not examples:
        return None

    variant_round = (sequence_index - 1) // len(examples)
    example = examples[(sequence_index - 1) % len(examples)]
    should_rewrite_original = _should_rewrite_module_quiz_example(example=example, source_text=source_text)
    if variant_round > 0 or should_rewrite_original:
        extra_question = _build_workbook_concept_application_question(
            question_id=question_id,
            concept=concept,
            section_title=section_title,
            difficulty=difficulty,
            citations=citations,
            source_text=source_text,
            sequence_index=sequence_index,
            examples=examples,
        )
        if extra_question is not None:
            return extra_question
    else:
        fresh_question = _build_workbook_concept_application_question(
            question_id=question_id,
            concept=concept,
            section_title=section_title,
            difficulty=difficulty,
            citations=citations,
            source_text=source_text,
            sequence_index=sequence_index,
            examples=examples,
        )
        if fresh_question is not None:
            return fresh_question

    return None


def _build_workbook_concept_application_question(
    *,
    question_id: str,
    concept: str,
    section_title: str,
    difficulty: float,
    citations: list[SourceChunk],
    source_text: str,
    sequence_index: int,
    examples: list[_ModuleQuizExample] | None = None,
    ) -> tuple[QuizQuestion, str, str | None] | None:
    clean_concept = cleanSectionDisplayTitle(concept)
    lowered = source_text.lower()
    if any(token in lowered for token in ["capital asset pricing model", "capm", "arbitrage pricing theory", "apt"]):
        return _build_workbook_asset_pricing_question(
            question_id=question_id,
            concept=clean_concept,
            section_title=section_title,
            difficulty=difficulty,
            citations=citations,
            sequence_index=sequence_index,
        )

    fact_question = _build_workbook_fact_question(
        question_id=question_id,
        concept=clean_concept,
        section_title=section_title,
        difficulty=difficulty,
        citations=citations,
        source_text=source_text,
        sequence_index=sequence_index,
        examples=examples or [],
    )
    if fact_question is not None:
        return fact_question

    if (
        "short hedge" in lowered
        and "basis risk" in lowered
        and ("cross hedge" in lowered or "futures" in lowered)
    ):
        prompts = [
            "Which statement best describes basis risk in a hedge?",
            "Which statement best describes a cross hedge?",
            "Which statement best describes a futures hedge tradeoff?",
        ]
        raw_options = [
            "Basis risk remains when spot and futures prices do not move together",
            "A short hedge eliminates all upside from every price increase",
            "A cross hedge uses the exact asset with no remaining mismatch",
            "Futures hedges remove basis risk whenever contract maturities match",
        ]
        rationale = (
            "The module content says basis risk remains when spot and futures prices do not "
            "move together, especially for related-asset hedges."
        )
    elif all(token in lowered for token in ["accept", "avoid", "mitigate", "transfer"]):
        prompts = [
            "Which statement best summarizes the risk-management strategy choices?",
            "An analyst compares risk responses. Which statement is most accurate?",
            "Which choice correctly describes how firms can respond to risk?",
        ]
        raw_options = [
            "Firms can accept, avoid, mitigate, or transfer risk",
            "Firms should always avoid every identified risk",
            "Mitigating risk means ignoring the exposure",
            "Risk transfer eliminates all counterparty risk",
        ]
        rationale = (
            "The key concept lists four risk responses: accepting, avoiding, mitigating, "
            "or transferring risk."
        )
    elif any(token in lowered for token in ["forward contracts", "futures contracts", "options", "swaps"]):
        prompts = [
            "Which statement about choosing hedge instruments is most accurate?",
            "A firm compares hedge tools for a customized exposure. Which statement is correct?",
            "Which choice best reflects the module quiz logic for hedging tools?",
        ]
        raw_options = [
            "Customization matters when selecting a hedge instrument",
            "Futures always provide the most customized hedge",
            "Every hedge instrument removes basis risk equally",
            "Options and swaps are unrelated to risk transfer",
        ]
        rationale = "The module quiz emphasizes matching the hedge tool to the exposure and basis-risk needs."
    else:
        return None

    rotation = (sequence_index - 1) % len(raw_options)
    ordered_options = raw_options[rotation:] + raw_options[:rotation]
    correct_option_id = ["A", "B", "C", "D"][ordered_options.index(raw_options[0])]
    options = [
        QuizQuestionOption(option_id=option_id, text=sanitizeOptionText(option_text))
        for option_id, option_text in zip(["A", "B", "C", "D"], ordered_options, strict=True)
    ]
    question = QuizQuestion(
        question_id=question_id,
        question_type=QuestionType.MCQ,
        concept=clean_concept,
        section_title=cleanSectionDisplayTitle(section_title),
        difficulty=difficulty,
        prompt=sanitizeQuestionText(prompts[(sequence_index - 1) % len(prompts)]),
        options=options,
        citations=list(citations),
        rationale=sanitizeExplanationText(rationale),
    )
    return question, sanitizeOptionText(raw_options[0]), correct_option_id


def _build_workbook_fact_question(
    *,
    question_id: str,
    concept: str,
    section_title: str,
    difficulty: float,
    citations: list[SourceChunk],
    source_text: str,
    sequence_index: int,
    examples: list[_ModuleQuizExample],
) -> tuple[QuizQuestion, str, str | None] | None:
    facts = _workbook_question_facts(source_text, examples=examples)
    if not facts:
        return None

    style_example = examples[(sequence_index - 1) % len(examples)] if examples else None
    patterned_question = _build_workbook_patterned_question(
        question_id=question_id,
        concept=concept,
        section_title=section_title,
        difficulty=difficulty,
        citations=citations,
        source_text=source_text,
        facts=facts,
        style_example=style_example,
        sequence_index=sequence_index,
    )
    if patterned_question is not None:
        return patterned_question

    if style_example and _module_quiz_uses_roman_statements(style_example) and len(facts) >= 2:
        roman_question = _build_workbook_roman_fact_question(
            question_id=question_id,
            concept=concept,
            section_title=section_title,
            difficulty=difficulty,
            citations=citations,
            facts=facts,
            sequence_index=sequence_index,
        )
        if roman_question is not None:
            return roman_question

    selected_fact = facts[(sequence_index - 1) % len(facts)]
    prompt = _workbook_fact_prompt(selected_fact, style_example, sequence_index=sequence_index)
    correct_answer = sanitizeOptionText(selected_fact.answer)
    distractors = _workbook_fact_distractors(
        selected_fact,
        facts=facts,
        examples=examples,
    )
    options, correct_option_id = _assemble_workbook_options(correct_answer, distractors, sequence_index)
    if len(options) != 4 or correct_option_id is None:
        return None
    question = QuizQuestion(
        question_id=question_id,
        question_type=QuestionType.MCQ,
        concept=concept,
        section_title=cleanSectionDisplayTitle(section_title),
        difficulty=difficulty,
        prompt=sanitizeWorkbookQuestionText(prompt),
        options=[
            QuizQuestionOption(option_id=option_id, text=option_text)
            for option_id, option_text in zip(["A", "B", "C", "D"], options, strict=True)
        ],
        citations=list(citations),
        rationale=sanitizeExplanationText(selected_fact.rationale),
    )
    return question, correct_answer, correct_option_id


def _build_workbook_patterned_question(
    *,
    question_id: str,
    concept: str,
    section_title: str,
    difficulty: float,
    citations: list[SourceChunk],
    source_text: str,
    facts: list[_WorkbookQuestionFact],
    style_example: _ModuleQuizExample | None,
    sequence_index: int,
) -> tuple[QuizQuestion, str, str | None] | None:
    source_lower = source_text.lower()
    style_profile = _workbook_style_profile(style_example.prompt if style_example is not None else "")

    if "roman_statement" in style_profile and "risk appetite" in source_lower:
        return _build_workbook_risk_appetite_question(
            question_id=question_id,
            concept=concept,
            section_title=section_title,
            difficulty=difficulty,
            citations=citations,
            sequence_index=sequence_index,
        )

    if "negative_selection" in style_profile and _has_fund_structure_source(source_lower):
        return _build_workbook_fund_structure_question(
            question_id=question_id,
            concept=concept,
            section_title=section_title,
            difficulty=difficulty,
            citations=citations,
            sequence_index=sequence_index,
        )

    if "roman_statement" in style_profile and _has_basis_risk_source(source_lower):
        return _build_workbook_basis_risk_question(
            question_id=question_id,
            concept=concept,
            section_title=section_title,
            difficulty=difficulty,
            citations=citations,
            sequence_index=sequence_index,
        )

    if _has_risk_strategy_source(source_lower):
        return _build_workbook_risk_strategy_question(
            question_id=question_id,
            concept=concept,
            section_title=section_title,
            difficulty=difficulty,
            citations=citations,
            sequence_index=sequence_index,
        )

    if _has_basis_risk_source(source_lower) and any("basis risk" in fact.answer.lower() for fact in facts):
        return _build_workbook_basis_risk_question(
            question_id=question_id,
            concept=concept,
            section_title=section_title,
            difficulty=difficulty,
            citations=citations,
            sequence_index=sequence_index,
        )

    return None


def _build_workbook_asset_pricing_question(
    *,
    question_id: str,
    concept: str,
    section_title: str,
    difficulty: float,
    citations: list[SourceChunk],
    sequence_index: int,
) -> tuple[QuizQuestion, str, str | None]:
    variants = [
        (
            "An analyst reviews asset-pricing model assumptions. Which statement is most accurate?",
            [
                "APT can use multiple systematic factors with changing sensitivities",
                "CAPM and APT both require only one market factor",
                "Factor betas are fixed by definition and should not be updated",
                "Multifactor models ignore macroeconomic drivers of return",
            ],
            "APT can use multiple systematic factors with changing sensitivities",
            "APT extends beyond a single market factor and uses factor sensitivities that can change.",
        ),
        (
            "A portfolio manager compares CAPM and APT for a diversified portfolio. Which statement is correct?",
            [
                "CAPM uses market beta as its single systematic risk factor",
                "CAPM requires separate betas for each macroeconomic factor",
                "APT assumes only market beta can affect expected return",
                "Both models ignore systematic risk when estimating return",
            ],
            "CAPM uses market beta as its single systematic risk factor",
            "CAPM is the single-factor benchmark, while APT permits multiple systematic factors.",
        ),
        (
            "An analyst reviews changing factor sensitivities after macro exposure shifts. Which statement is most appropriate?",
            [
                "Update factor sensitivities to reflect current exposures",
                "Discard APT because factor sensitivities changed",
                "Keep all factor betas fixed until the model is replaced",
                "Reduce APT to the CAPM market-beta structure",
            ],
            "Update factor sensitivities to reflect current exposures",
            "Multifactor inputs should reflect the current exposure of returns to systematic factors.",
        ),
    ]
    prompt, options, correct_answer, rationale = variants[(sequence_index - 1) % len(variants)]
    return _build_patterned_workbook_mcq(
        question_id=question_id,
        concept=concept,
        section_title=section_title,
        difficulty=difficulty,
        citations=citations,
        prompt=prompt,
        options=options,
        correct_answer=correct_answer,
        rationale=rationale,
        sequence_index=sequence_index,
    )


def _build_workbook_risk_strategy_question(
    *,
    question_id: str,
    concept: str,
    section_title: str,
    difficulty: float,
    citations: list[SourceChunk],
    sequence_index: int,
) -> tuple[QuizQuestion, str, str | None]:
    scenarios = [
        (
            "A food company expects a small commodity-price exposure but chooses to leave it unhedged because the hedge cost exceeds the expected loss. Which high-level risk response is illustrated?",
            "Accept the exposure",
            "Accepting risk is one of the core risk responses for intentionally retaining an exposure when the expected tradeoff is tolerable.",
        ),
        (
            "A regional lender exits a product line after deciding that the related loss volatility is outside its tolerance. Which high-level risk response is illustrated?",
            "Avoid the exposure",
            "Avoiding risk is one of the core risk responses for choosing not to take the activity that creates the exposure.",
        ),
        (
            "A manufacturer uses forward contracts to reduce the cash-flow volatility from a forecasted input purchase. Which high-level risk response is illustrated?",
            "Mitigate the exposure",
            "Mitigating risk is one of the core risk responses that reduces the exposure while allowing the underlying activity to continue.",
        ),
        (
            "An exporter buys insurance that shifts a defined loss exposure to another party for a premium. Which high-level risk response is illustrated?",
            "Transfer the exposure",
            "Transferring risk is one of the core risk responses that shifts a defined exposure to another party instead of retaining it fully.",
        ),
    ]
    prompt, correct_answer, rationale = scenarios[(sequence_index - 1) % len(scenarios)]
    options = [
        "Accept the exposure",
        "Avoid the exposure",
        "Mitigate the exposure",
        "Transfer the exposure",
    ]
    return _build_patterned_workbook_mcq(
        question_id=question_id,
        concept=concept,
        section_title=section_title,
        difficulty=difficulty,
        citations=citations,
        prompt=prompt,
        options=options,
        correct_answer=correct_answer,
        rationale=rationale,
        sequence_index=sequence_index,
    )


def _build_workbook_risk_appetite_question(
    *,
    question_id: str,
    concept: str,
    section_title: str,
    difficulty: float,
    citations: list[SourceChunk],
    sequence_index: int,
) -> tuple[QuizQuestion, str, str | None]:
    prompt = (
        "The board is reviewing how much earnings volatility the firm is willing to retain before hedging. "
        "Which statements about risk appetite are correct? "
        "I. It can be stated using qualitative guidance or quantitative limits. "
        "II. It means the firm should never retain risk once a hedge is available."
    )
    options = ["I only", "II only", "Both I and II", "Neither I nor II"]
    return _build_patterned_workbook_mcq(
        question_id=question_id,
        concept=concept,
        section_title=section_title,
        difficulty=difficulty,
        citations=citations,
        prompt=prompt,
        options=options,
        correct_answer="I only",
        rationale="Risk appetite is the amount of risk the firm is willing to retain and may be expressed qualitatively or quantitatively.",
        sequence_index=sequence_index,
        preserve_option_order=True,
    )


def _build_workbook_fund_structure_question(
    *,
    question_id: str,
    concept: str,
    section_title: str,
    difficulty: float,
    citations: list[SourceChunk],
    sequence_index: int,
) -> tuple[QuizQuestion, str, str | None]:
    options = [
        "Open-end funds redeem shares at the next available NAV",
        "Closed-end fund shares may trade away from NAV on an exchange",
        "ETF shares cannot be bought or sold during the trading day",
        "ETF creation and redemption can keep market prices near NAV",
    ]
    return _build_patterned_workbook_mcq(
        question_id=question_id,
        concept=concept,
        section_title=section_title,
        difficulty=difficulty,
        citations=citations,
        prompt="Which statement is least accurate regarding exchange-traded and mutual fund structures available to public investors?",
        options=options,
        correct_answer="ETF shares cannot be bought or sold during the trading day",
        rationale="ETFs trade intraday on exchanges; the other statements describe open-end funds, closed-end funds, or ETF creation and redemption.",
        sequence_index=sequence_index,
    )


def _build_workbook_basis_risk_question(
    *,
    question_id: str,
    concept: str,
    section_title: str,
    difficulty: float,
    citations: list[SourceChunk],
    sequence_index: int,
) -> tuple[QuizQuestion, str, str | None]:
    if sequence_index % 2 == 0:
        return _build_workbook_short_hedge_tradeoff_question(
            question_id=question_id,
            concept=concept,
            section_title=section_title,
            difficulty=difficulty,
            citations=citations,
            sequence_index=sequence_index,
        )

    prompt = (
        "Which situations describe a hedge with meaningful basis risk? "
        "I. An airline hedges jet-fuel costs with heating-oil futures because no exact jet-fuel futures contract is available. "
        "II. A wheat farmer hedges a harvest sale with the same delivery-month wheat futures contract."
    )
    options = ["I only", "II only", "Both I and II", "Neither I nor II"]
    return _build_patterned_workbook_mcq(
        question_id=question_id,
        concept=concept,
        section_title=section_title,
        difficulty=difficulty,
        citations=citations,
        prompt=prompt,
        options=options,
        correct_answer="I only",
        rationale="Basis risk is meaningful when the futures contract does not closely match the spot exposure or the two prices diverge.",
        sequence_index=sequence_index,
        preserve_option_order=True,
    )


def _build_workbook_short_hedge_tradeoff_question(
    *,
    question_id: str,
    concept: str,
    section_title: str,
    difficulty: float,
    citations: list[SourceChunk],
    sequence_index: int,
) -> tuple[QuizQuestion, str, str | None]:
    options = [
        "The futures loss offsets much of the higher spot sale proceeds",
        "The hedge converts the inventory sale into a guaranteed arbitrage profit",
        "Matching the delivery month removes every source of basis risk",
        "The producer keeps all price upside while also earning on the futures",
    ]
    return _build_patterned_workbook_mcq(
        question_id=question_id,
        concept=concept,
        section_title=section_title,
        difficulty=difficulty,
        citations=citations,
        prompt=(
            "Which statement best describes the cost of a short futures hedge for a crude oil producer "
            "if spot prices rise sharply before the planned inventory sale?"
        ),
        options=options,
        correct_answer="The futures loss offsets much of the higher spot sale proceeds",
        rationale="A short futures hedge stabilizes the sale value, but gains in the spot market are offset by losses on the short futures position.",
        sequence_index=sequence_index,
    )


def _build_patterned_workbook_mcq(
    *,
    question_id: str,
    concept: str,
    section_title: str,
    difficulty: float,
    citations: list[SourceChunk],
    prompt: str,
    options: list[str],
    correct_answer: str,
    rationale: str,
    sequence_index: int,
    preserve_option_order: bool = False,
) -> tuple[QuizQuestion, str, str | None]:
    clean_options = [sanitizeOptionText(option) for option in options]
    clean_correct = sanitizeOptionText(correct_answer)
    if preserve_option_order:
        ordered_options = clean_options
    else:
        rotation = (sequence_index - 1) % len(clean_options)
        ordered_options = clean_options[rotation:] + clean_options[:rotation]
    correct_option_id = ["A", "B", "C", "D"][ordered_options.index(clean_correct)]
    question = QuizQuestion(
        question_id=question_id,
        question_type=QuestionType.MCQ,
        concept=concept,
        section_title=cleanSectionDisplayTitle(section_title),
        difficulty=difficulty,
        prompt=sanitizeWorkbookQuestionText(prompt),
        options=[
            QuizQuestionOption(option_id=option_id, text=option_text)
            for option_id, option_text in zip(["A", "B", "C", "D"], ordered_options, strict=True)
        ],
        citations=list(citations),
        rationale=sanitizeExplanationText(rationale),
    )
    return question, clean_correct, correct_option_id


def _has_risk_strategy_source(source_lower: str) -> bool:
    return all(token in source_lower for token in ("accept", "avoid", "mitigate", "transfer"))


def _has_fund_structure_source(source_lower: str) -> bool:
    return all(token in source_lower for token in ("open-end", "closed-end")) and (
        "exchange-traded" in source_lower or "etf" in source_lower
    )


def _has_basis_risk_source(source_lower: str) -> bool:
    return "basis risk" in source_lower and ("futures" in source_lower or "hedge" in source_lower)


def _module_quiz_uses_roman_statements(example: _ModuleQuizExample) -> bool:
    return bool(re.search(r"\bI\.\s+", example.prompt) and re.search(r"\bII\.\s+", example.prompt))


def _build_workbook_roman_fact_question(
    *,
    question_id: str,
    concept: str,
    section_title: str,
    difficulty: float,
    citations: list[SourceChunk],
    facts: list[_WorkbookQuestionFact],
    sequence_index: int,
) -> tuple[QuizQuestion, str, str | None] | None:
    true_fact = facts[(sequence_index - 1) % len(facts)]
    false_fact = facts[sequence_index % len(facts)]
    true_statement = _workbook_fact_statement(true_fact)
    false_statement = _workbook_false_statement(false_fact)
    if not true_statement or not false_statement or _near_duplicate(_fingerprint(true_statement), _fingerprint(false_statement)):
        return None

    topic = _workbook_fact_topic(true_fact, fallback=concept)
    prompt = (
        f"Which of the following statements about {topic} is correct? "
        f"I. {true_statement}. II. {false_statement}."
    )
    options = ["I only", "II only", "Both I and II", "Neither I nor II"]
    question = QuizQuestion(
        question_id=question_id,
        question_type=QuestionType.MCQ,
        concept=concept,
        section_title=cleanSectionDisplayTitle(section_title),
        difficulty=difficulty,
        prompt=sanitizeWorkbookQuestionText(prompt),
        options=[
            QuizQuestionOption(option_id=option_id, text=option_text)
            for option_id, option_text in zip(["A", "B", "C", "D"], options, strict=True)
        ],
        citations=list(citations),
        rationale=sanitizeExplanationText(true_fact.rationale),
    )
    return question, "I only", "A"


def _workbook_question_facts(
    source_text: str,
    *,
    examples: list[_ModuleQuizExample],
) -> list[_WorkbookQuestionFact]:
    content = _workbook_key_concept_text(source_text)
    if not content:
        return []
    original_text = " ".join(
        [
            *[example.prompt for example in examples],
            *[option for example in examples for option in example.options.values()],
        ]
    )
    original_fingerprint = _fingerprint(original_text)
    facts: list[_WorkbookQuestionFact] = []
    for sentence in _extract_sentences(content):
        fact = _workbook_fact_from_sentence(sentence)
        if fact is None:
            continue
        fact_text = f"{fact.prompt} {fact.answer}"
        if original_fingerprint and _similarity(fact_text, original_text) >= 0.72:
            continue
        if any(_near_duplicate(_fingerprint(fact.prompt), _fingerprint(existing.prompt)) for existing in facts):
            continue
        facts.append(fact)
        if len(facts) >= 12:
            break
    return facts


def _workbook_key_concept_text(source_text: str) -> str:
    text = source_text or ""
    quiz_match = MODULE_QUIZ_HEADING_RE.search(text)
    if quiz_match is not None:
        text = text[: quiz_match.start()]
    key_concepts_match = re.search(r"\bKEY\s+CONCEPTS\b", text, flags=re.IGNORECASE)
    if key_concepts_match is not None:
        text = text[key_concepts_match.end() :]
    else:
        exam_focus_match = re.search(r"\bEXAM\s+FOCUS\b", text, flags=re.IGNORECASE)
        if exam_focus_match is not None:
            text = text[exam_focus_match.end() :]
    text = re.sub(r"\b(?:STUDY\s+SESSION|READING|MODULE)\s+\d+(?:\.\d+)?\s*[:\-]?", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bKEY\s+CONCEPTS\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(?:L\s*O|Learning\s+Objective)\s*\d+\s*(?:\.|\s+)?\s*[a-z]\b[:.]?", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _workbook_fact_from_sentence(sentence: str) -> _WorkbookQuestionFact | None:
    cleaned = _normalize_line(sentence).strip(".")
    if not cleaned or len(cleaned.split()) < 6:
        return None
    if re.search(r"\b(?:module quiz|answer key|which of the following|the following is a review)\b", cleaned, re.IGNORECASE):
        return None

    match = re.match(
        r"(?P<subject>[A-Z][A-Za-z0-9 /()'’.-]{2,90}?)\s+"
        r"(?P<verb>issue and redeem|can increase|can pick|locks in|may trade|trade|trades|issue|issues|use|uses|"
        r"compare|compares|increase|increases|reduce|reduces|include|includes|is|are|means|"
        r"refers to|measure|measures|represent|represents|depend|depends|remain|remains)\s+"
        r"(?P<object>.+)",
        cleaned,
        re.IGNORECASE,
    )
    if match is None:
        return None
    subject = re.sub(r"^(?:an?|the)\s+", "", match.group("subject"), flags=re.IGNORECASE).strip()
    subject = _limit_words(subject, 7)
    verb = match.group("verb").lower()
    obj = match.group("object").strip(" .")
    if not subject or not obj or len(subject.split()) > 7:
        return None

    answer = _workbook_fact_answer(subject=subject, verb=verb, obj=obj)
    if not answer:
        return None
    prompt = _workbook_question_prompt_for_fact(subject=subject, verb=verb)
    rationale = _workbook_fact_rationale(subject=subject, answer=answer)
    return _WorkbookQuestionFact(
        subject=subject,
        prompt=prompt,
        answer=answer,
        rationale=rationale,
    )


def _workbook_question_prompt_for_fact(*, subject: str, verb: str) -> str:
    lowered_subject = subject.lower()
    auxiliary = "do" if _workbook_subject_looks_plural(subject) else "does"
    if verb in {"compare", "compares"}:
        return f"What {auxiliary} {lowered_subject} compare?"
    if verb in {"increase", "increases", "can increase"}:
        return f"What can {lowered_subject} increase?"
    if verb in {"reduce", "reduces"}:
        return f"What {auxiliary} {lowered_subject} reduce?"
    if verb in {"measure", "measures"}:
        return f"What {auxiliary} {lowered_subject} measure?"
    return f"Which statement best describes {lowered_subject}?"


def _workbook_fact_prompt(
    fact: _WorkbookQuestionFact,
    example: _ModuleQuizExample | None,
    *,
    sequence_index: int,
) -> str:
    if _is_risk_strategy_fact(fact):
        variants = [
            "Which statement best describes the risk-management strategy choices?",
            "A firm is choosing how to respond to a risk exposure. Which statement is most accurate?",
            "Which choice correctly identifies the main risk response categories?",
        ]
        return variants[(sequence_index - 1) % len(variants)]

    if _is_risk_appetite_fact(fact):
        variants = [
            "Which statement about a firm's risk appetite is correct?",
            "Which choice best describes risk appetite?",
            "Which statement correctly applies the concept of risk appetite?",
        ]
        return variants[(sequence_index - 1) % len(variants)]

    if example is None:
        base_prompt = fact.prompt
    else:
        prompt = example.prompt.lower()
        if prompt.startswith("how "):
            base_prompt = fact.prompt
        elif "which statement best describes" in prompt:
            base_prompt = f"Which statement best describes {fact.subject.lower()}?"
        else:
            base_prompt = fact.prompt
    variants = [
        base_prompt,
        f"Which choice is most accurate about {fact.subject.lower()}?",
        f"Which statement correctly applies {fact.subject.lower()}?",
    ]
    return variants[(sequence_index - 1) % len(variants)]


def _is_risk_strategy_fact(fact: _WorkbookQuestionFact) -> bool:
    answer = fact.answer.lower()
    return all(token in answer for token in ("accept", "avoid", "mitigate", "transfer"))


def _is_risk_appetite_fact(fact: _WorkbookQuestionFact) -> bool:
    return "willingness to retain risk" in fact.answer.lower()


def _workbook_fact_topic(fact: _WorkbookQuestionFact, *, fallback: str) -> str:
    subject = re.sub(r"^(?:an?|the)\s+", "", fact.subject, flags=re.IGNORECASE).strip()
    subject = subject[:1].lower() + subject[1:] if subject else ""
    if subject and not re.search(r"\bstudy\s+session\b", subject, re.IGNORECASE):
        return subject
    clean_fallback = cleanSectionDisplayTitle(fallback).lower()
    if not clean_fallback or re.search(r"\bstudy\s+session\b", clean_fallback, re.IGNORECASE):
        return "the module concepts"
    return clean_fallback


def _workbook_fact_answer(*, subject: str, verb: str, obj: str) -> str:
    obj = _clean_workbook_fact_object(obj)
    lowered_obj = obj.lower()
    if "net asset value" in lowered_obj and "issue and redeem" in verb:
        return f"{subject} redeem shares at net asset value"
    if "fixed number of shares" in lowered_obj:
        return f"{subject} issue fixed shares that can trade away from NAV"
    if "intraday" in lowered_obj:
        return f"{subject} trade intraday on exchanges"
    if "expense ratios" in lowered_obj:
        return "Expense ratios, loads, 12b-1 fees, and turnover"
    if "trading costs" in lowered_obj and "tax" in lowered_obj:
        return "It can increase trading costs and taxes"
    if verb == "can pick" and all(token in lowered_obj for token in ("accept", "avoid", "mitigate", "transfer")):
        return f"{subject} can accept, avoid, mitigate, or transfer risk"
    if verb == "locks in" and "limit upside" in lowered_obj:
        return f"{subject} locks in a sale price but can limit upside"
    if verb in {"remain", "remains"} and "spot" in lowered_obj and "futures" in lowered_obj:
        return f"{subject} remains when spot and futures prices diverge"
    if "related but different asset" in lowered_obj and verb in {"use", "uses"}:
        return f"{subject} uses a futures contract on a related but different asset"

    pronoun = "They" if _workbook_subject_looks_plural(subject) else "It"
    normalized_verb = {
        "issues": "issues",
        "issue": "issue",
        "trades": "trades",
        "trade": "trade",
        "uses": "uses",
        "use": "use",
        "compares": "compares",
        "compare": "compare",
        "can pick": "can pick",
        "locks in": "locks in",
        "can increase": "can increase",
        "increases": "increases",
        "increase": "increase",
        "reduces": "reduces",
        "reduce": "reduce",
        "includes": "includes",
        "include": "include",
        "measures": "measures",
        "measure": "measure",
        "represents": "represents",
        "represent": "represent",
        "depends": "depends on",
        "depend": "depend on",
        "remains": "remains",
        "remain": "remain",
    }.get(verb, verb)
    return _limit_words(f"{pronoun} {normalized_verb} {obj}", 12)


def _clean_workbook_fact_object(value: str) -> str:
    cleaned = re.split(
        r"\b(?:MODULE\s+QUIZ|ANSWER\s+KEY\s+FOR\s+MODULE\s+QUIZZES)\b",
        value,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    cleaned = re.sub(r"\s+\d+\.\s+.*$", "", cleaned).strip(" .")
    cleaned = re.sub(r":\s*\d+\s*$", "", cleaned).strip(" .")
    return cleaned


def _workbook_fact_distractors(
    selected_fact: _WorkbookQuestionFact,
    *,
    facts: list[_WorkbookQuestionFact],
    examples: list[_ModuleQuizExample],
) -> list[str]:
    original_options = {
        _fingerprint(option)
        for example in examples
        for option in example.options.values()
    }
    distractors: list[str] = []
    for fact in facts:
        if fact is selected_fact:
            continue
        candidate = sanitizeOptionText(fact.answer)
        if not candidate or _fingerprint(candidate) in original_options:
            continue
        if _near_duplicate(_fingerprint(candidate), _fingerprint(selected_fact.answer)):
            continue
        if any(_near_duplicate(_fingerprint(candidate), _fingerprint(existing)) for existing in distractors):
            continue
        distractors.append(candidate)
        if len(distractors) >= 3:
            return distractors

    fallback_pool = _workbook_fallback_distractors(selected_fact)
    for fallback in fallback_pool:
        if _fingerprint(fallback) == _fingerprint(selected_fact.answer):
            continue
        if any(_near_duplicate(_fingerprint(fallback), _fingerprint(existing)) for existing in distractors):
            continue
        distractors.append(fallback)
        if len(distractors) >= 3:
            break
    return distractors


def _workbook_fallback_distractors(selected_fact: _WorkbookQuestionFact) -> list[str]:
    lowered_answer = selected_fact.answer.lower()
    if all(token in lowered_answer for token in ("accept", "avoid", "mitigate", "transfer")):
        return [
            "They should always avoid every identified risk",
            "They mitigate risk by ignoring the exposure",
            "They transfer every risk without residual tradeoff",
            "They accept risk only after eliminating uncertainty",
        ]
    if "willingness to retain risk" in lowered_answer:
        return [
            "It means eliminating all retained risk",
            "It is set only after hedges are chosen",
            "It cannot be expressed qualitatively",
            "It requires avoiding every financial exposure",
        ]
    if "sale price" in lowered_answer and "limit upside" in lowered_answer:
        return [
            "It guarantees unlimited upside",
            "It removes basis risk from every hedge",
            "It creates a perfect hedge without cost",
            "It increases profit whenever prices rise",
        ]
    if "spot" in lowered_answer and "futures" in lowered_answer:
        return [
            "It disappears whenever maturities match",
            "It exists only when the same asset is hedged",
            "It guarantees profit in every futures hedge",
            "It is unrelated to spot and futures prices",
        ]
    if "related but different asset" in lowered_answer:
        return [
            "It uses the exact same asset as the exposure",
            "It eliminates basis risk by construction",
            "It avoids futures contracts entirely",
            "It guarantees that prices move identically",
        ]
    return [
        "They eliminate all fees and trading costs",
        "They guarantee prices equal NAV at every trade",
        "They remove the need to compare fund structures",
        "They always eliminate taxable distributions",
    ]


def _assemble_workbook_options(
    correct_answer: str,
    distractors: list[str],
    sequence_index: int,
) -> tuple[list[str], str | None]:
    clean_correct = sanitizeOptionText(correct_answer)
    options: list[str] = []
    for distractor in distractors:
        clean = sanitizeOptionText(distractor)
        if not clean or _near_duplicate(_fingerprint(clean), _fingerprint(clean_correct)):
            continue
        if any(_near_duplicate(_fingerprint(clean), _fingerprint(existing)) for existing in options):
            continue
        options.append(clean)
        if len(options) >= 3:
            break
    if len(options) < 3:
        return [], None
    rotation = (sequence_index - 1) % len(options)
    options = options[rotation:] + options[:rotation]
    insertion_index = (sequence_index - 1) % 4
    options.insert(insertion_index, clean_correct)
    return options[:4], ["A", "B", "C", "D"][insertion_index]


def _workbook_fact_statement(fact: _WorkbookQuestionFact) -> str:
    answer = fact.answer.strip()
    lowered_answer = answer.lower()
    if lowered_answer.startswith(fact.subject.lower()):
        return _limit_words(answer, 18)
    for pronoun in ("they ", "it "):
        if lowered_answer.startswith(pronoun):
            return _limit_words(f"{fact.subject} {answer.split(' ', 1)[1]}", 18)
    if lowered_answer.startswith("expense ratios"):
        return _limit_words(f"{fact.subject} compare {answer[:1].lower()}{answer[1:]}", 18)
    return _limit_words(f"{fact.subject} is associated with {answer[:1].lower()}{answer[1:]}", 18)


def _workbook_false_statement(fact: _WorkbookQuestionFact) -> str:
    lowered_answer = fact.answer.lower()
    if "net asset value" in lowered_answer:
        return f"{fact.subject} always trade away from net asset value"
    if "intraday" in lowered_answer:
        return f"{fact.subject} cannot trade intraday"
    if "fixed shares" in lowered_answer:
        return f"{fact.subject} continuously issue and redeem shares at NAV"
    if "trading costs" in lowered_answer:
        return f"{fact.subject} eliminates trading costs and taxes"
    if all(token in lowered_answer for token in ("accept", "avoid", "mitigate", "transfer")):
        return f"{fact.subject} must avoid every identified risk"
    if "willingness to retain risk" in lowered_answer:
        return f"{fact.subject} means eliminating all retained risk"
    if "sale price" in lowered_answer and "limit upside" in lowered_answer:
        return f"{fact.subject} guarantees unlimited upside"
    if "spot" in lowered_answer and "futures" in lowered_answer:
        return f"{fact.subject} disappears whenever maturities match"
    if "related but different asset" in lowered_answer:
        return f"{fact.subject} uses the exact same asset as the exposure"
    return f"{fact.subject} guarantees the same outcome in every market"


def _workbook_fact_rationale(*, subject: str, answer: str) -> str:
    return f"{subject} is tested by the fact that {answer[:1].lower()}{answer[1:]}."


def _workbook_subject_looks_plural(subject: str) -> bool:
    lowered = subject.lower()
    if lowered.endswith("s") and not lowered.endswith("ss"):
        return True
    return any(token in lowered for token in ("funds", "investors", "options", "contracts", "shares"))


def _should_rewrite_module_quiz_example(*, example: _ModuleQuizExample, source_text: str) -> bool:
    prompt = example.prompt.lower()
    source = source_text.lower()
    if "short hedge" in prompt and "basis risk" in source:
        return True
    return False


def _module_quiz_examples_from_citations(citations: list[SourceChunk]) -> list[_ModuleQuizExample]:
    examples: list[_ModuleQuizExample] = []
    for citation in citations:
        text = getattr(citation, "text", "") or ""
        examples.extend(_parse_module_quiz_examples(text))
        if examples:
            break
    return examples


def _parse_module_quiz_examples(text: str) -> list[_ModuleQuizExample]:
    quiz_match = re.search(
        r"\bMODULE\s+QUIZ\s+(?P<quiz_number>\d+\.\d+)\b(?P<body>.*?)(?:\n\s*ANSWER\s+KEY\s+FOR\s+MODULE\s+QUIZZES\b|\Z)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if quiz_match is None:
        return []

    examples = _parse_module_quiz_question_body(quiz_match.group("body"))
    if not examples:
        return []

    answer_key = _parse_module_quiz_answer_key(text, quiz_match.group("quiz_number"))
    enriched: list[_ModuleQuizExample] = []
    for example in examples:
        correct_option_id, rationale = answer_key.get(example.number, (None, ""))
        enriched.append(
            _ModuleQuizExample(
                number=example.number,
                prompt=example.prompt,
                options=example.options,
                correct_option_id=correct_option_id,
                rationale=rationale,
            )
        )
    return enriched


def _parse_module_quiz_question_body(body: str) -> list[_ModuleQuizExample]:
    examples: list[_ModuleQuizExample] = []
    current_number: int | None = None
    current_prompt: list[str] = []
    current_options: dict[str, list[str]] = {}
    current_option_id: str | None = None

    def flush() -> None:
        nonlocal current_number, current_prompt, current_options, current_option_id
        if current_number is not None and current_prompt and len(current_options) >= 4:
            examples.append(
                _ModuleQuizExample(
                    number=current_number,
                    prompt=" ".join(" ".join(current_prompt).split()),
                    options={
                        option_id: " ".join(" ".join(parts).split())
                        for option_id, parts in current_options.items()
                    },
                )
            )
        current_number = None
        current_prompt = []
        current_options = {}
        current_option_id = None

    for raw_line in body.splitlines():
        line = _normalize_line(raw_line)
        if not line:
            continue
        question_match = re.match(r"^(\d+)\.\s+(.+)$", line)
        option_match = re.match(r"^([A-D])\.\s+(.+)$", line)
        if question_match:
            flush()
            current_number = int(question_match.group(1))
            current_prompt = [question_match.group(2)]
            continue
        if option_match and current_number is not None:
            option_id = option_match.group(1)
            current_option_id = option_id
            current_options[option_id] = [option_match.group(2)]
            continue
        if current_option_id is not None:
            current_options[current_option_id].append(line)
        elif current_number is not None:
            current_prompt.append(line)

    flush()
    return examples


def _parse_module_quiz_answer_key(text: str, quiz_number: str) -> dict[int, tuple[str, str]]:
    answer_match = re.search(
        rf"\bANSWER\s+KEY\s+FOR\s+MODULE\s+QUIZZES\b.*?\bMODULE\s+QUIZ\s+{re.escape(quiz_number)}\b(?P<body>.*?)(?=\n\s*MODULE\s+QUIZ\s+\d+\.\d+\b|\Z)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if answer_match is None:
        answer_match = re.search(
            r"\bANSWER\s+KEY\s+FOR\s+MODULE\s+QUIZZES\b(?P<body>.*?)(?=\n\s*MODULE\s+QUIZ\s+\d+\.\d+\b|\Z)",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
    if answer_match is None:
        return {}

    answer_body = answer_match.group("body")
    answers: dict[int, tuple[str, str]] = {}
    for match in re.finditer(
        r"(?ms)^\s*(\d+)\.\s*([A-D])\s+(.*?)(?=^\s*\d+\.\s*[A-D]\s+|\Z)",
        answer_body,
    ):
        number = int(match.group(1))
        option_id = match.group(2)
        rationale = _clean_module_answer_key_rationale(match.group(3))
        answers[number] = (option_id, rationale)
    return answers


def _clean_module_answer_key_rationale(value: str) -> str:
    rationale = " ".join(value.split())
    rationale = re.split(r"\s+\(LO\s+\d+(?:\.[a-z])?\)", rationale, maxsplit=1, flags=re.IGNORECASE)[0]
    rationale = re.split(r"\bThe following is a review\b", rationale, maxsplit=1, flags=re.IGNORECASE)[0]
    return _limit_words(rationale.strip(), 28)


def validateQuestion(
    question: QuizQuestion,
    *,
    source_text: str,
    knowledge: SectionKnowledge,
    correct_answer: str,
) -> QuestionValidationResult:
    notes: list[str] = []
    score = 1.0
    has_workbook_quiz = hasWorkbookModuleQuiz(source_text)
    normalized_source = _fingerprint(source_text)
    prompt_text = question.prompt.lower()
    module_quiz_copy_issues = _module_quiz_copy_issues(question, source_text)
    workbook_quality_issues = _workbook_module_quiz_quality_issues(question, source_text)

    if any(keyword in prompt_text for keyword in ADMIN_KEYWORDS):
        notes.append("Question mentions administrative or logistics content.")
        score -= 0.5
    if _contains_metadata_leakage(question.prompt):
        notes.append("Question still contains source metadata or display noise.")
        score -= 0.25
    if _contains_low_quality_quiz_filler(question.prompt):
        notes.append("Question uses generic quiz filler instead of module-specific content.")
        score -= 0.4
    if module_quiz_copy_issues:
        notes.extend(module_quiz_copy_issues)
        score -= 0.45
    if workbook_quality_issues:
        notes.extend(workbook_quality_issues)
        score -= min(0.55, 0.25 * len(workbook_quality_issues))
    if "supported by the section" in prompt_text or "source excerpt" in prompt_text:
        notes.append("Prompt still sounds like a retrieval check instead of an exam question.")
        score -= 0.25
    max_prompt_words = 95 if has_workbook_quiz else 22
    if len(question.prompt.split()) > max_prompt_words:
        notes.append("Prompt is too long.")
        score -= 0.15

    if question.question_type == QuestionType.MCQ:
        if len(question.options) != 4:
            notes.append("MCQ must have exactly four answer choices.")
            score -= 0.4
        option_texts = [option.text for option in question.options]
        if len(set(_fingerprint(text) for text in option_texts)) != len(option_texts):
            notes.append("Answer choices are duplicated or nearly duplicated.")
            score -= 0.25
        for option in question.options:
            lowered_option = option.text.lower()
            if len(option.text.split()) > 20:
                notes.append(f"Option {option.option_id} is too long.")
                score -= 0.2
            if any(keyword in lowered_option for keyword in ADMIN_KEYWORDS):
                notes.append(f"Option {option.option_id} contains administrative content.")
                score -= 0.5
            if _contains_metadata_leakage(option.text):
                notes.append(f"Option {option.option_id} contains source metadata or page labels.")
                score -= 0.25
            if _contains_low_quality_quiz_filler(option.text):
                notes.append(f"Option {option.option_id} uses generic quiz filler.")
                score -= 0.4
            if _copied_from_source(option.text, normalized_source) and not _is_allowed_workbook_answer_format(
                option.text,
                has_workbook_quiz=has_workbook_quiz,
            ):
                notes.append(f"Option {option.option_id} copies source wording too closely.")
                score -= 0.18
        if not _is_parallel_workbook_answer_set(option_texts, has_workbook_quiz=has_workbook_quiz):
            similar_to_correct = [
                option.text
                for option in question.options
                if option.text != correct_answer and _similarity(option.text, correct_answer) >= 0.82
            ]
            if similar_to_correct:
                notes.append("At least one distractor is too close to the correct answer.")
                score -= 0.2
    else:
        if _copied_from_source(question.prompt, normalized_source):
            notes.append("Short-answer prompt copies source wording too closely.")
            score -= 0.15

    if knowledge.content_label != ContentLabel.TESTABLE_CONTENT:
        notes.append("Source content is not strong enough for exam-style questioning.")
        score -= 0.35

    if question.rationale and _contains_low_quality_quiz_filler(question.rationale):
        notes.append("Rationale uses generic quiz filler instead of module-specific content.")
        score -= 0.4

    accepted = (
        score >= 0.68
        and not workbook_quality_issues
        and not any("administrative" in note.lower() for note in notes)
    )
    rejection_reason = None
    if not accepted:
        if knowledge.content_label == ContentLabel.ADMINISTRATIVE_CONTENT:
            rejection_reason = "administrative_only"
        elif knowledge.content_label == ContentLabel.WEAK_CONTENT:
            rejection_reason = "insufficient_testable_content"
        elif workbook_quality_issues:
            rejection_reason = "workbook_format_quality"
        else:
            rejection_reason = "noisy_extraction"
    return QuestionValidationResult(
        accepted=accepted,
        score=round(max(0.0, min(score, 1.0)), 4),
        notes=notes,
        rejection_reason=rejection_reason,
    )


def _workbook_module_quiz_quality_issues(question: QuizQuestion, source_text: str) -> list[str]:
    if not hasWorkbookModuleQuiz(source_text):
        return []
    examples = _parse_module_quiz_examples(source_text)
    if not examples:
        return []

    issues: list[str] = []
    original_profile: set[str] = set()
    for example in examples:
        original_profile.update(_workbook_style_profile(example.prompt))
    generated_profile = _workbook_style_profile(question.prompt)
    required_profile = original_profile.intersection(
        {"scenario_application", "roman_statement", "negative_selection", "calculation", "quote_review"},
    )
    if required_profile and not generated_profile.intersection(required_profile):
        issues.append("Generated workbook question does not match the book-level module quiz format.")

    if _is_shallow_workbook_prompt(question.prompt):
        issues.append("Generated workbook question uses a shallow fact-template stem instead of book-level phrasing.")

    clipped_options = [
        option.option_id
        for option in question.options
        if _looks_like_clipped_workbook_option(option.text)
    ]
    if clipped_options:
        issues.append("Generated workbook question contains clipped or fragmentary answer choices.")

    source_terms = _workbook_module_terms(source_text)
    if source_terms:
        surface = " ".join(
            [
                question.prompt,
                *[option.text for option in question.options],
                question.rationale or "",
            ],
        ).lower()
        matched_terms = {term for term in source_terms if term in surface}
        if len(matched_terms) < min(2, len(source_terms)):
            issues.append("Generated workbook question lacks enough module-specific terminology.")

    return issues


def _workbook_style_profile(prompt: str) -> set[str]:
    lowered = prompt.lower()
    profile: set[str] = set()
    if re.search(r"\bI\.\s+", prompt) and re.search(r"\bII\.\s+", prompt):
        profile.add("roman_statement")
    if re.search(r"\b(?:not correct|least accurate|not accurate|incorrect|except)\b", lowered):
        profile.add("negative_selection")
    if re.search(r"\b(?:closest|calculate|amount|ratio|standard deviation|covariance)\b", lowered) and re.search(
        r"\d",
        prompt,
    ):
        profile.add("calculation")
    if re.search(
        r"\b(?:bank|company|firm|analyst|manager|farmer|airline|manufacturer|lender|exporter|portfolio|board)\b",
        lowered,
    ) and re.search(
        r"\b(?:decides|expects|chooses|uses|receives|wants|prepared|reviewing|reviews|compares|"
        r"selects|hedges|exposure|volatility)\b",
        lowered,
    ):
        profile.add("scenario_application")
    if '"' in prompt or re.search(r"\b(?:statements? is|statements? are|excerpt)\b", lowered):
        profile.add("quote_review")
    if "which statement" in lowered or "which of the following" in lowered:
        profile.add("statement_selection")
    return profile


def _is_shallow_workbook_prompt(prompt: str) -> bool:
    lowered = prompt.lower()
    if _contains_low_quality_quiz_filler(lowered):
        return True
    shallow_patterns = [
        r"^which statement best describes (?:firms|funds|it|they)\??$",
        r"^which choice is most accurate about (?:firms|funds|it|they)\??$",
        r"^what do(?:es)? (?:firms|funds|it|they) .+\??$",
    ]
    if any(re.search(pattern, lowered) for pattern in shallow_patterns):
        return True
    if len(prompt.split()) <= 7 and not _workbook_style_profile(prompt).intersection(
        {"scenario_application", "roman_statement", "negative_selection", "calculation"},
    ):
        return True
    return False


def _looks_like_clipped_workbook_option(option_text: str) -> bool:
    stripped = option_text.strip()
    lowered = stripped.lower()
    if re.search(r"[:;]\s*\d+\s*$", stripped):
        return True
    if re.search(r"\bit\s+are\b", lowered):
        return True
    if re.search(r"\b(?:it|they)\s+include\b", lowered):
        return True
    if re.search(r"\b(?:with respect to|return on a|consider, which|through)$", lowered):
        return True
    if lowered in {"incorrect interpretation", "different idea", "unrelated rule"}:
        return True
    return bool(re.search(r"\b(?:module quiz|answer key|source excerpt)\b", lowered))


def _workbook_module_terms(source_text: str) -> list[str]:
    key_concepts = _workbook_key_concept_text(source_text).lower()
    preferred_terms = [
        "risk appetite",
        "retain risk",
        "qualitative",
        "quantitative",
        "risk management",
        "accept",
        "avoid",
        "mitigate",
        "transfer",
        "open-end",
        "closed-end",
        "exchange-traded",
        "etf",
        "net asset value",
        "capital asset pricing model",
        "capm",
        "arbitrage pricing theory",
        "apt",
        "factor sensitivity",
        "factor sensitivities",
        "factor beta",
        "market beta",
        "multifactor",
        "basis risk",
        "short hedge",
        "cross hedge",
        "futures",
    ]
    return [term for term in preferred_terms if term in key_concepts]


def _is_allowed_workbook_answer_format(option_text: str, *, has_workbook_quiz: bool) -> bool:
    if not has_workbook_quiz:
        return False
    fingerprint = _fingerprint(option_text)
    if fingerprint in {
        "i only",
        "ii only",
        "both i and ii",
        "neither i nor ii",
    }:
        return True
    return len(fingerprint.split()) <= 4


def _is_parallel_workbook_answer_set(option_texts: list[str], *, has_workbook_quiz: bool) -> bool:
    if not has_workbook_quiz or len(option_texts) != 4:
        return False
    fingerprints = [_fingerprint(option) for option in option_texts]
    if set(fingerprints) == {
        "i only",
        "ii only",
        "both i and ii",
        "neither i nor ii",
    }:
        return True
    split_options = [fingerprint.split() for fingerprint in fingerprints]
    if not all(2 <= len(option) <= 5 for option in split_options):
        return False
    suffixes = {tuple(option[1:]) for option in split_options}
    return len(suffixes) == 1


def _normalize_line(line: str) -> str:
    collapsed = " ".join(line.replace("\u2022", " ").replace("\xa0", " ").replace("_", " ").split())
    collapsed = re.sub(r"\b([A-Za-z0-9][A-Za-z0-9+\-_/]*)\s+(?:\1\s+){2,}", r"\1", collapsed)
    collapsed = re.sub(r"([A-Za-z])\1{4,}", r"\1\1", collapsed)
    return collapsed.strip(" -|:")


def cleanSectionDisplayTitle(value: str) -> str:
    cleaned = _normalize_line(value)
    cleaned = re.sub(r"\b(?:page|pages|slide|slides)\s+\d+(?:-\d+)?\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b[a-z0-9_\-]+\.(?:pdf|pptx|docx|txt)\b", "", cleaned, flags=re.IGNORECASE)
    parts = [part.strip(" -|:") for part in re.split(r"\s+\|\s+|:", cleaned) if part.strip(" -|:")]
    deduped: list[str] = []
    for part in parts:
        normalized = _fingerprint(part)
        if not normalized or any(_near_duplicate(normalized, _fingerprint(existing)) for existing in deduped):
            continue
        deduped.append(part)
    title = ": ".join(deduped[:2]) if deduped else cleaned
    title = re.sub(r"\s{2,}", " ", title).strip(" -|:")
    return _limit_words(title or "Study section", 10)


def sanitizeQuestionText(value: str) -> str:
    cleaned = _normalize_line(value)
    cleaned = re.sub(r"\b(?:page|pages|slide|slides)\s+\d+(?:-\d+)?\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b[a-z0-9_\-]+\.(?:pdf|pptx|docx|txt)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.replace("Citation label", "").replace("Source excerpt", "")
    cleaned = cleaned.replace("|", " ")
    cleaned = re.sub(r"\bon\s+of\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bfrom\s+is\b", "is", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" -|:")
    return _limit_words(cleaned, 22)


def sanitizeWorkbookQuestionText(value: str) -> str:
    cleaned = _normalize_line(value)
    cleaned = re.sub(r"\b(?:page|pages|slide|slides)\s+\d+(?:-\d+)?\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b[a-z0-9_\-]+\.(?:pdf|pptx|docx|txt)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.replace("Citation label", "").replace("Source excerpt", "")
    cleaned = cleaned.replace("|", " ")
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" -|:")
    return _limit_words(cleaned, 140)


def sanitizeOptionText(value: str) -> str:
    cleaned = sanitizeQuestionText(value)
    cleaned = re.sub(r"^[A-D]\.\s*", "", cleaned)
    cleaned = re.sub(r"^option\s+[A-D]\s*[:.-]?\s*", "", cleaned, flags=re.IGNORECASE)
    return _limit_words(cleaned, 20)


def sanitizeExplanationText(value: str) -> str:
    cleaned = _normalize_line(value)
    cleaned = re.sub(r"\b[a-z0-9_\-]+\.(?:pdf|pptx|docx|txt)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(?:citation|source)\b[: ]*", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.replace("|", " ")
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" -|:")
    return _limit_words(cleaned, 32)


def _contains_metadata_leakage(value: str) -> bool:
    return any(pattern.search(value) for pattern in METADATA_LEAK_PATTERNS) or "|" in value


def _contains_low_quality_quiz_filler(value: str) -> bool:
    lowered = (value or "").lower()
    return any(phrase in lowered for phrase in LOW_QUALITY_QUIZ_PHRASES)


def _module_quiz_copy_issues(question: QuizQuestion, source_text: str) -> list[str]:
    if not hasWorkbookModuleQuiz(source_text):
        return []
    examples = _parse_module_quiz_examples(source_text)
    if not examples:
        return []

    issues: list[str] = []
    for example in examples:
        copies_prompt = _similarity(question.prompt, example.prompt) >= 0.86
        torch_similarity = _torch_semantic_similarity(question.prompt, example.prompt)
        semantically_copies_prompt = torch_similarity is not None and torch_similarity >= 0.78
        if copies_prompt:
            issues.append("Prompt copies the original module quiz too closely.")
        if semantically_copies_prompt:
            issues.append("PyTorch semantic check found the prompt too close to the original module quiz.")
        if copies_prompt or semantically_copies_prompt:
            break

    roman_option_fingerprints = {
        _fingerprint(option)
        for option in ("I only", "II only", "Both I and II", "Neither I nor II")
    }
    original_options = [
        option
        for example in examples
        for option in example.options.values()
        if _fingerprint(option) not in roman_option_fingerprints
    ]
    for option in question.options:
        option_fingerprint = _fingerprint(option.text)
        if not option_fingerprint or option_fingerprint in roman_option_fingerprints:
            continue
        if any(_similarity(option.text, original_option) >= 0.9 for original_option in original_options):
            issues.append(f"Option {option.option_id} copies an original module quiz answer choice.")
            break
        if any(
            (semantic_score := _torch_semantic_similarity(option.text, original_option)) is not None
            and semantic_score >= 0.84
            for original_option in original_options
        ):
            issues.append(f"PyTorch semantic check found option {option.option_id} too close to an original answer choice.")
            break

    original_rationales = [example.rationale for example in examples if example.rationale]
    if question.rationale and any(
        (semantic_score := _torch_semantic_similarity(question.rationale, rationale)) is not None
        and semantic_score >= 0.84
        for rationale in original_rationales
    ):
        issues.append("PyTorch semantic check found the rationale too close to the original answer key.")
    return issues


def _should_remove_line(line: str, *, title: str) -> bool:
    lowered = line.lower()
    if PAGE_JUNK_RE.match(lowered) or DATE_ONLY_RE.match(lowered):
        return True
    if re.fullmatch(r"(lecture|slide|slides|page|session)\s+\d+", lowered):
        return True
    if lowered.startswith("http://") or lowered.startswith("https://"):
        return True
    if "canvas announcement" in lowered or "posted on canvas" in lowered:
        return True
    if any(keyword in lowered for keyword in ADMIN_KEYWORDS) and not any(
        keyword in lowered for keyword in TESTABLE_KEYWORDS
    ):
        return True
    if "week of" in lowered and len(re.findall(r"\b(?:oct|nov|dec|jan|feb|mar|apr|may)\b", lowered)) >= 2:
        return True
    if lowered.endswith("notes") and len(lowered.split()) <= 3:
        return True
    if sum(char.isdigit() for char in line) >= len(line) / 2 and len(line.split()) <= 4:
        return True
    tokens = lowered.split()
    if len(tokens) > 6 and len(set(tokens)) <= max(2, len(tokens) // 4):
        return True
    return False


def _fingerprint(text: str) -> str:
    normalized = text.lower()
    normalized = re.sub(r"[^a-z0-9\s]", " ", normalized)
    return " ".join(normalized.split())


def _torch_semantic_similarity(left: str, right: str) -> float | None:
    left_counts = _semantic_token_counts(left)
    right_counts = _semantic_token_counts(right)
    if not left_counts or not right_counts:
        return None
    vocabulary = sorted(set(left_counts).union(right_counts))
    try:
        import torch
    except ImportError:
        return None

    left_tensor = torch.tensor([float(left_counts.get(token, 0)) for token in vocabulary], dtype=torch.float32)
    right_tensor = torch.tensor([float(right_counts.get(token, 0)) for token in vocabulary], dtype=torch.float32)
    left_norm = torch.linalg.vector_norm(left_tensor)
    right_norm = torch.linalg.vector_norm(right_tensor)
    if float(left_norm.item()) == 0.0 or float(right_norm.item()) == 0.0:
        return None
    return float((torch.dot(left_tensor, right_tensor) / (left_norm * right_norm)).item())


def _semantic_token_counts(text: str) -> Counter[str]:
    aliases = {
        "main": "primary",
        "principal": "primary",
        "downside": "disadvantage",
        "using": "implementing",
        "use": "implementing",
        "uses": "implementing",
        "implement": "implementing",
        "implements": "implementing",
        "limits": "limit",
        "limited": "limit",
        "increases": "increase",
        "increased": "increase",
        "prices": "price",
        "maturities": "maturity",
        "matching": "match",
    }
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    normalized = [aliases.get(token, token[:-1] if token.endswith("s") and len(token) > 4 else token) for token in tokens]
    return Counter(token for token in normalized if len(token) >= 3)


def _near_duplicate(left: str, right: str) -> bool:
    if left == right:
        return True
    if not left or not right:
        return False
    return SequenceMatcher(a=left, b=right).ratio() >= 0.92


def _derive_semantic_title(
    kept_lines: list[str],
    *,
    fallback_title: str,
    file_name: str,
    section_index: int,
) -> str:
    title_candidates = [fallback_title, *kept_lines[:3]]
    for candidate in title_candidates:
        normalized = _normalize_line(candidate)
        if not normalized or _is_generic_title(normalized):
            continue
        if len(normalized.split()) <= 8 and not _looks_like_sentence_title(normalized):
            return cleanSectionDisplayTitle(normalized[:120])
    content_title = _semantic_title_from_content(" ".join(kept_lines[:5]))
    if content_title:
        return cleanSectionDisplayTitle(content_title)
    if kept_lines:
        tokens = _top_tokens(" ".join(kept_lines[:8]))
        if tokens:
            return cleanSectionDisplayTitle(_title_case_from_tokens(tokens[:4]))
    return cleanSectionDisplayTitle(f"{Path(file_name).stem} topic {section_index}")


def _kind_for_label(content_label: ContentLabel, *, file_suffix: str) -> SectionKind:
    if content_label == ContentLabel.ADMINISTRATIVE_CONTENT:
        return SectionKind.LOGISTICS
    if content_label == ContentLabel.WEAK_CONTENT:
        return SectionKind.REFERENCE
    if file_suffix == ".pdf":
        return SectionKind.INSTRUCTIONAL
    return SectionKind.INSTRUCTIONAL


def _should_drop_semantic_section(
    section: SourceSection,
    content_label: ContentLabel,
    *,
    file_suffix: str,
) -> bool:
    if content_label == ContentLabel.ADMINISTRATIVE_CONTENT:
        return True
    if file_suffix == ".pdf" and _looks_like_title_only_section(section):
        return True
    if (
        file_suffix == ".pdf"
        and content_label == ContentLabel.WEAK_CONTENT
        and _looks_like_title_only_section(section)
    ):
        return True
    return False


def _looks_like_title_only_section(section: SourceSection) -> bool:
    text = " ".join(section.text.split())
    if not text:
        return True
    words = _fingerprint(text).split()
    generic_title = _is_generic_title(section.section_title)
    if len(words) <= 4 and generic_title and _teaching_signal_score(text) < 2:
        return True
    lines = [_normalize_line(line) for line in section.text.splitlines() if _normalize_line(line)]
    if len(words) <= 14 and len(lines) <= 3 and generic_title and _teaching_signal_score(text) < 2:
        return True
    if (
        generic_title
        and _near_duplicate(_fingerprint(section.section_title), _fingerprint(text))
        and len(words) <= 12
    ):
        return True
    return False


def _teaching_signal_score(text: str) -> int:
    academic_hits = len(ACADEMIC_SIGNAL_RE.findall(text))
    code_hits = len(CODE_SIGNAL_RE.findall(text))
    relationship_hits = len(
        re.findall(
            r"\b(?:is|are|means|refers to|returns|stores|compares|controls|creates|uses|allows|because)\b",
            text,
            re.IGNORECASE,
        )
    )
    return academic_hits + code_hits + min(relationship_hits, 2)


def _priority_score(section: SourceSection, content_label: ContentLabel) -> float:
    if content_label == ContentLabel.ADMINISTRATIVE_CONTENT:
        return 0.05
    if content_label == ContentLabel.WEAK_CONTENT:
        return 0.35
    score = 0.7
    if len(section.text.split()) >= 60:
        score += 0.1
    if any(keyword in section.text.lower() for keyword in ["example", "definition", "compare", "because"]):
        score += 0.15
    return round(min(score, 1.0), 2)


def _should_build_single_session(sections: list[SourceSection]) -> bool:
    total_words = sum(len(section.text.split()) for section in sections)
    return len(sections) <= 3 or total_words <= 650


def _build_session_section(
    sections: list[SourceSection],
    *,
    file_name: str,
    content_type: str,
) -> SourceSection:
    testable_sections = [section for section in sections if section.content_label == ContentLabel.TESTABLE_CONTENT]
    selected_sections = testable_sections or sections
    anchor = selected_sections[0]
    combined_text = "\n\n".join(section.text for section in selected_sections).strip()
    semantic_title = _derive_semantic_title(
        [selected_sections[0].section_title, *combined_text.splitlines()[:3]],
        fallback_title=selected_sections[0].section_title,
        file_name=file_name,
        section_index=anchor.locator.section_index,
    )
    return anchor.model_copy(
        update={
            "content_type": content_type,
            "section_title": semantic_title,
            "text": combined_text,
            "section_kind": SectionKind.SESSION,
            "content_label": classifyChunk(
                anchor.model_copy(update={"section_title": semantic_title, "text": combined_text})
            ),
            "priority_score": 1.0 if testable_sections else 0.35,
            "is_default": bool(testable_sections),
            "citation_label": f"{file_name} | {semantic_title}",
        }
    )


def _aggregate_pdf_sections(
    sections: list[SourceSection],
    *,
    file_name: str,
    content_type: str,
) -> list[SourceSection]:
    if len(sections) <= 6:
        return sections

    groups: list[list[SourceSection]] = []
    current_group: list[SourceSection] = []
    for section in sections:
        if not current_group:
            current_group.append(section)
            continue
        previous = current_group[-1]
        if (
            len(current_group) >= 4
            or _semantic_topic_shift(previous.section_title, section.section_title)
            or previous.content_label != section.content_label
        ):
            groups.append(current_group)
            current_group = [section]
            continue
        current_group.append(section)
    if current_group:
        groups.append(current_group)

    aggregated: list[SourceSection] = []
    for group in groups:
        first = group[0]
        combined_text = "\n\n".join(section.text for section in group).strip()
        title = _group_semantic_title(group, file_name=file_name)
        content_label = _group_content_label(group)
        aggregated.append(
            first.model_copy(
                update={
                    "content_type": content_type,
                    "section_title": title,
                    "text": combined_text,
                    "content_label": content_label,
                    "section_kind": _kind_for_label(content_label, file_suffix=".pdf"),
                    "priority_score": round(sum(section.priority_score for section in group) / len(group), 2),
                    "is_default": content_label == ContentLabel.TESTABLE_CONTENT,
                    "citation_label": f"{file_name} | {title}",
                }
            )
        )
    return aggregated


def _merge_semantic_neighbors(sections: list[SourceSection], *, file_name: str) -> list[SourceSection]:
    merged: list[SourceSection] = []
    for section in sections:
        if not merged:
            merged.append(section)
            continue
        previous = merged[-1]
        if (
            previous.content_label == section.content_label
            and not _semantic_topic_shift(previous.section_title, section.section_title)
            and len(previous.text.split()) < 240
        ):
            new_title = _group_semantic_title([previous, section], file_name=file_name)
            merged[-1] = previous.model_copy(
                update={
                    "section_title": new_title,
                    "text": f"{previous.text}\n\n{section.text}".strip(),
                    "citation_label": f"{previous.file_name} | {new_title}",
                    "priority_score": round(max(previous.priority_score, section.priority_score), 2),
                    "is_default": previous.is_default or section.is_default,
                }
            )
            continue
        merged.append(section)
    return merged


def _group_content_label(group: list[SourceSection]) -> ContentLabel:
    labels = [section.content_label for section in group]
    counts = Counter(labels)
    if counts[ContentLabel.TESTABLE_CONTENT] > 0:
        return ContentLabel.TESTABLE_CONTENT
    if counts[ContentLabel.WEAK_CONTENT] > 0:
        return ContentLabel.WEAK_CONTENT
    return ContentLabel.ADMINISTRATIVE_CONTENT


def _group_semantic_title(group: list[SourceSection], *, file_name: str) -> str:
    titles = [section.section_title for section in group if section.section_title]
    meaningful_titles = [
        title
        for title in titles
        if not _is_generic_title(title)
    ]
    if meaningful_titles:
        first_title = meaningful_titles[0]
        if len(group) == 1 or all(_semantic_topic_shift(first_title, title) is False for title in meaningful_titles[1:3]):
            return cleanSectionDisplayTitle(first_title)
        second_title = meaningful_titles[1]
        return cleanSectionDisplayTitle(f"{first_title}: {second_title}")
    tokens = _top_tokens(" ".join(section.text for section in group))
    if tokens:
        return cleanSectionDisplayTitle(_title_case_from_tokens(tokens[:4]))
    return cleanSectionDisplayTitle(Path(file_name).stem)


def _semantic_topic_shift(left_title: str, right_title: str) -> bool:
    left_tokens = set(_fingerprint(left_title).split())
    right_tokens = set(_fingerprint(right_title).split())
    if not left_tokens or not right_tokens:
        return False
    overlap = len(left_tokens.intersection(right_tokens))
    return overlap == 0


def _extract_sentences(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text.replace("\n", " ")).strip()
    if not normalized:
        return []
    parts = re.split(r"(?<=[.!?])\s+", normalized)
    return [part.strip().strip(".") for part in parts if part.strip()]


def _best_concept_name(section_title: str, sentences: list[str]) -> str:
    if section_title and not _is_generic_title(section_title) and not _looks_like_sentence_title(section_title):
        return section_title
    semantic_title = _semantic_title_from_content(" ".join(sentences[:4]))
    if semantic_title:
        return semantic_title
    tokens = _top_tokens(" ".join(sentences[:6]))
    return _title_case_from_tokens(tokens[:4]) if tokens else "Core concept"


def _pick_definition(sentences: list[str], concept_name: str) -> str:
    lowered_concept = concept_name.lower()
    for sentence in sentences:
        lowered = sentence.lower()
        if lowered_concept in lowered and any(phrase in lowered for phrase in [" is ", " refers to ", " means "]):
            return sentence
    for sentence in sentences:
        lowered = sentence.lower()
        if any(phrase in lowered for phrase in [" is ", " refers to ", " means "]):
            return sentence
    return sentences[0] if sentences else ""


def _pick_key_points(sentences: list[str], *, skip: str) -> list[str]:
    points: list[str] = []
    for sentence in sentences:
        if sentence == skip:
            continue
        lowered = sentence.lower()
        if any(keyword in lowered for keyword in ["because", "used", "helps", "allows", "step", "result"]):
            points.append(sentence)
    if not points:
        points = [sentence for sentence in sentences if sentence != skip]
    return points


def _pick_confusions(sentences: list[str], concept_name: str) -> list[str]:
    confusions: list[str] = []
    lowered_concept = concept_name.lower()
    for sentence in sentences:
        lowered = sentence.lower()
        if " vs " in lowered or "different from" in lowered or "not" in lowered:
            confusions.append(sentence)
        elif lowered_concept and lowered_concept not in lowered and any(
            token in lowered for token in ["expression", "statement", "type", "loop", "variable", "function"]
        ):
            confusions.append(sentence)
    return confusions


def _pick_examples(sentences: list[str]) -> list[str]:
    return [
        sentence
        for sentence in sentences
        if any(keyword in sentence.lower() for keyword in ["example", "for example", "e.g.", "such as", "="])
    ]


def _pick_testable_facts(sentences: list[str], definition: str, key_points: list[str]) -> list[str]:
    facts = [definition, *key_points]
    for sentence in sentences:
        lowered = sentence.lower()
        if any(keyword in lowered for keyword in ["always", "only", "returns", "controls", "creates", "stores"]):
            facts.append(sentence)
    return [fact for fact in facts if fact]


def _unique_trimmed(values: list[str], *, limit: int) -> list[str]:
    unique: list[str] = []
    for value in values:
        normalized = _fingerprint(value)
        if not normalized or any(_near_duplicate(normalized, _fingerprint(item)) for item in unique):
            continue
        unique.append(value.strip())
        if len(unique) >= limit:
            break
    return unique


def _build_mcq_from_knowledge(knowledge: SectionKnowledge, sequence_index: int) -> GeneratedExamQuestion:
    concept = knowledge.concepts[0] if knowledge.concepts else KnowledgeConcept(
        name=knowledge.section_title,
        definition=knowledge.summary,
        key_points=[knowledge.summary],
        common_confusions=[],
        examples=[],
        testable_facts=[knowledge.summary],
    )
    mode = sequence_index % 3
    selected_fact = _select_fact_for_question(concept, sequence_index)
    parsed_fact = _parse_fact(selected_fact)
    if parsed_fact is not None:
        prompt, correct, distractors, rationale = _build_mcq_from_fact(parsed_fact, concept)
    elif concept.common_confusions and mode == 0:
        prompt = f"Which statement correctly distinguishes {concept.name.lower()}?"
        correct = _paraphrase_fact(concept.definition or concept.testable_facts[0])
        distractors = [_negate_or_shift(confusion, concept.name) for confusion in concept.common_confusions[:3]]
        rationale = f"The correct answer captures the core distinction behind {concept.name.lower()}."
    elif concept.examples and mode == 1:
        prompt = "Which concept is illustrated by the example?"
        correct = _limit_words(concept.name, 20)
        distractors = _distractors_from_knowledge(concept, correct)
        rationale = f"The example matches the defining features of {concept.name.lower()}."
    else:
        prompt = f"Which statement best defines {concept.name.lower()}?"
        correct = _paraphrase_fact(concept.definition or concept.testable_facts[0])
        distractors = _distractors_from_knowledge(concept, correct)
        rationale = f"The correct answer matches the core idea behind {concept.name.lower()}."

    options = _assemble_options(correct, distractors, sequence_index)
    correct_text = _limit_words(correct, 20)
    return GeneratedExamQuestion(
        prompt=_limit_words(prompt, 16),
        options=options,
        correct_answer=correct_text,
        correct_option_id=["A", "B", "C", "D"][options.index(correct_text)],
        rationale=_limit_words(rationale, 24),
        incorrect_rationales=[f'"{option}" does not match the tested concept.' for option in options if option != correct_text],
    )


def _distractors_from_knowledge(concept: KnowledgeConcept, correct: str) -> list[str]:
    distractors: list[str] = []
    for confusion in concept.common_confusions:
        distractors.append(_negate_or_shift(confusion, concept.name))
    for point in concept.key_points:
        if _fingerprint(point) != _fingerprint(correct):
            distractors.append(_paraphrase_distractor(point))
    generic = [
        "It follows an unrelated rule.",
        "It reverses the main idea.",
        "It changes a different quantity.",
        "It confuses the concept with another step.",
    ]
    distractors.extend(generic)
    return distractors


def _assemble_options(correct: str, distractors: list[str], sequence_index: int) -> list[str]:
    correct_text = _limit_words(correct, 20)
    option_pool: list[str] = []
    for distractor in distractors:
        compact = _limit_words(distractor, 20)
        if not compact or _fingerprint(compact) == _fingerprint(correct_text):
            continue
        if any(_near_duplicate(_fingerprint(compact), _fingerprint(existing)) for existing in option_pool):
            continue
        option_pool.append(compact)
        if len(option_pool) >= 3:
            break

    while len(option_pool) < 3:
        fallback = f"Incorrect interpretation {len(option_pool) + 1}"
        option_pool.append(fallback)

    insertion_index = (sequence_index - 1) % 4
    options = option_pool[:]
    options.insert(insertion_index, correct_text)
    return options[:4]


def _negate_or_shift(text: str, concept_name: str) -> str:
    lowered = text.lower()
    if " not " in lowered:
        return _limit_words(text, 20)
    if concept_name.lower() in lowered:
        return _limit_words(text.replace(concept_name, f"not {concept_name}"), 20)
    return _limit_words(f"It is not about {concept_name.lower()}.", 20)


def _swap_key_terms(text: str) -> str:
    replacements = [
        ("increases", "removes"),
        ("decreases", "guarantees"),
        ("stores", "ignores"),
        ("returns", "replaces"),
        ("controls", "ignores"),
        ("expression", "instruction"),
        ("statement", "value"),
        ("loop", "single step"),
        ("variable", "fixed constant"),
        ("learning rate", "feature count"),
        ("gradient", "output label"),
    ]
    updated = text
    for left, right in replacements:
        if left in updated.lower():
            updated = re.sub(left, right, updated, flags=re.IGNORECASE)
            return _limit_words(updated, 20)
    return _limit_words("It describes a different idea than the concept.", 20)


def _top_tokens(text: str) -> list[str]:
    tokens = [
        _singularize_token(token)
        for token in _fingerprint(text).split()
        if len(token) > 3 and token not in {"this", "that", "with", "from", "into", "about", "there", "their"}
        and token not in {"notes", "topic", "section", "worked", "example", "introduction", "page", "pages"}
        and token not in {keyword.replace(" ", "") for keyword in ADMIN_KEYWORDS}
    ]
    counts = Counter(tokens)
    return [token for token, _count in counts.most_common(6)]


def _title_case_from_tokens(tokens: list[str]) -> str:
    formatted: list[str] = []
    for token in tokens:
        if token == "vs":
            formatted.append("vs")
        else:
            formatted.append(token.capitalize())
    return " ".join(formatted)


def _limit_words(text: str, max_words: int) -> str:
    words = text.replace("\n", " ").split()
    if len(words) <= max_words:
        return " ".join(words).strip().strip(".")
    return " ".join(words[:max_words]).strip().strip(".")


def _looks_like_sentence_title(text: str) -> bool:
    lowered = text.lower().strip()
    if lowered.endswith(".") or lowered.endswith("?"):
        return True
    return any(token in lowered for token in [" is ", " are ", " uses ", " updates ", " controls ", " shows "])


def _copied_from_source(candidate: str, normalized_source: str) -> bool:
    fingerprint = _fingerprint(candidate)
    if not fingerprint:
        return False
    if len(fingerprint.split()) >= 10 and fingerprint in normalized_source:
        return True
    source_windows = normalized_source.split()
    if len(source_windows) < 8:
        return False
    return any(
        _similarity(candidate, " ".join(source_windows[index : index + min(16, len(fingerprint.split()))])) >= 0.9
        for index in range(max(len(source_windows) - 7, 1))
    )


def _is_generic_title(title: str) -> bool:
    lowered = _normalize_line(title).lower()
    if not lowered:
        return True
    if lowered in GENERIC_SECTION_TITLES:
        return True
    if re.fullmatch(r"(lecture|slide|slides|page|session|week|topic|module)\s+\d+", lowered):
        return True
    if re.fullmatch(r"worked example\s+\d+", lowered):
        return True
    if any(keyword in lowered for keyword in ADMIN_KEYWORDS):
        return True
    tokens = _fingerprint(lowered).split()
    if not tokens:
        return True
    if tokens[-1] == "notes" and len(tokens) <= 3:
        return True
    generic_tokens = {"notes", "lecture", "slides", "slide", "session", "week", "topic", "overview"}
    if all(token in generic_tokens or token.isdigit() for token in tokens):
        return True
    return False


def _semantic_title_from_content(text: str) -> str | None:
    phrases: list[str] = []
    for sentence in _extract_sentences(text):
        phrase = _subject_phrase(sentence)
        if not phrase:
            continue
        title = _title_case_phrase(phrase)
        if title and title.lower() not in {item.lower() for item in phrases}:
            phrases.append(title)
        if len(phrases) >= 2:
            break
    if len(phrases) >= 2 and phrases[0].lower() != phrases[1].lower():
        return f"{phrases[0]} and {phrases[1]}"
    if phrases:
        return phrases[0]
    return None


def _subject_phrase(sentence: str) -> str | None:
    normalized = _normalize_line(sentence).strip(".")
    match = re.match(
        r"(?P<subject>[A-Za-z][A-Za-z0-9+\-/ ]{1,60}?)\s+"
        r"(?P<verb>is|are|means|refers to|updates|controls|uses|returns|stores|creates|shows|describes|compares|moves|takes|produces|performs)\b",
        normalized,
        re.IGNORECASE,
    )
    if not match:
        return None
    subject = re.sub(r"^(?:an?|the)\s+", "", match.group("subject"), flags=re.IGNORECASE).strip()
    if not subject or len(subject.split()) > 5:
        return None
    return subject


def _title_case_phrase(text: str) -> str:
    words = [word for word in _fingerprint(text).split() if word]
    return " ".join(word.capitalize() for word in words[:5])


def _singularize_token(token: str) -> str:
    if token.endswith("ies") and len(token) > 4:
        return f"{token[:-3]}y"
    if token.endswith("s") and len(token) > 4 and not token.endswith("ss"):
        return token[:-1]
    return token


def _select_fact_for_question(concept: KnowledgeConcept, sequence_index: int) -> str:
    fact_pool = concept.testable_facts or concept.key_points or [concept.definition]
    return fact_pool[(sequence_index - 1) % len(fact_pool)]


def _parse_fact(sentence: str) -> tuple[str, str, str] | None:
    normalized = _normalize_line(sentence).strip(".")
    match = re.match(
        r"(?P<subject>.+?)\s+(?P<verb>updates|controls|uses|returns|stores|creates|moves|takes|produces|performs|is|are|means|refers to)\s+(?P<object>.+)",
        normalized,
        re.IGNORECASE,
    )
    if not match:
        return None
    subject = re.sub(r"^(?:an?|the)\s+", "", match.group("subject"), flags=re.IGNORECASE).strip()
    verb = match.group("verb").lower().strip()
    obj = match.group("object").strip()
    if not subject or not obj:
        return None
    return subject, verb, obj


def _build_mcq_from_fact(
    parsed_fact: tuple[str, str, str],
    concept: KnowledgeConcept,
) -> tuple[str, str, list[str], str]:
    subject, verb, obj = parsed_fact
    lowered_subject = subject.lower()
    if verb == "controls":
        prompt = f"What does {lowered_subject} control?"
        correct = _paraphrase_object(obj)
        distractors = [
            "The number of output classes",
            "The feature names",
            "The label values",
        ]
        rationale = f"The teaching section states that {lowered_subject} determines {correct.lower()}."
        return prompt, correct, distractors, rationale
    if verb == "produces":
        prompt = f"What does {lowered_subject} produce?"
        correct = _paraphrase_object(obj)
        distractors = [
            "A side effect only",
            "A control statement",
            "A fixed file path",
        ]
        rationale = f"The concept is defined by producing {correct.lower()}."
        return prompt, correct, distractors, rationale
    if verb == "performs":
        prompt = f"What does {lowered_subject} primarily do?"
        correct = _paraphrase_object(obj)
        distractors = [
            "Stores a value automatically",
            "Returns a dataset label",
            "Names a variable type",
        ]
        rationale = f"The concept is characterized by {correct.lower()}."
        return prompt, correct, distractors, rationale
    if verb == "uses":
        prompt = f"What does {lowered_subject} use for each step?"
        correct = _paraphrase_object(obj)
        distractors = [
            "Only the validation set",
            "One feature at a time",
            "A random target label",
        ]
        rationale = f"The teaching section identifies {correct.lower()} as the input used on each step."
        return prompt, correct, distractors, rationale
    if verb == "updates":
        target, method = _split_method_phrase(obj)
        prompt = f"How does {lowered_subject} update {target.lower()}?"
        correct = _paraphrase_method(method or obj)
        distractors = [
            "By following the gradient direction",
            "By leaving all values unchanged",
            "By resetting parameters randomly",
        ]
        rationale = f"The update rule is based on {correct.lower()}."
        return prompt, correct, distractors, rationale
    if verb in {"is", "are", "means", "refers to"}:
        prompt = f"Which statement best defines {lowered_subject}?"
        correct = _paraphrase_object(obj)
        distractors = [
            "A fixed reporting format",
            "An unrelated preprocessing step",
            "A random output label",
        ]
        rationale = f"The correct answer captures the definition of {lowered_subject}."
        return prompt, correct, distractors, rationale
    prompt = f"Which statement is most accurate about {concept.name.lower()}?"
    correct = _paraphrase_fact(" ".join(parsed_fact))
    distractors = _distractors_from_knowledge(concept, correct)
    rationale = f"The correct answer matches the tested principle behind {concept.name.lower()}."
    return prompt, correct, distractors, rationale


def _split_method_phrase(text: str) -> tuple[str, str | None]:
    if " by " not in text.lower():
        return text, None
    target, method = re.split(r"\bby\b", text, maxsplit=1, flags=re.IGNORECASE)
    return target.strip(), method.strip()


def _paraphrase_method(text: str) -> str:
    compact = _normalize_line(text).strip(".")
    compact = re.sub(r"^(?:by\s+)?", "By ", compact, flags=re.IGNORECASE)
    compact = compact.replace("each update", "each step")
    return _limit_words(compact, 12)


def _paraphrase_object(text: str) -> str:
    compact = _normalize_line(text).strip(".")
    compact = re.sub(r"\bduring each update\b", "for each update", compact, flags=re.IGNORECASE)
    compact = re.sub(r"\bfor each step\b", "", compact, flags=re.IGNORECASE).strip(" ,")
    compact = compact.replace("the whole dataset", "the full dataset")
    compact = compact.replace("step size", "size of each update step")
    return _limit_words(compact, 12)


def _paraphrase_fact(text: str) -> str:
    compact = _normalize_line(text).strip(".")
    replacements = [
        ("updates model parameters by moving opposite the gradient", "moves parameters opposite the gradient"),
        ("updates parameters by moving opposite the gradient", "moves parameters opposite the gradient"),
        ("controls the step size during each update", "sets the size of each update step"),
        ("uses the whole dataset for each step", "uses the full dataset on every step"),
    ]
    lowered = compact.lower()
    for source, target in replacements:
        if source in lowered:
            return _limit_words(target, 12)
    return _limit_words(compact, 12)


def _paraphrase_distractor(text: str) -> str:
    return _swap_key_terms(_paraphrase_fact(text))


def _similarity(left: str, right: str) -> float:
    return SequenceMatcher(a=_fingerprint(left), b=_fingerprint(right)).ratio()
