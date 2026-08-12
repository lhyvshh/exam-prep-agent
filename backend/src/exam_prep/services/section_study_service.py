from collections import Counter
from datetime import UTC, datetime
import hashlib
import json
import re
from urllib.parse import quote

from exam_prep.repositories.material_store import MaterialStore
from exam_prep.schemas.materials import (
    ContentLabel,
    MaterialStageStatus,
    MaterialStudyDocument,
    MaterialStudyGroup,
    MaterialStudySection,
    OriginalBookContent,
    OriginalBookItem,
    SectionKind,
    SourceSection,
    StudyConceptCard,
    StudiedStatus,
    StudyDifficulty,
    StudyFlashcard,
    StudyFormulaCard,
    StudyLearningOutcome,
)
from exam_prep.services.question_pipeline import (
    KnowledgeConcept,
    SectionKnowledge,
    cleanSectionDisplayTitle,
    extractKnowledge,
)

TOKEN_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9_\-]{2,}\b")
FORMULA_RE = re.compile(
    r"(?i)(?:"
    r"\b[a-z_][a-z0-9_]*\s*(?:==|!=|<=|>=|=|<|>)\s*[^.;\n]{1,100}|"
    r"\b[a-z_][a-z0-9_]*\s*\([^)]{0,80}\)|"
    r"\b(?:and|or|not)\b\s*[:=-]?\s*[^.;\n]{4,100}|"
    r"\b(?:formula|rule|function|method|algorithm|constraint|equation|operator)\b[^.\n]{0,140}"
    r")"
)
FORMULA_LABEL_RE = re.compile(
    r"^(?P<name>[A-Za-z][A-Za-z0-9 /()'’.,&+-]{2,120}):\s*(?P<formula>.+?=.+)$"
)
GENERIC_FLASHCARD_FRONT_RE = re.compile(
    r"(what exact rule|what does this module say|what is the key idea|"
    r"what does the book give here|summarize this section|"
    r"what exam trap should you remember for|why does .{1,120} matter for\s+lo\s*\d+\.[a-z]|"
    r"what is event is|what is of the|what is all the|what is the following conditions|"
    r"what (?:is|are) (?:these opinions|there|when the assets|another option)|"
    r"what (?:is|are) (?:var and|banks should|while the)\b|"
    r"what is and reward|what is opportunities with lower|what is risk have lower|what is to the risk|"
    r"what is if a time series|what is such a time series|what are if the observations|"
    r"what (?:is|are) (?:also\s+)?assume that\b|"
    r"what (?:is|are) assume that there\b|"
    r"what (?:is|are) also assume that the\b|"
    r"what (?:is|are).*?\bassume that\b|"
    r"what (?:is|are) also\b|"
    r"what (?:is|are) (?:because|if|when|where|while|although|suppose|given|some)\b|"
    r"what (?:is|are) (?:no payments?|payment|payments|countries)\?|"
    r"what (?:is|are) (?:electricity|interest|t-bond prices)\?|"
    r"what are because option contracts\?|"
    r"what (?:is|are) .{1,120}\boccurs (?:when|because)\b|"
    r"what are european options\?|"
    r"what are not all|what is a special type of serially uncorrelated series|"
    r"what does some of\b|what are their goals|"
    r"what should you remember about\b|"
    r"how does .{1,160}\brelate to\b .{1,160}|"
    r"what is .{1,120}\bis\b|"
    r"what (?:is|are) (?:domino effect where|retain risk|frontline managers|various functional units|"
    r"borrower defaulting|derive the capital|both treynor|pricing theory)\?|"
    r"what is .{1,80}\b(?:where|that|which|per|from|to|with|and|both|various)\?|"
    r"what are they\?|what is risk management process\?|"
    r"what are two events\?|"
    r"what is use the t-test\b|"
    r"what are each of these assumptions\?|"
    r"what are a parametric model typically assumes\b|"
    r"what is a positive butterfly means\b|"
    r"what is determine if\b|"
    r"what is the term\b|"
    r"what is each data point\?|"
    r"what is the centers\b|"
    r"what is the bsm model suggests\b|"
    r"what is the plot\?|"
    r"what is [a-z]\s+variables\?|"
    r"what is explain\s+how\b|"
    r"what is the (?:two|three|four|most|important)\b|"
    r"what (?:is|are) (?:the\s+)?(?:formula|applications?)\?|"
    r"what does best practices for\b|"
    r"what is a common exam trap about (?!expected loss|risk and reward|economic capital|tail risk|risk management|"
    r"operational loss frequency and severity|black-scholes-merton stock-price and return distributions|forward rates)"
    r"[a-z0-9 /()'-]{3,120}|"
    r"methods include scenario relate to value risk economic capital ways|"
    r"^what is random event\?|"
    r"\blo\s*\d+\.[a-z]\b)",
    re.IGNORECASE,
)
DANGLING_FLASHCARD_PHRASES = {
    "and reward",
    "opportunities with lower",
    "risk have lower",
    "to the risk",
    "methods include scenario",
    "value risk economic capital ways",
    "if a time series",
    "such a time series",
    "if the observations",
    "because option contracts",
    "no payments",
    "t-bond prices",
    "also assume that",
    "assume that",
    "assume that there",
    "assume that the",
    "also assume that the",
    "suppose that",
    "two events",
    "use the t-test",
    "each of these assumptions",
    "a parametric model typically assumes",
    "positive butterfly means",
    "determine if",
    "the term linear",
    "each data point",
    "centers of the data clusters",
    "bsm model suggests",
    "the plot",
    "sometimes we",
    "note that the",
    "note also that",
}
CONTENT_ANCHOR_STOPWORDS = {
    "about",
    "after",
    "again",
    "answer",
    "before",
    "book",
    "card",
    "does",
    "exam",
    "give",
    "here",
    "idea",
    "key",
    "module",
    "question",
    "remember",
    "rule",
    "section",
    "should",
    "step",
    "summarize",
    "this",
    "what",
    "when",
    "where",
    "which",
    "with",
}
MIN_FLASHCARDS_PER_CONCEPT = 10
MIN_FLASHCARDS_PER_LEARNING_OUTCOME = 10
MAX_FLASHCARDS_PER_CONCEPT = 24
STUDY_PIPELINE_VERSION = 34
MAX_FORMULA_SOURCE_EXCERPT_CHARS = 4_000
MAX_FLASHCARD_LLM_SOURCE_CHARS = 2_800
FLASHCARD_LLM_SYSTEM_PROMPT = (
    "You generate exam-prep flashcards only from validated source anchors. "
    "You must not invent content, use broken fragments, or create generic cards. "
    "Every card must be tied to a source page, module, and learning objective when available."
)
WORKBOOK_MODULE_TITLE_RE = re.compile(
    r"^Study Session (?P<session_number>\d+): (?P<session_title>.+?) / "
    r"Reading (?P<reading_number>\d+): (?P<reading_title>.+?) / "
    r"Module (?P<module_number>\d+(?:\.[0-9A-Za-z]+)*): (?P<module_title>.+)$",
    re.IGNORECASE,
)
FORMULA_IMAGE_CROP_RE = re.compile(
    r'^\[FORMULA_IMAGE_CROP\s+page=(?P<page>\d+)\s+path=(?P<path>\S+)\s+label="(?P<label>[^"]+)"\]$'
)
FINANCE_ACADEMIC_TERMS = [
    "risk",
    "risk management",
    "financial risk",
    "market risk",
    "credit risk",
    "liquidity",
    "operational risk",
    "governance",
    "valuation",
    "interest rate",
    "foreign exchange",
    "cyber risk",
    "regulation",
    "capital",
    "portfolio",
    "derivative",
    "treasury bond futures contract",
    "treasury bond futures",
    "bond futures",
    "futures contract",
    "conversion factor",
    "cheapest-to-deliver bond",
    "deliverable bond",
    "delivery options",
    "quality option",
    "timing option",
    "wild card option",
    "accrued interest",
    "short position",
    "long position",
    "basis",
    "futures price",
    "cash futures price",
    "quoted futures price",
    "cost of carry",
    "yield curve",
    "interest rate risk",
    "forward contract",
    "option contract",
    "strike price",
    "exercise price",
    "initial margin",
    "maintenance margin",
    "clearinghouse",
    "call option",
    "put option",
    "underlying asset",
    "underlying share price",
    "hedge",
    "volatility",
    "probability",
    "event space",
    "random event",
    "conditional probability",
    "unconditional probability",
    "joint probability",
    "independent events",
    "mutually exclusive events",
    "conditional independence",
    "bayes rule",
    "probability mass function",
    "probability function",
    "cumulative distribution function",
    "probability matrix",
    "marginal distribution",
    "conditional distribution",
    "covariance",
    "correlation coefficient",
    "independent and identically distributed random variables",
    "iid random variables",
    "regression analysis",
    "dependent variable",
    "independent variable",
    "regression coefficient",
    "residual",
    "r-squared",
    "multiple regression",
    "covariance stationary time series",
    "autocorrelation",
    "autoregressive model",
    "moving average model",
    "unit root",
    "seasonality",
    "returns",
    "correlation",
    "dependence",
    "bootstrapping",
    "random number generation",
    "principal components analysis",
    "k-means clustering",
    "training sample",
    "test sample",
    "overfitting",
    "regularization",
    "logistic regression",
    "coherent risk measure",
    "expected shortfall",
    "monotonicity",
    "subadditivity",
    "positive homogeneity",
    "translational invariance",
    "fat tails",
    "skewness",
    "stochastic volatility",
    "regime switching",
    "loss frequency",
    "loss severity",
    "monte carlo simulation",
    "p-value",
    "t-test",
    "confidence interval",
    "population parameter",
    "test statistic",
    "multiple testing",
    "null hypothesis",
    "alternative hypothesis",
    "type i error",
    "type ii error",
    "test power",
    "black-scholes-merton model",
    "black-scholes model",
    "lognormal distribution",
    "lognormally distributed",
    "realized return",
    "historical volatility",
    "option delta",
    "delta hedging",
    "delta-neutral portfolio",
    "delta-neutral hedge",
    "stress",
    "scenario",
    "expected loss",
    "unexpected loss",
    "risk factor",
    "option",
    "options",
    "option writer",
    "option writers",
    "margin",
    "margin account",
    "margin requirements",
    "uncovered call",
    "uncovered calls",
    "covered call",
    "covered calls",
    "options clearing corporation",
    "occ",
    "exchange-traded options",
    "otc options",
    "default risk",
    "insurance",
    "insurance coverage",
    "premium",
    "premiums",
    "policyholders",
    "life insurance",
    "property and casualty insurance",
    "health insurance",
    "pension",
    "pension plans",
    "retirement obligations",
    "diversification",
    "time series",
    "white noise",
    "coverage",
    "mutual fund",
    "mutual funds",
    "exchange-traded fund",
    "exchange-traded funds",
    "etf",
    "etfs",
    "late trading",
    "market timing",
    "net asset value",
    "nav",
    "option pricing factors",
    "time to expiration",
    "dividends",
    "american option",
    "american options",
    "european option",
    "european options",
    "option buyer",
    "option seller",
    "option payoff",
    "interest rate swap",
    "plain vanilla interest rate swap",
    "notional principal",
    "sofr",
    "floating rate",
    "fixed rate",
    "fixed-rate payer",
    "floating-rate payer",
    "swap dealer",
    "isda master agreement",
    "comparative advantage",
    "central counterparty",
    "central counterparties",
    "ccp",
    "clearing member",
    "clearing members",
    "non-member",
    "non-members",
    "default fund",
    "model risk",
    "legal risk",
    "investment risk",
    "default correlation",
    "long futures position",
    "short futures position",
    "spot price",
    "delivery",
    "open interest",
    "storage costs",
    "transportation costs",
    "transport costs",
    "shorting costs",
    "lease rate",
    "convenience yield",
    "carry market",
    "commodity futures",
    "agricultural commodities",
    "crude oil",
    "metals",
    "weather derivatives",
    "day count conventions",
    "actual/actual",
    "30/360",
    "actual/360",
    "discount rate basis",
    "clean price",
    "dirty price",
    "duration-based hedge",
    "duration-based hedges",
    "duration-based hedge ratio",
    "hedge ratio",
    "nonparallel shifts",
    "convexity",
    "bank risks",
    "banking book",
    "trading book",
    "deposit insurance",
    "moral hazard",
    "originate-to-distribute",
    "regulatory capital",
    "economic capital",
    "solvency risk",
    "basel committee",
    "investment banking",
    "foreign exchange quotes",
    "fx quote",
    "base currency",
    "quote currency",
    "bid price",
    "ask price",
    "spot transaction",
    "outright forward",
    "fx swap",
    "transaction risk",
    "translation risk",
    "economic risk",
    "purchasing power parity",
    "covered interest rate parity",
    "uncovered interest rate parity",
    "real interest rate",
    "nominal interest rate",
    "currency appreciation",
    "currency depreciation",
    "mortgage-backed security",
    "mortgage-backed securities",
    "mbs",
    "fixed-rate mortgage",
    "adjustable-rate mortgage",
    "weighted average coupon",
    "weighted average maturity",
    "wac",
    "wam",
    "single monthly mortality",
    "smm",
    "conditional prepayment rate",
    "cpr",
    "prepayment risk",
    "pass-through security",
    "collateralized mortgage obligation",
    "collateralized mortgage obligations",
    "cmo",
    "tranche",
    "tranches",
    "option-adjusted spread",
    "oas",
    "swap valuation",
    "fixed-rate bond",
    "floating-rate bond",
    "forward rate agreement",
    "forward rate agreements",
    "fra",
    "discount curve",
    "fair swap rate",
    "spot rate",
    "spot rates",
    "forward rate",
    "forward rates",
    "zero-coupon bond",
    "discount factor",
    "discount factors",
    "yield to maturity",
    "duration",
    "modified duration",
    "effective duration",
    "price-yield relationship",
    "credit spread",
    "credit spreads",
    "event risk",
    "rating migration risk",
    "recovery rate",
    "high-yield bond",
    "high-yield bonds",
    "investment-grade bond",
    "investment-grade bonds",
    "protective put",
    "covered call",
    "bull spread",
    "bear spread",
    "box spread",
    "straddle",
    "strangle",
    "butterfly spread",
    "uniform distribution",
    "bernoulli trial",
    "binomial distribution",
    "poisson distribution",
    "standard normal distribution",
    "cumulative distribution function",
    "historical-based var approaches",
    "parametric var approach",
    "nonparametric var approach",
    "historical simulation",
    "implied volatility",
    "filtered historical simulation",
    "normal yield curve",
    "flat yield curve",
    "inverted yield curve",
    "positive butterfly",
    "negative butterfly",
    "yield curve twist",
    "twist",
]
JUNK_STUDY_TERMS = {
    "agenda",
    "announcement",
    "announcements",
    "attendance",
    "basics",
    "break",
    "canvas",
    "class",
    "course",
    "could",
    "date",
    "dec",
    "deadline",
    "due",
    "email",
    "exam",
    "final",
    "firm",
    "firms",
    "friday",
    "holiday",
    "homework",
    "hours",
    "instructor",
    "introduction",
    "lecture",
    "line managers",
    "line managers right",
    "logistics",
    "management strategies",
    "operational risks attempts",
    "midterm",
    "monday",
    "name",
    "nov",
    "oct",
    "office",
    "practice",
    "powerpoint",
    "practices in corporate",
    "should",
    "senior managers",
    "schedule",
    "session",
    "slide",
    "slides",
    "ta",
    "thanksgiving",
    "they",
    "their goals",
    "today",
    "topic",
    "week",
    "worksheet",
    "would",
    "is usually influenced",
    "another option",
    "these opinions",
    "there",
    "when the assets",
    "late trading occurs when",
    "market timing occurs because",
    "european options",
    "zoom",
    "all the subsets",
    "also",
    "assume",
    "assume that",
    "assume that there",
    "assume that the",
    "also assume that",
    "also assume that the",
    "event is one",
    "four different risk",
    "following conditions",
    "general term",
    "borrower defaulting",
    "both treynor",
    "derive the capital",
    "domino effect where",
    "frontline managers",
    "of the possible",
    "role and responsibilities",
    "pricing theory",
    "retain risk",
    "various functional units",
    "models",
    "quotes",
    "spot quotes",
    "so portfolio currency risk",
    "less costly alternative",
    "answer because",
    "trading",
    "two events",
    "use the t-test",
    "each of these assumptions",
    "a parametric model typically assumes",
    "positive butterfly means",
}

FRAGMENT_FLASHCARD_TERMS = {
    "all the subsets",
    "also",
    "also assume that",
    "also assume that the",
    "and reward",
    "assume",
    "assume that",
    "assume that there",
    "assume that the",
    "another option",
    "borrower defaulting",
    "both treynor",
    "derive the capital",
    "domino effect where",
    "event is one",
    "frontline managers",
    "four different risk",
    "following conditions",
    "general term",
    "if a time series",
    "if the observations",
    "methods include scenario",
    "operational risks attempts",
    "of the possible",
    "one",
    "opportunities with lower",
    "possible",
    "risk have lower",
    "role and responsibilities",
    "pricing theory",
    "retain risk",
    "subsets",
    "such a time series",
    "models",
    "quotes",
    "spot quotes",
    "so portfolio currency risk",
    "less costly alternative",
    "answer because",
    "trading",
    "two events",
    "use the t-test",
    "each of these assumptions",
    "a parametric model typically assumes",
    "positive butterfly means",
    "they",
    "these opinions",
    "their goals",
    "there",
    "to the risk",
    "various functional units",
    "value risk economic capital ways",
    "when the assets",
    "late trading occurs when",
    "market timing occurs because",
    "european options",
}

WORKBOOK_SUPPORT_BLOCKS = {
    "exam_focus": "EXAM FOCUS",
    "key_concepts": "KEY CONCEPTS",
    "module_quiz": "MODULE QUIZ",
    "answer_key": "ANSWER KEY FOR MODULE QUIZZES",
    "formulas": "FORMULAS",
}

FRM_MEMORIZE_PHRASES = [
    "risk management",
    "risk management process",
    "risk management strategy",
    "risk management strategies",
    "risk appetite",
    "risk acceptance",
    "accept risk",
    "avoid risk",
    "mitigate risk",
    "transfer risk",
    "expected loss",
    "unexpected loss",
    "market risk",
    "credit risk",
    "liquidity risk",
    "operational risk",
    "basis risk",
    "credit derivatives",
    "credit derivatives market",
    "credit risk transfer",
    "interest rate risk",
    "foreign exchange risk",
    "counterparty risk",
    "board oversight",
    "corporate governance",
    "corporate risk management",
    "financial crisis",
    "hedging",
    "derivatives",
    "modern portfolio theory",
    "capital market line",
    "capital asset pricing model",
    "risk data aggregation",
    "risk culture",
    "scenario analysis",
    "model risk",
    "rogue trading",
    "securitization",
]

WORKBOOK_KEYWORD_TRAILING_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "be",
    "been",
    "being",
    "began",
    "can",
    "could",
    "declined",
    "did",
    "do",
    "does",
    "equal",
    "for",
    "from",
    "has",
    "have",
    "helped",
    "in",
    "is",
    "leading",
    "may",
    "of",
    "on",
    "participants",
    "rational",
    "refers",
    "should",
    "that",
    "the",
    "to",
    "was",
    "were",
    "will",
    "with",
    "would",
}


class SectionStudyService:
    def __init__(self, store: MaterialStore) -> None:
        self.store = store

    def ensure_study_document(
        self,
        material_id: str,
        *,
        force: bool = False,
    ) -> MaterialStudyDocument | None:
        parsed = self.store.get_parsed_document(material_id)
        if parsed is None:
            return None

        existing = self.store.get_study_document(material_id)
        if (
            existing is not None
            and not force
            and existing.content_hash == parsed.record.content_hash
            and existing.pipeline_version == STUDY_PIPELINE_VERSION
        ):
            return existing

        previous_by_id = {
            section.section_id: section
            for section in existing.sections
        } if existing is not None else {}
        usable_sections = self._usable_sections(parsed.sections)
        groups = self._build_groups(parsed.record.material_id, usable_sections)
        group_by_section = self._group_id_by_section(groups, usable_sections)

        study_sections = [
            self._build_study_section(
                section,
                display_order=index,
                parent_group_id=group_by_section.get(section.source_id),
                previous=previous_by_id.get(section.source_id),
            )
            for index, section in enumerate(usable_sections, start=1)
        ]
        study_sections = self._dedupe_study_sections(study_sections)
        groups = self._hydrate_group_counts(groups, study_sections)
        document = MaterialStudyDocument(
            material_id=material_id,
            content_hash=parsed.record.content_hash,
            pipeline_version=STUDY_PIPELINE_VERSION,
            generated_at=datetime.now(UTC).isoformat(),
            groups=groups,
            sections=study_sections,
        )
        self.store.save_study_document(document)
        return document

    def _dedupe_study_sections(
        self,
        sections: list[MaterialStudySection],
    ) -> list[MaterialStudySection]:
        """Keep the richest real module when parser fallbacks create duplicate cards."""

        by_key: dict[str, MaterialStudySection] = {}
        merged_source_ids: dict[str, list[str]] = {}
        ordered_keys: list[str] = []
        for section in sections:
            key = section.normalized_title or section.title.lower()
            if key not in by_key:
                by_key[key] = section
                merged_source_ids[key] = list(section.source_ids)
                ordered_keys.append(key)
                continue

            current = by_key[key]
            merged_source_ids[key].extend(section.source_ids)
            if self._study_section_richness_score(section) > self._study_section_richness_score(current):
                by_key[key] = section

        deduped: list[MaterialStudySection] = []
        for display_order, key in enumerate(ordered_keys, start=1):
            section = by_key[key]
            source_ids = list(dict.fromkeys(merged_source_ids[key]))
            deduped.append(section.model_copy(update={"display_order": display_order, "source_ids": source_ids}))
        return deduped

    def _study_section_richness_score(self, section: MaterialStudySection) -> int:
        score = 0
        score += len(section.flashcards) * 100
        score += len(section.formulas) * 80
        score += len(section.concepts) * 25
        score += len(section.learning_outcomes) * 20
        score += len(section.original_book_content.key_concepts) * 15
        score += len(section.original_book_content.module_quiz) * 15
        score += len(section.original_book_content.answers) * 15
        score += len(section.source_ids) * 5
        if section.quiz_ready:
            score += 10
        if section.page_start is not None and section.page_start <= 6 and not section.formulas:
            score -= 50
        return score

    def update_studied_status(
        self,
        material_id: str,
        section_id: str,
        studied_status: StudiedStatus,
    ) -> MaterialStudySection | None:
        document = self.ensure_study_document(material_id)
        if document is None:
            return None

        updated_sections: list[MaterialStudySection] = []
        updated_section: MaterialStudySection | None = None
        for section in document.sections:
            if section.section_id == section_id:
                section = section.model_copy(update={"studied_status": studied_status})
                updated_section = section
            updated_sections.append(section)

        if updated_section is None:
            return None

        updated_document = document.model_copy(
            update={
                "sections": updated_sections,
                "groups": self._hydrate_group_counts(document.groups, updated_sections),
            }
        )
        self.store.save_study_document(updated_document)
        return updated_section

    def _usable_sections(self, sections: list[SourceSection]) -> list[SourceSection]:
        usable = [
            section
            for section in sections
            if self._is_usable_section(section)
        ]
        if len(usable) <= 12:
            return usable
        return self._merge_tiny_neighbors(usable)

    def _is_usable_section(self, section: SourceSection) -> bool:
        if section.section_kind == SectionKind.LOGISTICS:
            return False
        if section.section_kind == SectionKind.REFERENCE and not self._is_formula_source_section(section):
            return False
        if self._is_formula_source_section(section):
            return self._formula_source_has_content(section)
        if section.content_label == ContentLabel.ADMINISTRATIVE_CONTENT:
            return False
        text = " ".join(section.text.split())
        if self._looks_like_title_only(section, text):
            return False
        if self._looks_like_schedule_or_admin(text, section.section_title):
            return False
        if section.content_label == ContentLabel.WEAK_CONTENT and not self._has_academic_signal(text):
            return False
        if len(text) < 180 and section.content_label != ContentLabel.TESTABLE_CONTENT:
            return False
        lowered_title = section.section_title.lower()
        junk_markers = [
            "office hour",
            "syllabus",
            "bibliography",
            "references",
            "grading policy",
            "course logistics",
        ]
        return not any(marker in lowered_title for marker in junk_markers)

    def _is_formula_source_section(self, section: SourceSection) -> bool:
        return (
            section.section_title.strip().lower() == "formulas"
            or section.text.lstrip().upper().startswith("FORMULAS")
        )

    def _formula_source_has_content(self, section: SourceSection) -> bool:
        workbook_blocks = self._workbook_support_blocks(section.text)
        return bool(
            section.formula_assets
            or self._parse_workbook_formula_lines(workbook_blocks.get("formulas", []))
            or self._parse_workbook_formula_image_crops(workbook_blocks.get("formulas", []))
        )

    def _merge_tiny_neighbors(self, sections: list[SourceSection]) -> list[SourceSection]:
        merged: list[SourceSection] = []
        for section in sections:
            if (
                merged
                and len(section.text) < 420
                and section.locator.page_number is not None
                and merged[-1].locator.page_number is not None
                and section.locator.page_number - merged[-1].locator.page_number <= 1
            ):
                previous = merged[-1]
                merged[-1] = previous.model_copy(
                    update={
                        "text": f"{previous.text}\n\n{section.text}".strip(),
                        "section_title": previous.section_title,
                        "citation_label": previous.citation_label,
                        "page_end": section.page_end or section.locator.page_number or previous.page_end,
                    }
                )
                continue
            merged.append(section)
        return merged

    def _build_groups(
        self,
        material_id: str,
        sections: list[SourceSection],
    ) -> list[MaterialStudyGroup]:
        if not sections:
            return []
        workbook_groups = self._build_workbook_groups(material_id, sections)
        if workbook_groups:
            return workbook_groups
        if len(sections) <= 8:
            first = sections[0]
            last = sections[-1]
            return [
                MaterialStudyGroup(
                    group_id=f"{material_id}-group-1",
                    material_id=material_id,
                    title="Study sections",
                    page_start=first.locator.page_number,
                    page_end=last.locator.page_number,
                    display_order=1,
                )
            ]

        group_size = 8 if len(sections) <= 80 else 12
        groups: list[MaterialStudyGroup] = []
        for index in range(0, len(sections), group_size):
            group_sections = sections[index : index + group_size]
            first = group_sections[0]
            last = group_sections[-1]
            title = self._group_title(group_sections, len(groups) + 1)
            groups.append(
                MaterialStudyGroup(
                    group_id=f"{material_id}-group-{len(groups) + 1}",
                    material_id=material_id,
                    title=title,
                    page_start=first.locator.page_number,
                    page_end=last.locator.page_number,
                    display_order=len(groups) + 1,
                )
            )
        return groups

    def _group_id_by_section(
        self,
        groups: list[MaterialStudyGroup],
        sections: list[SourceSection],
    ) -> dict[str, str]:
        if not groups:
            return {}
        mapping: dict[str, str] = {}
        workbook_group_by_title = {
            group.title.lower(): group.group_id
            for group in groups
            if group.title.lower().startswith("study session ")
        }
        formula_group_id = next(
            (group.group_id for group in groups if group.title.strip().lower() == "formulas"),
            None,
        )
        for section in sections:
            if self._is_formula_source_section(section) and formula_group_id is not None:
                mapping[section.source_id] = formula_group_id
                continue
            workbook_match = WORKBOOK_MODULE_TITLE_RE.match(section.section_title)
            if workbook_match:
                group_id = workbook_group_by_title.get(
                    self._workbook_group_title_from_match(workbook_match).lower()
                )
                if group_id is not None:
                    mapping[section.source_id] = group_id
                    continue
            page = section.locator.page_number
            selected_group = groups[0]
            if page is not None:
                for group in groups:
                    if (
                        group.page_start is not None
                        and group.page_end is not None
                        and group.page_start <= page <= group.page_end
                    ):
                        selected_group = group
                        break
            else:
                selected_group = groups[
                    min(len(groups) - 1, max(0, section.locator.section_index // 8))
                ]
            mapping[section.source_id] = selected_group.group_id
        return mapping

    def _build_study_section(
        self,
        section: SourceSection,
        *,
        display_order: int,
        parent_group_id: str | None,
        previous: MaterialStudySection | None,
    ) -> MaterialStudySection:
        workbook_blocks = self._workbook_support_blocks(section.text)
        workbook_match = WORKBOOK_MODULE_TITLE_RE.match(section.section_title)
        is_workbook_section = workbook_match is not None
        source_concepts = []

        if is_workbook_section:
            assert workbook_match is not None
            normalized_title = (
                f"Module {workbook_match.group('module_number')}: "
                f"{workbook_match.group('module_title').strip()}"
            )
            key_points: list[str] = []
            keywords: list[str] = []
            formulas = self._workbook_formulas(workbook_blocks)
            traps: list[str] = []
            summary = self._official_workbook_summary(workbook_blocks)
            quiz_ready = bool(workbook_blocks.get("module_quiz")) or bool(
                re.search(r"\bMODULE\s+QUIZ\s+\d+(?:\.[0-9A-Za-z]+)*\b", section.text, re.IGNORECASE)
            )
        else:
            knowledge = extractKnowledge(section)
            concepts = knowledge.concepts
            source_concepts = concepts
            normalized_title = self._normalized_title(section, knowledge)
            key_points = self._unique_items(
                [
                    item
                    for concept in concepts
                    for item in [concept.definition, *concept.key_points, *concept.testable_facts]
                ],
                limit=5,
            )
            key_points = self._quality_points(key_points, normalized_title)
            if not key_points:
                key_points = self._fallback_key_points(section.text, normalized_title)
            keywords = self._keywords(section, concepts)
            formulas = self._formulas(section.text)
            summary = self._summary(section, knowledge.summary)
            traps = self._unique_items(
                [item for concept in concepts for item in concept.common_confusions],
                limit=4,
            )
            traps = self._quality_points(traps, normalized_title, limit=4)
            quiz_ready = bool(section.source_id) and self._has_academic_signal(section.text)

        if not traps and section.content_label == ContentLabel.WEAK_CONTENT:
            traps = ["This section has weaker exam signal, so focus on definitions and examples."]

        key_concept_lines = workbook_blocks.get("key_concepts", [])
        if not key_concept_lines and source_concepts:
            key_concept_lines = [
                item
                for concept in source_concepts
                for item in [f"Objective: {concept.name}", section.text]
            ]
        workbook_key_concepts = self._workbook_display_lines(key_concept_lines)
        workbook_module_quiz = self._workbook_display_lines(workbook_blocks.get("module_quiz", []))
        workbook_answer_key = self._workbook_answer_key_display_lines(
            workbook_blocks.get("answer_key", []),
            workbook_blocks.get("module_quiz", []),
        )
        original_book_content = self._original_book_content(
            section,
            key_concepts=workbook_key_concepts,
            module_quiz=workbook_module_quiz,
            answer_key=workbook_answer_key,
        )
        learning_outcomes = self._learning_outcomes_from_original_book(
            section,
            original_book_content,
            difficulty=self._difficulty(section.text, key_points, formulas),
        )
        concept_cards = [concept for outcome in learning_outcomes for concept in outcome.concepts]
        formula_cards = self._formula_cards_from_original_book(
            section,
            original_book_content,
            concept_cards,
            workbook_blocks=workbook_blocks,
        )
        if self._is_formula_source_section(section):
            normalized_title = "Formulas"
            summary = "Official formula sheet extracted from the source book."
            key_points = [
                "Use these source-linked formula entries for exact notation and calculation practice."
            ] if formula_cards else [
                "No verified formula text or formula image crops were detected for this source."
            ]
            keywords = ["Formulas", "Formula Sheet"]
            formulas = [
                formula.formula_text
                for formula in formula_cards
                if formula.formula_text
            ][:8]
            traps = []
            quiz_ready = bool(formula_cards)
        for concept in concept_cards:
            concept.formulas = [
                formula
                for formula in formula_cards
                if formula.concept_id == concept.concept_id
            ]
        flashcards = self._flashcards_from_original_book(
            section,
            original_book_content,
            concept_cards,
            formula_cards,
        )
        weakest_concepts = [
            concept.title
            for concept in concept_cards
            if concept.title
        ][:3]
        difficulty = self._difficulty(section.text, key_points, formulas)

        return MaterialStudySection(
            section_id=section.source_id,
            material_id=section.material_id,
            parent_group_id=parent_group_id,
            title=normalized_title,
            normalized_title=normalized_title,
            page_start=section.locator.page_number,
            page_end=section.page_end or section.locator.page_number,
            source_anchor=section.citation_label,
            summary=summary,
            key_points=key_points,
            memorize_keywords=keywords,
            memorize_functions_or_formulas=formulas,
            traps=traps,
            workbook_key_concepts=workbook_key_concepts,
            workbook_module_quiz=workbook_module_quiz,
            workbook_answer_key=workbook_answer_key,
            original_book_content=original_book_content,
            learning_outcomes=learning_outcomes,
            concepts=concept_cards,
            formulas=formula_cards,
            flashcards=flashcards,
            due_flashcard_count=len(flashcards),
            mastery_percent=100.0 if previous and previous.studied_status == StudiedStatus.STUDIED else 0.0,
            weakest_concepts=weakest_concepts,
            difficulty=difficulty,
            studied_status=previous.studied_status if previous else StudiedStatus.NOT_STARTED,
            quiz_ready=quiz_ready,
            display_order=display_order,
            enrichment_status=MaterialStageStatus.COMPLETED,
            source_ids=[section.source_id],
        )

    def _workbook_support_blocks(self, text: str) -> dict[str, list[str]]:
        blocks: dict[str, list[str]] = {key: [] for key in WORKBOOK_SUPPORT_BLOCKS}
        active_block: str | None = None

        for raw_line in text.splitlines():
            line = " ".join(raw_line.split()).strip()
            if not line:
                continue
            normalized = line.upper()
            if normalized in {"EXAM FOCUS", "EXAM EXPECTATIONS", "EXAM TIPS", "EXAM TIP"}:
                active_block = "exam_focus"
                continue
            if normalized in {
                "KEY CONCEPT",
                "KEY CONCEPTS",
                "KEY TAKEAWAY",
                "KEY TAKEAWAYS",
                "KEY TAKE-AWAYS",
                "IMPORTANT TERMS",
                "IMPORTANT CONCEPTS",
                "SUMMARY",
                "KEY SUMMARY",
            }:
                active_block = "key_concepts"
                continue
            if normalized in {"LEARNING OBJECTIVE", "LEARNING OBJECTIVES"}:
                active_block = None
                continue
            if normalized == "FORMULAS":
                active_block = "formulas"
                continue
            if normalized.startswith("ANSWER KEY FOR MODULE QUIZ"):
                active_block = "answer_key"
                blocks["answer_key"].append(line)
                continue
            if re.match(r"^MODULE\s+QUIZ\s+\d+(?:\.[0-9A-Za-z]+)*\b", line, re.IGNORECASE):
                if active_block == "answer_key":
                    blocks["answer_key"].append(line)
                else:
                    active_block = "module_quiz"
                    blocks["module_quiz"].append(line)
                continue
            if active_block:
                blocks[active_block].append(line)

        return {key: value for key, value in blocks.items() if value}

    def _official_workbook_summary(self, blocks: dict[str, list[str]]) -> str:
        labels: list[str] = []
        if blocks.get("key_concepts"):
            labels.append("key concepts")
        if blocks.get("module_quiz"):
            labels.append("module quiz")
        if blocks.get("answer_key"):
            labels.append("answer key")
        if not labels:
            return "Official workbook module shell. No extracted key concepts, module quiz, or answer key were found."
        if len(labels) == 1:
            joined = labels[0]
        else:
            joined = f"{', '.join(labels[:-1])}, and {labels[-1]}"
        return f"Official workbook blocks extracted from {joined}."

    def _workbook_display_lines(self, lines: list[str]) -> list[str]:
        display_lines: list[str] = []
        for raw_line in lines:
            line = self._normalize_workbook_display_line(raw_line)
            if line:
                display_lines.append(line)
        # Workbook blocks can span many lines: Key Concepts alone often contains
        # every LO for a reading. Do not silently cut later LOs such as 5.b/5.c.
        return self._unique_items(display_lines, limit=max(300, len(display_lines)))

    def _workbook_answer_key_display_lines(
        self,
        answer_lines: list[str],
        quiz_lines: list[str],
    ) -> list[str]:
        display_lines = self._workbook_display_lines(answer_lines)
        if not display_lines:
            return []

        question_numbers = self._workbook_quiz_question_numbers(quiz_lines)
        if not question_numbers:
            return [
                line
                for line in display_lines
                if not re.match(r"^[A-D]\s+[A-Z]", line)
            ]

        filtered: list[str] = []
        active_question: str | None = None
        for line in display_lines:
            answer_match = re.match(r"^(?P<number>\d+)\.\s+[A-D]\b", line)
            if answer_match:
                active_question = answer_match.group("number")
                if active_question in question_numbers:
                    filtered.append(line)
                continue
            if self._looks_like_answer_key_heading(line):
                filtered.append(line)
                continue
            if active_question in question_numbers and not re.match(r"^[A-D]\s+[A-Z]", line):
                filtered.append(line)

        return self._unique_items(filtered, limit=80)

    def _workbook_quiz_question_numbers(self, quiz_lines: list[str]) -> set[str]:
        numbers: set[str] = set()
        for line in self._workbook_display_lines(quiz_lines):
            match = re.match(r"^(?P<number>\d+)\.\s+", line)
            if match:
                numbers.add(match.group("number"))
        return numbers

    def _looks_like_answer_key_heading(self, line: str) -> bool:
        return bool(
            re.match(
                r"^(?:ANSWER KEY FOR MODULE QUIZZES|MODULE QUIZ \d+(?:\.[0-9A-Za-z]+)*)$",
                line,
                re.IGNORECASE,
            )
        )

    def _original_book_content(
        self,
        section: SourceSection,
        *,
        key_concepts: list[str],
        module_quiz: list[str],
        answer_key: list[str],
    ) -> OriginalBookContent:
        return OriginalBookContent(
            key_concepts=self._original_book_items(
                section,
                lines=key_concepts,
                content_type="key_concept",
                title="Original Key Concepts",
            ),
            module_quiz=self._original_book_items(
                section,
                lines=module_quiz,
                content_type="module_quiz",
                title="Original Module Quiz",
            ),
            answers=self._original_book_items(
                section,
                lines=answer_key,
                content_type="answer",
                title="Original Answer Key",
            ),
        )

    def _original_book_items(
        self,
        section: SourceSection,
        *,
        lines: list[str],
        content_type: str,
        title: str,
    ) -> list[OriginalBookItem]:
        if not lines:
            return []

        if content_type == "key_concept":
            grouped = self._group_key_concept_lines(lines)
        elif content_type == "answer":
            grouped = self._group_answer_key_lines(lines)
        else:
            grouped = [(title, lines)]

        source_pages = self._section_source_pages(section)
        items: list[OriginalBookItem] = []
        for index, (item_title, item_lines) in enumerate(grouped, start=1):
            content = "\n".join(line for line in item_lines if line.strip()).strip()
            if not content:
                continue
            items.append(
                OriginalBookItem(
                    item_id=f"{section.source_id}-{content_type}-{index}",
                    title=item_title,
                    content=content,
                    source_pages=source_pages,
                    original_order=index,
                    source_block_ids=[section.source_id],
                )
            )
        return items

    def _group_key_concept_lines(self, lines: list[str]) -> list[tuple[str, list[str]]]:
        groups: list[tuple[str, list[str]]] = []
        active_title: str | None = None
        active_lines: list[str] = []

        for line in lines:
            lo_match = re.match(r"^(LO\s+\d+\.[a-z])\b\s*:?\s*(?P<body>.*)$", line, re.IGNORECASE)
            if lo_match:
                if active_title and active_lines:
                    groups.append((active_title, active_lines))
                active_title = re.sub(r"\s+", " ", lo_match.group(1)).strip()
                active_lines = [active_title]
                body = (lo_match.group("body") or "").strip()
                if body:
                    active_lines.append(body)
                continue
            objective_match = re.match(
                r"^(?:Learning\s+Objective|Objective)\s*"
                r"(?:\d+(?:\.[A-Za-z0-9]+)*)?\s*:?\s*(?P<body>.+)$",
                line,
                re.IGNORECASE,
            )
            if objective_match:
                if active_title and active_lines:
                    groups.append((active_title, active_lines))
                active_title = objective_match.group("body").strip()
                active_lines = [line]
                continue
            if active_title:
                active_lines.append(line)
            else:
                active_title = "Original Key Concepts"
                active_lines = [line]

        if active_title and active_lines:
            groups.append((active_title, active_lines))
        return groups

    def _group_answer_key_lines(self, lines: list[str]) -> list[tuple[str, list[str]]]:
        groups: list[tuple[str, list[str]]] = []
        heading_lines: list[str] = []
        active_title: str | None = None
        active_lines: list[str] = []

        for line in lines:
            if self._looks_like_answer_key_heading(line):
                if active_title and active_lines:
                    groups.append((active_title, active_lines))
                    active_title = None
                    active_lines = []
                heading_lines.append(line)
                continue
            answer_match = re.match(r"^(?P<number>\d+)\.\s+(?P<answer>[A-D])\b", line)
            if answer_match:
                if active_title and active_lines:
                    groups.append((active_title, active_lines))
                active_title = f"Question {answer_match.group('number')} answer"
                active_lines = [line]
                continue
            if active_title:
                active_lines.append(line)
            elif heading_lines:
                heading_lines.append(line)

        if active_title and active_lines:
            groups.append((active_title, active_lines))
        if not groups and heading_lines:
            groups.append(("Original Answer Key", heading_lines))
        return groups

    def _learning_outcomes_from_original_book(
        self,
        section: SourceSection,
        original_book_content: OriginalBookContent,
        *,
        difficulty: StudyDifficulty,
    ) -> list[StudyLearningOutcome]:
        outcomes: list[StudyLearningOutcome] = []
        for key_concept in original_book_content.key_concepts:
            outcome_title = key_concept.title
            concept_title = self._concept_title_from_key_concept(
                key_concept.content,
                fallback=outcome_title,
            )
            concept_id = f"{section.source_id}-concept-{key_concept.original_order}"
            concept = StudyConceptCard(
                concept_id=concept_id,
                material_id=section.material_id,
                module_id=section.module_id,
                title=concept_title,
                learning_outcome=outcome_title,
                related_original_key_concept_id=key_concept.item_id,
                source_pages=key_concept.source_pages,
                source_excerpt=key_concept.content,
                simplified_explanation=self._first_meaningful_sentence(key_concept.content),
                key_terms=self._terms_from_text(key_concept.content, limit=6),
                exam_focus=f"Study the original {outcome_title} key concept, then practice the matching module quiz style.",
                common_traps=self._trap_sentences_from_text(key_concept.content),
                difficulty_level=difficulty,
            )
            outcomes.append(
                StudyLearningOutcome(
                    outcome_id=f"{section.source_id}-outcome-{key_concept.original_order}",
                    outcome_title=outcome_title,
                    related_original_key_concept_ids=[key_concept.item_id],
                    concepts=[concept],
                )
            )
        return outcomes

    def _formula_cards_from_original_book(
        self,
        section: SourceSection,
        original_book_content: OriginalBookContent,
        concepts: list[StudyConceptCard],
        *,
        workbook_blocks: dict[str, list[str]] | None = None,
    ) -> list[StudyFormulaCard]:
        cards: list[StudyFormulaCard] = []
        formula_entries = self._parse_workbook_formula_lines((workbook_blocks or {}).get("formulas", []))
        formula_crop_entries: list[dict[str, object]] = [
            *self._parse_workbook_formula_image_crops((workbook_blocks or {}).get("formulas", [])),
            *self._formula_assets_as_crop_entries(section),
        ]
        source_excerpt = self._formula_source_excerpt((workbook_blocks or {}).get("formulas", []))
        source_page = section.page_end or section.locator.page_number
        reading_number = self._reading_number_from_section_title(section.section_title)
        anchor_concept = concepts[0] if concepts else None
        for formula_index, (formula_name, formula_text, formula_reading_number) in enumerate(formula_entries, start=1):
            candidate_name = formula_name or self._formula_name_from_text(formula_text)
            if not self._is_good_formula_text_candidate(candidate_name, formula_text, source_excerpt or formula_text):
                continue
            cards.append(
                StudyFormulaCard(
                    formula_id=f"{section.source_id}-formula-{formula_index}",
                    course_id=section.course_id,
                    material_id=section.material_id,
                    module_id=section.module_id,
                    concept_id=anchor_concept.concept_id if anchor_concept else None,
                    reading_number=formula_reading_number or reading_number,
                    formula_name=candidate_name,
                    formula_text=formula_text,
                    variables_json=self._variables_from_formula(formula_text),
                    source_page=source_page,
                    formula_section_page=source_page,
                    source_excerpt=source_excerpt or formula_text,
                    source_image_crop_path=None,
                    parse_confidence="high",
                    needs_review=False,
                    usage_note="Verified formula from the book's FORMULAS section.",
                )
            )
        for crop_index, crop in enumerate(formula_crop_entries, start=len(cards) + 1):
            label = str(crop["label"])
            source_page_for_crop = self._int_or_none(crop["source_page"])
            if source_page_for_crop is None:
                continue
            crop_reading_number = self._int_or_none(crop.get("reading_number"))
            extracted_text = self._string_or_none(crop.get("extracted_text"))
            extracted_latex = self._string_or_none(crop.get("extracted_latex"))
            ocr_confidence = self._float_or_none(crop.get("ocr_confidence"))
            crop_needs_review = bool(crop.get("needs_review", not extracted_text))
            crop_formula_text = extracted_text or label
            crop_high_confidence = bool(extracted_text) and not crop_needs_review and (
                ocr_confidence is None or ocr_confidence >= 0.55
            )
            cards.append(
                StudyFormulaCard(
                    formula_id=f"{section.source_id}-formula-crop-{crop_index}",
                    course_id=section.course_id,
                    material_id=section.material_id,
                    module_id=section.module_id,
                    concept_id=anchor_concept.concept_id if anchor_concept else None,
                    reading_number=crop_reading_number or reading_number,
                    formula_name=self._formula_name_from_text(crop_formula_text) if extracted_text else label,
                    formula_text=crop_formula_text,
                    formula_latex=extracted_latex,
                    variables_json=self._variables_from_formula(crop_formula_text) if extracted_text else {},
                    source_page=source_page_for_crop,
                    formula_section_page=source_page_for_crop,
                    source_excerpt=source_excerpt or crop_formula_text,
                    source_image_crop_path=self._formula_crop_public_path(str(crop["path"]), section.material_id),
                    parse_confidence="high" if crop_high_confidence else "low",
                    needs_review=not crop_high_confidence,
                    usage_note=(
                        "Formula OCR and LaTeX conversion were extracted from the preserved PDF crop."
                        if crop_high_confidence
                        else "Formula preserved as a source image crop; OCR/LaTeX needs review."
                    ),
                )
            )
        return cards[:12]

    def _formula_crop_public_path(self, path: str, fallback_material_id: str) -> str:
        match = re.match(r"^formula-crop://(?P<material_id>[^/]+)/(?P<asset_name>[^/]+)$", path)
        if not match:
            return path
        material_id = match.group("material_id") or fallback_material_id
        asset_name = match.group("asset_name")
        return f"/api/v1/materials/{quote(material_id)}/formula-crops/{quote(asset_name)}"

    def _formula_assets_as_crop_entries(self, section: SourceSection) -> list[dict[str, object]]:
        entries: list[dict[str, object]] = []
        for asset in getattr(section, "formula_assets", []):
            entry: dict[str, object] = {
                "source_page": asset.source_page,
                "path": asset.path,
                "label": asset.label,
                "extracted_text": asset.extracted_text,
                "extracted_latex": asset.extracted_latex,
                "extracted_latex_blocks": asset.extracted_latex_blocks,
                "ocr_engine": asset.ocr_engine,
                "ocr_confidence": asset.ocr_confidence,
                "needs_review": asset.needs_review,
            }
            if asset.reading_number is not None:
                entry["reading_number"] = asset.reading_number
            entries.append(entry)
        return entries

    def _string_or_none(self, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _float_or_none(self, value: object) -> float | None:
        if not isinstance(value, (str, int, float)):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _int_or_none(self, value: object) -> int | None:
        if not isinstance(value, (str, int)):
            return None
        try:
            return int(value)
        except ValueError:
            return None

    def _formula_source_excerpt(self, lines: list[str]) -> str:
        cleaned = [
            " ".join(line.split()).strip()
            for line in lines
            if line and not FORMULA_IMAGE_CROP_RE.match(" ".join(line.split()).strip())
        ]
        return "\n".join(cleaned).strip()[:MAX_FORMULA_SOURCE_EXCERPT_CHARS]

    def _flashcards_from_original_book(
        self,
        section: SourceSection,
        original_book_content: OriginalBookContent,
        concepts: list[StudyConceptCard],
        formulas: list[StudyFormulaCard],
    ) -> list[StudyFlashcard]:
        concept_cards: list[StudyFlashcard] = []
        for concept in concepts:
            if not concept.source_excerpt:
                continue
            cards_for_concept = self._content_specific_flashcards_for_concept(section, concept)
            cards_for_concept = self._valid_unique_flashcards(
                cards_for_concept,
                limit=MAX_FLASHCARDS_PER_CONCEPT,
            )
            if len(cards_for_concept) < MIN_FLASHCARDS_PER_LEARNING_OUTCOME:
                source_page = concept.source_pages[0] if concept.source_pages else section.locator.page_number
                top_up_cards: list[StudyFlashcard] = []
                top_up_cards.extend(self._book_agnostic_family_top_up_flashcards(section, concept, source_page))
                top_up_cards.extend(self._module_anchor_top_up_flashcards_from_concept(section, concept, source_page))
                top_up_cards.extend(self._learning_outcome_anchor_top_up_flashcards(section, concept, source_page))
                top_up_cards.extend(self._minimum_learning_outcome_top_up_flashcards(section, concept, source_page))
                cards_for_concept = self._valid_unique_flashcards(
                    cards_for_concept + top_up_cards,
                    limit=MAX_FLASHCARDS_PER_CONCEPT,
                )
            needs_more_source = len(cards_for_concept) < MIN_FLASHCARDS_PER_LEARNING_OUTCOME
            concept_cards.extend(
                card.model_copy(update={"needs_more_source": needs_more_source})
                for card in cards_for_concept
            )
        concept_cards = self._valid_unique_flashcards(concept_cards, limit=max(120, len(concept_cards)))
        concept_cards = self._ensure_learning_outcome_flashcard_coverage(section, concepts, concept_cards)
        formula_cards: list[StudyFlashcard] = []
        for formula in formulas[:8]:
            if not self._is_good_formula_flashcard_candidate(formula):
                continue
            formula_name = formula.formula_name or self._formula_name_from_text(formula.formula_text)
            formula_snippet = (formula.source_excerpt or formula.formula_text).strip()
            formula_reading_number = formula.reading_number or self._reading_number_from_section_title(section.section_title)
            formula_module_number = self._module_number_from_section_title(section.section_title)
            formula_tags = self._flashcard_tags(
                reading_number=formula_reading_number,
                module_number=formula_module_number,
                lo_code=None,
                anchor_text=formula_name,
            )
            formula_cards.append(
                StudyFlashcard(
                    flashcard_id=f"{formula.formula_id}-flashcard",
                    bookId=section.material_id,
                    course_id=section.course_id,
                    material_id=section.material_id,
                    module_id=section.module_id,
                    concept_id=formula.concept_id,
                    formula_id=formula.formula_id,
                    studySession=self._study_session_from_section_title(section.section_title),
                    readingNumber=formula_reading_number,
                    moduleNumber=formula_module_number,
                    pageStart=formula.source_page,
                    pageEnd=formula.source_page,
                    anchorType="formula",
                    anchorText=formula_name,
                    sourceTextSnippet=formula_snippet,
                    front=f"What is the formula for {formula_name}?",
                    back=formula.formula_text,
                    back_concise=formula.formula_text,
                    card_type="formula",
                    formulaLatex=formula.formula_latex,
                    tags=formula_tags,
                    qualityScore=self._flashcard_quality_score(
                        front=f"What is the formula for {formula_name}?",
                        back=formula.formula_text,
                        source_text_snippet=formula_snippet,
                        anchor_text=formula_name,
                    ),
                    sourceHash=self._flashcard_source_hash(
                        material_id=section.material_id,
                        concept_id=formula.formula_id,
                        front=f"What is the formula for {formula_name}?",
                        source_text_snippet=formula_snippet,
                    ),
                    source_page=formula.source_page,
                    source_excerpt=formula.source_excerpt,
                    difficulty=StudyDifficulty.MEDIUM,
                )
            )
            for variable, meaning in list(formula.variables_json.items())[:4]:
                concise_meaning = self._concise_flashcard_back(f"{variable} = {meaning}")
                formula_cards.append(
                    StudyFlashcard(
                        flashcard_id=(
                            f"{formula.formula_id}-variable-"
                            f"{re.sub(r'[^a-z0-9]+', '-', variable.lower()).strip('-') or 'value'}-flashcard"
                        ),
                        bookId=section.material_id,
                        course_id=section.course_id,
                        material_id=section.material_id,
                        module_id=section.module_id,
                        concept_id=formula.concept_id,
                        formula_id=formula.formula_id,
                        studySession=self._study_session_from_section_title(section.section_title),
                        readingNumber=formula_reading_number,
                        moduleNumber=formula_module_number,
                        pageStart=formula.source_page,
                        pageEnd=formula.source_page,
                        anchorType="formula",
                        anchorText=formula_name,
                        sourceTextSnippet=formula_snippet,
                        front=f"In {formula_name.lower()}, what does {variable} mean?",
                        back=concise_meaning,
                        back_concise=concise_meaning,
                        card_type="short_answer_recall",
                        formulaLatex=formula.formula_latex,
                        tags=formula_tags + [variable],
                        qualityScore=self._flashcard_quality_score(
                            front=f"In {formula_name.lower()}, what does {variable} mean?",
                            back=concise_meaning,
                            source_text_snippet=formula_snippet,
                            anchor_text=formula_name,
                        ),
                        sourceHash=self._flashcard_source_hash(
                            material_id=section.material_id,
                            concept_id=formula.formula_id,
                            front=f"In {formula_name.lower()}, what does {variable} mean?",
                            source_text_snippet=formula_snippet,
                        ),
                        source_page=formula.source_page,
                        source_excerpt=formula.source_excerpt,
                        difficulty=StudyDifficulty.MEDIUM,
                    )
                )
        valid_formula_cards = self._valid_unique_flashcards(formula_cards, limit=max(24, len(formula_cards)))
        combined_cards = self._valid_unique_flashcards(
            concept_cards + valid_formula_cards,
            limit=max(160, len(concept_cards) + len(valid_formula_cards)),
        )
        if len(combined_cards) < MIN_FLASHCARDS_PER_CONCEPT:
            top_up_cards = self._module_top_up_flashcards(
                section,
                original_book_content,
                concepts,
            )
            combined_cards = self._valid_unique_flashcards(
                combined_cards + top_up_cards,
                limit=max(160, len(combined_cards) + len(top_up_cards)),
            )
        if len(combined_cards) < MIN_FLASHCARDS_PER_CONCEPT:
            return [
                card.model_copy(update={"needs_more_source": True})
                if not card.learning_outcome_id
                else card
                for card in combined_cards
            ]
        return combined_cards

    def _ensure_learning_outcome_flashcard_coverage(
        self,
        section: SourceSection,
        concepts: list[StudyConceptCard],
        cards: list[StudyFlashcard],
    ) -> list[StudyFlashcard]:
        concepts_by_lo: dict[str, list[StudyConceptCard]] = {}
        aliases_by_lo: dict[str, set[str]] = {}
        for concept in concepts:
            lo_key = self._learning_outcome_group_key(concept)
            if not lo_key or not concept.source_excerpt:
                continue
            concepts_by_lo.setdefault(lo_key, []).append(concept)
            aliases = aliases_by_lo.setdefault(lo_key, {lo_key})
            for alias in (concept.related_original_key_concept_id, concept.concept_id):
                if alias:
                    aliases.add(alias)
        if not concepts_by_lo:
            return cards

        def card_lo_key(card: StudyFlashcard) -> str | None:
            normalized = self._normalize_learning_outcome_code(
                card.lo_code,
                card.learning_outcome_id,
                card.concept_id,
            )
            if normalized and normalized in concepts_by_lo:
                return normalized
            for lo_key, aliases in aliases_by_lo.items():
                if card.learning_outcome_id in aliases or card.concept_id in aliases:
                    return lo_key
            return None

        def balance_lo_cards(
            candidate_cards: list[StudyFlashcard],
            lo_concepts: list[StudyConceptCard],
        ) -> list[StudyFlashcard]:
            def is_minimum_top_up(card: StudyFlashcard) -> bool:
                if "minimum-lo-" in card.flashcard_id:
                    return True
                return card.front.startswith(
                    (
                        "What exam fact is tied to ",
                        "Why does ",
                        "How is ",
                        "Which detail should be connected with ",
                    )
                ) and (
                    " in this module?" in card.front
                    or " described in the source?" in card.front
                    or card.front.startswith("What exam fact is tied to ")
                    or card.front.startswith("Which detail should be connected with ")
                )

            buckets: list[list[StudyFlashcard]] = []
            fallback_buckets: list[list[StudyFlashcard]] = []
            used_indexes: set[int] = set()
            for concept in lo_concepts:
                concept_aliases = {
                    alias
                    for alias in (concept.concept_id, concept.related_original_key_concept_id)
                    if alias
                }
                bucket: list[StudyFlashcard] = []
                for index, card in enumerate(candidate_cards):
                    if index in used_indexes:
                        continue
                    if card.concept_id in concept_aliases or card.learning_outcome_id in concept_aliases:
                        bucket.append(card)
                        used_indexes.add(index)
                if bucket:
                    priority_cards = [card for card in bucket if not is_minimum_top_up(card)]
                    fallback_cards = [card for card in bucket if is_minimum_top_up(card)]
                    if priority_cards:
                        buckets.append(priority_cards)
                    if fallback_cards:
                        fallback_buckets.append(fallback_cards)
            if not buckets:
                return candidate_cards

            balanced: list[StudyFlashcard] = []
            for bucket_group in (buckets, fallback_buckets):
                if not bucket_group:
                    continue
                for offset in range(max(len(bucket) for bucket in bucket_group)):
                    for bucket in bucket_group:
                        if offset < len(bucket):
                            balanced.append(bucket[offset])
            balanced.extend(
                card for index, card in enumerate(candidate_cards) if index not in used_indexes
            )
            return balanced

        preserved_cards = [
            card for card in cards if card_lo_key(card) is None
        ]
        repaired_cards: list[StudyFlashcard] = []
        for lo_key, lo_concepts in concepts_by_lo.items():
            lo_concepts = sorted(
                lo_concepts,
                key=lambda concept: len(concept.source_excerpt or ""),
                reverse=True,
            )
            candidate_lo_cards = [card for card in cards if card_lo_key(card) == lo_key]
            lo_cards = self._valid_unique_flashcards(
                balance_lo_cards(candidate_lo_cards, lo_concepts),
                limit=MAX_FLASHCARDS_PER_CONCEPT,
            )
            lo_cards = self._ensure_key_concept_flashcard_coverage(section, lo_key, lo_concepts, lo_cards)
            if len(lo_cards) < MIN_FLASHCARDS_PER_LEARNING_OUTCOME:
                top_up_cards: list[StudyFlashcard] = []
                minimum_top_up_cards: list[StudyFlashcard] = []
                for concept in lo_concepts:
                    source_page = concept.source_pages[0] if concept.source_pages else section.locator.page_number
                    top_up_cards.extend(self._book_agnostic_family_top_up_flashcards(section, concept, source_page))
                    top_up_cards.extend(self._module_anchor_top_up_flashcards_from_concept(section, concept, source_page))
                    top_up_cards.extend(self._learning_outcome_anchor_top_up_flashcards(section, concept, source_page))
                    top_up_cards.extend(self._balanced_learning_outcome_top_up_flashcards(section, concept, source_page))
                    minimum_top_up_cards.extend(
                        self._minimum_learning_outcome_top_up_flashcards(section, concept, source_page)
                    )
                top_up_cards.extend(self._aggregate_learning_outcome_top_up_flashcards(section, lo_key, lo_concepts))
                top_up_cards.extend(minimum_top_up_cards)
                lo_cards = self._valid_unique_flashcards(
                    lo_cards + top_up_cards,
                    limit=MAX_FLASHCARDS_PER_CONCEPT,
                )
            needs_more_source = (
                len(lo_cards) < MIN_FLASHCARDS_PER_LEARNING_OUTCOME
                or self._key_concept_coverage_needs_more_source(lo_concepts, lo_cards)
            )
            repaired_cards.extend(
                card.model_copy(update={"needs_more_source": needs_more_source, "lo_code": lo_key})
                for card in lo_cards
            )

        return self._valid_unique_flashcards(
            repaired_cards + preserved_cards,
            limit=max(160, len(repaired_cards) + len(preserved_cards)),
        )

    def _ensure_key_concept_flashcard_coverage(
        self,
        section: SourceSection,
        lo_key: str,
        concepts: list[StudyConceptCard],
        lo_cards: list[StudyFlashcard],
    ) -> list[StudyFlashcard]:
        repaired_cards: list[StudyFlashcard] = []
        used_indexes: set[int] = set()
        for concept in concepts:
            aliases = {
                alias
                for alias in (concept.concept_id, concept.related_original_key_concept_id)
                if alias
            }
            if not aliases:
                continue
            concept_indexes = [
                index
                for index, card in enumerate(lo_cards)
                if card.concept_id in aliases or card.learning_outcome_id in aliases
            ]
            used_indexes.update(concept_indexes)
            concept_cards = [
                lo_cards[index].model_copy(
                    update={
                        "concept_id": concept.concept_id,
                        "learning_outcome_id": lo_cards[index].learning_outcome_id
                        or concept.related_original_key_concept_id
                        or concept.concept_id,
                        "anchor_text": lo_cards[index].anchor_text or concept.title,
                        "source_excerpt": lo_cards[index].source_excerpt or concept.source_excerpt,
                        "source_text_snippet": lo_cards[index].source_text_snippet
                        or concept.source_excerpt,
                    }
                )
                for index in concept_indexes
            ]
            target_minimum = (
                MAX_FLASHCARDS_PER_CONCEPT
                if len(concepts) == 1
                else MIN_FLASHCARDS_PER_CONCEPT
            )
            target_limit = max(len(concept_cards), target_minimum)
            if len(concept_cards) < MIN_FLASHCARDS_PER_CONCEPT:
                source_page = concept.source_pages[0] if concept.source_pages else section.locator.page_number
                top_up_cards: list[StudyFlashcard] = []
                top_up_cards.extend(self._aggregate_learning_outcome_top_up_flashcards(section, lo_key, [concept]))
                top_up_cards.extend(self._book_agnostic_family_top_up_flashcards(section, concept, source_page))
                top_up_cards.extend(self._module_anchor_top_up_flashcards_from_concept(section, concept, source_page))
                top_up_cards.extend(self._learning_outcome_anchor_top_up_flashcards(section, concept, source_page))
                top_up_cards.extend(self._balanced_learning_outcome_top_up_flashcards(section, concept, source_page))
                top_up_cards.extend(self._minimum_learning_outcome_top_up_flashcards(section, concept, source_page))
                concept_cards.extend(
                    card.model_copy(
                        update={
                            "concept_id": concept.concept_id,
                            "learning_outcome_id": concept.related_original_key_concept_id
                            or concept.concept_id,
                            "anchor_text": card.anchor_text or concept.title,
                            "source_excerpt": card.source_excerpt or concept.source_excerpt,
                            "source_text_snippet": card.source_text_snippet or concept.source_excerpt,
                        }
                    )
                    for card in top_up_cards
                )
            repaired_cards.extend(
                self._valid_unique_flashcards(concept_cards, limit=target_limit)
            )
        repaired_cards.extend(
            card
            for index, card in enumerate(lo_cards)
            if index not in used_indexes
        )
        return self._valid_unique_flashcards(
            repaired_cards,
            limit=max(MAX_FLASHCARDS_PER_CONCEPT * max(1, len(concepts)), len(repaired_cards)),
        )

    def _key_concept_coverage_needs_more_source(
        self,
        concepts: list[StudyConceptCard],
        cards: list[StudyFlashcard],
    ) -> bool:
        for concept in concepts:
            aliases = {
                alias
                for alias in (concept.concept_id, concept.related_original_key_concept_id)
                if alias
            }
            if not aliases:
                continue
            concept_count = sum(
                card.concept_id in aliases or card.learning_outcome_id in aliases
                for card in cards
            )
            if concept_count < MIN_FLASHCARDS_PER_CONCEPT:
                return True
        return False

    def _learning_outcome_group_key(self, concept: StudyConceptCard) -> str | None:
        return (
            self._normalize_learning_outcome_code(
                concept.learning_outcome,
                concept.title,
                concept.source_excerpt,
                concept.related_original_key_concept_id,
                concept.concept_id,
            )
            or concept.related_original_key_concept_id
            or concept.concept_id
        )

    def _normalize_learning_outcome_code(self, *values: object) -> str | None:
        for value in values:
            if value is None:
                continue
            normalized = re.sub(r"[_-]+", " ", str(value))
            match = re.search(
                r"\b(?:L\s*O|Learning\s+Objective)\s*"
                r"(?P<number>\d+)\s*(?:\.|\s+)?\s*(?P<letter>[A-Za-z])\b",
                normalized,
                re.IGNORECASE,
            )
            if match:
                return f"LO {int(match.group('number'))}.{match.group('letter').lower()}"
        return None

    def _aggregate_learning_outcome_top_up_flashcards(
        self,
        section: SourceSection,
        lo_key: str,
        concepts: list[StudyConceptCard],
    ) -> list[StudyFlashcard]:
        if not concepts:
            return []
        primary = concepts[0]
        source_page = primary.source_pages[0] if primary.source_pages else section.locator.page_number
        anchor_terms = self._learning_outcome_anchor_terms(concepts)
        excerpt_parts = [
            re.sub(r"\s+", " ", concept.source_excerpt or "").strip()
            for concept in concepts
            if concept.source_excerpt
        ]
        section_window = self._learning_outcome_section_window(section.text, lo_key)
        if section_window:
            excerpt_parts.append(section_window)
        else:
            excerpt_parts.extend(
                sentence
                for sentence in self._sentences(self._clean_academic_text(section.text))
                if self._is_valid_flashcard_source_unit(sentence)
                and self._sentence_overlaps_learning_outcome_terms(sentence, anchor_terms)
            )
        combined_excerpt = " ".join(dict.fromkeys(part for part in excerpt_parts if part))
        primary_context = primary.model_copy(
            update={
                "source_excerpt": combined_excerpt,
                "key_terms": list(
                    dict.fromkeys(
                        list(primary.key_terms)
                        + [term for term in anchor_terms if self._is_good_flashcard_term(term)]
                    )
                ),
            }
        )
        clean_sentences = [
            sentence
            for sentence in self._sentences(self._clean_academic_text(combined_excerpt))
            if self._is_valid_flashcard_source_unit(sentence)
        ]
        if not clean_sentences:
            return []
        lowered = combined_excerpt.lower()
        cards: list[StudyFlashcard] = []

        def add(suffix: str, front: str, back: str, card_type: str) -> None:
            cards.append(
                self._build_flashcard(
                    section,
                    primary_context,
                    suffix=f"aggregate-{lo_key.lower().replace(' ', '-').replace('.', '-')}-{suffix}",
                    front=front,
                    back=back,
                    card_type=card_type,
                    source_page=source_page,
                )
            )

        if all(term in lowered for term in ("r-squared", "residual", "outlier")):
            add(
                "r-squared-vs-residuals",
                "How do R-squared and residuals differ in regression diagnostics?",
                "R-squared measures explained variation; residuals show differences between observed and fitted values.",
                "comparison",
            )
            add(
                "outliers-after-fitting-regression",
                "Why should outliers be reviewed after fitting a regression?",
                "Outliers can distort coefficient estimates and fitted values.",
                "exam_trap",
            )

        cleaned_terms: list[str] = []
        for concept in concepts:
            for term in concept.key_terms:
                cleaned = self._clean_flashcard_term(term)
                if cleaned and cleaned.lower() not in {"borrowers", "correlations", "payments", "coverage"}:
                    cleaned_terms.append(cleaned)
        cleaned_terms = list(dict.fromkeys(cleaned_terms))
        if len(cleaned_terms) >= 4:
            module_number = self._module_number_from_section_title(section.section_title)
            topic = cleanSectionDisplayTitle(section.section_title).split(" / ")[-1]
            module_label = f"Module {module_number}" if module_number else topic
            add(
                "key-terms-list",
                f"Which key concepts should be reviewed together for {module_label}?",
                "\n".join(f"{index}. {term}" for index, term in enumerate(cleaned_terms[:5], start=1)),
                "list_recall",
            )
        cards.extend(self._learning_outcome_anchor_top_up_flashcards(section, primary_context, source_page))
        for index, sentence in enumerate(clean_sentences, start=1):
            cards.extend(
                self._top_up_flashcards_from_sentence(
                    section,
                    primary_context,
                    source_page,
                    sentence,
                    index=200 + index,
                )
            )
        cards.extend(self._minimum_learning_outcome_top_up_flashcards(section, primary_context, source_page))
        return self._valid_unique_flashcards(cards, limit=32)

    def _minimum_learning_outcome_top_up_flashcards(
        self,
        section: SourceSection,
        concept: StudyConceptCard,
        source_page: int | None,
    ) -> list[StudyFlashcard]:
        excerpt = re.sub(r"\s+", " ", concept.source_excerpt).strip()
        if not self._is_valid_flashcard_source_unit(excerpt):
            return []

        raw_sentences = [
            re.sub(
                r"^(?:L\s*O|Learning\s+Objective)\s*\d+\s*(?:\.|\s+)?\s*[a-z]\b[:.]?\s+",
                "",
                sentence.strip(),
                flags=re.IGNORECASE,
            )
            for sentence in self._sentences(excerpt)
        ]
        sentences = [
            sentence
            for sentence in raw_sentences
            if sentence and self._is_valid_flashcard_source_unit(sentence)
        ]
        if not sentences:
            sentences = [re.sub(r"^\s*LO\s+\d+\.[a-z]\s*", "", excerpt, flags=re.IGNORECASE).strip()]

        term_candidates = [
            self._clean_flashcard_term(term)
            for term in [
                *concept.key_terms,
                concept.title,
                concept.learning_outcome,
                concept.simplified_explanation,
            ]
        ]
        for sentence in sentences[:4]:
            term_candidates.extend(self._terms_from_text(sentence, limit=6))
        terms = [
            term
            for term in dict.fromkeys(term_candidates)
            if term
            and self._is_good_flashcard_term(term)
            and not re.fullmatch(r"LO\s+\d+\.[a-z]", term, flags=re.IGNORECASE)
        ]
        if not terms:
            topic = self._clean_flashcard_topic(concept)
            if topic:
                terms = [topic]
        if not terms:
            return []

        topic = self._clean_flashcard_topic(concept) or terms[0]
        cards: list[StudyFlashcard] = []

        def sentence_for(term: str, offset: int) -> str:
            for sentence in sentences:
                if term.lower() in sentence.lower():
                    return sentence
            return sentences[offset % len(sentences)]

        def grounded_back(sentence: str) -> str:
            cleaned = sentence.strip().rstrip(".")
            if not cleaned:
                return ""
            return f"The source emphasizes that {cleaned[:1].lower()}{cleaned[1:]}."

        def add(suffix: str, front: str, back: str, card_type: str) -> None:
            if not back:
                return
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix=f"minimum-lo-{suffix}",
                    front=front,
                    back=back,
                    card_type=card_type,
                    source_page=source_page,
                )
            )

        topic_sentence = sentence_for(topic, 0)
        add(
            "topic-core-point",
            f"What is the core point of {topic.lower()}?",
            grounded_back(topic_sentence),
            "short_answer_recall",
        )
        add(
            "topic-exam-use",
            f"How should {topic.lower()} be used in an exam question?",
            grounded_back(topic_sentence),
            "application",
        )

        for index, term in enumerate(terms[:10], start=1):
            sentence = sentence_for(term, index - 1)
            term_lower = term.lower()
            add(
                f"{index}-exam-fact",
                f"What exam fact is tied to {term_lower}?",
                grounded_back(sentence),
                "short_answer_recall",
            )
            add(
                f"{index}-why-matters",
                f"Why does {term_lower} matter in this module?",
                grounded_back(sentence),
                "interpretation",
            )
            add(
                f"{index}-source-description",
                f"How is {term_lower} described in the source?",
                grounded_back(sentence),
                "definition",
            )
            add(
                f"{index}-linked-detail",
                f"Which detail should be connected with {term_lower}?",
                grounded_back(sentence),
                "application",
            )

        return self._valid_unique_flashcards(cards, limit=32)

    def _learning_outcome_anchor_terms(self, concepts: list[StudyConceptCard]) -> set[str]:
        terms: set[str] = set()
        for concept in concepts:
            candidates = [
                concept.title,
                concept.learning_outcome,
                concept.exam_focus,
                concept.simplified_explanation,
                *concept.key_terms,
            ]
            for candidate in candidates:
                cleaned = self._clean_flashcard_term(candidate or "")
                if not cleaned:
                    continue
                if self._is_good_flashcard_term(cleaned) or cleaned.lower() in FINANCE_ACADEMIC_TERMS:
                    terms.add(cleaned)
            for sentence in self._sentences(concept.source_excerpt or "")[:4]:
                for term in self._terms_from_text(sentence, limit=6):
                    cleaned = self._clean_flashcard_term(term)
                    if self._is_good_flashcard_term(cleaned) or cleaned.lower() in FINANCE_ACADEMIC_TERMS:
                        terms.add(cleaned)
        return terms

    def _learning_outcome_section_window(self, section_text: str, lo_key: str) -> str:
        cleaned = self._clean_academic_text(section_text)
        match = re.match(r"LO\s+(?P<number>\d+)\.(?P<letter>[a-z])", lo_key, re.IGNORECASE)
        if not cleaned or not match:
            return ""
        number = match.group("number")
        letter = match.group("letter")
        lo_marker = r"(?:L\s*O|Learning\s+Objective)"
        start_match = re.search(
            rf"\b{lo_marker}\s*{re.escape(number)}\s*(?:\.|\s+)?\s*{re.escape(letter)}\b[:.]?",
            cleaned,
            re.IGNORECASE,
        )
        if not start_match:
            return ""
        tail = cleaned[start_match.start():]
        search_start = start_match.end() - start_match.start()
        end_match = re.search(
            rf"\b{lo_marker}\s*\d+\s*(?:\.|\s+)?\s*[a-z]\b[:.]?"
            r"|\bMODULE\s+\d+\.\d+\b|\bKEY CONCEPTS\b|\bMODULE QUIZ\b|\bANSWER KEY\b",
            tail[search_start:],
            re.IGNORECASE,
        )
        window = tail
        if end_match:
            window = tail[: search_start + end_match.start()]
        window = re.sub(r"\s+", " ", window).strip()
        if len(window) > 4500:
            boundary = window.rfind(". ", 0, 4500)
            window = window[: boundary + 1 if boundary > 1500 else 4500].strip()
        return window

    def _sentence_overlaps_learning_outcome_terms(self, sentence: str, anchor_terms: set[str]) -> bool:
        if not anchor_terms:
            return False
        lowered = sentence.lower()
        for term in anchor_terms:
            term_lower = term.lower()
            if len(term_lower) >= 4 and term_lower in lowered:
                return True
            tokens = [
                token.lower()
                for token in TOKEN_RE.findall(term)
                if token.lower() not in CONTENT_ANCHOR_STOPWORDS
            ]
            if tokens and sum(1 for token in tokens if token in lowered) >= min(2, len(tokens)):
                return True
        return False

    def _module_top_up_flashcards(
        self,
        section: SourceSection,
        original_book_content: OriginalBookContent,
        concepts: list[StudyConceptCard],
    ) -> list[StudyFlashcard]:
        cards: list[StudyFlashcard] = []
        usable_concepts = [
            concept
            for concept in concepts
            if concept.source_excerpt and self._is_valid_flashcard_source_unit(concept.source_excerpt)
        ]
        if not usable_concepts and self._is_valid_flashcard_source_unit(section.text):
            usable_concepts = [
                StudyConceptCard(
                    concept_id=f"{section.source_id}-module-top-up-concept",
                    material_id=section.material_id,
                    module_id=section.module_id,
                    title=cleanSectionDisplayTitle(section.section_title) or section.section_title,
                    learning_outcome=None,
                    related_original_key_concept_id=f"{section.source_id}-module-top-up",
                    source_pages=self._section_source_pages(section),
                    source_excerpt=section.text,
                    simplified_explanation="",
                    key_terms=self._terms_from_text(section.text, limit=8),
                    formulas=[],
                    exam_focus="",
                    common_traps=[],
                )
            ]

        for concept in usable_concepts[:12]:
            source_page = concept.source_pages[0] if concept.source_pages else section.locator.page_number
            cards.extend(self._book_agnostic_family_top_up_flashcards(section, concept, source_page))
            cards.extend(self._module_anchor_top_up_flashcards_from_concept(section, concept, source_page))
            cards.extend(self._learning_outcome_anchor_top_up_flashcards(section, concept, source_page))
            cards.extend(self._balanced_learning_outcome_top_up_flashcards(section, concept, source_page))
            lo_key = self._learning_outcome_group_key(concept)
            if lo_key:
                sibling_concepts = [
                    candidate
                    for candidate in usable_concepts
                    if self._learning_outcome_group_key(candidate) == lo_key
                ]
                cards.extend(self._aggregate_learning_outcome_top_up_flashcards(section, lo_key, sibling_concepts))
            if len(cards) >= MIN_FLASHCARDS_PER_CONCEPT * 2:
                break
        return self._valid_unique_flashcards(cards, limit=max(40, len(cards)))

    def _is_good_formula_flashcard_candidate(self, formula: StudyFormulaCard) -> bool:
        return self._is_good_formula_text_candidate(
            formula.formula_name,
            formula.formula_text,
            formula.source_excerpt,
        )

    def _is_good_formula_text_candidate(
        self,
        formula_name: str | None,
        formula_text: str | None,
        source_text: str | None = None,
    ) -> bool:
        formula_text = re.sub(r"\s+", " ", formula_text or "").strip()
        formula_name = re.sub(r"\s+", " ", formula_name or "").strip()
        source_text = re.sub(r"\s+", " ", source_text or "").strip()
        combined = " ".join(part for part in [formula_name, formula_text] if part).lower()
        if "=" not in formula_text:
            return False
        if re.match(r"^(?:if|when|given|suppose|assume|the significance level|the confidence level|the p-value)\b", formula_name, re.IGNORECASE):
            return False
        if re.match(r"^(?:if|when|given|suppose|assume)\b", formula_text, re.IGNORECASE):
            return False
        if re.search(r"\b(?:calculate the|confidence interval|significance level|p-value)\b", combined):
            return False
        left_side = formula_text.split("=", 1)[0].strip(" :;")
        if len(left_side.split()) > 6:
            return False
        if re.search(r"\b(?:if|when|given|suppose|assume|there|because)\b", left_side, re.IGNORECASE):
            return False
        if re.search(r"[A-Za-z][A-Za-z0-9()_ βσρμΣΔ./-]*\s*=", formula_text):
            return True
        return False

    def _content_specific_flashcards_for_concept(
        self,
        section: SourceSection,
        concept: StudyConceptCard,
    ) -> list[StudyFlashcard]:
        if not self._is_valid_flashcard_source_unit(concept.source_excerpt):
            return []
        anchors = self._card_anchors_for_concept(concept)
        if not anchors:
            return []
        cards: list[StudyFlashcard] = []
        source_page = concept.source_pages[0] if concept.source_pages else section.locator.page_number
        cards.extend(self._value_at_risk_flashcards(section, concept, source_page))
        cards.extend(self._modern_portfolio_flashcards(section, concept, source_page))
        cards.extend(self._capm_flashcards(section, concept, source_page))
        cards.extend(self._code_of_conduct_flashcards(section, concept, source_page))
        cards.extend(self._time_series_flashcards(section, concept, source_page))
        cards.extend(self._population_moments_flashcards(section, concept, source_page))
        cards.extend(self._compounding_flashcards(section, concept, source_page))
        cards.extend(self._mutual_fund_flashcards(section, concept, source_page))
        cards.extend(self._option_type_flashcards(section, concept, source_page))
        cards.extend(self._option_pricing_factor_flashcards(section, concept, source_page))
        cards.extend(self._options_market_flashcards(section, concept, source_page))
        cards.extend(self._interest_rate_swap_flashcards(section, concept, source_page))
        cards.extend(self._ccp_risk_flashcards(section, concept, source_page))
        cards.extend(self._futures_characteristics_flashcards(section, concept, source_page))
        cards.extend(self._commodity_flashcards(section, concept, source_page))
        cards.extend(self._day_count_flashcards(section, concept, source_page))
        cards.extend(self._duration_hedging_flashcards(section, concept, source_page))
        cards.extend(self._treasury_bond_futures_flashcards(section, concept, source_page))
        cards.extend(self._insurance_pension_flashcards(section, concept, source_page))
        cards.extend(self._banking_flashcards(section, concept, source_page))
        cards.extend(self._foreign_exchange_flashcards(section, concept, source_page))
        cards.extend(self._exchange_rate_parity_flashcards(section, concept, source_page))
        cards.extend(self._mortgage_loan_flashcards(section, concept, source_page))
        cards.extend(self._mortgage_backed_security_flashcards(section, concept, source_page))
        cards.extend(self._prepayment_modeling_flashcards(section, concept, source_page))
        cards.extend(self._swap_valuation_flashcards(section, concept, source_page))
        cards.extend(self._interest_rate_curve_flashcards(section, concept, source_page))
        cards.extend(self._duration_convexity_flashcards(section, concept, source_page))
        cards.extend(self._credit_bond_flashcards(section, concept, source_page))
        cards.extend(self._option_margin_flashcards(section, concept, source_page))
        cards.extend(self._option_strategy_flashcards(section, concept, source_page))
        definition = self._definition_flashcard_from_concept(section, concept, source_page)
        if definition is not None:
            cards.append(definition)
        list_recall = self._list_recall_flashcard_from_concept(section, concept, source_page)
        if list_recall is not None:
            cards.append(list_recall)
        comparison = self._comparison_flashcard_from_concept(section, concept, source_page)
        if comparison is not None:
            cards.append(comparison)
        trap = self._exam_trap_flashcard_from_concept(section, concept, source_page)
        if trap is not None:
            cards.append(trap)
        cards.extend(self._risk_management_process_flashcards(section, concept, source_page))
        cards.extend(self._learning_objective_command_flashcards(section, concept, source_page))
        cards.extend(self._process_step_flashcards_from_concept(section, concept, source_page))
        cards.extend(self._sentence_level_flashcards_from_concept(section, concept, source_page))
        cards.extend(self._term_flashcards_from_concept(section, concept, source_page))
        if not cards:
            anchor = self._anchor_flashcard_from_concept(section, concept, source_page)
            if anchor is not None:
                cards.append(anchor)
        cards.extend(self._probability_relationship_flashcards(section, concept, source_page))
        cards.extend(self._book_agnostic_family_top_up_flashcards(section, concept, source_page))
        cards.extend(self._module_anchor_top_up_flashcards_from_concept(section, concept, source_page))
        unique = self._valid_unique_flashcards(cards, limit=MAX_FLASHCARDS_PER_CONCEPT)
        if len(unique) < MIN_FLASHCARDS_PER_CONCEPT:
            return [card.model_copy(update={"needs_more_source": True}) for card in unique]
        return unique

    def _learning_objective_command_flashcards(
        self,
        section: SourceSection,
        concept: StudyConceptCard,
        source_page: int | None,
    ) -> list[StudyFlashcard]:
        excerpt = re.sub(r"\s+", " ", concept.source_excerpt).strip()
        if not self._is_valid_flashcard_source_unit(excerpt):
            return []

        cards: list[StudyFlashcard] = []
        lo_sentence = next(
            (
                sentence
                for sentence in self._sentences(excerpt)
                if re.match(r"^LO\s+\d+\.[a-z]\b", sentence, re.IGNORECASE)
            ),
            "",
        )
        if not lo_sentence:
            return []

        command = re.sub(r"^LO\s+\d+\.[a-z]\s*", "", lo_sentence, flags=re.IGNORECASE).strip()
        lowered = excerpt.lower()

        if "multiple testing" in lowered:
            problem_sentence = self._source_sentence_containing(
                excerpt,
                "multiple testing",
                "means",
                exclude_prefix="lo ",
            )
            if problem_sentence:
                cards.append(
                    self._build_flashcard(
                        section,
                        concept,
                        suffix="lo-multiple-testing-problem",
                        front="What is the problem of multiple testing?",
                        back=problem_sentence,
                        card_type="definition",
                        source_page=source_page,
                    )
                )
            type_i_sentence = self._source_sentence_containing(excerpt, "type i error", "increases")
            if type_i_sentence:
                cards.append(
                    self._build_flashcard(
                        section,
                        concept,
                        suffix="lo-multiple-testing-type-i-error",
                        front="How does multiple testing affect Type I error probability?",
                        back=type_i_sentence,
                        card_type="exam_trap",
                        source_page=source_page,
                    )
                )

        if "delta hedging" in lowered or "option delta" in lowered:
            if "explain delta hedging" in command.lower():
                sentence = self._source_sentence_containing(excerpt, "delta hedging", "creates")
                if sentence:
                    cards.append(
                        self._build_flashcard(
                            section,
                            concept,
                            suffix="lo-delta-hedging",
                            front="What is delta hedging?",
                            back=sentence,
                            card_type="definition",
                            source_page=source_page,
                        )
                    )
            if "interpret option delta" in command.lower() or "option delta" in lowered:
                sentence = self._source_sentence_containing(excerpt, "delta", "option", "ratio")
                if sentence:
                    cards.append(
                        self._build_flashcard(
                            section,
                            concept,
                            suffix="lo-option-delta",
                            front="What is option delta?",
                            back=sentence,
                            card_type="definition",
                            source_page=source_page,
                        )
                    )
        return self._valid_unique_flashcards(cards, limit=12)

    def _process_step_flashcards_from_concept(
        self,
        section: SourceSection,
        concept: StudyConceptCard,
        source_page: int | None,
    ) -> list[StudyFlashcard]:
        excerpt = re.sub(r"\s+", " ", concept.source_excerpt).strip()
        if not self._is_valid_flashcard_source_unit(excerpt):
            return []

        steps: list[tuple[str, str]] = []
        for match in re.finditer(
            r"\bStep\s+(?P<number>\d+)\s*:\s*(?P<text>.*?)(?=\s+Step\s+\d+\s*:|$)",
            excerpt,
            re.IGNORECASE,
        ):
            step_text = match.group("text").strip(" .")
            if len(TOKEN_RE.findall(step_text)) < 3:
                continue
            steps.append((match.group("number"), step_text + "."))

        if len(steps) < 2:
            return []

        lowered = excerpt.lower()
        process_name = "hypothesis test" if "hypothesis" in lowered else self._clean_flashcard_topic(concept)
        if not process_name:
            process_name = "the process"
        display_process = process_name.lower()
        cards: list[StudyFlashcard] = [
            self._build_flashcard(
                section,
                concept,
                suffix="process-steps",
                front=f"What are the steps in a {display_process}?",
                back="\n".join(f"{number}. {text}" for number, text in steps),
                card_type="list_recall",
                source_page=source_page,
            )
        ]

        for number, text in steps[:6]:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix=f"process-step-{number}",
                    front=f"What is Step {number} in a {display_process}?",
                    back=text,
                    card_type="short_answer_recall",
                    source_page=source_page,
                )
            )
        return self._valid_unique_flashcards(cards, limit=10)

    def _book_agnostic_family_top_up_flashcards(
        self,
        section: SourceSection,
        concept: StudyConceptCard,
        source_page: int | None,
    ) -> list[StudyFlashcard]:
        """Add deterministic cards for common exam-book concept families.

        These cards are source anchored: each branch only fires when the source
        unit contains the actual terms or relationships. This is the escape
        hatch for future books that use clean headings/bold terms but do not
        match one of the provider-specific generators above.
        """

        excerpt = re.sub(r"\s+", " ", concept.source_excerpt).strip()
        lowered = excerpt.lower()
        if not self._is_valid_flashcard_source_unit(excerpt):
            return []
        cards: list[StudyFlashcard] = []

        def has(*phrases: str) -> bool:
            return all(phrase.lower() in lowered for phrase in phrases)

        def add(
            *,
            suffix: str,
            front: str,
            back: str,
            card_type: str,
        ) -> None:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix=f"family-{suffix}",
                    front=front,
                    back=back,
                    card_type=card_type,
                    source_page=source_page,
                )
            )

        if any(
            phrase in lowered
            for phrase in (
                "discrete probability function",
                "unconditional probability",
                "collectively exhaustive",
                "bayes",
            )
        ):
            if has("discrete probability function"):
                add(
                    suffix="discrete-probability-function",
                    front="What is a discrete probability function?",
                    back="A discrete probability function assigns probabilities to possible outcomes.",
                    card_type="definition",
                )
            if has("discrete probability function") or "possible outcome" in lowered:
                add(
                    suffix="probability-function-outcomes",
                    front="What does a probability function give?",
                    back="A probability function gives the probability of each possible outcome.",
                    card_type="short_answer_recall",
                )
            if has("conditional probability", "unconditional probability"):
                add(
                    suffix="conditional-vs-unconditional-probability",
                    front="How does conditional probability differ from unconditional probability?",
                    back="Conditional probability is given another event; unconditional probability is not conditional on another event.",
                    card_type="comparison",
                )
                add(
                    suffix="unconditional-probability",
                    front="What is unconditional probability?",
                    back="Unconditional probability is the probability of an event without conditioning on another event.",
                    card_type="definition",
                )
            if has("collectively exhaustive"):
                add(
                    suffix="collectively-exhaustive-events",
                    front="What does it mean for events to be collectively exhaustive?",
                    back="Collectively exhaustive events cover all possible outcomes.",
                    card_type="definition",
                )
            if has("mutually exclusive", "collectively exhaustive"):
                add(
                    suffix="mutually-exclusive-vs-collectively-exhaustive",
                    front="How do mutually exclusive events differ from collectively exhaustive events?",
                    back="Mutually exclusive events cannot occur together; collectively exhaustive events cover all possible outcomes.",
                    card_type="comparison",
                )
            if "bayes" in lowered:
                add(
                    suffix="bayes-rule-update",
                    front="What does Bayes' rule allow you to update?",
                    back="Bayes' rule updates probabilities using prior probabilities and new information.",
                    card_type="application",
                )
                add(
                    suffix="bayes-rule-relationship",
                    front="What relationship leads to Bayes' rule?",
                    back="P(A|B)P(B) = P(B|A)P(A).",
                    card_type="formula",
                )
                add(
                    suffix="bayes-rule-inputs",
                    front="What information is needed to apply Bayes' rule?",
                    back="Bayes' rule uses prior probabilities and conditional probabilities.",
                    card_type="short_answer_recall",
                )
                add(
                    suffix="bayes-rule-exam-trap",
                    front="What is a common exam trap about Bayes' rule?",
                    back="Do not update probabilities without using both the prior probability and the relevant conditional probability.",
                    card_type="exam_trap",
                )
            if has("mutually exclusive", "collectively exhaustive"):
                add(
                    suffix="mutually-exclusive-collectively-exhaustive-trap",
                    front="What is a common exam trap about mutually exclusive and collectively exhaustive events?",
                    back="Mutually exclusive means no overlap; collectively exhaustive means all outcomes are covered.",
                    card_type="exam_trap",
                )

        if any(
            phrase in lowered
            for phrase in (
                "probability mass function",
                "pmf",
                "cumulative distribution function",
                "discrete random variable",
                "continuous random variable",
                "bernoulli random variable",
                "expected value",
                "expectations operator",
            )
        ):
            if has("discrete random variable"):
                add(
                    suffix="discrete-random-variable",
                    front="What is a discrete random variable?",
                    back="A discrete random variable has countable possible outcomes.",
                    card_type="definition",
                )
            if "probability mass function" in lowered or "pmf" in lowered:
                add(
                    suffix="probability-mass-function",
                    front="What does a probability mass function (PMF) give?",
                    back="A probability mass function gives the probability of each value of a discrete random variable.",
                    card_type="definition",
                )
            if has("cumulative distribution function"):
                add(
                    suffix="cumulative-distribution-function",
                    front="What does a cumulative distribution function (CDF) give?",
                    back="A cumulative distribution function gives the probability that a random variable is less than or equal to a value.",
                    card_type="definition",
                )
            if ("probability mass function" in lowered or "pmf" in lowered) and has("cumulative distribution function"):
                add(
                    suffix="pmf-vs-cdf",
                    front="How does a probability mass function differ from a cumulative distribution function?",
                    back="A PMF gives probabilities for individual values; a CDF gives cumulative probabilities up to a value.",
                    card_type="comparison",
                )
            if has("bernoulli random variable"):
                add(
                    suffix="bernoulli-random-variable",
                    front="What is a Bernoulli random variable?",
                    back="A Bernoulli random variable takes the value 1 for success and 0 for failure.",
                    card_type="definition",
                )
                add(
                    suffix="bernoulli-random-variable-values",
                    front="What are the possible values of a Bernoulli random variable?",
                    back="The possible values are 1 for success and 0 for failure.",
                    card_type="list_recall",
                )
            if has("continuous random variable"):
                add(
                    suffix="continuous-random-variable",
                    front="What is a continuous random variable?",
                    back="A continuous random variable can take any value in an interval.",
                    card_type="definition",
                )
            if has("discrete random variable", "continuous random variable"):
                add(
                    suffix="discrete-vs-continuous-random-variable",
                    front="How does a discrete random variable differ from a continuous random variable?",
                    back="A discrete random variable has countable outcomes; a continuous random variable can take any value in an interval.",
                    card_type="comparison",
                )
            if has("expected value"):
                add(
                    suffix="expected-value",
                    front="What is the expected value of a random variable?",
                    back="Expected value is the probability-weighted average of possible outcomes.",
                    card_type="definition",
                )
            if has("expectations operator"):
                add(
                    suffix="expectations-operator",
                    front="What does the expectations operator indicate?",
                    back="The expectations operator indicates the expected value of a random variable.",
                    card_type="short_answer_recall",
                )
            if ("probability mass function" in lowered or "pmf" in lowered) and has("cumulative distribution function"):
                add(
                    suffix="pmf-cdf-exam-trap",
                    front="What is a common exam trap about PMFs and CDFs?",
                    back="Do not confuse point probabilities from a PMF with cumulative probabilities from a CDF.",
                    card_type="exam_trap",
                )

        if any(
            phrase in lowered
            for phrase in (
                "multiple regression",
                "partial slope coefficient",
                "ordinary least squares",
                "homoskedasticity",
                "multicollinearity",
                "adjusted r-squared",
                "outliers",
                "explanatory variables",
            )
        ):
            if has("multiple regression"):
                add(
                    suffix="multiple-regression",
                    front="What is multiple regression?",
                    back="Multiple regression models one dependent variable using two or more explanatory variables.",
                    card_type="definition",
                )
                add(
                    suffix="multiple-vs-simple-regression",
                    front="How does multiple regression differ from simple regression?",
                    back="Multiple regression uses two or more explanatory variables; simple regression uses one.",
                    card_type="comparison",
                )
            if has("explanatory variables"):
                add(
                    suffix="explanatory-variable",
                    front="What is an explanatory variable in multiple regression?",
                    back="An explanatory variable is used to explain or predict the dependent variable.",
                    card_type="definition",
                )
            if has("partial slope coefficient"):
                add(
                    suffix="partial-slope-coefficient",
                    front="What does a partial slope coefficient measure?",
                    back="A partial slope coefficient measures one independent variable's effect while holding other independent variables constant.",
                    card_type="definition",
                )
                add(
                    suffix="holding-variables-constant",
                    front="What does holding other independent variables constant mean?",
                    back="It means interpreting one coefficient while treating the other explanatory variables as unchanged.",
                    card_type="interpretation",
                )
            if has("ordinary least squares"):
                add(
                    suffix="ordinary-least-squares",
                    front="What does ordinary least squares minimize?",
                    back="Ordinary least squares minimizes the sum of squared residuals.",
                    card_type="short_answer_recall",
                )
            if has("homoskedasticity"):
                add(
                    suffix="homoskedasticity",
                    front="What is homoskedasticity?",
                    back="Homoskedasticity means the error variance is constant.",
                    card_type="definition",
                )
            if has("multicollinearity"):
                add(
                    suffix="multicollinearity",
                    front="What is multicollinearity?",
                    back="Multicollinearity occurs when independent variables are highly correlated.",
                    card_type="definition",
                )
            if has("outliers"):
                add(
                    suffix="outliers-regression",
                    front="Why do outliers matter in multiple regression?",
                    back="Outliers can distort coefficient estimates.",
                    card_type="exam_trap",
                )
            if has("adjusted r-squared"):
                add(
                    suffix="adjusted-r-squared",
                    front="What does adjusted R-squared penalize?",
                    back="Adjusted R-squared penalizes adding variables that do not improve model fit.",
                    card_type="interpretation",
                )
            if has("partial slope coefficient"):
                add(
                    suffix="partial-slope-coefficient-trap",
                    front="What is a common exam trap about multiple regression coefficients?",
                    back="Do not interpret a partial slope coefficient without holding the other independent variables constant.",
                    card_type="exam_trap",
                )

        if any(
            phrase in lowered
            for phrase in (
                "principal components analysis",
                "pca",
                "principal components",
                "k-means",
                "cluster center",
                "inertia",
                "parallel shift",
                "twist",
            )
        ):
            if "principal components analysis" in lowered or "pca" in lowered:
                add(
                    suffix="pca-goal",
                    front="What is the goal of principal components analysis (PCA)?",
                    back="PCA reduces dimensionality by transforming correlated variables into uncorrelated principal components.",
                    card_type="definition",
                )
                add(
                    suffix="pca-dimensionality",
                    front="How does PCA reduce dimensionality?",
                    back="PCA transforms correlated variables into a smaller set of uncorrelated principal components.",
                    card_type="interpretation",
                )
            if has("principal components"):
                add(
                    suffix="principal-components",
                    front="What are principal components?",
                    back="Principal components are uncorrelated transformed variables that summarize variation in the original variables.",
                    card_type="definition",
                )
            if "yield curve" in lowered and ("pca" in lowered or "principal component" in lowered):
                add(
                    suffix="yield-curve-pca",
                    front="How is PCA applied to yield curve movements?",
                    back="PCA identifies key uncorrelated components of yield curve movement, such as level shifts and twists.",
                    card_type="application",
                )
            if has("parallel shift", "twist"):
                add(
                    suffix="parallel-shift-vs-twist-pca",
                    front="How does a parallel shift differ from a twist in yield-curve PCA?",
                    back="A parallel shift changes the yield curve level; a twist changes the yield curve slope.",
                    card_type="comparison",
                )
            if "k-means" in lowered:
                add(
                    suffix="k-means-k",
                    front="What does K represent in K-means clustering?",
                    back="K is the number of clusters.",
                    card_type="short_answer_recall",
                )
                add(
                    suffix="k-means-algorithm",
                    front="What does the K-means algorithm do?",
                    back="K-means partitions data into K clusters.",
                    card_type="definition",
                )
            if has("cluster center"):
                add(
                    suffix="cluster-center",
                    front="What is a cluster center in K-means?",
                    back="A cluster center is the mean location of the observations assigned to that cluster.",
                    card_type="definition",
                )
            if "cluster assignment" in lowered or has("cluster assignments"):
                add(
                    suffix="k-means-cluster-updates",
                    front="How does K-means update cluster assignments?",
                    back="K-means updates cluster assignments and cluster centers until fit stops improving.",
                    card_type="application",
                )
            if has("inertia"):
                add(
                    suffix="inertia",
                    front="What does inertia measure in K-means clustering?",
                    back="Inertia measures within-cluster variation.",
                    card_type="definition",
                )
                add(
                    suffix="k-means-model-fit",
                    front="How is model fit assessed in K-means clustering?",
                    back="Model fit can be assessed using inertia, which measures within-cluster variation.",
                    card_type="interpretation",
                )

        if any(
            phrase in lowered
            for phrase in (
                "uniform distribution",
                "bernoulli trial",
                "binomial distribution",
                "poisson distribution",
                "standard normal distribution",
                "cumulative distribution function",
            )
        ):
            if has("uniform distribution"):
                add(
                    suffix="uniform-distribution",
                    front="What is a uniform distribution?",
                    back="A uniform distribution gives equal probability to all outcomes in a range.",
                    card_type="definition",
                )
            if has("bernoulli trial"):
                add(
                    suffix="bernoulli-trial-outcomes",
                    front="What are the two outcomes of a Bernoulli trial?",
                    back="Success and failure.",
                    card_type="list_recall",
                )
            if has("binomial distribution"):
                add(
                    suffix="binomial-distribution-model",
                    front="What does a binomial distribution model?",
                    back="The number of successes in a fixed number of independent Bernoulli trials.",
                    card_type="definition",
                )
            if has("poisson distribution"):
                add(
                    suffix="poisson-distribution-model",
                    front="What does a Poisson distribution model?",
                    back="The number of events occurring over an interval.",
                    card_type="definition",
                )
            if has("standard normal distribution"):
                add(
                    suffix="standard-normal-mean-variance",
                    front="What are the mean and variance of the standard normal distribution?",
                    back="Mean 0 and variance 1.",
                    card_type="short_answer_recall",
                )
            if has("cumulative distribution function"):
                add(
                    suffix="cdf-gives",
                    front="What does the cumulative distribution function give?",
                    back="The probability that a random variable is less than or equal to a value.",
                    card_type="definition",
                )
            if has("bernoulli trial", "binomial distribution"):
                add(
                    suffix="bernoulli-vs-binomial",
                    front="How does a Bernoulli trial relate to a binomial distribution?",
                    back="A binomial distribution counts successes across independent Bernoulli trials.",
                    card_type="comparison",
                )
            if has("poisson distribution", "binomial distribution"):
                add(
                    suffix="poisson-vs-binomial",
                    front="How does a Poisson distribution differ from a binomial distribution?",
                    back="Poisson models events over an interval; binomial models successes in a fixed number of trials.",
                    card_type="comparison",
                )
            if has("uniform distribution", "standard normal distribution"):
                add(
                    suffix="uniform-vs-standard-normal",
                    front="How does a uniform distribution differ from a standard normal distribution?",
                    back="Uniform assigns equal probability over a range; standard normal is bell-shaped with mean 0 and variance 1.",
                    card_type="comparison",
                )
            if has("poisson distribution"):
                add(
                    suffix="poisson-application",
                    front="When is a Poisson distribution useful?",
                    back="When modeling the number of events occurring over an interval.",
                    card_type="application",
                )

        if any(
            phrase in lowered
            for phrase in (
                "event space",
                "random event",
                "conditional probability",
                "independent",
                "mutually exclusive",
            )
        ):
            if has("event space"):
                add(
                    suffix="event-space",
                    front="What is the event space in probability?",
                    back="The event space is the set of all possible outcomes.",
                    card_type="definition",
                )
            if has("random event"):
                add(
                    suffix="random-event",
                    front="What is a random event?",
                    back="A random event is a subset of the event space.",
                    card_type="definition",
                )
            if has("conditional probability"):
                add(
                    suffix="conditional-probability",
                    front="What does conditional probability measure?",
                    back="Conditional probability measures the probability of event A given event B.",
                    card_type="definition",
                )
            if "independent" in lowered and ("p(a ∩ b)" in lowered or "p(a|b)" in lowered or "p(a)p(b)" in lowered):
                add(
                    suffix="independence-condition",
                    front="What condition defines independence between events A and B?",
                    back="P(A ∩ B) = P(A)P(B). Equivalently, P(A|B) = P(A) when P(B) > 0.",
                    card_type="formula",
                )
                add(
                    suffix="conditional-probability-independence",
                    front="If A and B are independent, what is P(A|B) equal to?",
                    back="P(A|B) = P(A) when P(B) > 0.",
                    card_type="formula",
                )
            if "mutually exclusive" in lowered:
                add(
                    suffix="mutually-exclusive-condition",
                    front="What condition defines mutually exclusive events?",
                    back="P(A ∩ B) = 0, meaning the events cannot occur together.",
                    card_type="formula",
                )
                add(
                    suffix="mutually-exclusive-meaning",
                    front="What does it mean for two events to be mutually exclusive?",
                    back="The events cannot occur together.",
                    card_type="definition",
                )
            if "independent" in lowered and "mutually exclusive" in lowered:
                add(
                    suffix="independent-vs-mutually-exclusive",
                    front="How do independent events differ from mutually exclusive events?",
                    back="Independent events do not change each other's probabilities; mutually exclusive events cannot occur together.",
                    card_type="comparison",
                )
                add(
                    suffix="mutual-exclusivity-dependence-trap",
                    front="Why does mutual exclusivity usually imply dependence when both events have positive probability?",
                    back="If one mutually exclusive event occurs, the other cannot occur, so the occurrence changes the other event's probability.",
                    card_type="exam_trap",
                )
                add(
                    suffix="mutual-exclusivity-positive-probabilities",
                    front="When do mutually exclusive events usually imply dependence?",
                    back="When both events have positive probability.",
                    card_type="exam_trap",
                )
            if has("event space", "random event"):
                add(
                    suffix="event-space-random-event",
                    front="How are random events related to the event space?",
                    back="Random events are subsets of the event space.",
                    card_type="application",
                )
            if has("conditional probability") and "independent" in lowered:
                add(
                    suffix="conditional-probability-independent-events",
                    front="How does conditional probability relate to independent events?",
                    back="For independent events, P(A|B) = P(A) when P(B) > 0.",
                    card_type="formula",
                )
                add(
                    suffix="conditional-probability-independence-trap",
                    front="What is a common exam trap about conditional probability and independence?",
                    back="Do not treat P(A|B) as different from P(A) when A and B are independent.",
                    card_type="exam_trap",
                )

        if any(
            phrase in lowered
            for phrase in (
                "probability matrix",
                "marginal distribution",
                "conditional distribution",
                "covariance",
                "correlation coefficient",
                "identically distributed",
            )
        ):
            if has("probability matrix"):
                add(
                    suffix="probability-matrix",
                    front="What does a probability matrix display?",
                    back="A probability matrix displays the joint probability distribution for two random variables.",
                    card_type="definition",
                )
            if has("marginal distribution"):
                add(
                    suffix="marginal-distribution",
                    front="What is a marginal distribution?",
                    back="A marginal distribution gives the probability distribution of one random variable.",
                    card_type="definition",
                )
            if has("conditional distribution"):
                add(
                    suffix="conditional-distribution",
                    front="What is a conditional distribution?",
                    back="A conditional distribution gives one variable's distribution given the value of another variable.",
                    card_type="definition",
                )
            if "covariance" in lowered:
                add(
                    suffix="covariance-measure",
                    front="What does covariance measure?",
                    back="Covariance measures how two random variables move together.",
                    card_type="definition",
                )
            if has("correlation coefficient"):
                add(
                    suffix="correlation-coefficient",
                    front="What does the correlation coefficient measure?",
                    back="The correlation coefficient standardizes covariance and ranges from -1 to +1.",
                    card_type="definition",
                )
                add(
                    suffix="correlation-coefficient-range",
                    front="What is the range of the correlation coefficient?",
                    back="The correlation coefficient ranges from -1 to +1.",
                    card_type="short_answer_recall",
                )
            if "covariance" in lowered and "correlation" in lowered:
                add(
                    suffix="covariance-vs-correlation",
                    front="How does covariance differ from correlation?",
                    back="Covariance measures joint movement; correlation standardizes that movement to a -1 to +1 scale.",
                    card_type="comparison",
                )
            if "independent and identically distributed" in lowered or "iid" in lowered:
                add(
                    suffix="iid-random-variables",
                    front="What does it mean for random variables to be independent and identically distributed?",
                    back="IID variables have the same distribution and are mutually independent.",
                    card_type="definition",
                )
                add(
                    suffix="iid-sum-expected-value",
                    front="How is the expected value of a sum of IID variables calculated?",
                    back="The expected value of the sum is n times the mean.",
                    card_type="short_answer_recall",
                )
                add(
                    suffix="iid-sum-variance",
                    front="How is the variance of a sum of IID variables calculated?",
                    back="The variance of the sum is n times the variance.",
                    card_type="short_answer_recall",
                )
                add(
                    suffix="iid-exam-trap",
                    front="What is a common exam trap about IID random variables?",
                    back="Do not assume identical distributions alone imply independence; IID requires both identical distribution and mutual independence.",
                    card_type="exam_trap",
                )

        if any(
            phrase in lowered
            for phrase in (
                "regression analysis",
                "dependent variable",
                "regression coefficient",
                "residual",
                "r-squared",
                "covariance stationary",
                "autoregressive model",
                "moving average model",
                "unit root",
            )
        ):
            if has("regression analysis"):
                add(
                    suffix="regression-analysis",
                    front="What does regression analysis model?",
                    back="Regression analysis models the relationship between a dependent variable and one or more independent variables.",
                    card_type="definition",
                )
            if has("dependent variable", "independent variables"):
                add(
                    suffix="dependent-vs-independent-variable",
                    front="How does a dependent variable differ from an independent variable in regression?",
                    back="The dependent variable is explained or predicted; independent variables are used to explain or predict it.",
                    card_type="comparison",
                )
                add(
                    suffix="regression-variable-purpose",
                    front="Why does regression analysis use a dependent variable and independent variables?",
                    back="The dependent variable is the outcome being explained; independent variables provide the explanatory information.",
                    card_type="short_answer_recall",
                )
            if "linear regression conditions" in lowered or (
                "relationship between y and x" in lowered
                and "error term" in lowered
                and "observable" in lowered
            ):
                add(
                    suffix="linear-regression-conditions",
                    front="What conditions must be satisfied to use linear regression?",
                    back="The Y-X relationship should be linear, the error term should be additive, and all X variables should be observable.",
                    card_type="list_recall",
                )
            if any(
                phrase in lowered
                for phrase in (
                    "linear function of the regression coefficients",
                    "linear function of regression coefficients",
                    "linear function of the coefficients",
                    "linear in the coefficients",
                    "linear in coefficients",
                )
            ):
                add(
                    suffix="linear-in-coefficients",
                    front="What does it mean for a regression relationship to be linear?",
                    back="The dependent variable is modeled as a linear function of the regression coefficients.",
                    card_type="interpretation",
                )
            if (
                "relationship between y and x should be linear" in lowered
                or "relationship between y and x is linear" in lowered
            ):
                add(
                    suffix="linear-y-x-relationship",
                    front="What relationship must Y and X have for linear regression?",
                    back="The relationship between Y and X should be linear.",
                    card_type="short_answer_recall",
                )
            if (
                "transforming an independent variable" in lowered
                or "transformation" in lowered
                or "transformed value of the independent variable" in lowered
            ):
                add(
                    suffix="regression-transformation",
                    front="Why can transforming an independent variable help a linear regression model?",
                    back="A transformation can make a nonlinear variable relationship fit a model that is linear in the coefficients.",
                    card_type="application",
                )
            if "nonlinear relationship" in lowered and "transformed value" in lowered:
                add(
                    suffix="regression-transformed-value",
                    front="How can a transformed independent variable help linear regression?",
                    back="A transformed independent variable can make a nonlinear relationship fit a linear regression model.",
                    card_type="application",
                )
            if (
                "error term should be additive" in lowered
                or "error term is additive" in lowered
                or "error term must be additive" in lowered
            ):
                add(
                    suffix="additive-error-term",
                    front="Why must the error term be additive in linear regression?",
                    back="An additive error term keeps model error separated from the explanatory variables and supports the regression assumptions.",
                    card_type="exam_trap",
                )
            if "all x variables should be observable" in lowered or "all x variables are observable" in lowered:
                add(
                    suffix="observable-x-variables",
                    front="Why must all X variables be observable in linear regression?",
                    back="The model cannot estimate the relationship correctly if required independent variables are missing or unobservable.",
                    card_type="exam_trap",
                )
            if "unknown parameter" in lowered and (
                "multiplicatively" in lowered or "exponent" in lowered
            ):
                add(
                    suffix="unknown-parameter-nonlinear",
                    front="When is linear regression inappropriate for unknown coefficients?",
                    back="Linear regression is inappropriate when unknown parameters enter the model nonlinearly, such as multiplicatively or in an exponent.",
                    card_type="exam_trap",
                )
            if has("regression coefficient"):
                add(
                    suffix="regression-coefficient",
                    front="What does a regression coefficient measure?",
                    back="A regression coefficient measures the change in the dependent variable for a one-unit change in an independent variable.",
                    card_type="definition",
                )
            if "residual" in lowered:
                add(
                    suffix="regression-residual",
                    front="What is a residual in regression analysis?",
                    back="A residual is the difference between the observed value and the fitted value.",
                    card_type="definition",
                )
            if "r-squared" in lowered:
                add(
                    suffix="r-squared",
                    front="What does R-squared measure in regression?",
                    back="R-squared measures the proportion of variation in the dependent variable explained by the regression.",
                    card_type="definition",
                )
            if "covariance stationary" in lowered:
                add(
                    suffix="covariance-stationarity-conditions",
                    front="What are the conditions for covariance stationarity?",
                    back="Constant mean, constant variance, and autocovariances that depend only on lag.",
                    card_type="list_recall",
                )
            if "autocorrelation" in lowered:
                add(
                    suffix="autocorrelation",
                    front="What does autocorrelation measure in a time series?",
                    back="Autocorrelation measures correlation between observations of a time series at different lags.",
                    card_type="definition",
                )
            if has("autoregressive model") and has("moving average model"):
                add(
                    suffix="ar-vs-ma-model",
                    front="How does an autoregressive model differ from a moving average model?",
                    back="An autoregressive model uses lagged dependent-variable values; a moving average model uses lagged error terms.",
                    card_type="comparison",
                )
            if "unit root" in lowered:
                add(
                    suffix="unit-root",
                    front="What does a unit root indicate in time-series analysis?",
                    back="A unit root indicates nonstationarity.",
                    card_type="short_answer_recall",
                )
            if "seasonality" in lowered:
                add(
                    suffix="seasonality",
                    front="What is seasonality in a time series?",
                    back="Seasonality is a repeating pattern over calendar periods.",
                    card_type="definition",
                )
            if "unit root" in lowered and "covariance stationary" in lowered:
                add(
                    suffix="unit-root-stationarity-trap",
                    front="What is a common exam trap about unit roots and stationarity?",
                    back="A series with a unit root is nonstationary, so it does not satisfy covariance stationarity.",
                    card_type="exam_trap",
                )

        if any(
            phrase in lowered
            for phrase in (
                "coherent risk measure",
                "expected shortfall",
                "subadditivity",
                "operational loss",
                "loss frequency",
                "loss severity",
                "monte carlo simulation",
            )
        ):
            if has("coherent risk measure"):
                add(
                    suffix="coherent-risk-measure-properties",
                    front="What properties must a coherent risk measure satisfy?",
                    back="Monotonicity, subadditivity, positive homogeneity, and translational invariance.",
                    card_type="list_recall",
                )
            if has("expected shortfall"):
                add(
                    suffix="expected-shortfall",
                    front="What does expected shortfall measure?",
                    back="Expected shortfall measures average loss conditional on losses exceeding the VaR threshold.",
                    card_type="definition",
                )
                add(
                    suffix="expected-shortfall-vs-var",
                    front="How does expected shortfall differ from VaR?",
                    back="VaR gives a threshold loss; expected shortfall averages losses beyond that threshold.",
                    card_type="comparison",
                )
            if "var is not coherent" in lowered or ("var" in lowered and "subadditivity" in lowered):
                add(
                    suffix="var-not-coherent",
                    front="Why is VaR not always a coherent risk measure?",
                    back="VaR can violate subadditivity.",
                    card_type="exam_trap",
                )
            if "subadditivity" in lowered:
                add(
                    suffix="subadditivity",
                    front="What does subadditivity require for a risk measure?",
                    back="The risk of a combined portfolio should not exceed the sum of the separate portfolio risks.",
                    card_type="short_answer_recall",
                )
            if has("loss frequency") and has("loss severity"):
                add(
                    suffix="loss-frequency-vs-severity",
                    front="How does loss frequency differ from loss severity?",
                    back="Loss frequency describes how often losses occur; loss severity describes how large losses are.",
                    card_type="comparison",
                )
            if has("loss frequency", "poisson distribution"):
                add(
                    suffix="loss-frequency-poisson",
                    front="How is loss frequency often modeled?",
                    back="Loss frequency is often modeled with a Poisson distribution.",
                    card_type="application",
                )
            if has("loss severity", "lognormal distribution"):
                add(
                    suffix="loss-severity-lognormal",
                    front="How is loss severity often modeled?",
                    back="Loss severity is often modeled with a lognormal distribution.",
                    card_type="application",
                )
            if has("monte carlo simulation"):
                add(
                    suffix="monte-carlo-operational-loss",
                    front="How can Monte Carlo simulation be used in operational loss modeling?",
                    back="Monte Carlo simulation can combine frequency and severity to estimate the loss distribution.",
                    card_type="application",
                )
            if has("operational loss") and has("loss frequency", "loss severity"):
                add(
                    suffix="operational-loss-modeling-inputs",
                    front="What two components does operational loss modeling separate?",
                    back="Operational loss modeling separates loss frequency from loss severity.",
                    card_type="list_recall",
                )
            if has("coherent risk measure", "expected shortfall"):
                add(
                    suffix="expected-shortfall-coherence",
                    front="Why is expected shortfall useful as a coherent tail risk measure?",
                    back="Expected shortfall captures average losses beyond the VaR threshold and can satisfy coherent risk properties.",
                    card_type="interpretation",
                )
            if has("operational loss"):
                add(
                    suffix="operational-loss-modeling",
                    front="What is operational loss modeling used to estimate?",
                    back="Operational loss modeling estimates an operational loss distribution.",
                    card_type="application",
                )
            if has("loss frequency"):
                add(
                    suffix="loss-frequency",
                    front="What is loss frequency?",
                    back="Loss frequency is the number of losses over a time period.",
                    card_type="definition",
                )
            if has("loss severity"):
                add(
                    suffix="loss-severity",
                    front="What is loss severity?",
                    back="Loss severity is the size of a loss.",
                    card_type="definition",
                )
            if has("loss frequency", "loss severity"):
                add(
                    suffix="frequency-severity-separate-modeling",
                    front="Why is loss frequency modeled separately from loss severity?",
                    back="Frequency measures how often losses occur, while severity measures how large losses are.",
                    card_type="interpretation",
                )
                add(
                    suffix="operational-loss-frequency-severity-trap",
                    front="What is a common exam trap about operational loss frequency and severity?",
                    back="Do not confuse how often losses occur with how large those losses are.",
                    card_type="exam_trap",
                )
            if has("operational loss") and has("monte carlo simulation"):
                add(
                    suffix="operational-loss-distribution",
                    front="What does the operational loss distribution combine?",
                    back="It combines loss frequency and loss severity.",
                    card_type="list_recall",
                )

        if any(
            phrase in lowered
            for phrase in (
                "historical-based var",
                "parametric approach",
                "nonparametric approach",
                "historical simulation",
                "implied volatility",
                "filtered historical simulation",
            )
        ):
            if has("historical-based var", "parametric", "nonparametric"):
                add(
                    suffix="historical-var-subcategories",
                    front="What are the two subcategories of historical-based VaR approaches?",
                    back="Parametric and nonparametric approaches.",
                    card_type="list_recall",
                )
            if has("parametric approach"):
                add(
                    suffix="parametric-var-assumption",
                    front="What does a parametric VaR approach typically assume?",
                    back="Asset returns follow a specified distribution, such as normal or lognormal.",
                    card_type="definition",
                )
            if has("nonparametric approach"):
                add(
                    suffix="nonparametric-var-less-restrictive",
                    front="Why is a nonparametric VaR approach less restrictive?",
                    back="It uses observed historical returns rather than imposing a return distribution.",
                    card_type="interpretation",
                )
            if has("historical simulation"):
                add(
                    suffix="historical-simulation-estimate-var",
                    front="How does historical simulation estimate VaR?",
                    back="It estimates VaR directly from past return data.",
                    card_type="application",
                )
            if has("implied volatility"):
                add(
                    suffix="implied-volatility-option-prices",
                    front="What does implied volatility infer from option prices?",
                    back="Market expectations about future volatility.",
                    card_type="definition",
                )
            if has("filtered historical simulation"):
                add(
                    suffix="filtered-historical-simulation-combines",
                    front="What does filtered historical simulation combine?",
                    back="Historical returns with volatility scaling.",
                    card_type="definition",
                )
            if has("parametric approach", "nonparametric approach"):
                add(
                    suffix="parametric-vs-nonparametric-var",
                    front="How does a parametric VaR approach differ from a nonparametric VaR approach?",
                    back="Parametric VaR assumes a distribution; nonparametric VaR uses observed historical returns.",
                    card_type="comparison",
                )
            if has("historical simulation", "implied volatility"):
                add(
                    suffix="historical-simulation-vs-implied-volatility",
                    front="How does historical simulation differ from implied-volatility-based VaR?",
                    back="Historical simulation uses past return data; implied-volatility-based VaR uses option prices to infer future volatility.",
                    card_type="comparison",
                )
            if has("parametric approach", "nonparametric approach"):
                add(
                    suffix="var-method-exam-trap",
                    front="What is a common exam trap when comparing parametric and nonparametric VaR approaches?",
                    back="Do not treat nonparametric VaR as distribution-free if the historical sample is not representative.",
                    card_type="exam_trap",
                )
            if has("filtered historical simulation"):
                add(
                    suffix="filtered-historical-simulation-volatility-scaling",
                    front="Why does filtered historical simulation use volatility scaling?",
                    back="To adjust historical returns for changing volatility conditions.",
                    card_type="interpretation",
                )

        if any(
            phrase in lowered
            for phrase in (
                "normal yield curve",
                "flat yield curve",
                "inverted yield curve",
                "positive butterfly",
                "negative butterfly",
                "twist",
            )
        ):
            if has("normal yield curve"):
                add(
                    suffix="normal-yield-curve",
                    front="What is a normal yield curve?",
                    back="An upward-sloping yield curve where longer maturities have higher yields.",
                    card_type="definition",
                )
            if has("flat yield curve"):
                add(
                    suffix="flat-yield-curve",
                    front="What does a flat yield curve mean?",
                    back="Short-term and long-term yields are similar.",
                    card_type="definition",
                )
                add(
                    suffix="flat-yield-curve-identification",
                    front="Which yield curve shape has similar short-term and long-term yields?",
                    back="A flat yield curve.",
                    card_type="short_answer_recall",
                )
            if has("inverted yield curve"):
                add(
                    suffix="inverted-yield-curve",
                    front="What is an inverted yield curve?",
                    back="A downward-sloping yield curve where short-term yields exceed long-term yields.",
                    card_type="definition",
                )
            if has("positive butterfly"):
                add(
                    suffix="positive-butterfly-yield-curve",
                    front="What does a positive butterfly indicate for the yield curve?",
                    back="The yield curve becomes more curved.",
                    card_type="interpretation",
                )
            if has("negative butterfly"):
                add(
                    suffix="negative-butterfly-yield-curve",
                    front="What does a negative butterfly indicate for the yield curve?",
                    back="The yield curve becomes less curved.",
                    card_type="interpretation",
                )
            if has("twist"):
                add(
                    suffix="yield-curve-twist",
                    front="What does a twist change in the yield curve?",
                    back="The slope of the yield curve.",
                    card_type="interpretation",
                )
            if has("normal yield curve", "inverted yield curve"):
                add(
                    suffix="normal-vs-inverted-yield-curve",
                    front="How does a normal yield curve differ from an inverted yield curve?",
                    back="A normal yield curve slopes upward; an inverted yield curve slopes downward.",
                    card_type="comparison",
                )
            if has("positive butterfly", "negative butterfly"):
                add(
                    suffix="positive-vs-negative-butterfly",
                    front="How does a positive butterfly differ from a negative butterfly?",
                    back="A positive butterfly increases curvature; a negative butterfly decreases curvature.",
                    card_type="comparison",
                )
                add(
                    suffix="butterfly-curvature-change",
                    front="Which yield curve change affects curvature rather than slope?",
                    back="A butterfly change affects yield curve curvature; a twist changes yield curve slope.",
                    card_type="comparison",
                )
            if has("twist"):
                add(
                    suffix="yield-curve-twist-feature",
                    front="What yield curve feature does a twist affect?",
                    back="A twist affects the slope of the yield curve.",
                    card_type="short_answer_recall",
                )
            if has("positive butterfly", "negative butterfly"):
                add(
                    suffix="yield-curve-butterfly-trap",
                    front="What is a common exam trap about yield curve butterflies?",
                    back="Butterflies describe curvature changes, not the overall level of rates.",
                    card_type="exam_trap",
                )

        if any(
            phrase in lowered
            for phrase in (
                "multiple testing",
                "hypothesis test",
                "null hypothesis",
                "alternative hypothesis",
                "test statistic",
                "p-value",
                "type i error",
                "type ii error",
            )
        ):
            if has("multiple testing"):
                sentence = self._source_sentence_containing(excerpt, "multiple testing", "means")
                add(
                    suffix="multiple-testing-definition",
                    front="What is multiple testing?",
                    back=sentence or "Multiple testing means testing multiple hypotheses on the same data set.",
                    card_type="definition",
                )
            if "type i error" in lowered and "increases" in lowered:
                sentence = self._source_sentence_containing(excerpt, "type i error", "increases")
                add(
                    suffix="multiple-testing-type-i-error",
                    front="How does multiple testing affect Type I error probability?",
                    back=sentence or "Multiple testing increases the probability of at least one Type I error.",
                    card_type="exam_trap",
                )
            if has("null", "alternative hypotheses"):
                add(
                    suffix="null-alternative-hypotheses",
                    front="What are the null and alternative hypotheses used for in a hypothesis test?",
                    back="They state the competing claims being tested.",
                    card_type="short_answer_recall",
                )
            if has("test statistic"):
                add(
                    suffix="test-statistic-role",
                    front="What role does the test statistic play in a hypothesis test?",
                    back="The test statistic is calculated from sample evidence and compared against the decision rule.",
                    card_type="application",
                )
            if "p-value" in lowered:
                add(
                    suffix="p-value-role",
                    front="What role does the p-value play in a hypothesis test?",
                    back="The p-value helps decide whether to reject or fail to reject the null hypothesis.",
                    card_type="application",
                )
            if "significance level" in lowered:
                add(
                    suffix="significance-level-role",
                    front="What role does the significance level play in a hypothesis test?",
                    back="The significance level sets the threshold for rejecting the null hypothesis.",
                    card_type="application",
                )

        if any(
            phrase in lowered
            for phrase in (
                "black-scholes-merton",
                "black-scholes",
                "lognormally distributed",
                "realized return",
                "historical volatility",
                "option delta",
                "delta hedging",
                "delta-neutral",
            )
        ):
            if "black-scholes-merton" in lowered or "black-scholes" in lowered:
                sentence = self._source_sentence_containing(excerpt, "black-scholes", "assumes")
                add(
                    suffix="bsm-stock-prices",
                    front="What does the Black-Scholes-Merton model assume about stock prices?",
                    back=sentence or "The Black-Scholes-Merton model assumes stock prices are lognormally distributed.",
                    card_type="short_answer_recall",
                )
                add(
                    suffix="bsm-stock-price-return-trap",
                    front="What is a common exam trap about Black-Scholes-Merton stock-price and return distributions?",
                    back="Stock prices are assumed lognormally distributed, while continuously compounded returns are normally distributed.",
                    card_type="exam_trap",
                )
            if "lognormally distributed" in lowered and "normally distributed" in lowered:
                add(
                    suffix="lognormal-prices-vs-normal-returns",
                    front="How do lognormal stock prices differ from normally distributed stock returns in the Black-Scholes-Merton model?",
                    back="Stock prices are lognormally distributed; continuously compounded stock returns are normally distributed.",
                    card_type="comparison",
                )
            if "natural logarithm" in lowered and "normally distributed" in lowered:
                add(
                    suffix="log-stock-price-distribution",
                    front="How is the natural logarithm of stock price distributed in the Black-Scholes-Merton setting?",
                    back="The natural logarithm of stock price is normally distributed.",
                    card_type="short_answer_recall",
                )
            if "realized return" in lowered and "normally distributed" in lowered:
                sentence = self._source_sentence_containing(excerpt, "realized return", "normally distributed")
                add(
                    suffix="realized-return-distribution",
                    front="How are continuously compounded realized returns distributed in the Black-Scholes-Merton setting?",
                    back=sentence or "Continuously compounded realized return is normally distributed.",
                    card_type="short_answer_recall",
                )
                add(
                    suffix="realized-return",
                    front="What is realized return?",
                    back="Realized return is the return observed over a period.",
                    card_type="definition",
                )
            if "historical volatility" in lowered:
                sentence = self._source_sentence_containing(excerpt, "historical volatility", "estimated")
                add(
                    suffix="historical-volatility-estimation",
                    front="How is historical volatility estimated?",
                    back=sentence or "Historical volatility is estimated from realized returns.",
                    card_type="application",
                )
                add(
                    suffix="historical-volatility",
                    front="What does historical volatility measure?",
                    back="Historical volatility measures volatility estimated from realized returns.",
                    card_type="definition",
                )
                if "annualized" in lowered:
                    add(
                        suffix="historical-volatility-annualized",
                        front="How is historical volatility annualized?",
                        back="Historical volatility is annualized using the square root of the number of trading days.",
                        card_type="application",
                    )
                    add(
                        suffix="annualized-volatility",
                        front="What does annualized volatility measure?",
                        back="Annualized volatility expresses volatility on a one-year scale.",
                        card_type="interpretation",
                    )
                    add(
                        suffix="historical-volatility-annualization-reason",
                        front="Why is historical volatility annualized?",
                        back="Historical volatility is annualized so volatility estimates are comparable on a one-year scale.",
                        card_type="interpretation",
                    )
            if "ex-dividend" in lowered and "volatility" in lowered:
                add(
                    suffix="ex-dividend-volatility-adjustment",
                    front="Why remove ex-dividend stock price changes when estimating volatility?",
                    back="Ex-dividend price changes should be removed so dividend effects do not distort volatility estimates.",
                    card_type="exam_trap",
                )
            if "option delta" in lowered or "delta of an option" in lowered:
                sentence = self._source_sentence_containing(excerpt, "delta", "option", "ratio")
                add(
                    suffix="option-delta-definition",
                    front="What is option delta?",
                    back=sentence or "Option delta is the ratio of the change in option value to the change in the underlying asset value.",
                    card_type="definition",
                )
                add(
                    suffix="option-delta-measures",
                    front="What does option delta measure?",
                    back="Option delta measures option value sensitivity to changes in the underlying asset value.",
                    card_type="interpretation",
                )
            if "delta hedging" in lowered:
                sentence = self._source_sentence_containing(excerpt, "delta hedging", "creates")
                add(
                    suffix="delta-hedging-definition",
                    front="What is delta hedging?",
                    back=sentence or "Delta hedging creates a delta-neutral portfolio by combining an option with the underlying asset.",
                    card_type="definition",
                )
                add(
                    suffix="delta-hedging-combination",
                    front="What positions are combined in delta hedging?",
                    back="An option position is combined with shares of the underlying asset.",
                    card_type="application",
                )
            if "delta-neutral" in lowered:
                add(
                    suffix="delta-neutral-portfolio",
                    front="What is a delta-neutral portfolio?",
                    back="A delta-neutral portfolio offsets option delta exposure with a position in the underlying asset.",
                    card_type="definition",
                )
            if "must be rebalanced" in lowered or "rebalanced as the option delta changes" in lowered:
                sentence = self._source_sentence_containing(excerpt, "rebalanced", "option delta")
                add(
                    suffix="delta-neutral-rebalance",
                    front="Why must a delta-neutral hedge be rebalanced?",
                    back=sentence or "A delta-neutral hedge must be rebalanced because option delta changes.",
                    card_type="exam_trap",
                )

        return self._valid_unique_flashcards(cards, limit=32)

    def _module_anchor_top_up_flashcards_from_concept(
        self,
        section: SourceSection,
        concept: StudyConceptCard,
        source_page: int | None,
    ) -> list[StudyFlashcard]:
        excerpt = re.sub(r"\s+", " ", concept.source_excerpt).strip()
        if not self._is_valid_flashcard_source_unit(excerpt):
            return []
        cards: list[StudyFlashcard] = []
        sentences = [
            re.sub(r"^LO\s+\d+\.[a-z]\s+", "", sentence.strip(), flags=re.IGNORECASE)
            for sentence in self._sentences(excerpt)
            if len(TOKEN_RE.findall(sentence)) >= 5
        ]
        sentences = [sentence for sentence in sentences if sentence and len(TOKEN_RE.findall(sentence)) >= 5]
        for index, sentence in enumerate(sentences[:16], start=1):
            cards.extend(
                self._top_up_flashcards_from_sentence(
                    section,
                    concept,
                    source_page,
                    sentence,
                    index=index,
                )
            )

        lowered = excerpt.lower()
        if "mutually exclusive" in lowered and "independent event" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="top-up-independent-vs-mutually-exclusive",
                    front="How do independent events differ from mutually exclusive events?",
                    back=(
                        "Independent events do not change each other's probabilities; mutually "
                        "exclusive events cannot occur together."
                    ),
                    card_type="comparison",
                    source_page=source_page,
                )
            )
        if "type i error" in lowered and "type ii error" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="top-up-type-i-error-definition",
                    front="What is a Type I error?",
                    back="A Type I error rejects a true null hypothesis.",
                    card_type="definition",
                    source_page=source_page,
                )
            )
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="top-up-type-ii-error-definition",
                    front="What is a Type II error?",
                    back="A Type II error fails to reject a false null hypothesis.",
                    card_type="definition",
                    source_page=source_page,
                )
            )
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="top-up-type-i-vs-type-ii-error",
                    front="How does a Type I error differ from a Type II error?",
                    back=(
                        "A Type I error rejects a true null hypothesis; a Type II error fails "
                        "to reject a false null hypothesis."
                    ),
                    card_type="comparison",
                    source_page=source_page,
                )
            )
        return self._valid_unique_flashcards(cards, limit=32)

    def _learning_outcome_anchor_top_up_flashcards(
        self,
        section: SourceSection,
        concept: StudyConceptCard,
        source_page: int | None,
    ) -> list[StudyFlashcard]:
        excerpt = re.sub(r"\s+", " ", concept.source_excerpt).strip()
        if not self._is_valid_flashcard_source_unit(excerpt):
            return []

        cards: list[StudyFlashcard] = []

        def add(suffix: str, front: str, back: str, card_type: str) -> None:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix=f"lo-anchor-{suffix}",
                    front=front,
                    back=back,
                    card_type=card_type,
                    source_page=source_page,
                )
            )

        def clean_list_items(text: str) -> list[str]:
            cleaned = re.sub(r"\band\b", ",", text, flags=re.IGNORECASE)
            items = [
                self._clean_flashcard_term(item)
                for item in re.split(r",|;", cleaned)
                if self._clean_flashcard_term(item)
            ]
            return [
                item
                for item in items
                if len(TOKEN_RE.findall(item)) >= 2
                and self._is_good_flashcard_term(item)
                and not re.fullmatch(r"borrowers?", item, re.IGNORECASE)
            ]

        def list_answer(items: list[str]) -> str:
            return "\n".join(f"{index}. {item[:1].upper()}{item[1:]}" for index, item in enumerate(items, start=1))

        def preferred_key_term(raw_subject: str, *, contains: str | None = None) -> str:
            raw_clean = self._clean_flashcard_term(raw_subject)
            raw_lower = raw_clean.lower()
            candidates = [self._clean_flashcard_term(term) for term in concept.key_terms]
            candidates = [
                term
                for term in candidates
                if term
                and self._is_good_flashcard_term(term)
                and (contains is None or contains.lower() in term.lower())
                and (
                    raw_lower in term.lower()
                    or term.lower() in raw_lower
                    or raw_lower.rstrip("s") in term.lower()
                    or term.lower().rstrip("s") in raw_lower
                )
            ]
            if candidates:
                return max(candidates, key=lambda term: (len(term.split()), len(term)))
            return raw_clean

        sentences = [
            re.sub(r"^LO\s+\d+\.[a-z]\s+", "", sentence.strip(), flags=re.IGNORECASE)
            for sentence in self._sentences(excerpt)
            if len(TOKEN_RE.findall(sentence)) >= 5
        ]

        for sentence_index, sentence in enumerate(sentences, start=1):
            formula_uses_match = re.match(
                r"^(?P<subject>[A-Za-z][A-Za-z0-9 /()'’.-]{2,90}?formula)\s+uses\s+(?P<inputs>[^.]+)\.$",
                sentence,
                re.IGNORECASE,
            )
            if formula_uses_match:
                raw_subject = formula_uses_match.group("subject")
                subject = self._clean_contextual_flashcard_subject(raw_subject, excerpt) or self._clean_flashcard_term(raw_subject)
                inputs = clean_list_items(formula_uses_match.group("inputs"))
                if subject and inputs:
                    subject_display = subject.lower()
                    if subject_display == "expected loss formula":
                        subject_display = "the expected loss formula"
                    add(
                        f"{sentence_index}-formula-inputs",
                        f"What inputs does {subject_display} use?",
                        list_answer(inputs),
                        "list_recall",
                    )
                    if "expected loss" in subject_display:
                        add(
                            f"{sentence_index}-expected-loss-inputs",
                            "What inputs are needed to calculate expected loss?",
                            list_answer(inputs),
                            "list_recall",
                        )
                        add(
                            f"{sentence_index}-expected-loss-formula-concept",
                            "What is the expected loss formula in credit risk?",
                            "Expected loss uses probability of default, exposure at default, and loss given default.",
                            "short_answer_recall",
                        )

        lowered = excerpt.lower()
        if all(term in lowered for term in ("multiple regression", "independent variables", "dependent variable")):
            add(
                "multiple-regression-purpose",
                "Why does multiple regression use independent variables?",
                "Multiple regression uses two or more independent variables to explain a dependent variable.",
                "interpretation",
            )
            add(
                "multiple-regression-dependent-variable",
                "What is the dependent variable in multiple regression?",
                "The dependent variable is the outcome that multiple regression tries to explain.",
                "definition",
            )
            add(
                "multiple-regression-independent-variables",
                "What are independent variables in multiple regression?",
                "Independent variables are the explanatory variables used to explain the dependent variable.",
                "definition",
            )
        if "coefficient of determination" in lowered:
            add(
                "coefficient-determination-importance",
                "Why does the coefficient of determination matter in regression?",
                "The coefficient of determination measures the proportion of variation explained by the regression.",
                "interpretation",
            )
        if "adjusted r-squared" in lowered:
            add(
                "adjusted-r-squared-model-selection",
                "What does adjusted R-squared do in model selection?",
                "Adjusted R-squared penalizes adding independent variables that do not improve explanatory power.",
                "interpretation",
            )
        if "dummy variable" in lowered:
            add(
                "dummy-variable-represent",
                "What does a dummy variable represent in regression?",
                "A dummy variable is a binary variable used to represent categories in a regression model.",
                "definition",
            )
            add(
                "dummy-variable-binary",
                "Why is a dummy variable binary?",
                "A dummy variable is binary so it can indicate whether a category is present in a regression model.",
                "interpretation",
            )
            add(
                "dummy-variable-category",
                "What type of variable represents categories in regression?",
                "A dummy variable represents categories in a regression model.",
                "short_answer_recall",
            )
        if "interaction term" in lowered and "independent variable" in lowered:
            add(
                "interaction-term-independent-variables",
                "How are interaction terms related to independent variables?",
                "An interaction term allows the effect of one independent variable to depend on another independent variable.",
                "interpretation",
            )
            add(
                "interaction-term-purpose",
                "What does an interaction term do in regression?",
                "An interaction term models how one independent variable's effect depends on another independent variable.",
                "definition",
            )
        if "multicollinearity" in lowered and "highly correlated" in lowered:
            add(
                "multicollinearity-relationship",
                "What relationship creates multicollinearity?",
                "Multicollinearity occurs when independent variables are highly correlated.",
                "definition",
            )
            add(
                "multicollinearity-independent-variables",
                "Which variables are highly correlated under multicollinearity?",
                "Independent variables are highly correlated under multicollinearity.",
                "short_answer_recall",
            )
        if "regression assumptions" in lowered:
            assumption_items = [
                item
                for item in ("linearity", "homoscedasticity", "independent errors", "normally distributed errors")
                if item in lowered
            ]
            if assumption_items:
                add(
                    "regression-assumptions-list",
                    "What assumptions are included in regression assumptions?",
                    list_answer(assumption_items),
                    "list_recall",
                )
        if "homoscedasticity" in lowered and "variance of the errors is not constant" in lowered:
            add(
                "homoscedasticity-constant-variance",
                "What does homoscedasticity require in regression errors?",
                "Homoscedasticity requires the variance of the errors to be constant.",
                "definition",
            )
        if "heteroskedasticity" in lowered and "variance of the errors is not constant" in lowered:
            add(
                "heteroskedasticity-meaning",
                "What does heteroskedasticity mean in regression?",
                "Heteroskedasticity means the variance of the errors is not constant.",
                "definition",
            )
            add(
                "heteroskedasticity-exam-trap",
                "What is a common exam trap about heteroskedasticity?",
                "Heteroskedasticity refers to nonconstant error variance, not to nonnormal errors.",
                "exam_trap",
            )
        if "serial correlation" in lowered and "correlated across observations" in lowered:
            add(
                "serial-correlation-meaning",
                "What does serial correlation mean for regression errors?",
                "Serial correlation means regression errors are correlated across observations.",
                "definition",
            )
            if "independent errors" in lowered:
                add(
                    "independent-errors-vs-serial-correlation",
                    "How do independent errors differ from serial correlation?",
                    "Independent errors are not correlated; serial correlation means errors are correlated across observations.",
                    "comparison",
                )
        if all(term in lowered for term in ("expected loss", "probability of default", "exposure at default", "loss given default")):
            add(
                "expected-loss-formula",
                "What is the expected loss formula in credit risk?",
                "EL = PD × EAD × LGD.",
                "formula",
            )
            add(
                "expected-loss-average-credit-loss",
                "Why is expected loss treated as an average credit loss?",
                "Expected loss is the average credit loss expected over a given time horizon.",
                "interpretation",
            )
            add(
                "expected-loss-pd-input",
                "What does probability of default contribute to expected loss?",
                "Probability of default is one of the inputs used in the expected loss formula.",
                "short_answer_recall",
            )
            add(
                "expected-loss-ead-input",
                "What does exposure at default contribute to expected loss?",
                "Exposure at default is one of the inputs used in the expected loss formula.",
                "short_answer_recall",
            )
            add(
                "expected-loss-lgd-input",
                "What does loss given default contribute to expected loss?",
                "Loss given default is one of the inputs used in the expected loss formula.",
                "short_answer_recall",
            )
            add(
                "expected-loss-three-inputs-trap",
                "What is a common exam trap about the expected loss formula?",
                "Do not omit probability of default, exposure at default, or loss given default from expected loss.",
                "exam_trap",
            )
        if "unexpected loss" in lowered and "expected loss" in lowered and re.search(
            r"actual losses can exceed expected losses|losses can exceed expected losses|above expected",
            lowered,
        ):
            add(
                "unexpected-vs-expected-loss",
                "How does unexpected loss differ from expected loss?",
                "Expected loss is the average expected credit loss; unexpected loss is the amount by which actual losses can exceed expected losses.",
                "comparison",
            )
            add(
                "unexpected-loss-exam-trap",
                "What is a common exam trap about unexpected loss?",
                "Unexpected loss is not the average loss; it is the excess loss above the expected level.",
                "exam_trap",
            )
            add(
                "unexpected-loss-exceeds-what",
                "What does unexpected loss exceed?",
                "Unexpected loss exceeds the expected loss level when actual losses are higher than expected.",
                "short_answer_recall",
            )

        for sentence_index, sentence in enumerate(sentences, start=1):
            consider_match = re.match(
                r"^(?P<subject>[A-Za-z][A-Za-z0-9 /()'’.-]{2,90}?)\s+consider\s+(?P<items>[^.]+)\.$",
                sentence,
                re.IGNORECASE,
            )
            if consider_match:
                raw_subject = consider_match.group("subject")
                subject = self._clean_contextual_flashcard_subject(raw_subject, excerpt) or self._clean_flashcard_term(raw_subject)
                items = clean_list_items(consider_match.group("items"))
                if subject and items:
                    display_subject = self._flashcard_subject_display(subject, raw_subject).lower()
                    add(
                        f"{sentence_index}-consider-factors",
                        f"What factors do {display_subject} consider?",
                        list_answer(items),
                        "list_recall",
                    )
                    if any("concentration risk" in item.lower() for item in items):
                        add(
                            f"{sentence_index}-concentration-risk-factor",
                            f"Why does concentration risk matter in {display_subject}?",
                            "Concentration risk matters because a portfolio can be exposed to large losses from related or concentrated borrowers.",
                            "application",
                        )
                        add(
                            f"{sentence_index}-credit-portfolio-borrowers-factor",
                            "Why do credit portfolio models consider borrowers?",
                            "Credit portfolio models consider borrowers because borrower-level exposures affect portfolio credit risk.",
                            "application",
                        )
                        add(
                            f"{sentence_index}-credit-portfolio-default-correlation-factor",
                            "Why do credit portfolio models consider default correlations?",
                            "Credit portfolio models consider default correlations because borrower defaults can move together during economic stress.",
                            "application",
                        )
                        add(
                            f"{sentence_index}-credit-portfolio-concentration-risk-factor",
                            "What role does concentration risk play in credit portfolio models?",
                            "Concentration risk is a key portfolio factor because concentrated borrowers can create large linked credit losses.",
                            "interpretation",
                        )

            correlation_measure_match = re.match(
                r"^(?P<subject>[A-Za-z][A-Za-z0-9 /()'’.-]{2,80}?)\s+measures?\s+how\s+(?P<object>[^.]+)\.$",
                sentence,
                re.IGNORECASE,
            )
            if correlation_measure_match:
                raw_subject = correlation_measure_match.group("subject")
                subject = preferred_key_term(raw_subject, contains="correlation")
                subject = self._clean_contextual_flashcard_subject(subject, excerpt) or self._clean_flashcard_term(subject)
                measured_object = correlation_measure_match.group("object").strip()
                if subject and len(TOKEN_RE.findall(measured_object)) >= 4:
                    display_subject = self._flashcard_subject_display(subject, raw_subject)
                    verb = "do" if self._subject_looks_plural(display_subject) else "does"
                    answer_verb = "measure" if verb == "do" else "measures"
                    add(
                        f"{sentence_index}-correlation-measure",
                        f"What {verb} {display_subject.lower()} measure?",
                        f"{display_subject[:1].upper()}{display_subject[1:]} {answer_verb} how {measured_object}.",
                        "definition",
                    )
                    if "default correlation" in display_subject.lower():
                        add(
                            f"{sentence_index}-default-correlation-indicate",
                            "What do default correlations indicate in credit portfolio models?",
                            "Default correlations indicate how borrower defaults may move together during economic stress.",
                            "interpretation",
                        )

            higher_correlation_match = re.match(
                r"^Higher\s+(?P<subject>[A-Za-z][A-Za-z0-9 /()'’.-]{2,80}?)\s+reduces\s+(?P<reduced>.+?)\s+and\s+can\s+increase\s+(?P<increased>.+?)\.$",
                sentence,
                re.IGNORECASE,
            )
            if higher_correlation_match:
                subject = self._clean_flashcard_term(higher_correlation_match.group("subject"))
                reduced = higher_correlation_match.group("reduced").strip()
                increased = higher_correlation_match.group("increased").strip()
                if subject and len(TOKEN_RE.findall(reduced)) >= 2 and len(TOKEN_RE.findall(increased)) >= 2:
                    subject_display = subject
                    if subject_display.lower().endswith("correlation"):
                        subject_display = subject_display + "s"
                    add(
                        f"{sentence_index}-higher-correlation-diversification",
                        f"How do higher {subject_display.lower()} affect {reduced.lower()}?",
                        f"Higher {subject_display.lower()} reduce {reduced} and can increase {increased}.",
                        "application",
                    )
                    add(
                        f"{sentence_index}-default-correlation-exam-trap",
                        "Why do higher default correlations matter in credit portfolios?",
                        "Higher default correlations reduce diversification benefits and can increase portfolio credit losses.",
                        "exam_trap",
                    )
                    add(
                        f"{sentence_index}-default-correlation-portfolio-losses",
                        "How can default correlations affect portfolio credit losses?",
                        "Higher default correlations can increase portfolio credit losses.",
                        "application",
                    )
                    add(
                        f"{sentence_index}-default-correlation-diversification-trap",
                        "What is a common exam trap about default correlations?",
                        "Higher default correlations reduce diversification benefits rather than improving diversification.",
                        "exam_trap",
                    )

            higher_correlation_increase_match = re.match(
                r"^Higher\s+(?P<subject>[A-Za-z][A-Za-z0-9 /()'’.-]{2,80}?)\s+"
                r"increases\s+(?P<increased>.+?)\s+and\s+reduces\s+(?P<reduced>.+?)\.$",
                sentence,
                re.IGNORECASE,
            )
            if higher_correlation_increase_match:
                subject = self._clean_flashcard_term(higher_correlation_increase_match.group("subject"))
                increased = higher_correlation_increase_match.group("increased").strip()
                reduced = higher_correlation_increase_match.group("reduced").strip()
                if subject and len(TOKEN_RE.findall(increased)) >= 2 and len(TOKEN_RE.findall(reduced)) >= 2:
                    subject_display = subject
                    add(
                        f"{sentence_index}-higher-correlation-tail-risk",
                        f"How does higher {subject_display.lower()} affect {increased.lower()}?",
                        f"Higher {subject_display.lower()} increases {increased} and reduces {reduced}.",
                        "application",
                    )
                    add(
                        f"{sentence_index}-higher-correlation-diversification-benefits",
                        f"How does higher {subject_display.lower()} affect {reduced.lower()}?",
                        f"Higher {subject_display.lower()} reduces {reduced}.",
                        "application",
                    )
                    if "default correlation" in subject_display.lower():
                        add(
                            f"{sentence_index}-default-correlation-tail-risk-trap",
                            "Why do higher default correlations matter in credit portfolios?",
                            "Higher default correlations increase portfolio tail risk and reduce diversification benefits.",
                            "exam_trap",
                        )

            credit_portfolio_models_use_match = re.match(
                r"^(?P<subject>Credit\s+portfolio\s+models?)\s+use\s+(?P<inputs>.+?)\s+to\s+(?P<purpose>.+)\.$",
                sentence,
                re.IGNORECASE,
            )
            if credit_portfolio_models_use_match:
                subject = self._clean_flashcard_term(credit_portfolio_models_use_match.group("subject"))
                input_text = credit_portfolio_models_use_match.group("inputs").strip()
                purpose = credit_portfolio_models_use_match.group("purpose").strip()
                input_items = clean_list_items(input_text)
                if subject and len(input_items) >= 2 and len(TOKEN_RE.findall(purpose)) >= 2:
                    add(
                        f"{sentence_index}-credit-portfolio-model-inputs",
                        "What do credit portfolio models use?",
                        list_answer(input_items),
                        "list_recall",
                    )
                    add(
                        f"{sentence_index}-credit-portfolio-model-purpose",
                        "Why do credit portfolio models use borrower-level inputs?",
                        f"Credit portfolio models use borrower-level inputs to {purpose}.",
                        "application",
                    )

            compensate_match = re.match(
                r"^(?P<subject>[A-Za-z][A-Za-z0-9 /()'’.-]{2,80}?)\s+compensate\s+lenders\s+for\s+(?P<object>[^.]+)\.$",
                sentence,
                re.IGNORECASE,
            )
            if compensate_match:
                subject = self._clean_contextual_flashcard_subject(compensate_match.group("subject"), excerpt) or self._clean_flashcard_term(
                    compensate_match.group("subject")
                )
                obj = compensate_match.group("object").strip()
                if subject and len(TOKEN_RE.findall(obj)) >= 3:
                    add(
                        f"{sentence_index}-credit-spreads-compensate",
                        f"What do {subject.lower()} compensate lenders for?",
                        f"{subject[:1].upper()}{subject[1:]} compensate lenders for {obj}.",
                        "interpretation",
                    )

            increases_when_match = re.match(
                r"^(?P<subject>[A-Za-z][A-Za-z0-9 /()'’.-]{2,80}?)\s+increases\s+when\s+(?P<condition>[^.]+)\.$",
                sentence,
                re.IGNORECASE,
            )
            if increases_when_match:
                subject = self._clean_contextual_flashcard_subject(increases_when_match.group("subject"), excerpt) or self._clean_flashcard_term(
                    increases_when_match.group("subject")
                )
                condition = increases_when_match.group("condition").strip()
                if subject and len(TOKEN_RE.findall(condition)) >= 4:
                    add(
                        f"{sentence_index}-risk-increases-when",
                        f"When does {subject.lower()} increase?",
                        f"{subject[:1].upper()}{subject[1:]} increases when {condition}.",
                        "application",
                    )

        return self._valid_unique_flashcards(cards, limit=32)

    def _balanced_learning_outcome_top_up_flashcards(
        self,
        section: SourceSection,
        concept: StudyConceptCard,
        source_page: int | None,
    ) -> list[StudyFlashcard]:
        excerpt = re.sub(r"\s+", " ", concept.source_excerpt).strip()
        if not self._is_valid_flashcard_source_unit(excerpt):
            return []

        lowered = excerpt.lower()
        cards: list[StudyFlashcard] = []

        def has(*terms: str) -> bool:
            return all(term.lower() in lowered for term in terms)

        def add(suffix: str, front: str, back: str, card_type: str) -> None:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix=f"balanced-lo-{suffix}",
                    front=front,
                    back=back,
                    card_type=card_type,
                    source_page=source_page,
                )
            )

        if has("insurance companies", "pool risks"):
            add(
                "insurance-companies-pool-risks",
                "What do insurance companies pool?",
                "Insurance companies pool risks.",
                "short_answer_recall",
            )
        if has("insurance companies", "collect premiums"):
            add(
                "insurance-companies-collect-premiums",
                "What do insurance companies collect?",
                "Insurance companies collect premiums.",
                "short_answer_recall",
            )
        if has("life insurance companies", "provide"):
            add(
                "life-insurance-companies-provide",
                "What do life insurance companies provide?",
                "Life insurance companies provide death benefits and annuity products.",
                "definition",
            )
        if has("property and casualty insurers", "cover"):
            add(
                "property-casualty-insurers-cover",
                "What do property and casualty insurers cover?",
                "Property and casualty insurers cover losses from accidents, liability, and property damage.",
                "definition",
            )
        if has("health insurers", "cover"):
            add(
                "health-insurers-cover",
                "What do health insurers cover?",
                "Health insurers cover medical expenses.",
                "definition",
            )
        if has("reinsurance", "transfers"):
            add(
                "reinsurance-definition",
                "What is reinsurance?",
                "Reinsurance transfers part of insurer risk to another insurer.",
                "definition",
            )
            add(
                "reinsurance-risk-transfer",
                "What does reinsurance transfer?",
                "Reinsurance transfers part of insurer risk to another insurer.",
                "interpretation",
            )
        if has("premiums compensate"):
            add(
                "premiums-compensate-insurers",
                "What do premiums compensate insurers for?",
                "Premiums compensate insurers for expected claims and expenses.",
                "interpretation",
            )
        if has("reserves support"):
            add(
                "reserves-support-claims",
                "What do reserves support in insurance?",
                "Reserves support future claim payments.",
                "interpretation",
            )
        if has("diversification reduces total portfolio risk"):
            add(
                "diversification-risk-reduction",
                "How does diversification reduce total portfolio risk?",
                "Diversification reduces total portfolio risk by pooling independent exposures or policyholder claims.",
                "interpretation",
            )
        if has("independent policyholder claims", "pooled"):
            add(
                "policyholder-claims-pooling",
                "Why do independent policyholder claims matter for diversification?",
                "Independent policyholder claims can be pooled across many exposures to reduce total portfolio risk.",
                "application",
            )
            add(
                "policyholder-claims-pooled-across",
                "What are independent policyholder claims pooled across?",
                "Independent policyholder claims are pooled across many exposures.",
                "short_answer_recall",
            )
        if has("insurance coverage is"):
            add(
                "insurance-coverage-definition",
                "What is insurance coverage?",
                "Insurance coverage is the protection provided by an insurance contract.",
                "definition",
            )
            add(
                "insurance-coverage-protection",
                "What does insurance coverage provide?",
                "Insurance coverage provides protection through an insurance contract.",
                "interpretation",
            )
        if has("premium payments are"):
            add(
                "premium-payments-definition",
                "What are premium payments?",
                "Premium payments are amounts policyholders pay for insurance coverage.",
                "definition",
            )
            add(
                "premium-payments-policyholders",
                "Who makes premium payments?",
                "Policyholders make premium payments for insurance coverage.",
                "short_answer_recall",
            )
        if has("benefit payments are"):
            add(
                "benefit-payments-definition",
                "What are benefit payments?",
                "Benefit payments are amounts insurers pay to policyholders when covered events occur.",
                "definition",
            )
            add(
                "covered-events-benefit-payments",
                "What happens when covered events occur under insurance?",
                "Insurers make benefit payments to policyholders when covered events occur.",
                "application",
            )
            add(
                "benefit-payments-policyholders",
                "Who receives benefit payments when covered events occur?",
                "Policyholders receive benefit payments when covered events occur.",
                "short_answer_recall",
            )
        if has("premium payments are", "benefit payments are"):
            add(
                "premium-vs-benefit-payments",
                "How do premium payments differ from benefit payments?",
                "Premium payments are paid by policyholders for coverage; benefit payments are paid by insurers when covered events occur.",
                "comparison",
            )
        if has("pension plans", "promise retirement benefits"):
            add(
                "pension-plans-retirement-benefits",
                "What do pension plans promise?",
                "Pension plans promise retirement benefits.",
                "definition",
            )
        if has("asset-liability risk"):
            add(
                "pension-asset-liability-risk",
                "What risk must pension plans manage?",
                "Pension plans must manage asset-liability risk.",
                "application",
            )

        return self._valid_unique_flashcards(cards, limit=32)

    def _top_up_flashcards_from_sentence(
        self,
        section: SourceSection,
        concept: StudyConceptCard,
        source_page: int | None,
        sentence: str,
        *,
        index: int,
    ) -> list[StudyFlashcard]:
        cards: list[StudyFlashcard] = []
        sentence = sentence.strip().rstrip(".") + "."
        sentence = re.sub(
            r"^(?:L\s*O|Learning\s+Objective)\s*\d+\s*(?:\.|\s+)?\s*[a-z]\b[:.]?\s+",
            "",
            sentence,
            flags=re.IGNORECASE,
        )
        if re.match(
            r"^(?:explain|describe|define|calculate|interpret|compare|identify|differentiate|demonstrate|distinguish)\b",
            sentence,
            re.IGNORECASE,
        ):
            return cards

        definition_match = re.match(
            r"^(?P<article>A|An|The)?\s*(?P<subject>[A-Za-z][A-Za-z0-9 /()'’.-]{2,90}?)\s+"
            r"(?P<copula>is|are)\s+(?P<answer>.+)\.$",
            sentence,
            re.IGNORECASE,
        )
        if definition_match and not re.search(
            r"\b(?:occurs\s+when|gives|measures|indicates|provides|estimates|models|states|"
            r"compares|summarizes|explains|allows|penalizes)\b"
            r"|^(?:expected value|variance|standard deviation|mean)\s+of\b",
            definition_match.group("subject"),
            re.IGNORECASE,
        ) and not re.match(
            r"used\s+when\b",
            definition_match.group("answer").strip(),
            re.IGNORECASE,
        ):
            raw_subject = definition_match.group("subject")
            subject = self._clean_contextual_flashcard_subject(raw_subject, concept.source_excerpt)
            answer = definition_match.group("answer").strip()
            if (
                subject
                and self._is_contextual_flashcard_subject(subject, concept.source_excerpt)
                and not self._is_bad_sentence_definition(subject, answer)
                and not self._looks_like_bad_flashcard_answer(answer)
            ):
                article = (definition_match.group("article") or "").lower()
                display_subject = f"{article} {subject}".strip()
                copula = definition_match.group("copula").lower()
                definition_verb = "are" if copula == "are" and self._subject_looks_plural(display_subject) else "is"
                question_verb = "are" if definition_verb == "are" else "is"
                cards.append(
                    self._build_flashcard(
                        section,
                        concept,
                        suffix=f"top-up-{index}-definition",
                        front=f"What {question_verb} {display_subject.lower()}?",
                        back=f"{display_subject[:1].upper()}{display_subject[1:]} {definition_verb} {answer}.",
                        card_type="definition",
                        source_page=source_page,
                    )
                )
            return cards

        occurs_match = re.match(
            r"^(?P<subject>[A-Za-z][A-Za-z0-9 /()'’.-]{2,90}?)\s+occurs\s+when\s+(?P<answer>.+)\.$",
            sentence,
            re.IGNORECASE,
        )
        if occurs_match:
            raw_subject = occurs_match.group("subject")
            subject = self._clean_contextual_flashcard_subject(raw_subject, concept.source_excerpt)
            answer = occurs_match.group("answer").strip()
            if (
                subject
                and self._is_contextual_flashcard_subject(subject, concept.source_excerpt)
                and not self._looks_like_bad_flashcard_answer(answer)
            ):
                display_subject = self._flashcard_subject_display(subject, raw_subject)
                cards.append(
                    self._build_flashcard(
                        section,
                        concept,
                        suffix=f"top-up-{index}-occurs-when",
                        front=f"When does {display_subject} occur?",
                        back=f"{display_subject[:1].upper()}{display_subject[1:]} occurs when {answer}.",
                        card_type="application",
                        source_page=source_page,
                    )
                )
                cards.append(
                    self._build_flashcard(
                        section,
                        concept,
                        suffix=f"top-up-{index}-occurs-definition",
                        front=f"What is {display_subject}?",
                        back=f"{display_subject[:1].upper()}{display_subject[1:]} occurs when {answer}.",
                        card_type="definition",
                        source_page=source_page,
                    )
                )
            return cards

        intent_match = re.match(
            r"^(?P<subject>[A-Za-z][A-Za-z0-9 /()'’.-]{2,90}?)\s+"
            r"(?P<mode>attempts|seeks|tries)\s+to\s+"
            r"(?P<verb>measure|model|estimate|explain|predict|describe|determine|differentiate)\s+"
            r"(?P<object>.+)\.$",
            sentence,
            re.IGNORECASE,
        )
        if intent_match:
            raw_subject = intent_match.group("subject")
            subject = self._clean_contextual_flashcard_subject(raw_subject, concept.source_excerpt)
            mode = intent_match.group("mode").lower()
            verb = intent_match.group("verb").lower()
            obj = intent_match.group("object").strip()
            if (
                subject
                and len(obj.split()) >= 3
                and self._is_contextual_flashcard_subject(subject, concept.source_excerpt)
                and not self._looks_like_bad_flashcard_answer(obj)
            ):
                display_subject = self._flashcard_subject_display(subject, raw_subject)
                normalized_mode = "seek" if mode == "seeks" else "attempt"
                answer_mode = "seeks" if mode == "seeks" else "attempts"
                cards.append(
                    self._build_flashcard(
                        section,
                        concept,
                        suffix=f"top-up-{index}-{normalized_mode}-to-{verb}",
                        front=f"What does {display_subject} {normalized_mode} to {verb}?",
                        back=f"{display_subject[:1].upper()}{display_subject[1:]} {answer_mode} to {verb} {obj}.",
                        card_type="definition" if verb in {"measure", "model", "estimate"} else "short_answer_recall",
                        source_page=source_page,
                    )
                )
            return cards

        uses_direct_match = re.match(
            r"^(?P<subject>(?:A|An|The)?\s*[A-Za-z][A-Za-z0-9 /()'’.-]{2,90}?)\s+uses\s+(?P<object>.+)\.$",
            sentence,
            re.IGNORECASE,
        )
        if uses_direct_match:
            raw_subject = uses_direct_match.group("subject")
            subject = self._clean_contextual_flashcard_subject(raw_subject, concept.source_excerpt)
            obj = uses_direct_match.group("object").strip()
            if (
                subject
                and self._is_contextual_flashcard_subject(subject, concept.source_excerpt)
                and not self._looks_like_bad_flashcard_answer(obj)
            ):
                display_subject = self._flashcard_subject_display(subject, raw_subject)
                if re.search(r"\b(?:one|two|more|multiple)\s+independent\s+variables?\b", obj, re.IGNORECASE):
                    front = f"How many independent variables does {display_subject} use?"
                else:
                    front = f"What does {display_subject} use?"
                cards.append(
                    self._build_flashcard(
                        section,
                        concept,
                        suffix=f"top-up-{index}-uses-direct",
                        front=front,
                        back=f"{display_subject[:1].upper()}{display_subject[1:]} uses {obj}.",
                        card_type="short_answer_recall",
                        source_page=source_page,
                    )
                )
            return cards

        can_estimate_match = re.match(
            r"^(?P<subject>(?:A|An|The)?\s*[A-Za-z][A-Za-z0-9 /()'’.-]{2,90}?)\s+can\s+estimate\s+(?P<object>.+)\.$",
            sentence,
            re.IGNORECASE,
        )
        if can_estimate_match:
            raw_subject = can_estimate_match.group("subject")
            subject = self._clean_contextual_flashcard_subject(raw_subject, concept.source_excerpt)
            obj = can_estimate_match.group("object").strip()
            if (
                subject
                and self._is_contextual_flashcard_subject(subject, concept.source_excerpt)
                and not self._looks_like_bad_flashcard_answer(obj)
            ):
                display_subject = self._flashcard_subject_display(subject, raw_subject)
                cards.append(
                    self._build_flashcard(
                        section,
                        concept,
                        suffix=f"top-up-{index}-can-estimate",
                        front=f"What can {display_subject} estimate?",
                        back=f"{display_subject[:1].upper()}{display_subject[1:]} can estimate {obj}.",
                        card_type="application",
                        source_page=source_page,
                    )
                )
            return cards

        depends_match = re.match(
            r"^(?P<subject>(?:A|An|The)?\s*[A-Za-z][A-Za-z0-9 /()'’.-]{2,90}?)\s+depends\s+on\s+(?P<object>.+)\.$",
            sentence,
            re.IGNORECASE,
        )
        if depends_match:
            raw_subject = depends_match.group("subject")
            subject = self._clean_contextual_flashcard_subject(raw_subject, concept.source_excerpt)
            obj = depends_match.group("object").strip()
            if (
                subject
                and self._is_contextual_flashcard_subject(subject, concept.source_excerpt)
                and not self._looks_like_bad_flashcard_answer(obj)
            ):
                display_subject = self._flashcard_subject_display(subject, raw_subject)
                front = (
                    "What determines the appropriate regression model choice?"
                    if re.search(r"\bmodel choice\b", subject, re.IGNORECASE)
                    else f"What does {display_subject} depend on?"
                )
                cards.append(
                    self._build_flashcard(
                        section,
                        concept,
                        suffix=f"top-up-{index}-depends-on",
                        front=front,
                        back=f"{display_subject[:1].upper()}{display_subject[1:]} depends on {obj}.",
                        card_type="application",
                        source_page=source_page,
                    )
                )
            return cards

        uses_match = re.match(
            r"^(?P<subject>[A-Za-z][A-Za-z0-9 /()'’.-]{2,90}?)\s+uses\s+(?P<inputs>.+?)\s+to\s+(?P<purpose>.+)\.$",
            sentence,
            re.IGNORECASE,
        )
        if uses_match:
            raw_subject = uses_match.group("subject")
            subject = self._clean_contextual_flashcard_subject(raw_subject, concept.source_excerpt)
            inputs = uses_match.group("inputs").strip()
            purpose = uses_match.group("purpose").strip()
            if (
                subject
                and self._is_contextual_flashcard_subject(subject, concept.source_excerpt)
                and not self._looks_like_bad_flashcard_answer(inputs)
                and not self._looks_like_bad_flashcard_answer(purpose)
            ):
                display_subject = self._flashcard_subject_display(subject, raw_subject)
                answer = f"{display_subject[:1].upper()}{display_subject[1:]} uses {inputs} to {purpose}."
                cards.append(
                    self._build_flashcard(
                        section,
                        concept,
                        suffix=f"top-up-{index}-uses",
                        front=f"What is {display_subject}?",
                        back=answer,
                        card_type="definition",
                        source_page=source_page,
                    )
                )
                cards.append(
                    self._build_flashcard(
                        section,
                        concept,
                        suffix=f"top-up-{index}-uses-inputs",
                        front=f"What inputs does {display_subject} use?",
                        back=inputs + ".",
                        card_type="short_answer_recall",
                        source_page=source_page,
                    )
                )
            return cards

        metric_match = re.match(
            r"^The (?P<metric>expected value|variance|standard deviation|mean) of (?P<subject>.+?) is (?P<value>[^.]+)\.$",
            sentence,
            re.IGNORECASE,
        )
        if metric_match:
            metric = metric_match.group("metric").lower()
            subject = self._clean_flashcard_term(metric_match.group("subject"))
            value = metric_match.group("value").strip()
            if self._is_good_flashcard_term(subject):
                equation_answer = f"{metric.capitalize()} = {value}."
                cards.append(
                    self._build_flashcard(
                        section,
                        concept,
                        suffix=f"top-up-{index}-{self._slug(metric)}",
                        front=f"What is the {metric} of {subject.lower()}?",
                        back=equation_answer,
                        card_type="short_answer_recall",
                        source_page=source_page,
                    )
                )
                if metric in {"expected value", "variance"} and re.search(r"\b(?:n|p|x|r|sigma|β|beta)\b|[()×*/+-]", value):
                    cards.append(
                        self._build_flashcard(
                            section,
                            concept,
                            suffix=f"top-up-{index}-{self._slug(metric)}-formula",
                            front=f"What formula gives the {metric} of {subject.lower()}?",
                            back=equation_answer,
                            card_type="formula",
                            source_page=source_page,
                        )
                    )
            return cards

        counts_match = re.match(
            r"^(?P<subject>(?:A|An|The)?\s*[A-Za-z][A-Za-z0-9 /()'’.-]{2,90}?)\s+counts\s+(?P<object>.+)\.$",
            sentence,
            re.IGNORECASE,
        )
        if counts_match:
            raw_subject = counts_match.group("subject")
            subject = self._clean_flashcard_subject(raw_subject)
            obj = counts_match.group("object").strip()
            if subject:
                display_subject = self._flashcard_subject_display(subject, raw_subject)
                cards.append(
                    self._build_flashcard(
                        section,
                        concept,
                        suffix=f"top-up-{index}-counts",
                        front=f"What does {display_subject} count?",
                        back=obj + ".",
                        card_type="short_answer_recall",
                        source_page=source_page,
                    )
                )
            return cards

        used_when_match = re.match(
            r"^(?P<subject>(?:A|An|The)?\s*[A-Za-z][A-Za-z0-9 /()'’.-]{2,90}?)\s+is used when\s+(?P<condition>.+)\.$",
            sentence,
            re.IGNORECASE,
        )
        if used_when_match:
            raw_subject = used_when_match.group("subject")
            subject = self._clean_flashcard_subject(raw_subject)
            condition = used_when_match.group("condition").strip()
            if subject:
                display_subject = self._flashcard_subject_display(subject, raw_subject)
                cards.append(
                    self._build_flashcard(
                        section,
                        concept,
                        suffix=f"top-up-{index}-used-when",
                        front=f"When is {display_subject} used?",
                        back=condition + ".",
                        card_type="application",
                        source_page=source_page,
                    )
                )
                if " and " in condition and len(condition.split()) <= 18:
                    cards.append(
                        self._build_flashcard(
                            section,
                            concept,
                            suffix=f"top-up-{index}-conditions",
                            front=f"What conditions are required for {display_subject}?",
                            back=condition + ".",
                            card_type="list_recall",
                            source_page=source_page,
                        )
                    )
            return cards

        action_match = re.match(
            r"^(?P<subject>(?:A|An|The)?\s*[A-Za-z][A-Za-z0-9 /()'’.-]{2,90}?)\s+"
            r"(?P<verb>give|gives|measure|measures|indicates|provide|provides|cover|covers|estimate|estimates|model|models|"
            r"state|states|compare|compares|summarize|summarizes|explain|explains|allow|allows|penalize|penalizes|"
            r"transfer|transfers|support|supports|compensate|compensates|reduce|reduces|increase|increases|"
            r"decrease|decreases|affect|affects|mitigate|mitigates|manage|manages|promise|"
            r"promises|pool|pools|collect|collects|pay|pays|evaluate|evaluates|consider|considers|assign|assigns|"
            r"translate|translates|display|displays|identify|identifies|calculate|calculates|monitor|monitors|"
            r"track|tracks|reflect|reflects|constrain|constrains|combine|combines|"
            r"define|defines|document|documents|verify|verifies|guarantee|guarantees|control|controls|create|creates)\s+"
            r"(?P<object>.+)\.$",
            sentence,
            re.IGNORECASE,
        )
        if action_match:
            raw_subject = action_match.group("subject")
            subject = self._clean_contextual_flashcard_subject(raw_subject, concept.source_excerpt)
            verb = action_match.group("verb").lower()
            obj = action_match.group("object").strip()
            base_verb = {
                "give": "give",
                "gives": "give",
                "measure": "measure",
                "measures": "measure",
                "indicates": "indicate",
                "provide": "provide",
                "provides": "provide",
                "cover": "cover",
                "covers": "cover",
                "estimate": "estimate",
                "estimates": "estimate",
                "model": "model",
                "models": "model",
                "state": "state",
                "states": "state",
                "compare": "compare",
                "compares": "compare",
                "summarize": "summarize",
                "summarizes": "summarize",
                "explain": "explain",
                "explains": "explain",
                "allow": "allow",
                "allows": "allow",
                "penalize": "penalize",
                "penalizes": "penalize",
                "transfer": "transfer",
                "transfers": "transfer",
                "support": "support",
                "supports": "support",
                "compensate": "compensate",
                "compensates": "compensate",
                "reduce": "reduce",
                "reduces": "reduce",
                "increase": "increase",
                "increases": "increase",
                "decrease": "decrease",
                "decreases": "decrease",
                "affect": "affect",
                "affects": "affect",
                "mitigate": "mitigate",
                "mitigates": "mitigate",
                "manage": "manage",
                "manages": "manage",
                "promise": "promise",
                "promises": "promise",
                "pool": "pool",
                "pools": "pool",
                "collect": "collect",
                "collects": "collect",
                "pay": "pay",
                "pays": "pay",
                "evaluate": "evaluate",
                "evaluates": "evaluate",
                "consider": "consider",
                "considers": "consider",
                "assign": "assign",
                "assigns": "assign",
                "translate": "translate",
                "translates": "translate",
                "display": "display",
                "displays": "display",
                "identify": "identify",
                "identifies": "identify",
                "calculate": "calculate",
                "calculates": "calculate",
                "monitor": "monitor",
                "monitors": "monitor",
                "track": "track",
                "tracks": "track",
                "reflect": "reflect",
                "reflects": "reflect",
                "constrain": "constrain",
                "constrains": "constrain",
                "combine": "combine",
                "combines": "combine",
                "define": "define",
                "defines": "define",
                "document": "document",
                "documents": "document",
                "verify": "verify",
                "verifies": "verify",
                "guarantee": "guarantee",
                "guarantees": "guarantee",
                "control": "control",
                "controls": "control",
                "create": "create",
                "creates": "create",
            }[verb]
            if subject and len(obj.split()) >= 3 and not self._looks_like_bad_flashcard_answer(obj):
                display_subject = self._flashcard_subject_display(subject, raw_subject)
                card_type = "comparison" if verb in {"compare", "compares"} else "interpretation"
                if verb in {
                    "measure",
                    "measures",
                    "estimate",
                    "estimates",
                    "model",
                    "models",
                    "provide",
                    "provides",
                    "cover",
                    "covers",
                    "affect",
                    "affects",
                    "evaluate",
                    "evaluates",
                    "consider",
                    "considers",
                    "assign",
                    "assigns",
                    "display",
                    "displays",
                    "identify",
                    "identifies",
                    "track",
                    "tracks",
                    "reflect",
                    "reflects",
                    "constrain",
                    "constrains",
                    "combine",
                    "combines",
                    "calculate",
                    "calculates",
                    "mitigate",
                    "mitigates",
                    "define",
                    "defines",
                    "document",
                    "documents",
                    "verify",
                    "verifies",
                    "guarantee",
                    "guarantees",
                    "control",
                    "controls",
                    "create",
                    "creates",
                }:
                    card_type = "definition"
                auxiliary = "do" if self._subject_looks_plural(display_subject) else "does"
                if base_verb == "translate":
                    into_match = re.match(r"(?P<input>.+?)\s+into\s+(?P<target>.+)", obj, re.IGNORECASE)
                    if into_match:
                        input_text = into_match.group("input").strip()
                        target_text = into_match.group("target").strip()
                        cards.append(
                            self._build_flashcard(
                                section,
                                concept,
                                suffix=f"top-up-{index}-translate-into",
                                front=f"What {auxiliary} {display_subject} translate {input_text} into?",
                                back=f"{display_subject[:1].upper()}{display_subject[1:]} {verb} {input_text} into {target_text}.",
                                card_type="interpretation",
                                source_page=source_page,
                            )
                        )
                elif base_verb == "give":
                    holder_right_match = re.match(
                        r"(?:the\s+)?holder\s+the\s+right\s+to\s+(?P<right>.+)",
                        obj,
                        re.IGNORECASE,
                    )
                    holders_rights_match = re.match(
                        r"holders?\s+rights?\s+(?P<right>.+)",
                        obj,
                        re.IGNORECASE,
                    )
                    if holder_right_match:
                        right_text = holder_right_match.group("right").strip()
                        cards.append(
                            self._build_flashcard(
                                section,
                                concept,
                                suffix=f"top-up-{index}-holder-right",
                                front=f"What right {auxiliary} {display_subject} give the holder?",
                                back=f"{display_subject[:1].upper()}{display_subject[1:]} {verb} the holder the right to {right_text}.",
                                card_type="definition",
                                source_page=source_page,
                            )
                        )
                    elif holders_rights_match:
                        right_text = holders_rights_match.group("right").strip()
                        cards.append(
                            self._build_flashcard(
                                section,
                                concept,
                                suffix=f"top-up-{index}-holders-rights",
                                front=f"What rights {auxiliary} {display_subject} give holders?",
                                back=f"{display_subject[:1].upper()}{display_subject[1:]} {verb} holders rights {right_text}.",
                                card_type="definition",
                                source_page=source_page,
                            )
                        )
                    else:
                        cards.append(
                            self._build_flashcard(
                                section,
                                concept,
                                suffix=f"top-up-{index}-{base_verb}",
                                front=f"What {auxiliary} {display_subject} {base_verb}?",
                                back=f"{display_subject[:1].upper()}{display_subject[1:]} {verb} {obj}.",
                                card_type=card_type,
                                source_page=source_page,
                            )
                        )
                else:
                    cards.append(
                        self._build_flashcard(
                            section,
                            concept,
                            suffix=f"top-up-{index}-{base_verb}",
                            front=f"What {auxiliary} {display_subject} {base_verb}?",
                            back=f"{display_subject[:1].upper()}{display_subject[1:]} {verb} {obj}.",
                            card_type=card_type,
                            source_page=source_page,
                        )
                    )
            return cards

        written_match = re.match(
            r"^(?P<subject>[A-Za-z][A-Za-z0-9 /()'’.-]{2,90}?)\s+are written\s+(?P<answer>.+)\.$",
            sentence,
            re.IGNORECASE,
        )
        if written_match:
            subject = self._clean_flashcard_subject(written_match.group("subject"))
            answer = written_match.group("answer").strip()
            if subject and len(answer.split()) >= 3:
                cards.append(
                    self._build_flashcard(
                        section,
                        concept,
                        suffix=f"top-up-{index}-written",
                        front=f"What are {subject.lower()}?",
                        back=f"{subject} are written {answer}.",
                        card_type="definition",
                        source_page=source_page,
                    )
                )
            return cards

        has_match = re.match(
            r"^(?P<article>A|An|The)\s+(?P<subject>[A-Za-z][A-Za-z0-9 /()'’.-]{2,90}?)\s+has\s+(?P<answer>.+)\.$",
            sentence,
            re.IGNORECASE,
        )
        if has_match:
            article = has_match.group("article").lower()
            subject = self._clean_flashcard_subject(has_match.group("subject"))
            answer = has_match.group("answer").strip()
            if subject:
                display_subject = f"{article} {subject}"
                cards.append(
                    self._build_flashcard(
                        section,
                        concept,
                        suffix=f"top-up-{index}-has",
                        front=f"What is {display_subject}?",
                        back=f"{article.capitalize()} {subject} has {answer}.",
                        card_type="definition",
                        source_page=source_page,
                    )
                )
                variable_match = re.search(r"\bsuccess probability (?P<variable>[a-z])\b", answer, re.IGNORECASE)
                if variable_match:
                    variable = variable_match.group("variable")
                    cards.append(
                        self._build_flashcard(
                            section,
                            concept,
                            suffix=f"top-up-{index}-success-probability",
                            front=f"In {display_subject}, what does {variable} represent?",
                            back=f"{variable} is the probability of success.",
                            card_type="short_answer_recall",
                            source_page=source_page,
                    )
                )
            return cards

        means_match = re.match(
            r"^(?P<subject>[A-Za-z][A-Za-z0-9 /()'’.-]{2,90}?)\s+means\s+(?P<answer>.+)\.$",
            sentence,
            re.IGNORECASE,
        )
        if means_match:
            raw_subject = means_match.group("subject")
            subject = self._clean_flashcard_subject(raw_subject)
            answer = means_match.group("answer").strip()
            if subject and len(answer.split()) >= 3 and not self._looks_like_bad_flashcard_answer(answer):
                display_subject = self._flashcard_subject_display(subject, raw_subject)
                cards.append(
                    self._build_flashcard(
                        section,
                        concept,
                        suffix=f"top-up-{index}-means",
                        front=f"What is {display_subject}?",
                        back=f"{display_subject[:1].upper()}{display_subject[1:]} means {answer}.",
                        card_type="definition",
                        source_page=source_page,
                    )
                )
            return cards

        assumes_match = re.match(
            r"^(?P<subject>(?:A|An|The)?\s*[A-Za-z][A-Za-z0-9 /()'’.-]{2,90}?)\s+assumes\s+that\s+(?P<answer>.+)\.$",
            sentence,
            re.IGNORECASE,
        )
        if assumes_match:
            raw_subject = assumes_match.group("subject")
            subject = self._clean_flashcard_subject(raw_subject)
            answer = assumes_match.group("answer").strip()
            if subject and len(answer.split()) >= 3 and not self._looks_like_bad_flashcard_answer(answer):
                display_subject = self._flashcard_subject_display(subject, raw_subject)
                cards.append(
                    self._build_flashcard(
                        section,
                        concept,
                        suffix=f"top-up-{index}-assumes",
                        front=f"What does {display_subject} assume?",
                        back=f"{display_subject[:1].upper()}{display_subject[1:]} assumes that {answer}.",
                        card_type="short_answer_recall",
                        source_page=source_page,
                    )
                )
            return cards

        estimated_match = re.match(
            r"^(?P<subject>(?:A|An|The)?\s*[A-Za-z][A-Za-z0-9 /()'’.-]{2,90}?)\s+is estimated from\s+(?P<answer>.+)\.$",
            sentence,
            re.IGNORECASE,
        )
        if estimated_match:
            raw_subject = estimated_match.group("subject")
            subject = self._clean_flashcard_subject(raw_subject)
            answer = estimated_match.group("answer").strip()
            if subject and len(answer.split()) >= 2 and not self._looks_like_bad_flashcard_answer(answer):
                display_subject = self._flashcard_subject_display(subject, raw_subject)
                cards.append(
                    self._build_flashcard(
                        section,
                        concept,
                        suffix=f"top-up-{index}-estimated-from",
                        front=f"How is {display_subject} estimated?",
                        back=f"{display_subject[:1].upper()}{display_subject[1:]} is estimated from {answer}.",
                        card_type="application",
                        source_page=source_page,
                    )
                )
            return cards

        ratio_match = re.match(
            r"^(?P<subject>(?:A|An|The)?\s*[A-Za-z][A-Za-z0-9 /()'’.-]{2,90}?)\s+is the ratio of\s+(?P<answer>.+)\.$",
            sentence,
            re.IGNORECASE,
        )
        if ratio_match:
            raw_subject = ratio_match.group("subject")
            subject = self._clean_flashcard_subject(raw_subject)
            answer = ratio_match.group("answer").strip()
            if subject and len(answer.split()) >= 4 and not self._looks_like_bad_flashcard_answer(answer):
                display_subject = self._flashcard_subject_display(subject, raw_subject)
                cards.append(
                    self._build_flashcard(
                        section,
                        concept,
                        suffix=f"top-up-{index}-ratio",
                        front=f"What is {display_subject}?",
                        back=f"{display_subject[:1].upper()}{display_subject[1:]} is the ratio of {answer}.",
                        card_type="definition",
                        source_page=source_page,
                    )
                )
            return cards

        creates_match = re.match(
            r"^(?P<subject>[A-Za-z][A-Za-z0-9 /()'’.-]{2,90}?)\s+creates\s+(?P<answer>.+)\.$",
            sentence,
            re.IGNORECASE,
        )
        if creates_match:
            raw_subject = creates_match.group("subject")
            subject = self._clean_flashcard_subject(raw_subject)
            answer = creates_match.group("answer").strip()
            if subject and len(answer.split()) >= 3 and not self._looks_like_bad_flashcard_answer(answer):
                display_subject = self._flashcard_subject_display(subject, raw_subject)
                cards.append(
                    self._build_flashcard(
                        section,
                        concept,
                        suffix=f"top-up-{index}-creates",
                        front=f"What does {display_subject} create?",
                        back=f"{display_subject[:1].upper()}{display_subject[1:]} creates {answer}.",
                        card_type="application",
                        source_page=source_page,
                    )
                )
            return cards

        rebalanced_match = re.match(
            r"^(?P<subject>(?:A|An|The)?\s*[A-Za-z][A-Za-z0-9 /()'’.-]{2,90}?)\s+must be rebalanced\s+(?P<answer>.+)\.$",
            sentence,
            re.IGNORECASE,
        )
        if rebalanced_match:
            raw_subject = rebalanced_match.group("subject")
            subject = self._clean_flashcard_subject(raw_subject)
            answer = rebalanced_match.group("answer").strip()
            if subject and len(answer.split()) >= 3 and not self._looks_like_bad_flashcard_answer(answer):
                display_subject = self._flashcard_subject_display(subject, raw_subject)
                cards.append(
                    self._build_flashcard(
                        section,
                        concept,
                        suffix=f"top-up-{index}-rebalanced",
                        front=f"Why must {display_subject} be rebalanced?",
                        back=f"{display_subject[:1].upper()}{display_subject[1:]} must be rebalanced {answer}.",
                        card_type="exam_trap",
                        source_page=source_page,
                    )
                )
            return cards

        cannot_match = re.match(
            r"^(?P<subject>[A-Za-z][A-Za-z0-9 /()'’.-]{2,90}?)\s+cannot occur together\.$",
            sentence,
            re.IGNORECASE,
        )
        if cannot_match:
            subject = self._clean_flashcard_subject(cannot_match.group("subject"))
            if subject:
                cards.append(
                    self._build_flashcard(
                        section,
                        concept,
                        suffix=f"top-up-{index}-cannot-occur",
                        front=f"What are {subject.lower()}?",
                        back=f"{subject} cannot occur together.",
                        card_type="definition",
                        source_page=source_page,
                    )
                )
            return cards

        do_not_match = re.match(
            r"^(?P<subject>[A-Za-z][A-Za-z0-9 /()'’.-]{2,90}?)\s+do not change\s+(?P<object>.+)\.$",
            sentence,
            re.IGNORECASE,
        )
        if do_not_match:
            subject = self._clean_flashcard_subject(do_not_match.group("subject"))
            obj = do_not_match.group("object").strip()
            if subject:
                cards.append(
                    self._build_flashcard(
                        section,
                        concept,
                        suffix=f"top-up-{index}-do-not-change",
                        front=f"What are {subject.lower()}?",
                        back=f"{subject} do not change {obj}.",
                        card_type="definition",
                        source_page=source_page,
                    )
                )
            return cards

        include_match = re.search(
            r"(?P<subject>[A-Za-z][A-Za-z0-9 /()'’.-]{3,90})\s+(?:include|includes)\s+(?P<items>.+)\.$",
            sentence,
            re.IGNORECASE,
        )
        if include_match:
            subject = self._clean_flashcard_subject(include_match.group("subject"))
            items = include_match.group("items").strip()
            if subject and len(items.split()) >= 3:
                cards.append(
                    self._build_flashcard(
                        section,
                        concept,
                        suffix=f"top-up-{index}-includes",
                        front=f"What does {subject.lower()} include?",
                        back=items + ".",
                        card_type="list_recall",
                        source_page=source_page,
                    )
                )
        return cards

    def _source_sentence_containing(
        self,
        text: str,
        *terms: str,
        exclude_prefix: str | None = None,
    ) -> str:
        for sentence in self._sentences(text):
            stripped = sentence.strip()
            lowered = stripped.lower()
            if exclude_prefix and lowered.startswith(exclude_prefix.lower()):
                continue
            if all(term.lower() in lowered for term in terms):
                return stripped
        return ""

    def _clean_flashcard_subject(self, subject: str) -> str:
        cleaned = re.sub(r"^(?:a|an|the)\s+", "", subject.strip(), flags=re.IGNORECASE)
        cleaned = self._clean_flashcard_term(cleaned)
        if cleaned.lower() in {
            "mutually exclusive events",
            "independent events",
            "bernoulli random variable",
            "binomial random variable",
            "binomial distribution",
        }:
            return cleaned
        if not self._is_good_flashcard_term(cleaned):
            return ""
        if len(cleaned.split()) > 8:
            return ""
        return cleaned

    def _clean_contextual_flashcard_subject(self, subject: str, context: str) -> str:
        cleaned = re.sub(r"^(?:a|an|the)\s+", "", subject.strip(), flags=re.IGNORECASE)
        cleaned = self._clean_flashcard_term(cleaned)
        strict = self._clean_flashcard_subject(cleaned)
        if strict:
            return strict
        if self._is_contextual_flashcard_subject(cleaned, context):
            return cleaned
        return ""

    def _is_contextual_flashcard_subject(self, subject: str, context: str) -> bool:
        cleaned = self._clean_flashcard_term(subject)
        if not cleaned or len(cleaned) < 4 or len(cleaned.split()) > 8:
            return False
        lowered = cleaned.lower()
        if (
            lowered in JUNK_STUDY_TERMS
            or lowered in FRAGMENT_FLASHCARD_TERMS
            or self._is_junk_workbook_keyword(cleaned)
            or self._is_phrase_soup(cleaned)
        ):
            return False
        if re.match(
            r"^(?:as|of|the|all|one|possible|following|to|its|which|if|such|when|whether|"
            r"because|given|suppose|assume|also|there|some|payment|payments|countries|they)\b",
            lowered,
        ):
            return False
        if re.search(r"\b(?:where|that|which|per|from|to|with|and|both|various)$", lowered):
            return False
        pattern = re.escape(cleaned).replace(r"\ ", r"\s+")
        return bool(re.search(rf"\b{pattern}\b", context, re.IGNORECASE))

    def _flashcard_subject_display(self, subject: str, raw_subject: str) -> str:
        article_match = re.match(r"^\s*(?P<article>a|an|the)\s+", raw_subject, flags=re.IGNORECASE)
        article = article_match.group("article").lower() if article_match else ""
        cleaned = self._clean_flashcard_term(subject)
        if article:
            return f"{article} {cleaned}"
        return cleaned[:1].lower() + cleaned[1:] if cleaned else cleaned

    def _flashcard_llm_prompts_for_anchor(
        self,
        *,
        book_title: str,
        reading_number: int | str | None,
        module_number: str | None,
        lo_code: str | None,
        page_start: int | str | None,
        page_end: int | str | None,
        anchor_type: str | None,
        anchor_text: str,
        source_text: str,
    ) -> tuple[str, str]:
        """Build the strict prompt contract for optional LLM card generation."""

        source_text = re.sub(r"\s+", " ", source_text).strip()[:MAX_FLASHCARD_LLM_SOURCE_CHARS]
        input_payload = {
            "bookTitle": book_title or "",
            "readingNumber": "" if reading_number is None else str(reading_number),
            "moduleNumber": module_number or "",
            "loCode": lo_code or "",
            "pageStart": "" if page_start is None else str(page_start),
            "pageEnd": "" if page_end is None else str(page_end),
            "anchorType": anchor_type or "",
            "anchorText": anchor_text,
            "sourceText": source_text,
        }
        output_schema = {
            "cards": [
                {
                    "cardType": (
                        "Definition|Formula|Interpretation|CompareContrast|Process|"
                        "ExamTrap|Application|ShortAnswerRecall"
                    ),
                    "front": "...",
                    "back": "...",
                    "explanation": "...",
                    "tags": [],
                    "qualityRationale": "...",
                }
            ]
        }
        rules = [
            "1. Use only the provided source anchor and surrounding source text.",
            (
                "2. The card must test a real exam concept, formula, definition, "
                "comparison, process, interpretation, or exam trap."
            ),
            "3. Never generate a question from a broken phrase or partial sentence.",
            "4. The question must be grammatically complete.",
            "5. The answer must be concise and exam-useful.",
            "6. Do not copy the full paragraph as the answer.",
            "7. If the source contains a formula, preserve the formula and explain variables.",
            (
                "8. If the source contains a bold term followed by explanation, create a "
                "definition or interpretation card."
            ),
            "9. If the source contains a learning objective, create cards that directly test the LO.",
            "10. Return only valid JSON.",
        ]
        user_prompt = "\n".join(
            [
                "Generate high-quality exam flashcards from the following source anchor.",
                "",
                "Rules:",
                *rules,
                "",
                "Input:",
                json.dumps(input_payload, ensure_ascii=False, indent=2),
                "",
                "Output JSON:",
                json.dumps(output_schema, ensure_ascii=False, indent=2),
                "",
                "Reject the card and return an empty cards array if the source anchor is not meaningful.",
            ]
        )
        return FLASHCARD_LLM_SYSTEM_PROMPT, user_prompt

    def _card_anchors_for_concept(self, concept: StudyConceptCard) -> list[tuple[str, str]]:
        excerpt = re.sub(r"\s+", " ", concept.source_excerpt).strip()
        lowered = excerpt.lower()
        anchors: list[tuple[str, str]] = []

        lo_match = re.search(
            r"\b(?:L\s*O|Learning\s+Objective)\s*\d+\s*(?:\.|\s+)?\s*[a-z]\b",
            concept.learning_outcome or excerpt,
            re.IGNORECASE,
        )
        if lo_match and len(TOKEN_RE.findall(excerpt)) >= 4:
            anchors.append(("lo_heading", self._normalize_learning_outcome_code(lo_match.group(0)) or lo_match.group(0)))

        for term in concept.key_terms:
            cleaned = self._clean_flashcard_term(term)
            if self._is_good_flashcard_term(cleaned):
                anchors.append(("bold_term", cleaned))

        title_anchor = self._clean_flashcard_topic(concept)
        if title_anchor and self._is_good_flashcard_term(title_anchor):
            anchors.append(("key_concept", title_anchor))

        if self._numbered_items_from_excerpt(concept.source_excerpt):
            anchors.append(("process", "numbered process"))
        if "=" in excerpt and re.search(r"[A-Za-z][A-Za-z0-9()_,]*\s*=", excerpt):
            anchors.append(("formula", "formula block"))
        if re.search(r"\b(?:differ|different|versus| vs\.? |compare|contrast)\b", lowered):
            anchors.append(("comparison", "compare contrast"))
        if re.search(r"\b(?:common mistake|do not confuse|trap|misleading|limitation|conflict)\b", lowered):
            anchors.append(("exam_trap", "exam trap"))

        unique: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for anchor in anchors:
            key = (anchor[0], anchor[1].lower())
            if key in seen:
                continue
            seen.add(key)
            unique.append(anchor)
        return unique

    def _is_valid_flashcard_source_unit(self, text: str) -> bool:
        cleaned = re.sub(r"\s+", " ", text).strip()
        if not cleaned:
            return False
        if "formula-crop://" in cleaned or FORMULA_IMAGE_CROP_RE.search(cleaned):
            return False
        if re.search(r"[A-Za-z0-9+/]{160,}={0,2}", cleaned):
            return False

        without_lo = re.sub(
            r"\b(?:L\s*O|Learning\s+Objective)\s*\d+\s*(?:\.|\s+)?\s*[a-z]\b[:.]?",
            " ",
            cleaned,
            flags=re.IGNORECASE,
        )
        without_lo = re.sub(r"\s+", " ", without_lo).strip()
        if len(TOKEN_RE.findall(without_lo)) < 2:
            return False
        if self._is_low_value_text(without_lo):
            return False

        short_matters = re.fullmatch(
            r"(?P<topic>[A-Z][A-Za-z0-9 /()'-]{2,80})\s+matters\.?",
            without_lo,
            re.IGNORECASE,
        )
        if short_matters:
            topic = self._clean_flashcard_term(short_matters.group("topic"))
            if self._is_good_flashcard_term(topic) or topic.lower() in FINANCE_ACADEMIC_TERMS:
                return True

        formula_like = "=" in without_lo and re.search(r"[A-Za-z][A-Za-z0-9()_,]*\s*=", without_lo)
        sentence_like_units = [
            sentence
            for sentence in self._sentences(without_lo)
            if len(TOKEN_RE.findall(sentence)) >= 4
        ]
        if not sentence_like_units and len(TOKEN_RE.findall(without_lo)) >= 6:
            sentence_like_units = [without_lo]
        has_concept_context = any(
            re.search(
                r"\b(?:is|are|means|describes|measures|include|includes|requires|equals|depends|used|"
                r"summarize|represent|credit|charge|increase|decrease|affect|mitigate|reduce|cover|"
                r"evaluate|use|uses|calculate|consist|consists|contain|contains|regulate|regulates|"
                r"produce|produces|convert|converts|control|controls|support|supports|prevent|prevents|"
                r"occur|occurs|require|requires)\b",
                sentence.lower(),
            )
            or len(
                [
                    token
                    for token in TOKEN_RE.findall(sentence)
                    if token.lower() not in CONTENT_ANCHOR_STOPWORDS
                    and token.lower() not in FRAGMENT_FLASHCARD_TERMS
                ]
            )
            >= 5
            for sentence in sentence_like_units
        )
        if not has_concept_context and not formula_like:
            return False

        meaningful_tokens = [
            token.lower()
            for token in TOKEN_RE.findall(without_lo)
            if token.lower() not in CONTENT_ANCHOR_STOPWORDS
        ]
        if meaningful_tokens and all(token in FRAGMENT_FLASHCARD_TERMS for token in meaningful_tokens):
            return False
        fragment_sentence_count = sum(
            1
            for sentence in sentence_like_units
            if sentence.lower().strip(" .?!") in FRAGMENT_FLASHCARD_TERMS
        )
        if sentence_like_units and fragment_sentence_count == len(sentence_like_units):
            return False
        return True

    def _value_at_risk_flashcards(
        self,
        section: SourceSection,
        concept: StudyConceptCard,
        source_page: int | None,
    ) -> list[StudyFlashcard]:
        excerpt = re.sub(r"\s+", " ", concept.source_excerpt).strip()
        lowered = excerpt.lower()
        if "value at risk" not in lowered and not re.search(r"\bVaR\b", excerpt):
            return []

        cards = [
            self._build_flashcard(
                section,
                concept,
                suffix="var-definition",
                front="What is value at risk (VaR)?",
                back=(
                    "VaR estimates the loss amount that may be exceeded with a specified "
                    "probability over a defined time horizon."
                ),
                card_type="definition",
                source_page=source_page,
            )
        ]

        interpretation_match = re.search(
            r"(?P<horizon>one[- ]day|[\w -]+day)?\s*VaR\s+of\s+(?P<amount>\$?[0-9][0-9.,]*(?:\s*million|\s*billion)?)"
            r".{0,80}?(?P<confidence>[0-9]{2})%\s+confidence",
            excerpt,
            re.IGNORECASE,
        )
        if interpretation_match:
            horizon = (interpretation_match.group("horizon") or "one-day").strip()
            horizon = re.sub(r"^(?:a|an|the)\s+", "", horizon, flags=re.IGNORECASE)
            horizon = horizon.replace(" ", "-").strip("-").lower()
            amount = re.sub(r"\s+", " ", interpretation_match.group("amount")).strip()
            confidence = int(interpretation_match.group("confidence"))
            tail_probability = max(0, 100 - confidence)
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="var-interpretation",
                    front=(
                        f"How do you interpret a {horizon} VaR of {amount} "
                        f"at the {confidence}% confidence level?"
                    ),
                    back=f"There is a {tail_probability}% chance the {horizon} loss will exceed {amount}.",
                    card_type="interpretation",
                    source_page=source_page,
                )
            )

        if re.search(r"does not show loss severity|beyond the threshold|depends on .*assumptions|liquidity", lowered):
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="var-limitations",
                    front="What are the main limitations of value at risk (VaR)?",
                    back=(
                        "VaR does not show loss severity beyond the threshold, depends on assumptions, "
                        "and can be misleading when distributions or liquidity assumptions are weak."
                    ),
                    card_type="exam_trap",
                    source_page=source_page,
                )
            )
        if "expected shortfall" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="var-vs-expected-shortfall",
                    front="How does value at risk (VaR) differ from expected shortfall?",
                    back=(
                        "VaR gives a loss threshold at a confidence level; expected shortfall estimates "
                        "the average loss beyond that threshold."
                    ),
                    card_type="comparison",
                    source_page=source_page,
                )
            )
        return cards

    def _capm_flashcards(
        self,
        section: SourceSection,
        concept: StudyConceptCard,
        source_page: int | None,
    ) -> list[StudyFlashcard]:
        excerpt = re.sub(r"\s+", " ", concept.source_excerpt).strip()
        lowered = excerpt.lower()
        if not re.search(
            r"capital asset pricing model|\bcapm\b|security market line|\bsml\b|market risk premium|\bmrp\b|beta",
            lowered,
        ):
            return []

        cards: list[StudyFlashcard] = []
        if "capital asset pricing model" in lowered or re.search(r"\bcapm\b", lowered):
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="capm-definition",
                    front="What is the capital asset pricing model (CAPM)?",
                    back=(
                        "CAPM links an asset's expected return to beta, because company-specific "
                        "risk is diversified away."
                    ),
                    card_type="definition",
                    source_page=source_page,
                )
            )
        if (
            re.search(r"\be\s*\(\s*r[ia]\s*\)\s*=", lowered)
            or "capm equation" in lowered
            or (
                ("capital asset pricing model" in lowered or re.search(r"\bcapm\b", lowered))
                and ("market risk premium" in lowered or re.search(r"\bmrp\b|\bbeta\b|risk-free", lowered))
            )
        ):
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="capm-formula",
                    front="What is the CAPM expected return formula?",
                    back="E(Ri) = RF + [E(RM) - RF]βi.",
                    card_type="formula",
                    source_page=source_page,
                )
            )
        if ("capital asset pricing model" in lowered or re.search(r"\bcapm\b", lowered)) and "company-specific risk" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="capm-diversification",
                    front="Why does CAPM focus on beta instead of company-specific risk?",
                    back=(
                        "Company-specific risk can be diversified away, so CAPM prices systematic "
                        "market risk measured by beta."
                    ),
                    card_type="interpretation",
                    source_page=source_page,
                )
            )
        if ("capital asset pricing model" in lowered or re.search(r"\bcapm\b", lowered)) and "linear function of beta" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="capm-linear-beta",
                    front="What relationship does CAPM assume between expected return and beta?",
                    back="Expected return is a linear function of beta.",
                    card_type="interpretation",
                    source_page=source_page,
                )
            )
        if "market risk premium" in lowered or re.search(r"\bmrp\b", lowered):
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="market-risk-premium",
                    front="What is the market risk premium (MRP)?",
                    back="MRP is the extra expected return on the market portfolio over the risk-free rate.",
                    card_type="definition",
                    source_page=source_page,
                )
            )
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="market-risk-premium-capm-role",
                    front="How is the market risk premium (MRP) used in CAPM?",
                    back="The market risk premium is multiplied by beta and added to the risk-free rate.",
                    card_type="application",
                    source_page=source_page,
                )
            )
        if "security market line" in lowered or re.search(r"\bsml\b", lowered):
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="sml-depiction",
                    front="What does the security market line (SML) depict?",
                    back="The SML is the graphical depiction of CAPM, relating expected return to beta.",
                    card_type="interpretation",
                    source_page=source_page,
                )
            )
        if "slope" in lowered and ("security market line" in lowered or re.search(r"\bsml\b", lowered)):
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="sml-slope",
                    front="What does the slope of the security market line (SML) represent?",
                    back="The slope of the SML equals the market risk premium (MRP).",
                    card_type="interpretation",
                    source_page=source_page,
                )
            )
        if "beta" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="capm-beta",
                    front="What does beta measure in the capital asset pricing model (CAPM)?",
                    back="Beta measures exposure to systematic market risk; in CAPM, expected return depends on beta.",
                    card_type="interpretation",
                    source_page=source_page,
                )
            )
        if re.search(r"beta of the market (?:is|equals?) (?:equal to )?1", lowered):
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="market-beta",
                    front="What is the beta of the market portfolio in CAPM?",
                    back="The beta of the market portfolio is 1.",
                    card_type="short_answer_recall",
                    source_page=source_page,
                )
            )
        return cards

    def _modern_portfolio_flashcards(
        self,
        section: SourceSection,
        concept: StudyConceptCard,
        source_page: int | None,
    ) -> list[StudyFlashcard]:
        excerpt = re.sub(r"\s+", " ", concept.source_excerpt).strip()
        lowered = excerpt.lower()
        if not re.search(r"modern portfolio theory|\bmpt\b|efficient frontier|diversif", lowered):
            return []

        cards: list[StudyFlashcard] = []
        if "modern portfolio theory" in lowered or re.search(r"\bmpt\b", lowered):
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="mpt-definition",
                    front="What is Modern Portfolio Theory (MPT)?",
                    back=(
                        "MPT studies how investors can build portfolios that balance expected return "
                        "against risk through diversification."
                    ),
                    card_type="definition",
                    source_page=source_page,
                )
            )
        if "efficient frontier" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="efficient-frontier",
                    front="What is the Markowitz efficient frontier?",
                    back=(
                        "The efficient frontier contains portfolios that offer the best expected return "
                        "for a given risk level."
                    ),
                    card_type="definition",
                    source_page=source_page,
                )
            )
        if "maximize return per unit of risk" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="mpt-rational-investor-goal",
                    front="What do rational investors seek to maximize in Modern Portfolio Theory?",
                    back="Rational investors seek to maximize return per unit of risk.",
                    card_type="short_answer_recall",
                    source_page=source_page,
                )
            )
        if "risk-free asset" in lowered and "efficient frontier" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="mpt-no-risk-free-asset",
                    front="Absent a risk-free asset, where do rational investors hold portfolios?",
                    back="They hold portfolios on the efficient frontier.",
                    card_type="application",
                    source_page=source_page,
                )
            )
        if "diversif" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="mpt-diversification",
                    front="How does diversification reduce total portfolio risk?",
                    back="Diversification combines assets so company-specific risks offset each other.",
                    card_type="interpretation",
                    source_page=source_page,
                )
            )
        return cards

    def _code_of_conduct_flashcards(
        self,
        section: SourceSection,
        concept: StudyConceptCard,
        source_page: int | None,
    ) -> list[StudyFlashcard]:
        excerpt = re.sub(r"\s+", " ", concept.source_excerpt).strip()
        lowered = excerpt.lower()
        if "garp code of conduct" not in lowered and "code of conduct" not in lowered:
            return []

        cards: list[StudyFlashcard] = []
        if re.search(r"integrity|competence|diligence|respect|ethical", lowered):
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="garp-code-duties",
                    front="What duties does the GARP Code of Conduct emphasize for members?",
                    back="Members should act with integrity, competence, diligence, respect, and ethical conduct.",
                    card_type="short_answer_recall",
                    source_page=source_page,
                )
            )
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="garp-code-integrity",
                    front="Why is integrity central to the GARP Code of Conduct?",
                    back="Integrity requires members to act ethically and preserve trust in the risk profession.",
                    card_type="application",
                    source_page=source_page,
                )
            )
        if "conflicts of interest" in lowered or "conflict of interest" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="garp-code-conflicts",
                    front="How should a GARP member handle conflicts of interest?",
                    back="The member should disclose conflicts of interest and follow professional standards.",
                    card_type="application",
                    source_page=source_page,
                )
            )
        if "confidentiality" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="garp-code-confidentiality",
                    front="Why is confidentiality important under the GARP Code of Conduct?",
                    back="Members must protect confidential information unless disclosure is legally required.",
                    card_type="application",
                    source_page=source_page,
                )
            )
        if "professional standards" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="garp-code-professional-standards",
                    front="What professional standards should GARP members preserve?",
                    back="Members should comply with professional standards while acting competently and ethically.",
                    card_type="short_answer_recall",
                    source_page=source_page,
                )
            )
        if "violation" in lowered or "consequence" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="garp-code-violations",
                    front="What can happen after a violation of the GARP Code of Conduct?",
                    back="Consequences may include suspension, revocation of membership, or referral to regulators.",
                    card_type="application",
                    source_page=source_page,
                )
            )
        return cards

    def _definition_flashcard_from_concept(
        self,
        section: SourceSection,
        concept: StudyConceptCard,
        source_page: int | None,
    ) -> StudyFlashcard | None:
        first_sentence = self._first_meaningful_sentence(concept.source_excerpt)
        risk_definition = re.search(
            r"\bRisk is uncertainty surrounding outcomes\.?",
            concept.source_excerpt,
            re.IGNORECASE,
        )
        if risk_definition:
            return self._build_flashcard(
                section,
                concept,
                suffix="definition-risk",
                front="What is risk?",
                back="Risk is uncertainty surrounding outcomes.",
                card_type="definition",
                source_page=source_page,
            )
        if first_sentence and re.match(r"^[A-Z][A-Za-z0-9 ()/-]{2,80}\s+is\b", first_sentence):
            subject = first_sentence.split(" is ", 1)[0].strip()
            answer = first_sentence.split(" is ", 1)[1].strip().rstrip(".")
            if 2 <= len(subject.split()) <= 7 and not self._is_bad_sentence_definition(subject, answer):
                return self._build_flashcard(
                    section,
                    concept,
                    suffix="definition",
                    front=f"What is {subject[0].lower() + subject[1:]}?",
                    back=first_sentence,
                    card_type="definition",
                    source_page=source_page,
                )
        return None

    def _list_recall_flashcard_from_concept(
        self,
        section: SourceSection,
        concept: StudyConceptCard,
        source_page: int | None,
    ) -> StudyFlashcard | None:
        lines = [line.strip() for line in concept.source_excerpt.splitlines() if line.strip()]
        numbered_items: list[str] = []
        for line in lines:
            match = re.match(r"^(?P<number>\d+)\.\s+(?P<item>.+)$", line)
            if match:
                item = match.group("item").strip().rstrip(".")
                numbered_items.append(f"{match.group('number')}. {item}.")
        if len(numbered_items) >= 3 and re.search(
            r"four components of the risk management process|components of the risk management process",
            concept.source_excerpt,
            re.IGNORECASE,
        ):
            return self._build_flashcard(
                section,
                concept,
                suffix="risk-management-components",
                front="What are the four components of the risk management process?",
                back="\n".join(numbered_items[:4]),
                card_type="list_recall",
                source_page=source_page,
            )
        return None

    def _comparison_flashcard_from_concept(
        self,
        section: SourceSection,
        concept: StudyConceptCard,
        source_page: int | None,
    ) -> StudyFlashcard | None:
        excerpt = concept.source_excerpt
        if re.search(r"risk management.*risk taking|risk taking.*risk management", excerpt, re.IGNORECASE | re.DOTALL):
            return self._build_flashcard(
                section,
                concept,
                suffix="risk-management-vs-taking",
                front="What is the difference between risk management and risk taking?",
                back=(
                    "Risk management is a process designed to reduce or eliminate potential loss; "
                    "risk taking is the active acceptance of incremental risk in pursuit of incremental gains."
                ),
                card_type="comparison",
                source_page=source_page,
            )
        return None

    def _exam_trap_flashcard_from_concept(
        self,
        section: SourceSection,
        concept: StudyConceptCard,
        source_page: int | None,
    ) -> StudyFlashcard | None:
        trap = next((item for item in concept.common_traps if item), "")
        if not trap:
            return None
        front = self._exam_trap_prompt(concept, trap)
        if not front:
            return None
        return self._build_flashcard(
            section,
            concept,
            suffix="exam-trap",
            front=front,
            back=trap,
            card_type="exam_trap",
            source_page=source_page,
        )

    def _exam_trap_prompt(self, concept: StudyConceptCard, trap: str) -> str | None:
        combined = " ".join(
            [concept.title, concept.learning_outcome or "", concept.source_excerpt, trap]
        ).lower()
        if "expected loss" in combined or "expected losses" in combined:
            return "What is a common mistake when interpreting expected loss?"
        if "economic capital" in combined:
            return "What should you not confuse with economic capital?"
        if "tail risk" in combined:
            return "Why is tail risk important in risk management?"
        if "risk and reward" in combined or "trade-off between risk and reward" in combined:
            return "What is a common exam trap about risk and reward?"
        if "conflict" in combined and "shareholder" in combined:
            return "Why can corporate insider goals conflict with shareholder goals?"
        if "risk management" in combined and "eliminat" in combined:
            return "What is a common mistake about what risk management can eliminate?"
        return None

    def _risk_management_process_flashcards(
        self,
        section: SourceSection,
        concept: StudyConceptCard,
        source_page: int | None,
    ) -> list[StudyFlashcard]:
        excerpt = concept.source_excerpt
        if not re.search(r"\brisk management process\b", excerpt, re.IGNORECASE):
            return []

        cards: list[StudyFlashcard] = []
        if re.search(r"reduce or eliminate (?:the potential to incur )?loss", excerpt, re.IGNORECASE):
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="risk-management-reduce-loss",
                    front="What does a risk management process try to reduce or eliminate?",
                    back="The potential to incur loss.",
                    card_type="short_answer_recall",
                    source_page=source_page,
                )
            )
        if re.search(
            r"risk taking (?:refers to the active acceptance|accepts incremental risk)",
            excerpt,
            re.IGNORECASE,
        ):
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="risk-taking-involves",
                    front="What does risk taking involve?",
                    back="Active acceptance of incremental risk in pursuit of incremental gains.",
                    card_type="definition",
                    source_page=source_page,
                )
            )
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="risk-taking-gains",
                    front="What kind of gains motivate risk taking?",
                    back="Incremental gains.",
                    card_type="short_answer_recall",
                    source_page=source_page,
                )
            )
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="risk-taking-accepts",
                    front="What type of risk does risk taking accept?",
                    back="Incremental risk.",
                    card_type="short_answer_recall",
                    source_page=source_page,
                )
            )
        if re.search(r"perceived reward justifies the expected risks", excerpt, re.IGNORECASE):
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="risk-process-reward",
                    front="What does the risk management process help determine?",
                    back="Whether perceived reward justifies expected risks.",
                    card_type="application",
                    source_page=source_page,
                )
            )

        process_steps = self._numbered_items_from_excerpt(excerpt)
        if len(process_steps) >= 4:
            step_prompts = [
                ("risk-process-first-step", "Which step comes first in the risk management process?", process_steps[0]),
                (
                    "risk-process-second-step",
                    "Which step follows identifying risks in the risk management process?",
                    process_steps[1],
                ),
                (
                    "risk-process-impact-step",
                    "Which component evaluates the impact from risk events?",
                    process_steps[2],
                ),
                ("risk-process-final-step", "What is the final component of the risk management process?", process_steps[3]),
            ]
            for suffix, front, back in step_prompts:
                cards.append(
                    self._build_flashcard(
                        section,
                        concept,
                        suffix=suffix,
                        front=front,
                        back=back,
                        card_type="short_answer_recall",
                        source_page=source_page,
                    )
                )
        return cards

    def _time_series_flashcards(
        self,
        section: SourceSection,
        concept: StudyConceptCard,
        source_page: int | None,
    ) -> list[StudyFlashcard]:
        excerpt = re.sub(r"\s+", " ", concept.source_excerpt).strip()
        lowered = excerpt.lower()
        cards: list[StudyFlashcard] = []

        if "time series" in lowered and re.search(r"data collected over regular time periods", lowered):
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="time-series-definition",
                    front="What is a time series?",
                    back="Data collected over regular time periods.",
                    card_type="definition",
                    source_page=source_page,
                )
            )
        if "covariance stationary" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="covariance-stationary-conditions",
                    front="What conditions define a covariance stationary time series?",
                    back=(
                        "Its mean and variance are constant over time, and autocovariances depend "
                        "only on lag, not on the point in time."
                    ),
                    card_type="list_recall",
                    source_page=source_page,
                )
            )
        if "serially uncorrelated" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="serially-uncorrelated-condition",
                    front="What condition defines a serially uncorrelated time series?",
                    back="Its lagged values have zero correlation with each other.",
                    card_type="definition",
                    source_page=source_page,
                )
            )
        if "white noise" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="white-noise-definition",
                    front="What is white noise?",
                    back="A serially uncorrelated time series with mean zero and constant variance.",
                    card_type="definition",
                    source_page=source_page,
                )
            )
        if "independent white noise" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="independent-white-noise-definition",
                    front="What is independent white noise?",
                    back="White noise whose observations are independent as well as uncorrelated.",
                    card_type="definition",
                    source_page=source_page,
                )
            )
        if "normal white noise" in lowered and "independent white noise" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="normal-vs-independent-white-noise",
                    front="What is the relationship between normal white noise and independent white noise?",
                    back=(
                        "All normal white noise processes are independent white noise, but not all "
                        "independent white noise processes are normally distributed."
                    ),
                    card_type="comparison",
                    source_page=source_page,
                )
            )
        if "normal" in lowered and "white noise" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="normal-white-noise-definition",
                    front="What is normal white noise?",
                    back="White noise whose observations follow a normal distribution.",
                    card_type="definition",
                    source_page=source_page,
                )
            )
        if "autocovariance" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="autocovariance-function",
                    front="What does the autocovariance function measure?",
                    back="It measures covariance between a time series and its lagged values.",
                    card_type="definition",
                    source_page=source_page,
                )
            )
        if "autocorrelation" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="autocorrelation-function",
                    front="What does the autocorrelation function measure?",
                    back="It measures correlation between a time series and its lagged values.",
                    card_type="definition",
                    source_page=source_page,
                )
            )
        return cards

    def _population_moments_flashcards(
        self,
        section: SourceSection,
        concept: StudyConceptCard,
        source_page: int | None,
    ) -> list[StudyFlashcard]:
        excerpt = re.sub(r"\s+", " ", concept.source_excerpt).strip()
        lowered = excerpt.lower()
        if "population moments" not in lowered and not all(
            term in lowered for term in ("mean", "variance", "skewness", "kurtosis")
        ):
            return []

        prompts = [
            (
                "population-moments-list",
                "What are the four common population moments?",
                "1. Mean\n2. Variance\n3. Skewness\n4. Kurtosis",
                "list_recall",
            ),
            (
                "population-moment-mean",
                "What is the mean of a random variable?",
                "The mean measures expected value, E(X), or the distribution's central location.",
                "definition",
            ),
            (
                "population-moment-first",
                "Which population moment is the first moment?",
                "The first moment is the mean, or expected value.",
                "short_answer_recall",
            ),
            (
                "population-moment-variance",
                "What does variance measure?",
                "Variance measures dispersion around the mean.",
                "definition",
            ),
            (
                "population-moment-second-central",
                "Which population moment is the second central moment?",
                "The second central moment is variance.",
                "short_answer_recall",
            ),
            (
                "population-moment-skewness",
                "What does skewness measure?",
                "Skewness measures distribution asymmetry.",
                "definition",
            ),
            (
                "population-moment-kurtosis",
                "What does kurtosis measure?",
                "Kurtosis measures the proportion of outcomes in the tails, or tail thickness.",
                "definition",
            ),
            (
                "population-moments-skewness-vs-kurtosis",
                "How does skewness differ from kurtosis?",
                "Skewness describes asymmetry; kurtosis describes tail thickness.",
                "comparison",
            ),
            (
                "population-moments-time-series-use",
                "Why are population moments useful in time series analysis?",
                "They summarize location, dispersion, asymmetry, and tail behavior.",
                "application",
            ),
            (
                "population-moments-kurtosis-trap",
                "Why should kurtosis not be interpreted as the average level of a variable?",
                "Kurtosis concerns tail thickness, not the average level of the variable.",
                "exam_trap",
            ),
        ]
        return [
            self._build_flashcard(
                section,
                concept,
                suffix=suffix,
                front=front,
                back=back,
                card_type=card_type,
                source_page=source_page,
            )
            for suffix, front, back, card_type in prompts
        ]

    def _compounding_flashcards(
        self,
        section: SourceSection,
        concept: StudyConceptCard,
        source_page: int | None,
    ) -> list[StudyFlashcard]:
        excerpt = re.sub(r"\s+", " ", concept.source_excerpt).strip()
        lowered = excerpt.lower()
        if "compounding frequency" not in lowered and "continuous compounding" not in lowered:
            return []

        prompts = [
            (
                "compounding-frequency-definition",
                "What is compounding frequency?",
                "Compounding frequency describes how often interest is credited or charged.",
                "definition",
            ),
            (
                "compounding-frequency-future-value",
                "How does compounding frequency affect future value?",
                "Increasing compounding frequency increases future value for the same stated rate.",
                "interpretation",
            ),
            (
                "compounding-frequency-present-value",
                "How does compounding frequency affect present value?",
                "Increasing compounding frequency decreases the present value of a future cash flow.",
                "interpretation",
            ),
            (
                "compounding-frequency-common-types",
                "Which compounding frequencies commonly appear in bond valuation?",
                "Annual, semiannual, quarterly, monthly, and continuous compounding.",
                "list_recall",
            ),
            (
                "annual-compounding-definition",
                "What is annual compounding?",
                "Annual compounding credits or charges interest once per year.",
                "definition",
            ),
            (
                "semiannual-compounding-definition",
                "What is semiannual compounding?",
                "Semiannual compounding credits or charges interest twice per year.",
                "definition",
            ),
            (
                "quarterly-compounding-definition",
                "What is quarterly compounding?",
                "Quarterly compounding credits or charges interest four times per year.",
                "definition",
            ),
            (
                "monthly-compounding-definition",
                "What is monthly compounding?",
                "Monthly compounding credits or charges interest twelve times per year.",
                "definition",
            ),
            (
                "continuous-compounding-definition",
                "What is continuous compounding?",
                "Continuous compounding compounds interest at every instant.",
                "definition",
            ),
            (
                "compounding-frequency-matching-trap",
                "Why must discount rates and cash flow timing match the compounding frequency?",
                "Using inconsistent timing can misstate present value or future value.",
                "exam_trap",
            ),
            (
                "compounding-frequency-exam-trap",
                "What is a common exam trap about compounding frequency?",
                "Do not compare rates or cash flows unless their compounding frequencies are consistent.",
                "exam_trap",
            ),
        ]
        return [
            self._build_flashcard(
                section,
                concept,
                suffix=suffix,
                front=front,
                back=back,
                card_type=card_type,
                source_page=source_page,
            )
            for suffix, front, back, card_type in prompts
        ]

    def _mutual_fund_flashcards(
        self,
        section: SourceSection,
        concept: StudyConceptCard,
        source_page: int | None,
    ) -> list[StudyFlashcard]:
        excerpt = re.sub(r"\s+", " ", concept.source_excerpt).strip()
        lowered = excerpt.lower()
        if not re.search(r"\b(?:mutual funds?|etfs?|exchange-traded funds?|late trading|market timing)\b", lowered):
            return []

        cards: list[StudyFlashcard] = []
        if "mutual fund" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="mutual-fund-definition",
                    front="What are mutual funds?",
                    back="Mutual funds are pooled investment vehicles that invest shareholder money in diversified portfolios.",
                    card_type="definition",
                    source_page=source_page,
                )
            )
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="mutual-fund-diversification",
                    front="Why do mutual funds provide diversification?",
                    back="They pool investor capital and invest it across a diversified portfolio.",
                    card_type="interpretation",
                    source_page=source_page,
                )
            )
        if "late trading" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="late-trading-definition",
                    front="What is late trading in mutual funds?",
                    back="Late trading occurs when orders placed after market close receive the same-day NAV.",
                    card_type="definition",
                    source_page=source_page,
                )
            )
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="late-trading-exam-concern",
                    front="What is the main exam concern with late trading?",
                    back="Late orders can receive a stale same-day NAV, creating an unfair trading advantage.",
                    card_type="exam_trap",
                    source_page=source_page,
                )
            )
        if "market timing" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="market-timing-definition",
                    front="What is market timing in mutual funds?",
                    back="Market timing is trading designed to exploit stale or delayed fund asset prices.",
                    card_type="definition",
                    source_page=source_page,
                )
            )
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="stale-prices-market-timing",
                    front="Why can stale prices create market timing opportunities?",
                    back="Some fund assets may not immediately reflect current market values, allowing traders to exploit stale NAVs.",
                    card_type="application",
                    source_page=source_page,
                )
            )
        if "late trading" in lowered and "market timing" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="mutual-fund-trading-abuses",
                    front="What undesirable trading behaviors can affect mutual funds?",
                    back="Late trading and market timing.",
                    card_type="list_recall",
                    source_page=source_page,
                )
            )
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="late-trading-vs-market-timing",
                    front="How does late trading differ from market timing?",
                    back="Late trading uses after-close orders at same-day NAV; market timing exploits stale fund asset prices.",
                    card_type="comparison",
                    source_page=source_page,
                )
            )
        if "etf" in lowered or "exchange-traded fund" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="etf-vs-mutual-fund",
                    front="How do ETFs differ from traditional mutual funds?",
                    back="ETFs trade on exchanges and typically have lower fees than traditional mutual funds.",
                    card_type="comparison",
                    source_page=source_page,
                )
            )
        if "nav" in lowered or "net asset value" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="mutual-fund-nav",
                    front="What does NAV represent for a mutual fund?",
                    back="NAV is the per-share value of the fund's assets minus liabilities.",
                    card_type="definition",
                    source_page=source_page,
                )
            )
        return cards

    def _option_type_flashcards(
        self,
        section: SourceSection,
        concept: StudyConceptCard,
        source_page: int | None,
    ) -> list[StudyFlashcard]:
        excerpt = re.sub(r"\s+", " ", concept.source_excerpt).strip()
        lowered = excerpt.lower()
        if not (
            "option" in lowered
            and re.search(r"\b(?:call|put|american|european|buyer|seller|right|obligation|payoff|exercise)\b", lowered)
        ):
            return []

        cards: list[StudyFlashcard] = []
        if "option buyer" in lowered or ("right" in lowered and "option" in lowered):
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="option-buyer-right",
                    front="What right does an option buyer have?",
                    back="The option buyer has the right, but not the obligation, to exercise the option.",
                    card_type="definition",
                    source_page=source_page,
                )
            )
        if "option seller" in lowered or "option writer" in lowered or "obligation" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="option-seller-obligation",
                    front="What obligation does an option seller have?",
                    back="The option seller must perform if the option buyer exercises the option.",
                    card_type="definition",
                    source_page=source_page,
                )
            )
        if "call option" in lowered or "call" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="call-option-definition",
                    front="What is a call option?",
                    back="A call option gives the buyer the right to buy the underlying asset.",
                    card_type="definition",
                    source_page=source_page,
                )
            )
        if "put option" in lowered or "put" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="put-option-definition",
                    front="What is a put option?",
                    back="A put option gives the buyer the right to sell the underlying asset.",
                    card_type="definition",
                    source_page=source_page,
                )
            )
        if "american" in lowered and "european" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="american-vs-european-options",
                    front="How do American and European options differ?",
                    back="American options can be exercised any time before expiration; European options can be exercised only at expiration.",
                    card_type="comparison",
                    source_page=source_page,
                )
            )
        if "asymmetric" in lowered or "payoff" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="option-asymmetric-payoff",
                    front="Why are option payoffs asymmetric?",
                    back="The buyer's loss is limited to the premium, while the payoff can increase when the option moves in the money.",
                    card_type="interpretation",
                    source_page=source_page,
                )
            )
        if "in the money" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="option-in-the-money",
                    front="What does it mean for an option to be in the money?",
                    back="The option has positive exercise value.",
                    card_type="definition",
                    source_page=source_page,
                )
            )
        return cards

    def _option_pricing_factor_flashcards(
        self,
        section: SourceSection,
        concept: StudyConceptCard,
        source_page: int | None,
    ) -> list[StudyFlashcard]:
        excerpt = re.sub(r"\s+", " ", concept.source_excerpt).strip()
        lowered = excerpt.lower()
        context = " ".join([section.section_title, concept.title, excerpt]).lower()
        option_factor_context = any(
            phrase in context
            for phrase in (
                "option pricing factor",
                "factors influence the value of an option",
                "six factors influence the value of an option",
                "value of an option",
                "option value",
            )
        )
        if not (
            option_factor_context
            and "option" in lowered
            and re.search(r"\b(?:strike price|time to expiration|volatility|risk-free rate|dividends|six factors)\b", lowered)
        ):
            return []

        cards: list[StudyFlashcard] = [
            self._build_flashcard(
                section,
                concept,
                suffix="option-pricing-six-factors",
                front="What six factors influence the value of an option?",
                back="\n".join(
                    [
                        "1. Underlying asset value.",
                        "2. Strike price.",
                        "3. Time to expiration.",
                        "4. Volatility.",
                        "5. Risk-free rate.",
                        "6. Dividends.",
                    ]
                ),
                card_type="list_recall",
                source_page=source_page,
            )
        ]
        if "stock price" in lowered or "underlying" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="underlying-price-call-put-effect",
                    front="How does an increase in the underlying stock price affect call and put option values?",
                    back="It increases call option value and decreases put option value.",
                    card_type="interpretation",
                    source_page=source_page,
                )
            )
        if "strike price" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="strike-price-call-put-effect",
                    front="How does the strike price affect call and put option values?",
                    back="A higher strike price lowers call value and raises put value.",
                    card_type="interpretation",
                    source_page=source_page,
                )
            )
        if "time to expiration" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="time-to-expiration-option-value",
                    front="How does time to expiration affect an option's value?",
                    back="More time to expiration generally increases option value because there is more time for favorable price moves.",
                    card_type="interpretation",
                    source_page=source_page,
                )
            )
        if "volatility" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="volatility-option-value",
                    front="How does higher volatility affect option values?",
                    back="Higher volatility generally increases the value of both calls and puts.",
                    card_type="interpretation",
                    source_page=source_page,
                )
            )
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="volatility-pricing-factor",
                    front="Which option pricing factor captures uncertainty in the underlying asset price?",
                    back="Volatility.",
                    card_type="short_answer_recall",
                    source_page=source_page,
                )
            )
        if "risk-free rate" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="risk-free-rate-option-value",
                    front="How does the risk-free rate generally affect option values?",
                    back="A higher risk-free rate generally increases call value and decreases put value.",
                    card_type="interpretation",
                    source_page=source_page,
                )
            )
        if "dividend" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="dividends-option-value",
                    front="How do dividends affect call and put option values?",
                    back="Expected dividends generally decrease call value and increase put value.",
                    card_type="interpretation",
                    source_page=source_page,
                )
            )
        return cards

    def _interest_rate_swap_flashcards(
        self,
        section: SourceSection,
        concept: StudyConceptCard,
        source_page: int | None,
    ) -> list[StudyFlashcard]:
        excerpt = re.sub(r"\s+", " ", concept.source_excerpt).strip()
        lowered = excerpt.lower()
        if not ("interest rate swap" in lowered or ("plain vanilla" in lowered and "swap" in lowered)):
            return []

        cards: list[StudyFlashcard] = []
        cards.append(
            self._build_flashcard(
                section,
                concept,
                suffix="plain-vanilla-interest-rate-swap",
                front="What is a plain vanilla interest rate swap?",
                back="An agreement in which one party pays a fixed rate and receives a floating rate on a notional principal amount.",
                card_type="definition",
                source_page=source_page,
            )
        )
        if "net payment" in lowered or "exchange only" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="interest-rate-swap-net-payment",
                    front="What payment is exchanged in an interest rate swap?",
                    back="Only the net difference between the fixed-rate and floating-rate payments is exchanged.",
                    card_type="short_answer_recall",
                    source_page=source_page,
                )
            )
        if "notional principal" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="interest-rate-swap-notional",
                    front="Why is notional principal not exchanged in a plain vanilla interest rate swap?",
                    back="The notional principal is only a reference amount used to calculate payments.",
                    card_type="exam_trap",
                    source_page=source_page,
                )
            )
        if "fixed rate" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="fixed-rate-payer",
                    front="What does the fixed-rate payer pay in a plain vanilla interest rate swap?",
                    back="The fixed-rate payer pays a fixed rate on the notional principal.",
                    card_type="short_answer_recall",
                    source_page=source_page,
                )
            )
        if "floating rate" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="floating-rate-payer",
                    front="What does the floating-rate payer pay in a plain vanilla interest rate swap?",
                    back="The floating-rate payer pays a floating rate on the notional principal.",
                    card_type="short_answer_recall",
                    source_page=source_page,
                )
            )
        if "sofr" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="swap-floating-benchmark",
                    front="What benchmark can the floating leg of an interest rate swap reference?",
                    back="The floating leg can reference SOFR.",
                    card_type="short_answer_recall",
                    source_page=source_page,
                )
            )
        if "liabilities" in lowered or "transform" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="swap-transforms-liability",
                    front="How can an interest rate swap transform a liability?",
                    back="It can convert floating-rate exposure into fixed-rate exposure, or the reverse.",
                    card_type="application",
                    source_page=source_page,
                )
            )
        if "dealer" in lowered or "intermediaries" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="swap-dealer-role",
                    front="What role does a swap dealer play?",
                    back="A swap dealer acts as an intermediary between swap counterparties.",
                    card_type="definition",
                    source_page=source_page,
                )
            )
        if "isda" in lowered or "master agreement" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="isda-master-agreement",
                    front="What document is commonly used to govern OTC swap agreements?",
                    back="The ISDA master agreement.",
                    card_type="short_answer_recall",
                    source_page=source_page,
                )
            )
        if "comparative advantage" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="swap-comparative-advantage",
                    front="Why can comparative advantage motivate an interest rate swap?",
                    back="Each party may have a borrowing advantage in a different market, so the swap can improve their desired exposures.",
                    card_type="application",
                    source_page=source_page,
                )
            )
        return cards

    def _ccp_risk_flashcards(
        self,
        section: SourceSection,
        concept: StudyConceptCard,
        source_page: int | None,
    ) -> list[StudyFlashcard]:
        excerpt = re.sub(r"\s+", " ", concept.source_excerpt).strip()
        lowered = excerpt.lower()
        if not (
            "central counterparty" in lowered
            or re.search(r"\bccp\b", lowered)
            or ("clearing member" in lowered and "default" in lowered)
        ):
            return []

        cards: list[StudyFlashcard] = [
            self._build_flashcard(
                section,
                concept,
                suffix="ccp-definition",
                front="What is a central counterparty (CCP)?",
                back="A CCP interposes itself between buyers and sellers and becomes the counterparty to both sides of a trade.",
                card_type="definition",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="ccp-risk-list",
                front="What risks can a central counterparty (CCP) face?",
                back="\n".join(
                    [
                        "1. Clearing member default risk.",
                        "2. Liquidity risk.",
                        "3. Model risk.",
                        "4. Legal risk.",
                        "5. Investment risk.",
                        "6. Correlated default risk.",
                    ]
                ),
                card_type="list_recall",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="ccp-default-fund",
                front="What role does a CCP default fund play?",
                back="It helps absorb losses from a clearing member default.",
                card_type="short_answer_recall",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="clearing-member-default-risk",
                front="What is clearing member default risk for a CCP?",
                back="The risk that a clearing member fails to meet its obligations to the CCP.",
                card_type="definition",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="ccp-default-correlation",
                front="Why does default correlation matter for a CCP?",
                back="Correlated member defaults can create losses larger than a CCP's safeguards were designed to absorb.",
                card_type="exam_trap",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="ccp-liquidity-risk",
                front="What is liquidity risk for a central counterparty?",
                back="The risk that the CCP cannot meet cash or collateral needs on time during stressed conditions.",
                card_type="definition",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="ccp-model-risk",
                front="What is model risk for a central counterparty?",
                back="The risk that margin or risk models underestimate the exposure created by cleared positions.",
                card_type="definition",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="ccp-legal-risk",
                front="What is legal risk for a central counterparty?",
                back="The risk that legal rules, contracts, or enforcement issues weaken the CCP's protections.",
                card_type="definition",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="ccp-investment-risk",
                front="What is investment risk for a central counterparty?",
                back="The risk of loss on collateral, default fund resources, or other assets invested by the CCP.",
                card_type="definition",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="ccp-nonmember-exposure",
                front="How can non-members reduce exposure to CCP default losses?",
                back="They can clear through clearing members instead of facing the CCP directly.",
                card_type="application",
                source_page=source_page,
            ),
        ]
        return cards

    def _futures_characteristics_flashcards(
        self,
        section: SourceSection,
        concept: StudyConceptCard,
        source_page: int | None,
    ) -> list[StudyFlashcard]:
        excerpt = re.sub(r"\s+", " ", concept.source_excerpt).strip()
        lowered = excerpt.lower()
        if not (
            "futures contract" in lowered
            and ("long futures" in lowered or "short futures" in lowered or "spot price" in lowered or "open interest" in lowered)
        ):
            return []

        cards: list[StudyFlashcard] = [
            self._build_flashcard(
                section,
                concept,
                suffix="futures-contract-definition",
                front="What is a futures contract?",
                back="A standardized exchange-traded contract for future delivery or settlement of an underlying asset.",
                card_type="definition",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="long-futures-position",
                front="What is a long futures position?",
                back="The position that agrees to buy the underlying asset at the futures price.",
                card_type="definition",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="short-futures-position",
                front="What is a short futures position?",
                back="The position that agrees to sell or deliver the underlying asset at the futures price.",
                card_type="definition",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="spot-price-definition",
                front="What is the spot price?",
                back="The current cash market price of the underlying asset.",
                card_type="definition",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="futures-price-definition",
                front="What is the futures price?",
                back="The price agreed to today for delivery or settlement at a future date.",
                card_type="definition",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="futures-basis-definition",
                front="What is basis in futures markets?",
                back="Basis is the spot price minus the futures price.",
                card_type="definition",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="basis-convergence",
                front="What usually happens to basis as a futures contract approaches maturity?",
                back="Basis tends to converge toward zero as spot and futures prices come together.",
                card_type="interpretation",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="open-interest-definition",
                front="What does open interest measure?",
                back="Open interest measures the number of outstanding futures contracts.",
                card_type="definition",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="delivery-in-futures",
                front="What does delivery mean in a futures contract?",
                back="Delivery is the transfer of the underlying asset by the short position to settle the contract.",
                card_type="definition",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="futures-closeout",
                front="Why are many futures positions closed out before settlement?",
                back="Traders often offset positions before maturity to avoid delivery and realize gains or losses.",
                card_type="application",
                source_page=source_page,
            ),
        ]
        return cards

    def _commodity_flashcards(
        self,
        section: SourceSection,
        concept: StudyConceptCard,
        source_page: int | None,
    ) -> list[StudyFlashcard]:
        excerpt = re.sub(r"\s+", " ", concept.source_excerpt).strip()
        lowered = excerpt.lower()
        if not (
            "commodity" in lowered
            and (
                "storage" in lowered
                or "convenience yield" in lowered
                or "lease rate" in lowered
                or "carry market" in lowered
                or "electricity" in lowered
            )
        ):
            return []

        cards: list[StudyFlashcard] = [
            self._build_flashcard(
                section,
                concept,
                suffix="commodity-vs-financial-futures",
                front="How do commodity futures differ from financial futures?",
                back="Commodity futures can involve physical storage, transport, lease rates, shorting costs, and convenience yield.",
                card_type="comparison",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="commodity-storage-costs",
                front="Why do storage costs matter in commodity futures pricing?",
                back="Storage costs are carrying costs that can raise the futures price relative to the spot price.",
                card_type="interpretation",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="commodity-transport-costs",
                front="Why can transportation costs affect commodity prices?",
                back="Moving physical commodities between locations can change the delivered cost and market price.",
                card_type="application",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="commodity-shorting-costs",
                front="What are shorting costs in commodity markets?",
                back="Shorting costs are costs or constraints associated with borrowing or delivering the physical commodity.",
                card_type="definition",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="commodity-lease-rate",
                front="What is a lease rate for a commodity?",
                back="A lease rate is the return earned from lending or leasing a commodity.",
                card_type="definition",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="commodity-convenience-yield",
                front="What is convenience yield in commodity markets?",
                back="Convenience yield is the noncash benefit of holding the physical commodity.",
                card_type="definition",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="commodity-carry-market",
                front="What is a carry market in commodities?",
                back="A carry market exists when futures prices exceed spot prices enough to cover carrying costs.",
                card_type="definition",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="agricultural-seasonality",
                front="Why can agricultural commodity prices be seasonal?",
                back="Harvest cycles and seasonal supply patterns can change agricultural commodity prices.",
                card_type="application",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="electricity-storage",
                front="Why can electricity be difficult to store as a commodity?",
                back="Electricity generally cannot be stored economically in large quantities, so supply and demand must balance quickly.",
                card_type="application",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="weather-commodity-risk",
                front="How can weather affect commodity markets?",
                back="Weather can change supply, demand, production, transportation, and therefore commodity prices.",
                card_type="application",
                source_page=source_page,
            ),
        ]
        return cards

    def _day_count_flashcards(
        self,
        section: SourceSection,
        concept: StudyConceptCard,
        source_page: int | None,
    ) -> list[StudyFlashcard]:
        excerpt = re.sub(r"\s+", " ", concept.source_excerpt).strip()
        lowered = excerpt.lower()
        if not (
            "day count" in lowered
            or "actual/actual" in lowered
            or "30/360" in lowered
            or ("clean price" in lowered and "dirty price" in lowered)
        ):
            return []

        cards: list[StudyFlashcard] = [
            self._build_flashcard(
                section,
                concept,
                suffix="day-count-use",
                front="What are day count conventions used for in fixed income?",
                back="They determine how interest accrues between coupon dates.",
                card_type="definition",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="treasury-day-count",
                front="Which day count convention do US Treasury bonds commonly use?",
                back="US Treasury bonds commonly use actual/actual.",
                card_type="short_answer_recall",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="corporate-day-count",
                front="Which day count convention do corporate and municipal bonds commonly use?",
                back="Corporate and municipal bonds commonly use 30/360.",
                card_type="short_answer_recall",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="money-market-day-count",
                front="Which day count convention do many money market instruments use?",
                back="Many money market instruments use actual/360.",
                card_type="short_answer_recall",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="accrued-interest-definition",
                front="What is accrued interest?",
                back="Accrued interest is interest earned since the last coupon date but not yet paid.",
                card_type="definition",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="clean-price-definition",
                front="What is a clean bond price?",
                back="The clean price excludes accrued interest.",
                card_type="definition",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="dirty-price-definition",
                front="What is a dirty bond price?",
                back="The dirty price includes accrued interest.",
                card_type="definition",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="dirty-vs-clean-price",
                front="How does dirty price differ from clean price?",
                back="Dirty price equals clean price plus accrued interest.",
                card_type="comparison",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="day-count-pricing-effect",
                front="Why do day count conventions affect bond pricing calculations?",
                back="They determine the accrued-interest amount used in quoted and invoice prices.",
                card_type="application",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="discount-rate-basis",
                front="What is a discount rate basis used for?",
                back="It quotes some short-term debt instruments by discounting face value over a day-count basis.",
                card_type="definition",
                source_page=source_page,
            ),
        ]
        return cards

    def _duration_hedging_flashcards(
        self,
        section: SourceSection,
        concept: StudyConceptCard,
        source_page: int | None,
    ) -> list[StudyFlashcard]:
        excerpt = re.sub(r"\s+", " ", concept.source_excerpt).strip()
        lowered = excerpt.lower()
        if not (
            "duration" in lowered
            and ("hedge" in lowered or "hedging" in lowered)
        ):
            return []

        cards: list[StudyFlashcard] = [
            self._build_flashcard(
                section,
                concept,
                suffix="duration-based-hedge-definition",
                front="What is a duration-based hedge?",
                back="A hedge that uses futures contracts to offset bond price risk measured with duration.",
                card_type="definition",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="duration-hedge-goal",
                front="What is the goal of a duration-based hedge?",
                back="To offset interest rate risk by making the combined exposure less sensitive to yield changes.",
                card_type="short_answer_recall",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="duration-hedge-ratio-inputs",
                front="What inputs are needed for a duration-based hedge ratio?",
                back="Portfolio value and duration, plus futures price and futures duration.",
                card_type="list_recall",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="duration-hedge-futures-direction",
                front="Why is the futures position opposite the original bond exposure in a duration hedge?",
                back="The futures position is used to offset the original exposure's sensitivity to yield changes.",
                card_type="application",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="duration-hedge-large-yield-change",
                front="Why can large yield changes weaken a duration hedge?",
                back="Duration is a local linear approximation, so large yield changes can make the hedge less accurate.",
                card_type="exam_trap",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="duration-hedge-nonparallel-shift",
                front="Why can nonparallel yield curve shifts weaken a duration hedge?",
                back="A duration hedge usually assumes a common yield change, so nonparallel shifts can leave residual risk.",
                card_type="exam_trap",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="duration-hedge-convexity",
                front="Why does convexity matter in duration-based hedging?",
                back="Convexity captures curvature in the price-yield relationship that duration alone misses.",
                card_type="interpretation",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="duration-hedge-combined-duration",
                front="What should the combined portfolio duration be for a fully hedged position?",
                back="It should be close to zero after combining the original position with the futures hedge.",
                card_type="short_answer_recall",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="duration-hedge-limitation",
                front="What is a common limitation of using duration to hedge bond risk?",
                back="Duration hedges can be inaccurate for large rate changes, nonparallel shifts, or securities with different convexity.",
                card_type="exam_trap",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="duration-hedge-futures-contract",
                front="What instrument is commonly used in a duration-based hedge?",
                back="A futures contract is commonly used to offset the bond portfolio's duration exposure.",
                card_type="short_answer_recall",
                source_page=source_page,
            ),
        ]
        return cards

    def _options_market_flashcards(
        self,
        section: SourceSection,
        concept: StudyConceptCard,
        source_page: int | None,
    ) -> list[StudyFlashcard]:
        excerpt = re.sub(r"\s+", " ", concept.source_excerpt).strip()
        lowered = excerpt.lower()
        if not (
            ("option" in lowered or "options" in lowered)
            and re.search(r"\b(?:margin|uncovered call|covered call|options clearing corporation|\bocc\b)\b", lowered)
        ):
            return []

        cards: list[StudyFlashcard] = []
        if "nine months or fewer" in lowered and "cannot be purchased on margin" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="options-short-maturity-margin-rule",
                    front="What margin rule applies to options with maturities of nine months or fewer?",
                    back="Options with maturities of nine months or fewer cannot be purchased on margin.",
                    card_type="short_answer_recall",
                    source_page=source_page,
                )
            )
        if "longer maturities" in lowered and "25%" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="options-long-maturity-borrowing-limit",
                    front="How much can investors borrow for options with longer maturities?",
                    back="They can borrow a maximum of 25% of the option value.",
                    card_type="short_answer_recall",
                    source_page=source_page,
                )
            )
        if "writing options" in lowered and "margin account" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="option-writers-margin-account",
                    front="Why must option writers maintain a margin account?",
                    back="Writing options creates high potential losses and potential default risk.",
                    card_type="application",
                    source_page=source_page,
                )
            )
        if "uncovered call" in lowered or "uncovered calls" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="uncovered-call-definition",
                    front="What is an uncovered call?",
                    back="An uncovered call is written when the writer does not own the underlying asset.",
                    card_type="definition",
                    source_page=source_page,
                )
            )
        if "covered call" in lowered and "uncovered call" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="covered-vs-uncovered-call",
                    front="How does covered call writing differ from uncovered call writing?",
                    back=(
                        "Covered calls are written on stock the seller owns; uncovered calls are "
                        "written without owning the underlying asset."
                    ),
                    card_type="comparison",
                    source_page=source_page,
                )
            )
        if "options clearing corporation" in lowered or re.search(r"\bocc\b", lowered):
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="occ-guarantee",
                    front="What does the Options Clearing Corporation (OCC) guarantee?",
                    back=(
                        "The OCC guarantees that buyers and sellers in exchange-traded options "
                        "honor their obligations."
                    ),
                    card_type="definition",
                    source_page=source_page,
                )
            )
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="occ-records-positions",
                    front="What does the OCC record in the exchange-traded options market?",
                    back="The OCC records all exchange-traded option positions.",
                    card_type="short_answer_recall",
                    source_page=source_page,
                )
            )
        if "exchange-traded options" in lowered and ("otc options" in lowered or "default risk" in lowered):
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="exchange-traded-vs-otc-default-risk",
                    front="Why do exchange-traded options have lower default risk than OTC options?",
                    back=(
                        "Exchange-traded options are guaranteed by the OCC, while OTC options can "
                        "expose counterparties to default risk."
                    ),
                    card_type="comparison",
                    source_page=source_page,
                )
            )
        return cards

    def _treasury_bond_futures_flashcards(
        self,
        section: SourceSection,
        concept: StudyConceptCard,
        source_page: int | None,
    ) -> list[StudyFlashcard]:
        excerpt = re.sub(r"\s+", " ", concept.source_excerpt).strip()
        lowered = excerpt.lower()
        if not ("treasury bond futures" in lowered or ("treasury" in lowered and "futures contract" in lowered)):
            return []

        def has(*terms: str) -> bool:
            return all(term in lowered for term in terms)

        cards: list[StudyFlashcard] = []
        cards.append(
            self._build_flashcard(
                section,
                concept,
                suffix="treasury-bond-futures-contract",
                front="What is a Treasury bond futures contract?",
                back="A futures contract requiring delivery of an eligible Treasury security by the short position.",
                card_type="definition",
                source_page=source_page,
            )
        )
        if has("short position") and ("deliver" in lowered or "eligible" in lowered):
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="treasury-futures-short-delivery",
                    front="What does the short position deliver in a Treasury bond futures contract?",
                    back="An eligible Treasury security that satisfies exchange delivery rules.",
                    card_type="short_answer_recall",
                    source_page=source_page,
                )
            )
        if has("long position") and ("futures price" in lowered or "accrued interest" in lowered):
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="treasury-futures-long-payment",
                    front="What does the long position pay in a Treasury bond futures contract?",
                    back="The futures price plus accrued interest.",
                    card_type="short_answer_recall",
                    source_page=source_page,
                )
            )
        if "delivery options" in lowered or all(term in lowered for term in ["quality", "timing", "wild card"]):
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="treasury-futures-delivery-options",
                    front="What do delivery options include in Treasury bond futures?",
                    back="\n".join(
                        [
                            "1. Quality option.",
                            "2. Timing option.",
                            "3. Wild card option.",
                        ]
                    ),
                    card_type="list_recall",
                    source_page=source_page,
                )
            )
        if "conversion factor" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="treasury-futures-conversion-factor",
                    front="What does the conversion factor adjust in Treasury bond futures?",
                    back="It adjusts quoted prices for differences among deliverable bonds.",
                    card_type="interpretation",
                    source_page=source_page,
                )
            )
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="treasury-futures-conversion-factor-purpose",
                    front="Why are conversion factors used for deliverable Treasury bonds?",
                    back="Deliverable Treasury bonds have different coupons and maturities, so conversion factors standardize delivery pricing.",
                    card_type="interpretation",
                    source_page=source_page,
                )
            )
        if "10-year treasury notes" in lowered or "nearest three months" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="treasury-futures-ten-year-rounding",
                    front="How is maturity rounded for 10-year Treasury notes or longer when calculating conversion factors?",
                    back="Time to maturity is rounded down to the nearest three months.",
                    card_type="short_answer_recall",
                    source_page=source_page,
                )
            )
        if "2-year" in lowered or "5-year treasury notes" in lowered or "nearest month" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="treasury-futures-shorter-note-rounding",
                    front="How is maturity rounded for 2-year or 5-year Treasury notes when calculating conversion factors?",
                    back="Time to maturity is rounded down to the nearest month.",
                    card_type="short_answer_recall",
                    source_page=source_page,
                )
            )
        if "6% annual yield" in lowered or "compounded semiannually" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="treasury-futures-conversion-factor-yield-assumption",
                    front="What yield assumption is used to calculate Treasury futures conversion factors?",
                    back="A 6% annual yield compounded semiannually.",
                    card_type="short_answer_recall",
                    source_page=source_page,
                )
            )
        if "cheapest-to-deliver" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="treasury-futures-cheapest-to-deliver",
                    front="What is the cheapest-to-deliver bond?",
                    back="The deliverable bond selected by the short position to minimize delivery cost.",
                    card_type="definition",
                    source_page=source_page,
                )
            )
        if "quoted bond price" in lowered and "conversion factor" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="treasury-futures-ctd-cost",
                    front="How do you identify the cheapest-to-deliver bond?",
                    back="Choose the deliverable bond that minimizes quoted bond price minus quoted futures price times conversion factor.",
                    card_type="application",
                    source_page=source_page,
                )
            )
        if "yield curve" in lowered and "upward sloping" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="treasury-futures-upward-yield-curve-ctd",
                    front="How does an upward-sloping yield curve affect the cheapest-to-deliver bond?",
                    back="CTD bonds tend to have longer maturities when the yield curve is upward sloping.",
                    card_type="interpretation",
                    source_page=source_page,
                )
            )
        if "yield curve" in lowered and "downward sloping" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="treasury-futures-downward-yield-curve-ctd",
                    front="How does a downward-sloping yield curve affect the cheapest-to-deliver bond?",
                    back="CTD bonds tend to have shorter maturities when the yield curve is downward sloping.",
                    card_type="interpretation",
                    source_page=source_page,
                )
            )
        if "basis" in lowered and "futures price" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="treasury-futures-basis",
                    front="What is basis in Treasury bond futures?",
                    back="The cash bond price minus the futures price adjusted by the conversion factor.",
                    card_type="definition",
                    source_page=source_page,
                )
            )
        if "cash price" in lowered and "accrued interest" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="treasury-futures-cash-price",
                    front="How is the cash price of the CTD bond calculated?",
                    back="Cash price = quoted bond price + accrued interest.",
                    card_type="formula",
                    source_page=source_page,
                )
            )
        if "cash futures price" in lowered and "accrued interest" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="treasury-futures-quoted-futures-price",
                    front="How is quoted futures price at delivery calculated for a Treasury bond futures contract?",
                    back="Quoted futures price = cash futures price - accrued interest.",
                    card_type="formula",
                    source_page=source_page,
                )
            )
        if "theoretical price" in lowered and "conversion factor" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="treasury-futures-theoretical-price",
                    front="What is the theoretical price formula for a T-bond futures contract?",
                    back="Theoretical price = (cash futures price - accrued interest) / conversion factor.",
                    card_type="formula",
                    source_page=source_page,
                )
            )
        if "interest rate risk" in lowered or "hedge" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="treasury-futures-hedged-risk",
                    front="What risk can Treasury bond futures hedge?",
                    back="Interest rate risk.",
                    card_type="short_answer_recall",
                    source_page=source_page,
                )
            )
        if "delivery choices" in lowered or "contract assumptions" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="treasury-futures-delivery-choices",
                    front="Why do delivery choices matter in Treasury bond futures hedges?",
                    back="Delivery choices and contract assumptions can affect hedge performance.",
                    card_type="application",
                    source_page=source_page,
                )
            )
        if "eligible" in lowered or "eligibility" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="treasury-futures-eligibility-rule",
                    front="What eligibility rule matters for a delivered bond in a Treasury bond futures contract?",
                    back="The delivered bond must satisfy exchange eligibility rules.",
                    card_type="short_answer_recall",
                    source_page=source_page,
                )
            )
        return cards

    def _insurance_pension_flashcards(
        self,
        section: SourceSection,
        concept: StudyConceptCard,
        source_page: int | None,
    ) -> list[StudyFlashcard]:
        excerpt = re.sub(r"\s+", " ", concept.source_excerpt).strip()
        lowered = excerpt.lower()
        context = " ".join(
            [
                section.section_title,
                concept.title,
                concept.learning_outcome or "",
                " ".join(concept.key_terms),
            ]
        ).lower()
        strong_domain_terms = (
            "insurance companies",
            "pension plans",
            "policyholders",
            "life insurance",
            "property and casualty insurance",
            "health insurance",
            "retirement obligations",
        )
        weak_excerpt_hit = re.search(r"\b(?:insurance|premium|premiums|coverage|pension|policyholders)\b", lowered)
        strong_excerpt_hit = any(term in lowered for term in strong_domain_terms)
        context_hit = re.search(
            r"\b(?:insurance companies|pension plans|policyholders|life insurance|property and casualty|health insurance)\b",
            context,
        )
        if not weak_excerpt_hit or not (strong_excerpt_hit or context_hit):
            return []

        cards: list[StudyFlashcard] = []
        if "coverage" in lowered and ("premium" in lowered or "premiums" in lowered):
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="insurance-coverage-definition",
                    front="What is insurance coverage?",
                    back="Insurance coverage is protection funded by premiums and paid when covered losses occur.",
                    card_type="definition",
                    source_page=source_page,
                )
            )
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="insurance-premiums-use",
                    front="How do insurance companies use premiums?",
                    back="They collect premiums and make payments when covered losses occur.",
                    card_type="application",
                    source_page=source_page,
                )
            )
        if "diversification" in lowered and "not perfectly correlated" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="insurance-diversification",
                    front="How does diversification reduce total portfolio risk?",
                    back=(
                        "Diversification reduces total portfolio risk when losses are not perfectly "
                        "correlated across policyholders."
                    ),
                    card_type="interpretation",
                    source_page=source_page,
                )
            )
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="insurance-diversification-effective",
                    front="What makes insurance diversification effective?",
                    back="Losses should not be perfectly correlated across policyholders.",
                    card_type="short_answer_recall",
                    source_page=source_page,
                )
            )
        if all(term in lowered for term in ["life insurance", "property and casualty insurance", "health insurance"]):
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="insurance-company-categories",
                    front="What are the three categories of insurance companies?",
                    back="\n".join(
                        [
                            "1. Life insurance.",
                            "2. Property and casualty insurance.",
                            "3. Health insurance.",
                        ]
                    ),
                    card_type="list_recall",
                    source_page=source_page,
                )
            )
        if "pension plans" in lowered and "retirement obligations" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="pension-plan-contributions",
                    front="What do pension plans accumulate contributions for?",
                    back="They accumulate contributions and invest assets to meet future retirement obligations.",
                    card_type="short_answer_recall",
                    source_page=source_page,
                )
            )
        if "policyholders" in lowered and "premiums" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="insurance-risk-pooling",
                    front="How do insurance companies pool risk?",
                    back=(
                        "They collect premiums across policyholders so covered losses do not all "
                        "occur together."
                    ),
                    card_type="application",
                    source_page=source_page,
                )
            )
        if "pension plans" in lowered and ("insurance companies" in lowered or "premiums" in lowered):
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="pensions-vs-insurance",
                    front="How do pension plans differ from insurance companies?",
                    back=(
                        "Pension plans invest contributions for retirement obligations; insurance "
                        "companies collect premiums and pay covered losses."
                    ),
                    card_type="comparison",
                    source_page=source_page,
                )
            )
        return cards

    def _banking_flashcards(
        self,
        section: SourceSection,
        concept: StudyConceptCard,
        source_page: int | None,
    ) -> list[StudyFlashcard]:
        excerpt = re.sub(r"\s+", " ", concept.source_excerpt).strip()
        lowered = excerpt.lower()
        if not (
            "bank" in lowered
            and (
                "regulatory capital" in lowered
                or "economic capital" in lowered
                or "deposit insurance" in lowered
                or "banking book" in lowered
                or "trading book" in lowered
                or "originate-to-distribute" in lowered
            )
        ):
            return []

        cards: list[StudyFlashcard] = []
        if any(term in lowered for term in ["credit risk", "market risk", "liquidity risk", "operational risk", "solvency risk"]):
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="bank-main-risks",
                    front="What are the main risks faced by banks?",
                    back="\n".join(
                        [
                            "1. Credit risk.",
                            "2. Market risk.",
                            "3. Liquidity risk.",
                            "4. Operational risk.",
                            "5. Solvency risk.",
                        ]
                    ),
                    card_type="list_recall",
                    source_page=source_page,
                )
            )
        if "regulatory capital" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="regulatory-capital-definition",
                    front="What is regulatory capital?",
                    back="Regulatory capital is the minimum capital required by regulators.",
                    card_type="definition",
                    source_page=source_page,
                )
            )
        if "economic capital" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="economic-capital-definition",
                    front="What is economic capital?",
                    back="Economic capital is internally estimated capital needed to absorb unexpected losses.",
                    card_type="definition",
                    source_page=source_page,
                )
            )
        if "economic capital" in lowered and "regulatory capital" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="economic-vs-regulatory-capital",
                    front="How does economic capital differ from regulatory capital?",
                    back="Regulatory capital is externally required; economic capital is internally estimated for unexpected losses.",
                    card_type="comparison",
                    source_page=source_page,
                )
            )
        if "deposit insurance" in lowered:
            cards.extend(
                [
                    self._build_flashcard(
                        section,
                        concept,
                        suffix="deposit-insurance-definition",
                        front="What does deposit insurance protect?",
                        back="Deposit insurance protects depositors from losses on insured deposits.",
                        card_type="definition",
                        source_page=source_page,
                    ),
                    self._build_flashcard(
                        section,
                        concept,
                        suffix="deposit-insurance-moral-hazard",
                        front="Why can deposit insurance create moral hazard?",
                        back="Insured depositors may monitor banks less because their deposits are protected.",
                        card_type="exam_trap",
                        source_page=source_page,
                    ),
                ]
            )
        if "banking book" in lowered and "trading book" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="banking-book-vs-trading-book",
                    front="How does the banking book differ from the trading book?",
                    back="The banking book holds loans and deposits to maturity; the trading book holds marked-to-market positions.",
                    card_type="comparison",
                    source_page=source_page,
                )
            )
        if "originate-to-distribute" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="originate-to-distribute-definition",
                    front="What is the originate-to-distribute model?",
                    back="A bank originates loans and then sells or securitizes the exposure.",
                    card_type="definition",
                    source_page=source_page,
                )
            )
        if "unexpected losses" in lowered or "unexpected loss" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="bank-capital-unexpected-losses",
                    front="Why do banks hold capital against unexpected losses?",
                    back="Capital helps absorb losses beyond normal expected losses.",
                    card_type="short_answer_recall",
                    source_page=source_page,
                )
            )
        if "solvency risk" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="bank-solvency-risk",
                    front="What is solvency risk for a bank?",
                    back="Solvency risk is the risk that a bank lacks enough capital to absorb losses.",
                    card_type="definition",
                    source_page=source_page,
                )
            )
        if "securitizes" in lowered or "securitization" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="bank-securitization-transfer",
                    front="How can securitization transfer bank credit exposure?",
                    back="The bank can sell or securitize loans so investors take on the exposure.",
                    card_type="application",
                    source_page=source_page,
                )
            )
        return cards

    def _foreign_exchange_flashcards(
        self,
        section: SourceSection,
        concept: StudyConceptCard,
        source_page: int | None,
    ) -> list[StudyFlashcard]:
        excerpt = re.sub(r"\s+", " ", concept.source_excerpt).strip()
        lowered = excerpt.lower()
        if not (
            ("fx quote" in lowered or "foreign exchange" in lowered)
            and ("base currency" in lowered or "quote currency" in lowered or "bid price" in lowered)
        ):
            return []

        cards: list[StudyFlashcard] = []
        if "base currency" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="fx-base-currency",
                    front="What is the base currency in an FX quote?",
                    back="The base currency is the currency being bought or sold.",
                    card_type="definition",
                    source_page=source_page,
                )
            )
        if "quote currency" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="fx-quote-currency",
                    front="What is the quote currency in an FX quote?",
                    back="The quote currency is the price currency in the exchange-rate quote.",
                    card_type="definition",
                    source_page=source_page,
                )
            )
        if "bid price" in lowered and "ask price" in lowered:
            cards.extend(
                [
                    self._build_flashcard(
                        section,
                        concept,
                        suffix="fx-bid-vs-ask",
                        front="How does the bid price differ from the ask price in an FX quote?",
                        back="The bid is where the dealer buys the base currency; the ask is where the dealer sells it.",
                        card_type="comparison",
                        source_page=source_page,
                    ),
                    self._build_flashcard(
                        section,
                        concept,
                        suffix="fx-bid-ask-spread",
                        front="What do dealers earn from the bid-ask spread in FX markets?",
                        back="Dealers earn the difference between the ask price and the bid price.",
                        card_type="interpretation",
                        source_page=source_page,
                    ),
                    self._build_flashcard(
                        section,
                        concept,
                        suffix="fx-bid-below-ask",
                        front="Why is the FX bid price below the ask price?",
                        back="The spread compensates the dealer for providing liquidity and bearing trading costs.",
                        card_type="exam_trap",
                        source_page=source_page,
                    ),
                ]
            )
        if "spot transaction" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="fx-spot-transaction",
                    front="What is a spot FX transaction?",
                    back="A spot FX transaction exchanges currencies shortly after the trade date.",
                    card_type="definition",
                    source_page=source_page,
                )
            )
        if "outright forward" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="fx-outright-forward",
                    front="What is an outright forward in foreign exchange?",
                    back="An outright forward locks in an exchange rate for future currency delivery.",
                    card_type="definition",
                    source_page=source_page,
                )
            )
        if "fx swap" in lowered and "outright forward" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="fx-swap-vs-forward",
                    front="How does an FX swap differ from an outright forward transaction?",
                    back="An FX swap combines a spot transaction with an offsetting forward; an outright forward is only the future exchange.",
                    card_type="comparison",
                    source_page=source_page,
                )
            )
        if "transaction risk" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="fx-transaction-risk",
                    front="What is transaction risk in foreign exchange?",
                    back="Transaction risk is exposure from exchange-rate changes between agreeing to and settling a transaction.",
                    card_type="definition",
                    source_page=source_page,
                )
            )
        if "translation risk" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="fx-translation-risk",
                    front="What is translation risk in foreign exchange?",
                    back="Translation risk is accounting exposure from converting foreign-currency financial statements.",
                    card_type="definition",
                    source_page=source_page,
                )
            )
        if "economic risk" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="fx-economic-risk",
                    front="What is economic risk in foreign exchange?",
                    back="Economic risk is the effect of exchange-rate changes on future cash flows and firm value.",
                    card_type="definition",
                    source_page=source_page,
                )
            )
        return cards

    def _exchange_rate_parity_flashcards(
        self,
        section: SourceSection,
        concept: StudyConceptCard,
        source_page: int | None,
    ) -> list[StudyFlashcard]:
        excerpt = re.sub(r"\s+", " ", concept.source_excerpt).strip()
        lowered = excerpt.lower()
        if not (
            "purchasing power parity" in lowered
            or "covered interest rate parity" in lowered
            or "uncovered interest rate parity" in lowered
        ):
            return []

        cards: list[StudyFlashcard] = []
        if "purchasing power parity" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="ppp-statement",
                    front="What does purchasing power parity (PPP) state?",
                    back="PPP links exchange rates to relative price levels across countries.",
                    card_type="definition",
                    source_page=source_page,
                )
            )
        if "currency appreciation" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="currency-appreciation",
                    front="What does currency appreciation mean?",
                    back="Currency appreciation means a currency gains value relative to another currency.",
                    card_type="definition",
                    source_page=source_page,
                )
            )
        if "currency" in lowered and "depreciation" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="currency-depreciation",
                    front="What does currency depreciation mean?",
                    back="Currency depreciation means a currency loses value relative to another currency.",
                    card_type="definition",
                    source_page=source_page,
                )
            )
        if "nominal interest" in lowered and "real interest" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="nominal-real-inflation",
                    front="How do nominal interest rates relate to real interest rates and expected inflation?",
                    back="Nominal rates reflect real interest rates plus expected inflation.",
                    card_type="interpretation",
                    source_page=source_page,
                )
            )
        if "covered interest rate parity" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="covered-interest-rate-parity",
                    front="What does covered interest rate parity use forward contracts to do?",
                    back="It uses forward contracts to eliminate exchange-rate risk in the parity relationship.",
                    card_type="definition",
                    source_page=source_page,
                )
            )
        if "covered interest rate parity" in lowered and "uncovered interest rate parity" in lowered:
            cards.extend(
                [
                    self._build_flashcard(
                        section,
                        concept,
                        suffix="covered-vs-uncovered-interest-parity",
                        front="How does covered interest rate parity differ from uncovered interest rate parity?",
                        back="Covered parity uses forward hedging; uncovered parity relies on expected future spot rates without hedging.",
                        card_type="comparison",
                        source_page=source_page,
                    ),
                    self._build_flashcard(
                        section,
                        concept,
                        suffix="interest-parity-exam-trap",
                        front="What is a common exam trap when comparing covered and uncovered interest rate parity?",
                        back="Do not treat uncovered parity as hedged; it depends on expected future spot rates.",
                        card_type="exam_trap",
                        source_page=source_page,
                    ),
                ]
            )
        if "uncovered interest rate parity" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="uncovered-interest-rate-parity",
                    front="What does uncovered interest rate parity rely on?",
                    back="It relies on expected future spot exchange rates rather than a forward hedge.",
                    card_type="definition",
                    source_page=source_page,
                )
            )
        if "relative price levels" in lowered or "inflation" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="ppp-exchange-rate-driver",
                    front="What drives exchange-rate changes under purchasing power parity?",
                    back="Relative price-level or inflation changes drive exchange-rate adjustments under PPP.",
                    card_type="interpretation",
                    source_page=source_page,
                )
            )
        if "forward" in lowered and "exchange-rate risk" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="covered-parity-hedging",
                    front="Why is hedging important in covered interest rate parity?",
                    back="The forward contract locks in the exchange rate and removes exchange-rate uncertainty.",
                    card_type="application",
                    source_page=source_page,
                )
            )
        return cards

    def _mortgage_loan_flashcards(
        self,
        section: SourceSection,
        concept: StudyConceptCard,
        source_page: int | None,
    ) -> list[StudyFlashcard]:
        excerpt = re.sub(r"\s+", " ", concept.source_excerpt).strip()
        lowered = excerpt.lower()
        if "mortgage" not in lowered or "mortgage-backed" in lowered:
            return []

        cards: list[StudyFlashcard] = []
        if "fixed-rate mortgage" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="fixed-rate-mortgage",
                    front="What is a fixed-rate mortgage?",
                    back="A fixed-rate mortgage has an interest rate that stays constant over the loan term.",
                    card_type="definition",
                    source_page=source_page,
                )
            )
        if "adjustable-rate mortgage" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="adjustable-rate-mortgage",
                    front="What is an adjustable-rate mortgage?",
                    back="An adjustable-rate mortgage has an interest rate that can change over time.",
                    card_type="definition",
                    source_page=source_page,
                )
            )
        if "amortization" in lowered or "amortize" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="mortgage-amortization",
                    front="What does mortgage amortization do?",
                    back="Mortgage amortization repays principal gradually through scheduled payments.",
                    card_type="definition",
                    source_page=source_page,
                )
            )
        if "prepay" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="mortgage-prepayment-option",
                    front="What is the borrower prepayment option in a mortgage?",
                    back="It is the borrower's ability to repay the mortgage early.",
                    card_type="definition",
                    source_page=source_page,
                )
            )
        return cards

    def _mortgage_backed_security_flashcards(
        self,
        section: SourceSection,
        concept: StudyConceptCard,
        source_page: int | None,
    ) -> list[StudyFlashcard]:
        excerpt = re.sub(r"\s+", " ", concept.source_excerpt).strip()
        lowered = excerpt.lower()
        if not ("mortgage-backed" in lowered or re.search(r"\bmbs\b", lowered)):
            return []

        cards: list[StudyFlashcard] = []
        cards.append(
            self._build_flashcard(
                section,
                concept,
                suffix="mbs-definition",
                front="What is a mortgage-backed security (MBS)?",
                back="An MBS pools mortgage loans and passes principal and interest cash flows to investors.",
                card_type="definition",
                source_page=source_page,
            )
        )
        if "principal" in lowered and "interest" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="mbs-pass-through-cash-flows",
                    front="What cash flows pass through to mortgage-backed security investors?",
                    back="Principal and interest payments from the mortgage pool pass through to investors.",
                    card_type="short_answer_recall",
                    source_page=source_page,
                )
            )
        if "weighted average coupon" in lowered or "wac" in lowered or "weighted average maturity" in lowered or "wam" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="mbs-wac-wam",
                    front="What do WAC and WAM measure in mortgage-backed securities?",
                    back="WAC is the pool's average mortgage rate; WAM is the average time to final maturity.",
                    card_type="comparison",
                    source_page=source_page,
                )
            )
        if "prepayment risk" in lowered or "prepayment" in lowered:
            cards.extend(
                [
                    self._build_flashcard(
                        section,
                        concept,
                        suffix="mbs-prepayment-risk",
                        front="What is prepayment risk in mortgage-backed securities?",
                        back="Prepayment risk is the risk that borrowers repay mortgages earlier than expected.",
                        card_type="definition",
                        source_page=source_page,
                    ),
                    self._build_flashcard(
                        section,
                        concept,
                        suffix="mbs-prepayment-effect",
                        front="Why do prepayments matter for mortgage-backed security investors?",
                        back="Prepayments change the timing of principal cash flows and reinvestment exposure.",
                        card_type="interpretation",
                        source_page=source_page,
                    ),
                ]
            )
        if "single monthly mortality" in lowered or "smm" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="mbs-smm",
                    front="What does single monthly mortality (SMM) measure?",
                    back="SMM measures the monthly prepayment rate for a mortgage pool.",
                    card_type="definition",
                    source_page=source_page,
                )
            )
        if "conditional prepayment rate" in lowered or "cpr" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="mbs-cpr",
                    front="What does conditional prepayment rate (CPR) measure?",
                    back="CPR measures the annualized prepayment rate for a mortgage pool.",
                    card_type="definition",
                    source_page=source_page,
                )
            )
        if "collateralized mortgage obligation" in lowered or re.search(r"\bcmo\b", lowered):
            cards.extend(
                [
                    self._build_flashcard(
                        section,
                        concept,
                        suffix="cmo-definition",
                        front="What is a collateralized mortgage obligation (CMO)?",
                        back="A CMO is an MBS structure that divides mortgage cash flows into tranches.",
                        card_type="definition",
                        source_page=source_page,
                    ),
                    self._build_flashcard(
                        section,
                        concept,
                        suffix="cmo-cash-flow-exposure",
                        front="How do CMOs change mortgage-backed security cash-flow exposure?",
                        back="CMOs create tranches with different exposure to prepayment timing and cash-flow risk.",
                        card_type="interpretation",
                        source_page=source_page,
                    ),
                ]
            )
        if "tranche" in lowered or "tranches" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="mbs-tranche-purpose",
                    front="Why do MBS structures use tranches?",
                    back="Tranches allocate cash-flow timing and prepayment risk differently across investors.",
                    card_type="application",
                    source_page=source_page,
                )
            )
        return cards

    def _prepayment_modeling_flashcards(
        self,
        section: SourceSection,
        concept: StudyConceptCard,
        source_page: int | None,
    ) -> list[StudyFlashcard]:
        excerpt = re.sub(r"\s+", " ", concept.source_excerpt).strip()
        lowered = excerpt.lower()
        if not ("prepayment" in lowered and ("oas" in lowered or "option-adjusted" in lowered or "monte carlo" in lowered)):
            return []

        cards: list[StudyFlashcard] = []
        if "option-adjusted" in lowered or "oas" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="oas-definition",
                    front="What is option-adjusted spread (OAS)?",
                    back="OAS is the spread after adjusting for embedded options such as mortgage prepayment.",
                    card_type="definition",
                    source_page=source_page,
                )
            )
        if "monte carlo" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="mbs-monte-carlo",
                    front="Why can Monte Carlo simulation be used for mortgage-backed securities?",
                    back="It models many interest-rate paths and their effects on prepayment-sensitive cash flows.",
                    card_type="application",
                    source_page=source_page,
                )
            )
        if "refinancing" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="refinancing-incentive",
                    front="How does refinancing incentive affect mortgage prepayments?",
                    back="Borrowers are more likely to prepay when refinancing into a lower rate is attractive.",
                    card_type="interpretation",
                    source_page=source_page,
                )
            )
        return cards

    def _swap_valuation_flashcards(
        self,
        section: SourceSection,
        concept: StudyConceptCard,
        source_page: int | None,
    ) -> list[StudyFlashcard]:
        excerpt = re.sub(r"\s+", " ", concept.source_excerpt).strip()
        lowered = excerpt.lower()
        if not (
            "swap" in lowered
            and (
                "valuation" in lowered
                or "fixed-rate bond" in lowered
                or "floating-rate bond" in lowered
                or "forward rate agreement" in lowered
                or "discount curve" in lowered
                or "fair swap rate" in lowered
            )
        ):
            return []

        cards: list[StudyFlashcard] = [
            self._build_flashcard(
                section,
                concept,
                suffix="swap-valuation-methods",
                front="How can a plain vanilla interest rate swap be valued?",
                back="It can be valued as a bond position or as a sequence of forward rate agreements.",
                card_type="short_answer_recall",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="swap-bond-position",
                front="How can a swap be valued as a bond position?",
                back="Value it as the difference between a fixed-rate bond and a floating-rate bond.",
                card_type="application",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="swap-fra-sequence",
                front="How can a swap be valued as a sequence of forward rate agreements?",
                back="Treat each future net swap payment as an FRA-style cash flow and discount it.",
                card_type="application",
                source_page=source_page,
            ),
        ]
        if "net cash" in lowered or "cash flows" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="swap-net-cash-flows",
                    front="What cash flows are discounted in swap valuation?",
                    back="The future net cash flows between the fixed and floating swap legs are discounted.",
                    card_type="short_answer_recall",
                    source_page=source_page,
                )
            )
        if "discount curve" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="swap-discount-curve",
                    front="What curve is used to discount swap cash flows?",
                    back="The appropriate discount curve is used to discount future net swap cash flows.",
                    card_type="short_answer_recall",
                    source_page=source_page,
                )
            )
        if "zero at initiation" in lowered or "fair swap rate" in lowered:
            cards.extend(
                [
                    self._build_flashcard(
                        section,
                        concept,
                        suffix="swap-value-at-initiation",
                        front="What is the value of a fair swap at initiation?",
                        back="A fair swap has zero value at initiation when the fixed rate equals the fair swap rate.",
                        card_type="interpretation",
                        source_page=source_page,
                    ),
                    self._build_flashcard(
                        section,
                        concept,
                        suffix="swap-fair-rate",
                        front="Why does swap valuation depend on the fair swap rate?",
                        back="The fair swap rate makes the fixed and floating legs equal in value at initiation.",
                        card_type="interpretation",
                        source_page=source_page,
                    ),
                ]
            )
        if "rates move" in lowered or "changes as rates" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="swap-value-after-rates-move",
                    front="What happens to swap value after market rates move?",
                    back="The swap value changes as the fixed and floating legs are no longer equal in value.",
                    card_type="interpretation",
                    source_page=source_page,
                )
            )
        if "fixed-rate bond" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="swap-fixed-rate-bond-leg",
                    front="What does the fixed-rate bond represent in swap valuation?",
                    back="It represents the present value of the fixed swap payments.",
                    card_type="interpretation",
                    source_page=source_page,
                )
            )
        if "floating-rate bond" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="swap-floating-rate-bond-leg",
                    front="What does the floating-rate bond represent in swap valuation?",
                    back="It represents the present value of the floating swap payments.",
                    card_type="interpretation",
                    source_page=source_page,
                )
            )
        cards.append(
            self._build_flashcard(
                section,
                concept,
                suffix="swap-valuation-exam-trap",
                front="What is a common exam trap in valuing swaps after initiation?",
                back="Do not assume the swap remains worth zero after market rates move.",
                card_type="exam_trap",
                source_page=source_page,
            )
        )
        return cards

    def _interest_rate_curve_flashcards(
        self,
        section: SourceSection,
        concept: StudyConceptCard,
        source_page: int | None,
    ) -> list[StudyFlashcard]:
        excerpt = re.sub(r"\s+", " ", concept.source_excerpt).strip()
        lowered = excerpt.lower()
        if not any(
            term in lowered
            for term in [
                "spot rate",
                "spot rates",
                "forward rate",
                "forward rates",
                "forward rate agreement",
                "discount factor",
                "discount factors",
                "yield to maturity",
                "zero-coupon bond",
            ]
        ):
            return []

        return [
            self._build_flashcard(
                section,
                concept,
                suffix="spot-rate-definition",
                front="What is a spot rate?",
                back="A spot rate is the yield on a zero-coupon bond for a specific maturity.",
                card_type="definition",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="forward-rate-definition",
                front="What is a forward rate?",
                back="A forward rate is a future interest rate implied by current spot rates.",
                card_type="definition",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="spot-vs-forward-rate",
                front="How does a spot rate differ from a forward rate?",
                back="A spot rate is a current zero-coupon rate; a forward rate is an implied future rate between maturities.",
                card_type="comparison",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="fra-locked-rate",
                front="What does a forward rate agreement (FRA) lock in?",
                back="An FRA locks in a future borrowing or lending rate.",
                card_type="short_answer_recall",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="discount-factor-definition",
                front="What is a discount factor?",
                back="A discount factor converts a future cash flow into present value.",
                card_type="definition",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="yield-to-maturity-definition",
                front="What is yield to maturity?",
                back="Yield to maturity is the single discount rate that equates a bond's promised cash flows to its price.",
                card_type="definition",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="infer-forward-from-spot",
                front="Why can forward rates be inferred from spot rates?",
                back="The spot curve implies no-arbitrage rates for future periods between maturities.",
                card_type="interpretation",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="discount-factors-bond-valuation",
                front="How are discount factors used in fixed-income valuation?",
                back="Each expected cash flow is multiplied by its discount factor to find present value.",
                card_type="application",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="forward-rate-interpretation",
                front="What does a forward rate tell you in fixed-income analysis?",
                back="It gives the implied future rate for a period between two maturities.",
                card_type="interpretation",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="forward-rate-exam-trap",
                front="What is a common exam trap about forward rates?",
                back="Do not treat implied forward rates as guaranteed future spot rates.",
                card_type="exam_trap",
                source_page=source_page,
            ),
        ]

    def _duration_convexity_flashcards(
        self,
        section: SourceSection,
        concept: StudyConceptCard,
        source_page: int | None,
    ) -> list[StudyFlashcard]:
        excerpt = re.sub(r"\s+", " ", concept.source_excerpt).strip()
        lowered = excerpt.lower()
        if not any(term in lowered for term in ["duration", "modified duration", "effective duration", "convexity", "price-yield"]):
            return []

        return [
            self._build_flashcard(
                section,
                concept,
                suffix="duration-measure",
                front="What does duration measure?",
                back="Duration measures a bond price's sensitivity to changes in yield.",
                card_type="definition",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="modified-duration-approximation",
                front="What does modified duration approximate?",
                back="Modified duration approximates the percentage price change for a small yield change.",
                card_type="interpretation",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="effective-vs-modified-duration",
                front="How does effective duration differ from modified duration?",
                back="Effective duration captures embedded-option effects; modified duration assumes cash flows do not change.",
                card_type="comparison",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="convexity-definition",
                front="What does convexity measure?",
                back="Convexity measures the curvature in the bond price-yield relationship.",
                card_type="definition",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="convexity-improves-duration",
                front="How does convexity improve the duration price approximation?",
                back="Convexity adds a curvature adjustment, making price estimates better for larger yield changes.",
                card_type="interpretation",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="price-yield-curvature",
                front="Why is the bond price-yield relationship curved?",
                back="Bond prices rise at a different rate when yields fall than they decline when yields rise.",
                card_type="interpretation",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="yield-rise-price-effect",
                front="What happens to bond price when yield rises?",
                back="Bond price falls when yield rises.",
                card_type="short_answer_recall",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="convexity-large-yield-changes",
                front="Why is convexity more important for large yield changes?",
                back="Duration is a linear approximation, so curvature error grows as yield changes get larger.",
                card_type="application",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="duration-exam-trap",
                front="What is a common exam trap about duration?",
                back="Duration is an approximation, not an exact price-change formula for large yield moves.",
                card_type="exam_trap",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="when-effective-duration",
                front="When should effective duration be used?",
                back="Use effective duration when cash flows may change as yields change, such as with embedded options.",
                card_type="application",
                source_page=source_page,
            ),
        ]

    def _credit_bond_flashcards(
        self,
        section: SourceSection,
        concept: StudyConceptCard,
        source_page: int | None,
    ) -> list[StudyFlashcard]:
        excerpt = re.sub(r"\s+", " ", concept.source_excerpt).strip()
        lowered = excerpt.lower()
        if not any(
            term in lowered
            for term in [
                "credit risk",
                "default risk",
                "credit spread",
                "event risk",
                "rating migration",
                "recovery rate",
                "high-yield",
                "investment-grade",
            ]
        ):
            return []

        cards: list[StudyFlashcard] = []
        if "specified in the indenture" in lowered:
            cards.extend(
                [
                    self._build_flashcard(
                        section,
                        concept,
                        suffix="default-risk-missed-indenture-payments",
                        front="What event realizes credit default risk?",
                        back=(
                            "Credit default risk is realized when the issuer does not make "
                            "the payments specified in the indenture."
                        ),
                        card_type="application",
                        source_page=source_page,
                    ),
                    self._build_flashcard(
                        section,
                        concept,
                        suffix="default-risk-indenture-obligation",
                        front="Which obligation defines credit default risk in the source?",
                        back="The issuer's obligation to make the payments specified in the indenture.",
                        card_type="definition",
                        source_page=source_page,
                    ),
                ]
            )
        if "corresponding treasury rate" in lowered:
            cards.extend(
                [
                    self._build_flashcard(
                        section,
                        concept,
                        suffix="spread-risk-market-change",
                        front="What market change creates credit spread risk?",
                        back=(
                            "A change in the spread of a bond's interest rate over the "
                            "corresponding Treasury rate creates credit spread risk."
                        ),
                        card_type="application",
                        source_page=source_page,
                    ),
                    self._build_flashcard(
                        section,
                        concept,
                        suffix="spread-risk-treasury-benchmark",
                        front="Which benchmark defines the bond spread in credit spread risk?",
                        back="The bond's interest rate is compared with the corresponding Treasury rate.",
                        card_type="definition",
                        source_page=source_page,
                    ),
                ]
            )

        cards += [
            self._build_flashcard(
                section,
                concept,
                suffix="corporate-bond-credit-risk",
                front="What is credit risk for a corporate bond?",
                back="Credit risk is the risk that the issuer cannot make promised interest or principal payments.",
                card_type="definition",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="bond-default-risk",
                front="What is default risk for a bond investor?",
                back="Default risk is the risk that the issuer fails to meet debt obligations.",
                card_type="definition",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="credit-spread-compensation",
                front="What does a credit spread compensate investors for?",
                back="A credit spread compensates investors for credit risk above a default-free benchmark.",
                card_type="interpretation",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="event-risk-definition",
                front="What is event risk in credit analysis?",
                back="Event risk is the risk that a specific event weakens an issuer's credit quality.",
                card_type="definition",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="rating-migration-risk",
                front="What is rating migration risk?",
                back="Rating migration risk is the risk that a bond's credit rating changes, affecting value.",
                card_type="definition",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="recovery-rate-definition",
                front="What does recovery rate mean after bond default?",
                back="Recovery rate is the percentage of value recovered after default.",
                card_type="definition",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="high-yield-vs-investment-grade",
                front="How do high-yield bonds differ from investment-grade bonds?",
                back="High-yield bonds have lower credit ratings and higher credit risk than investment-grade bonds.",
                card_type="comparison",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="spread-widening",
                front="What does widening credit spread usually signal?",
                back="It usually signals higher perceived credit risk or weaker issuer credit quality.",
                card_type="interpretation",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="credit-risk-exam-trap",
                front="Why should credit spreads not be treated as only interest-rate effects?",
                back="Do not treat credit spread changes as only interest-rate effects; issuer credit quality also matters.",
                card_type="exam_trap",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="loss-severity-credit-risk",
                front="How does recovery rate affect credit loss severity?",
                back="Lower recovery rates increase loss severity when default occurs.",
                card_type="application",
                source_page=source_page,
            ),
        ]
        return cards

    def _option_margin_flashcards(
        self,
        section: SourceSection,
        concept: StudyConceptCard,
        source_page: int | None,
    ) -> list[StudyFlashcard]:
        excerpt = re.sub(r"\s+", " ", concept.source_excerpt).strip()
        lowered = excerpt.lower()
        if not any(
            term in lowered
            for term in [
                "margin requirement",
                "purchased on margin",
                "margin account",
                "option writers",
                "uncovered call",
                "covered call",
            ]
        ):
            return []

        cards: list[StudyFlashcard] = []
        if "margin requirement" in lowered or "margin account" in lowered:
            cards.extend(
                [
                    self._build_flashcard(
                        section,
                        concept,
                        suffix="option-margin-requirements",
                        front="What are option margin requirements?",
                        back="Option margin requirements are collateral rules that limit leverage and protect against option position losses.",
                        card_type="definition",
                        source_page=source_page,
                    ),
                    self._build_flashcard(
                        section,
                        concept,
                        suffix="option-writer-margin-account",
                        front="Why must option writers have a margin account?",
                        back="Option writers need margin because written options can create large losses and default risk.",
                        card_type="application",
                        source_page=source_page,
                    ),
                    self._build_flashcard(
                        section,
                        concept,
                        suffix="option-writer-margin-risk",
                        front="What risk drives margin requirements for option writers?",
                        back="The main risk is that option writers may face large losses and fail to meet obligations.",
                        card_type="exam_trap",
                        source_page=source_page,
                    ),
                ]
            )
        if "maturities of nine months" in lowered or "purchased on margin" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="short-maturity-options-no-margin",
                    front="Why are short-maturity options generally not purchased on margin?",
                    back="They are not purchased on margin because leverage would become too high.",
                    card_type="application",
                    source_page=source_page,
                )
            )
        if "uncovered call" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="uncovered-call-margin-definition",
                    front="What are uncovered calls?",
                    back="Uncovered calls are written call options where the writer does not own the underlying asset.",
                    card_type="definition",
                    source_page=source_page,
                )
            )
        if "covered call" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="covered-call-margin-definition",
                    front="What are covered calls?",
                    back="Covered calls are written call options on stock already owned by the option seller.",
                    card_type="definition",
                    source_page=source_page,
                )
            )
        if "covered call" in lowered and "uncovered call" in lowered:
            cards.extend(
                [
                    self._build_flashcard(
                        section,
                        concept,
                        suffix="covered-vs-uncovered-call-margin",
                        front="How do covered calls differ from uncovered calls?",
                        back="Covered calls are written against owned stock; uncovered calls are written without owning the underlying asset.",
                        card_type="comparison",
                        source_page=source_page,
                    ),
                    self._build_flashcard(
                        section,
                        concept,
                        suffix="covered-call-lower-margin",
                        front="Why does covered call writing generally require less margin than uncovered call writing?",
                        back="Covered calls are less risky because the seller already owns the underlying stock.",
                        card_type="application",
                        source_page=source_page,
                    ),
                ]
            )
        return cards

    def _option_strategy_flashcards(
        self,
        section: SourceSection,
        concept: StudyConceptCard,
        source_page: int | None,
    ) -> list[StudyFlashcard]:
        excerpt = re.sub(r"\s+", " ", concept.source_excerpt).strip()
        lowered = excerpt.lower()
        if not any(
            term in lowered
            for term in [
                "protective put",
                "covered call",
                "bull spread",
                "bear spread",
                "box spread",
                "straddle",
                "strangle",
                "butterfly spread",
                "option strategy",
            ]
        ):
            return []

        return [
            self._build_flashcard(
                section,
                concept,
                suffix="protective-put-definition",
                front="What is a protective put?",
                back="A protective put combines a long asset position with a long put to limit downside risk.",
                card_type="definition",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="covered-call-definition",
                front="What is a covered call?",
                back="A covered call combines owning the underlying asset with writing a call option on it.",
                card_type="definition",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="protective-put-vs-covered-call",
                front="How does a protective put differ from a covered call?",
                back="A protective put buys downside protection; a covered call earns premium income but limits upside.",
                card_type="comparison",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="bull-spread-definition",
                front="What is a bull spread?",
                back="A bull spread is an option strategy designed to profit when the underlying price rises moderately.",
                card_type="definition",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="bear-spread-definition",
                front="What is a bear spread?",
                back="A bear spread is an option strategy designed to profit when the underlying price falls moderately.",
                card_type="definition",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="bull-vs-bear-spread",
                front="How does a bull spread differ from a bear spread?",
                back="A bull spread benefits from price increases; a bear spread benefits from price decreases.",
                card_type="comparison",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="straddle-definition",
                front="What is a straddle?",
                back="A straddle combines a call and a put with the same strike price and expiration.",
                card_type="definition",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="strangle-definition",
                front="What is a strangle?",
                back="A strangle combines a call and a put with different strike prices but the same expiration.",
                card_type="definition",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="straddle-vs-strangle",
                front="How does a straddle differ from a strangle?",
                back="A straddle uses the same strike for call and put; a strangle uses different strikes.",
                card_type="comparison",
                source_page=source_page,
            ),
            self._build_flashcard(
                section,
                concept,
                suffix="option-strategy-exam-trap",
                front="What is a common exam trap about option strategies?",
                back="Match the option positions to the expected price move and volatility view, not just the strategy name.",
                card_type="exam_trap",
                source_page=source_page,
            ),
        ]

    def _probability_relationship_flashcards(
        self,
        section: SourceSection,
        concept: StudyConceptCard,
        source_page: int | None,
    ) -> list[StudyFlashcard]:
        excerpt = concept.source_excerpt
        normalized = re.sub(r"\s+", " ", excerpt)
        lowered = normalized.lower()
        cards: list[StudyFlashcard] = []

        has_independence = (
            "independent" in lowered
            and (
                re.search(r"P\(A\s*[∩&]\s*B\)\s*=\s*P\(A\)\s*P\(B\)", normalized)
                or re.search(r"P\(A\|B\)\s*=\s*P\(A\)", normalized)
            )
        )
        has_mutual_exclusivity = (
            "mutually exclusive" in lowered
            and re.search(r"P\(A\s*[∩&]\s*B\)\s*=\s*0", normalized)
        )

        if has_independence:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="probability-independence-condition",
                    front="What condition defines independence between events A and B?",
                    back="P(A ∩ B) = P(A)P(B). Equivalently, P(A|B) = P(A) when P(B) > 0.",
                    card_type="formula",
                    source_page=source_page,
                )
            )
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="probability-conditional-independence",
                    front="If A and B are independent, what is P(A|B) equal to?",
                    back="P(A|B) = P(A), assuming P(B) > 0.",
                    card_type="formula",
                    source_page=source_page,
                )
            )
        if has_mutual_exclusivity:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="probability-mutually-exclusive-condition",
                    front="What condition defines mutually exclusive events?",
                    back="P(A ∩ B) = 0, meaning both events cannot occur together.",
                    card_type="formula",
                    source_page=source_page,
                )
            )
        if has_independence and has_mutual_exclusivity:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="probability-independent-vs-mutually-exclusive",
                    front="What is the key difference between independent and mutually exclusive events?",
                    back=(
                        "Independent events do not change each other's probability; "
                        "mutually exclusive events cannot occur together."
                    ),
                    card_type="comparison",
                    source_page=source_page,
                )
            )
        if "event space" in lowered and "possible outcomes" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="probability-event-space",
                    front="What is the event space in probability?",
                    back="The set of all possible outcomes.",
                    card_type="definition",
                    source_page=source_page,
                )
            )
        if "random event" in lowered and "event space" in lowered:
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix="probability-random-event",
                    front="What is a random event?",
                    back="One or more outcomes from the event space.",
                    card_type="definition",
                    source_page=source_page,
                )
            )
        return cards

    def _sentence_level_flashcards_from_concept(
        self,
        section: SourceSection,
        concept: StudyConceptCard,
        source_page: int | None,
    ) -> list[StudyFlashcard]:
        cards: list[StudyFlashcard] = []
        excerpt = concept.source_excerpt
        sentences = self._sentences(excerpt.replace("\n", " "))
        for index, sentence in enumerate(sentences[:8], start=1):
            sentence = sentence.strip()
            if len(sentence.split()) < 7 or re.match(r"^LO\s+\d+\.[a-z]\b", sentence, re.IGNORECASE):
                continue
            definition_match = re.match(
                r"^(?P<subject>[A-Z][A-Za-z0-9 /()'-]{2,70}?)\s+(?:is|are)\s+(?P<answer>.+)$",
                sentence,
            )
            if definition_match:
                subject = definition_match.group("subject").strip()
                answer = definition_match.group("answer").strip().rstrip(".")
                if self._is_bad_sentence_definition(subject, answer):
                    continue
                if 1 <= len(subject.split()) <= 8 and len(answer.split()) >= 3:
                    verb = "are" if sentence[len(subject) :].lstrip().lower().startswith("are") else "is"
                    cards.append(
                        self._build_flashcard(
                            section,
                            concept,
                            suffix=f"sentence-definition-{index}",
                            front=f"What {verb} {subject[0].lower() + subject[1:]}?",
                            back=answer + ".",
                            card_type="definition",
                            source_page=source_page,
                        )
                    )
                    continue
            include_match = re.search(
                r"(?P<subject>[A-Za-z][A-Za-z0-9 /()'-]{3,80})\s+include\s+(?P<items>.+)$",
                sentence,
                re.IGNORECASE,
            )
            if include_match:
                subject = include_match.group("subject").strip(" ,.;:")
                items = include_match.group("items").strip().rstrip(".")
                if (
                    subject.lower().startswith("some of")
                    or self._is_phrase_soup(subject)
                    or not self._is_good_flashcard_term(subject)
                ):
                    continue
                if len(items.split()) >= 3:
                    verb = (
                        "do"
                        if re.search(
                            r"\b(?:practices|methods|strategies|components|advantages|disadvantages|challenges)\b",
                            subject,
                            re.IGNORECASE,
                        )
                        else ("do" if subject.lower().endswith("s") else "does")
                    )
                    cards.append(
                        self._build_flashcard(
                            section,
                            concept,
                            suffix=f"sentence-include-{index}",
                            front=f"What {verb} {subject.lower()} include?",
                            back=items + ".",
                            card_type="list_recall",
                            source_page=source_page,
                        )
                    )
        return cards[:4]

    def _term_flashcards_from_concept(
        self,
        section: SourceSection,
        concept: StudyConceptCard,
        source_page: int | None,
    ) -> list[StudyFlashcard]:
        cards: list[StudyFlashcard] = []
        excerpt = concept.source_excerpt
        sentences = self._sentences(excerpt.replace("\n", " "))
        meaningful_terms = [
            self._clean_flashcard_term(term)
            for term in concept.key_terms
            if self._is_good_flashcard_term(term)
        ]
        for index, term in enumerate(meaningful_terms[:4], start=1):
            if len(cards) >= 4:
                break
            source_sentence = next(
                (
                    re.sub(r"^\s*LO\s+\d+\.[a-z]\s+", "", sentence.strip(), flags=re.IGNORECASE)
                    for sentence in sentences
                    if re.search(rf"\b{re.escape(term)}\b", sentence, re.IGNORECASE)
                    and len(sentence.split()) >= 5
                ),
                "",
            )
            if not source_sentence:
                continue
            front = self._term_flashcard_front(term, concept, source_sentence)
            if not front:
                continue
            cards.append(
                self._build_flashcard(
                    section,
                    concept,
                    suffix=f"term-{index}-{self._slug(term)}",
                    front=front,
                    back=source_sentence,
                    card_type="application",
                    source_page=source_page,
                )
            )
        return cards

    def _anchor_flashcard_from_concept(
        self,
        section: SourceSection,
        concept: StudyConceptCard,
        source_page: int | None,
    ) -> StudyFlashcard | None:
        excerpt_without_heading = re.sub(r"^\s*LO\s+\d+\.[a-z]\s*", "", concept.source_excerpt, flags=re.IGNORECASE)
        first_sentence = self._first_meaningful_sentence(excerpt_without_heading)
        if not first_sentence or len(first_sentence.split()) < 2:
            return None
        matter_match = re.match(r"^(?P<topic>[A-Za-z][A-Za-z0-9 /()'-]{2,80}?)\s+matters\.?$", first_sentence, re.IGNORECASE)
        if matter_match:
            topic = self._clean_flashcard_term(matter_match.group("topic"))
            if self._is_good_flashcard_term(topic) or topic.lower() in FINANCE_ACADEMIC_TERMS:
                return self._build_flashcard(
                    section,
                    concept,
                    suffix="source-anchor",
                    front=f"Why does {topic.lower()} matter?",
                    back=first_sentence,
                    card_type="short_answer_recall",
                    source_page=source_page,
                )
        focus_term = next(
            (
                self._clean_flashcard_term(term)
                for term in concept.key_terms
                if self._is_good_flashcard_term(term) and len(self._clean_flashcard_term(term).split()) <= 4
            ),
            self._clean_flashcard_topic(concept),
        )
        if not focus_term:
            return None
        if re.match(rf"^{re.escape(focus_term)}\s+matters\.?$", first_sentence, re.IGNORECASE):
            return self._build_flashcard(
                section,
                concept,
                suffix="source-anchor",
                front=f"Why does {focus_term.lower()} matter?",
                back=first_sentence,
                card_type="short_answer_recall",
                source_page=source_page,
            )
        return self._build_flashcard(
            section,
            concept,
            suffix="source-anchor",
            front=f"What should you remember about {focus_term.lower()}?",
            back=first_sentence,
            card_type="short_answer_recall",
            source_page=source_page,
        )

    def _clean_flashcard_term(self, term: str | None) -> str:
        cleaned = re.sub(r"\bLO\s*\d+\.[a-z]\b:?", "", term or "", flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,:;-/")
        return cleaned

    def _clean_flashcard_topic(self, concept: StudyConceptCard) -> str:
        candidates = [
            concept.title,
            concept.exam_focus,
            concept.simplified_explanation,
        ]
        for candidate in candidates:
            cleaned = self._clean_flashcard_term(candidate)
            cleaned = re.sub(r"^(?:explain|define|describe|identify|calculate)\s+", "", cleaned, flags=re.IGNORECASE)
            sentence = self._first_meaningful_sentence(cleaned)
            if sentence:
                cleaned = sentence
            words = cleaned.split()
            if 1 <= len(words) <= 7 and not self._is_phrase_soup(cleaned):
                return cleaned
        return ""

    def _is_good_flashcard_term(self, term: str) -> bool:
        cleaned = self._clean_flashcard_term(term)
        if not cleaned or len(cleaned) < 4:
            return False
        lowered = cleaned.lower()
        if (
            lowered in JUNK_STUDY_TERMS
            or lowered in FRAGMENT_FLASHCARD_TERMS
            or self._is_junk_workbook_keyword(cleaned)
        ):
            return False
        if re.search(r"\b(?:is|are|was|were|be|being|been)\b", lowered):
            return False
        if re.match(
            r"^(?:as|of|the|all|one|possible|following|to|its|which|firms|if|such|when|whether|"
            r"because|given|suppose|assume|also|there|some|payment|payments|countries)\b",
            lowered,
        ):
            return False
        if re.match(r"^(?:both|derive|retain|various)\b", lowered):
            return False
        if re.search(r"\b(?:where|that|which|per|from|to|with|and|both|various)$", lowered):
            return False
        if re.search(r"\b(?:from four different|return per|existence of credit)\b", lowered):
            return False
        if re.search(r"\bLO\s*\d+\.[a-z]\b", cleaned, re.IGNORECASE):
            return False
        if self._is_phrase_soup(cleaned):
            return False
        tokens = TOKEN_RE.findall(cleaned)
        if len(tokens) == 1 and lowered not in set(FINANCE_ACADEMIC_TERMS):
            return False
        return True

    def _term_flashcard_front(
        self,
        term: str,
        concept: StudyConceptCard,
        source_sentence: str,
    ) -> str | None:
        term_lower = term.lower()
        sentence_lower = source_sentence.lower()
        if term_lower == "event space":
            return "What is the event space in probability?"
        if term_lower == "random event":
            return "What is a random event?"
        if "risk appetite" == term_lower:
            return "What is risk appetite?"
        if (
            re.search(r"\bis\b|\bare\b", source_sentence)
            and len(term.split()) <= 5
            and self._term_starts_definition_sentence(term, source_sentence)
        ):
            article = self._definition_article_for_term(term, source_sentence)
            subject = f"{article} {term_lower}" if article else term_lower
            copula = self._definition_copula_for_term(term, source_sentence)
            question_verb = "are" if copula == "are" and self._subject_looks_plural(subject) else "is"
            return f"What {question_verb} {subject}?"
        if "influenced" in sentence_lower and "risk appetite" in sentence_lower:
            return "What usually influences risk appetite?"
        return None

    def _term_starts_definition_sentence(self, term: str, source_sentence: str) -> bool:
        term_pattern = re.escape(term).replace(r"\ ", r"\s+")
        return bool(
            re.match(
                rf"^(?:a|an|the)?\s*{term_pattern}\s+(?:is|are)\b",
                source_sentence.strip(),
                re.IGNORECASE,
            )
        )

    def _definition_article_for_term(self, term: str, source_sentence: str) -> str:
        term_pattern = re.escape(term).replace(r"\ ", r"\s+")
        match = re.match(
            rf"^(?P<article>a|an|the)\s+{term_pattern}\s+(?:is|are)\b",
            source_sentence.strip(),
            re.IGNORECASE,
        )
        return match.group("article").lower() if match else ""

    def _definition_copula_for_term(self, term: str, source_sentence: str) -> str:
        term_pattern = re.escape(term).replace(r"\ ", r"\s+")
        match = re.match(
            rf"^(?:a|an|the)?\s*{term_pattern}\s+(?P<copula>is|are)\b",
            source_sentence.strip(),
            re.IGNORECASE,
        )
        return match.group("copula").lower() if match else "is"

    def _is_bad_sentence_definition(self, subject: str, answer: str) -> bool:
        subject_lower = subject.lower().strip()
        answer_lower = answer.lower().strip()
        if subject_lower in FRAGMENT_FLASHCARD_TERMS:
            return True
        if re.match(
            r"^(?:as|of|the|all|one|possible|following|to|its|which|firms|both|derive|retain|"
            r"various|they|while|if|such|when|whether|because|given|suppose|assume|also|there|some|payment|"
            r"payments|countries)\b",
            subject_lower,
        ):
            return True
        if subject_lower.startswith("a special type of"):
            return True
        if re.search(r"\b(?:should|could|would|may|might|must|will)\b", subject_lower):
            return True
        if re.match(r"^(?:var|value at risk)\s+and\b", subject_lower):
            return True
        if re.search(r"\b(?:where|that|which|per|from|to|with|and|both|various)$", subject_lower):
            return True
        if subject_lower in {"two events", "two events a and b"} and re.match(
            r"^(?:independent|mutually exclusive)\s+if\b",
            answer_lower,
        ):
            return True
        if re.match(
            r"^(?:of|the|all|one|possible|following|if|such|when|whether|because|given|suppose|"
            r"assume|also|there|some|payment|payments|countries)\b",
            subject_lower,
        ):
            return True
        return False

    def _looks_like_bad_flashcard_answer(self, value: str) -> bool:
        cleaned = re.sub(r"\s+", " ", value).strip()
        lowered = cleaned.lower()
        if len(TOKEN_RE.findall(cleaned)) < 3:
            return True
        if re.match(
            r"^(?:because|although|while|if|when|where|that|which|who|to|of|and|or|also)\b",
            lowered,
        ):
            return True
        if re.search(r"\b(?:where|that|which|from|to|with|and|or|also)$", lowered):
            return True
        if self._is_phrase_soup(cleaned):
            return True
        return False

    def _numbered_items_from_excerpt(self, text: str) -> list[str]:
        items: list[str] = []
        for line in text.splitlines():
            match = re.match(r"^\s*(?P<number>\d+)\.\s+(?P<item>.+?)\.?\s*$", line)
            if match:
                items.append(match.group("item").strip().rstrip(".") + ".")
        return items

    def _slug(self, value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "item"

    def _is_phrase_soup(self, value: str) -> bool:
        cleaned = re.sub(r"\s+", " ", value).strip()
        lowered = cleaned.lower()
        if not cleaned:
            return True
        if any(phrase in lowered for phrase in DANGLING_FLASHCARD_PHRASES):
            return True
        if re.search(r"\bwhat\s+(?:is|are|does)\s+(?:and|of|to|with)\b", lowered):
            return True
        if re.search(r"\bwhat\s+(?:is|are)\s+(?:also\s+)?assume\b", lowered):
            return True
        if re.search(r"\bwhat\s+are\s+two\s+events\?", lowered):
            return True
        if re.search(r"\bwhat\s+is\s+use\s+the\s+t-test\b", lowered):
            return True
        if re.search(r"\bwhat\s+are\s+each\s+of\s+these\s+assumptions\?", lowered):
            return True
        if re.search(r"\bwhat\s+are\s+a\s+parametric\s+model\s+typically\s+assumes\b", lowered):
            return True
        if re.search(r"\bwhat\s+is\s+a\s+positive\s+butterfly\s+means\b", lowered):
            return True
        if re.search(r"\bwhat\s+are\s+sometimes\s+we\?", lowered):
            return True
        if re.search(r"\bwhat\s+are\s+note(?:\s+also)?\s+that\b", lowered):
            return True
        if re.search(r"\bwhat\s+do\s+sequence\s+of\s+random\s+variables\s+include\?", lowered):
            return True
        if re.search(r"\bwhat\s+are\s+variables\?", lowered):
            return True
        if re.search(r"\bwhat\s+(?:is|are).*?\bassume\s+that\b", lowered):
            return True
        if re.search(r"\bwhat\s+(?:is|are)\s+also\b", lowered):
            return True
        if re.search(
            r"\bwhat\s+(?:is|are)\s+(?:these|there|when|another option|"
            r"that|those|this|it|one|possible|following|if|such|because|given|suppose|assume|some)\b",
            lowered,
        ):
            return True
        if re.search(r"\bwhat\s+(?:is|are)\s+(?:payment|payments|countries)\?", lowered):
            return True
        if re.search(r"\bwhat\s+are\s+if\b", lowered):
            return True
        if re.search(r"\bwhat\s+are\s+not\s+all\b", lowered):
            return True
        if re.search(r"\bwhat\s+is\s+a\s+special\s+type\s+of\b", lowered):
            return True
        if re.search(r"\bwhat\s+(?:is|are)\s+(?:var and|banks should|while the)\b", lowered):
            return True
        if re.search(r"\bwhat\s+is\s+\w+\s+(?:have|has|with)\s+\w+\b", lowered):
            return True
        if re.search(r"\bhow does .{1,160}\brelate to\b .{1,160}", lowered):
            return True
        if re.search(r"\bwhat does some of\b", lowered):
            return True
        if re.search(r"\bwhat are their goals\b", lowered):
            return True
        if re.search(r"\blo\s*\d+\.[a-z]\b", cleaned, re.IGNORECASE):
            return True
        if re.search(r"\b(?:why|how) does (?:firm|firms|they|line managers right)\b", lowered):
            return True
        if any(fragment in lowered for fragment in ("line managers right", "is usually influenced")):
            return True
        tokens = TOKEN_RE.findall(cleaned)
        if len(tokens) >= 4:
            stop_like = sum(1 for token in tokens if token.lower() in JUNK_STUDY_TERMS)
            if stop_like >= max(2, len(tokens) // 2):
                return True
        return False

    def _build_flashcard(
        self,
        section: SourceSection,
        concept: StudyConceptCard,
        *,
        suffix: str,
        front: str,
        back: str,
        card_type: str,
        source_page: int | None,
    ) -> StudyFlashcard:
        back_concise = self._concise_flashcard_back(back, preserve_list=card_type == "list_recall")
        anchor_type, anchor_text = self._anchor_metadata_for_flashcard(concept, front, card_type)
        source_text_snippet = self._source_text_snippet_for_flashcard(concept, anchor_text)
        page_start, page_end = self._flashcard_page_range(concept, source_page)
        reading_number = self._reading_number_from_section_title(section.section_title)
        module_number = self._module_number_from_section_title(section.section_title)
        lo_code = self._lo_code_from_concept(concept)
        return StudyFlashcard(
            flashcard_id=f"{concept.concept_id}-{suffix}-card",
            bookId=section.material_id,
            course_id=section.course_id,
            material_id=section.material_id,
            module_id=section.module_id,
            learning_outcome_id=concept.related_original_key_concept_id,
            concept_id=concept.concept_id,
            studySession=self._study_session_from_section_title(section.section_title),
            readingNumber=reading_number,
            moduleNumber=module_number,
            loCode=lo_code,
            pageStart=page_start,
            pageEnd=page_end,
            anchorType=anchor_type,
            anchorText=anchor_text,
            sourceTextSnippet=source_text_snippet,
            front=front,
            back=back_concise,
            back_concise=back_concise,
            card_type=card_type,
            tags=self._flashcard_tags(
                reading_number=reading_number,
                module_number=module_number,
                lo_code=lo_code,
                anchor_text=anchor_text,
            ),
            qualityScore=self._flashcard_quality_score(
                front=front,
                back=back_concise,
                source_text_snippet=source_text_snippet,
                anchor_text=anchor_text,
            ),
            sourceHash=self._flashcard_source_hash(
                material_id=section.material_id,
                concept_id=concept.concept_id,
                front=front,
                source_text_snippet=source_text_snippet,
            ),
            source_page=source_page,
            source_excerpt=concept.source_excerpt,
            difficulty=concept.difficulty_level,
        )

    def _anchor_metadata_for_flashcard(
        self,
        concept: StudyConceptCard,
        front: str,
        card_type: str,
    ) -> tuple[str | None, str | None]:
        anchors = self._card_anchors_for_concept(concept)
        contextual_anchor = self._contextual_anchor_from_flashcard_front(concept, front)
        if not anchors:
            if contextual_anchor:
                return contextual_anchor
            topic = self._clean_flashcard_topic(concept)
            return ("key_concept", topic) if topic else (None, None)

        front_lower = front.lower()
        preferred_by_type = {
            "definition": {"bold_term", "key_concept", "lo_heading"},
            "formula": {"formula", "bold_term", "key_concept"},
            "list_recall": {"process", "key_concept", "lo_heading"},
            "comparison": {"comparison", "bold_term", "key_concept"},
            "exam_trap": {"exam_trap", "bold_term", "key_concept"},
            "application": {"bold_term", "key_concept", "lo_heading"},
        }
        for anchor_type, anchor_text in anchors:
            lowered = anchor_text.lower()
            if lowered and lowered in front_lower:
                return anchor_type, anchor_text
            if lowered.startswith("value at risk") and "value at risk" in front_lower:
                return anchor_type, anchor_text
            if lowered in {"garp code of conduct", "code of conduct"} and "code of conduct" in front_lower:
                return anchor_type, anchor_text
        if contextual_anchor:
            return contextual_anchor
        preferred = preferred_by_type.get(card_type, {"key_concept", "bold_term", "lo_heading"})
        for anchor_type, anchor_text in anchors:
            if anchor_type in preferred:
                return anchor_type, anchor_text
        return anchors[0]

    def _contextual_anchor_from_flashcard_front(
        self,
        concept: StudyConceptCard,
        front: str,
    ) -> tuple[str, str] | None:
        cleaned_front = re.sub(r"\s+", " ", front).strip().rstrip("?")
        candidates: list[str] = []
        patterns = (
            r"^What is (?P<subject>.+)$",
            r"^What are (?P<subject>.+)$",
            r"^When does (?P<subject>.+?) occur$",
            r"^What inputs does (?P<subject>.+?) use$",
            r"^What does (?P<subject>.+?) "
            r"(?:measure|include|use|allow|penalize|estimate|model|compare|indicate|provide|explain|give|count)$",
            r"^How is (?P<subject>.+?) estimated$",
            r"^When is (?P<subject>.+?) used$",
        )
        for pattern in patterns:
            match = re.match(pattern, cleaned_front, re.IGNORECASE)
            if match:
                candidates.append(match.group("subject"))
        context = " ".join(
            item
            for item in [
                concept.title,
                concept.learning_outcome or "",
                " ".join(concept.key_terms),
                concept.source_excerpt,
            ]
            if item
        )
        for candidate in candidates:
            candidate = re.sub(r"\s+in\s+(?:regression|probability|finance|markets?)$", "", candidate, flags=re.IGNORECASE)
            candidate = re.sub(r"^(?:a|an|the)\s+", "", candidate.strip(), flags=re.IGNORECASE)
            cleaned = self._clean_flashcard_term(candidate)
            if self._is_contextual_flashcard_subject(cleaned, context):
                return "bold_term", cleaned
        return None

    def _source_text_snippet_for_flashcard(self, concept: StudyConceptCard, anchor_text: str | None) -> str:
        excerpt = re.sub(r"\s+", " ", concept.source_excerpt).strip()
        if not excerpt:
            return ""
        if anchor_text and anchor_text.lower() not in {"numbered process", "formula block", "compare contrast", "exam trap"}:
            for sentence in self._sentences(excerpt):
                if anchor_text.lower() in sentence.lower():
                    return sentence[:700].strip()
        sentence = self._first_meaningful_sentence(excerpt)
        return (sentence or excerpt)[:700].strip()

    def _flashcard_page_range(self, concept: StudyConceptCard, source_page: int | None) -> tuple[int | None, int | None]:
        pages = [page for page in concept.source_pages if page is not None]
        if pages:
            return min(pages), max(pages)
        return source_page, source_page

    def _study_session_from_section_title(self, title: str) -> str | None:
        match = WORKBOOK_MODULE_TITLE_RE.match(title)
        if match:
            return f"Study Session {match.group('session_number')}"
        fallback = re.search(r"\bStudy Session\s+(?P<number>\d+)\b", title, re.IGNORECASE)
        if fallback:
            return f"Study Session {fallback.group('number')}"
        return None

    def _module_number_from_section_title(self, title: str) -> str | None:
        match = WORKBOOK_MODULE_TITLE_RE.match(title)
        if match:
            return match.group("module_number")
        fallback = re.search(r"\bModule\s+(?P<number>\d+(?:\.[0-9A-Za-z]+)*)\b", title, re.IGNORECASE)
        return fallback.group("number") if fallback else None

    def _lo_code_from_concept(self, concept: StudyConceptCard) -> str | None:
        value = " ".join(
            item
            for item in [concept.learning_outcome or "", concept.source_excerpt]
            if item
        )
        match = re.search(r"\bLO\s*(?P<number>\d+)\.?(?P<letter>[a-z])\b", value, re.IGNORECASE)
        if not match:
            return None
        return f"LO {match.group('number')}.{match.group('letter').lower()}"

    def _flashcard_tags(
        self,
        *,
        reading_number: int | None,
        module_number: str | None,
        lo_code: str | None,
        anchor_text: str | None,
    ) -> list[str]:
        tags: list[str] = []
        if reading_number is not None:
            tags.append(f"Reading {reading_number}")
        if module_number:
            tags.append(f"Module {module_number}")
        if lo_code:
            tags.append(lo_code)
        if anchor_text and anchor_text.lower() not in {"numbered process", "formula block", "compare contrast", "exam trap"}:
            tags.append(anchor_text)
        return list(dict.fromkeys(tags))

    def _flashcard_quality_score(
        self,
        *,
        front: str,
        back: str,
        source_text_snippet: str,
        anchor_text: str | None,
    ) -> float:
        score = 1.0
        if GENERIC_FLASHCARD_FRONT_RE.search(front) or self._is_phrase_soup(front):
            score -= 0.5
        if not anchor_text:
            score -= 0.2
        if not source_text_snippet:
            score -= 0.2
        if len(back.split()) > 40:
            score -= 0.1
        return max(0.0, round(score, 2))

    def _flashcard_source_hash(
        self,
        *,
        material_id: str,
        concept_id: str | None,
        front: str,
        source_text_snippet: str,
    ) -> str:
        payload = "\n".join([material_id, concept_id or "", front, source_text_snippet])
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _concise_flashcard_back(self, text: str, *, preserve_list: bool = False) -> str:
        if preserve_list:
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            numbered_lines = [line for line in lines if re.match(r"^\d+[.)]\s+", line)]
            if numbered_lines:
                return "\n".join(numbered_lines[:6])
            if lines:
                return "\n".join(lines[:6])
        cleaned = re.sub(r"\s+", " ", text).strip()
        cleaned = re.sub(r"^\s*LO\s+\d+\.[a-z]\s*", "", cleaned, flags=re.IGNORECASE)
        sentences = self._sentences(cleaned)
        answer = sentences[0].strip() if sentences else cleaned
        words = answer.split()
        if len(words) > 32:
            answer = " ".join(words[:32]).rstrip(" ,;:") + "."
        if answer and answer[-1] not in ".!?":
            answer += "."
        return answer

    def _flashcard_semantic_key(self, card: StudyFlashcard) -> str:
        namespace_parts = [
            card.material_id or "",
            card.module_id or "",
        ]
        if card.card_type == "formula" and card.formula_id:
            namespace_parts.append(card.formula_id)
        namespace = "|".join(namespace_parts)
        definition_subject = self._definition_subject_from_front(card.front)
        if definition_subject:
            canonical_subject = self._canonical_flashcard_definition_subject(definition_subject)
            return f"{namespace}:definition:{canonical_subject}"
        normalized_front = re.sub(r"\W+", " ", card.front.lower()).strip()
        normalized_front = self._canonical_flashcard_front_key(normalized_front)
        return f"{namespace}:{normalized_front}"

    def _canonical_flashcard_front_key(self, normalized_front: str) -> str:
        cleaned = re.sub(r"\s+", " ", normalized_front.lower().strip())
        cleaned = re.sub(
            r"\bwhat does regression analysis (?:seek|seeks|attempt|attempts) to measure\b",
            "what does regression analysis measure",
            cleaned,
        )
        cleaned = re.sub(
            r"\bwhat does (?P<subject>[a-z][a-z\s]{3,80}?) "
            r"(?:seek|seeks|attempt|attempts) to (?P<verb>measure|model|estimate|explain)\b",
            lambda match: f"what does {match.group('subject').strip()} {match.group('verb')}",
            cleaned,
        )
        return cleaned

    def _definition_subject_from_front(self, front: str) -> str | None:
        cleaned = re.sub(r"\s+", " ", front).strip().rstrip("?!.")
        match = re.match(r"^what\s+(?:is|are)\s+(?P<subject>.+)$", cleaned, re.IGNORECASE)
        if not match:
            return None
        subject = re.sub(r"^(?:a|an|the)\s+", "", match.group("subject").strip(), flags=re.IGNORECASE)
        subject = self._clean_flashcard_term(subject)
        return subject.lower() if subject else None

    def _canonical_flashcard_definition_subject(self, subject: str) -> str:
        cleaned = re.sub(r"\s+", " ", subject.lower().strip())
        cleaned = re.sub(r"\bmortgage\s+backed\b", "mortgage-backed", cleaned)
        return self._strip_flashcard_domain_qualifier(cleaned)

    def _strip_flashcard_domain_qualifier(self, subject: str) -> str:
        cleaned = re.sub(r"\s+", " ", subject.lower().strip())
        stripped = re.sub(
            r"\s+(?:in|within|for|from|on)\s+"
            r"(?:mutual funds?|futures markets?|mortgage-backed securities|"
            r"mortgage backed securities|commodity markets?|commodities|"
            r"options?|credit risk|risk management|capital markets)$",
            "",
            cleaned,
            flags=re.IGNORECASE,
        ).strip()
        return stripped or cleaned

    def _flashcard_domain_specificity_score(self, card: StudyFlashcard) -> float:
        score = float(card.quality_score or 0)
        subject = self._definition_subject_from_front(card.front) or ""
        if subject:
            canonical = self._canonical_flashcard_definition_subject(subject)
            token_count = len([token for token in TOKEN_RE.findall(subject) if token.lower() not in CONTENT_ANCHOR_STOPWORDS])
            score += min(token_count, 8) * 0.03
            if card.card_type == "definition":
                score += 0.08
            if re.match(r"^\s*what\s+is\s+(?:a|an)\s+", card.front, re.IGNORECASE):
                score += 0.08
            if card.card_type == "application":
                score -= 0.04
            if canonical != subject:
                score += 0.35
            if re.search(
                r"\b(?:mutual funds?|futures markets?|mortgage-backed securit(?:y|ies)|"
                r"commodity markets?|commodities|covered calls?|uncovered calls?)\b",
                subject,
                re.IGNORECASE,
            ):
                score += 0.2
            if len(TOKEN_RE.findall(canonical)) <= 1 and canonical not in {"risk", "beta", "basis"}:
                score -= 0.12
        if card.card_type in {"comparison", "application", "exam_trap", "formula", "list_recall"}:
            score += 0.05
        return score

    def _singularize_flashcard_subject(self, subject: str) -> str:
        tokens = re.sub(r"\s+", " ", subject.lower().strip()).split()
        if not tokens:
            return ""
        last = tokens[-1].strip(".,;:")
        singular_exceptions = {
            "analysis",
            "basis",
            "business",
            "class",
            "cash",
            "loss",
            "process",
            "risk",
            "series",
            "stress",
        }
        if last not in singular_exceptions:
            if last.endswith("ies") and len(last) > 4:
                tokens[-1] = last[:-3] + "y"
            elif last.endswith("s") and not last.endswith("ss") and len(last) > 3:
                tokens[-1] = last[:-1]
        return " ".join(tokens)

    def _subject_looks_plural(self, subject: str) -> bool:
        cleaned = re.sub(r"^(?:a|an|the)\s+", "", subject.lower().strip(), flags=re.IGNORECASE)
        tokens = cleaned.split()
        if not tokens:
            return False
        last = tokens[-1].strip(".,;:")
        singular_exceptions = {
            "analysis",
            "basis",
            "business",
            "class",
            "cash",
            "loss",
            "process",
            "risk",
            "series",
            "stress",
        }
        return last.endswith("s") and not last.endswith("ss") and last not in singular_exceptions

    def _is_ungrammatical_plural_definition_front(self, front: str) -> bool:
        if self._is_allowed_domain_definition_front(front):
            return False
        if re.match(r"^\s*what\s+is\s+a\s+common\s+exam\s+trap\s+about\b", front, re.IGNORECASE):
            return bool(GENERIC_FLASHCARD_FRONT_RE.search(front))
        if re.match(r"^\s*what\s+is\s+(?:the\s+)?(?:key\s+)?difference\s+between\b", front, re.IGNORECASE):
            return False
        match = re.match(
            r"^\s*what\s+is\s+(?:a|an|the)?\s*(?P<subject>.+?)\?\s*$",
            front,
            re.IGNORECASE,
        )
        return bool(match and self._subject_looks_plural(match.group("subject")))

    def _valid_unique_flashcards(self, cards: list[StudyFlashcard], *, limit: int) -> list[StudyFlashcard]:
        best_by_key: dict[str, StudyFlashcard] = {}
        order: list[str] = []
        for card in cards:
            if not self._is_valid_generated_flashcard(card):
                continue
            key = self._flashcard_semantic_key(card)
            existing = best_by_key.get(key)
            if existing is None:
                best_by_key[key] = card
                order.append(key)
                continue
            if self._flashcard_domain_specificity_score(card) > self._flashcard_domain_specificity_score(existing):
                best_by_key[key] = card
        return [best_by_key[key] for key in order[:limit]]

    def _is_valid_generated_flashcard(self, card: StudyFlashcard) -> bool:
        return not self._flashcard_quality_flags(card)

    def _flashcard_quality_flags(self, card: StudyFlashcard) -> list[str]:
        flags: list[str] = []
        if GENERIC_FLASHCARD_FRONT_RE.search(card.front) and not self._is_allowed_domain_definition_front(card.front):
            flags.append("generic_question")
        if self._is_phrase_soup(card.front):
            flags.append("generic_question")
        if not card.front.strip().endswith("?"):
            flags.append("generic_question")
        if self._is_ungrammatical_plural_definition_front(card.front):
            flags.append("generic_question")
        if re.search(
            r"\bwhat\s+(?:is|are)\s+(?:event is|of the|all the|the following conditions|random event|if a time series|such a time series|if the observations|also assume|assume that|also)\b",
            card.front,
            re.IGNORECASE,
        ):
            flags.append("generic_question")
        if re.search(r"\bwhat\s+(?:is|are)\s+(?:and|or)\b", card.front, re.IGNORECASE):
            flags.append("generic_question")
        if re.search(
            r"\bwhat\s+(?:is|are)\s+(?:specifies that|specified that)\b",
            card.front,
            re.IGNORECASE,
        ):
            flags.append("generic_question")
        if re.search(r"\bwhat\s+does\b[^?]*\bseeks\s+to\b", card.front, re.IGNORECASE):
            flags.append("generic_question")
        if re.search(
            r"\bwhat\s+(?:is|are)\s+(?:late trading occurs|market timing occurs|so portfolio currency risk)\b",
            card.front,
            re.IGNORECASE,
        ):
            flags.append("generic_question")
        if re.search(
            r"\bwhat\s+(?:is|are)\s+(?:two events|use the t-test|each of these assumptions|"
            r"a parametric model typically assumes|a positive butterfly means)\b",
            card.front,
            re.IGNORECASE,
        ):
            flags.append("generic_question")
        if re.search(
            r"\bwhat\s+(?:is|are)\s+(?:models|quotes|spot quotes|because|so\b|answer\b|order\b|a\s+less\s+costly\s+alternative\b)\??\s*$",
            card.front,
            re.IGNORECASE,
        ):
            flags.append("generic_question")
        if re.search(r"\bwhat\s+(?:is|are)\s+trading\?\s*$", card.front, re.IGNORECASE):
            flags.append("generic_question")
        if re.search(
            r"\bwhat\s+(?:is|are)\s+(?:borrowers|correlations|(?:no\s+)?payments?|premiums?|coverage|benefits?)\?\s*$",
            card.front,
            re.IGNORECASE,
        ):
            flags.append("generic_question")
        if re.search(
            r"\bwhat\s+does\s+(?:credit\s+portfolio\s+model|portfolio\s+model|model)\?\s*$",
            card.front,
            re.IGNORECASE,
        ):
            flags.append("generic_question")
        if re.search(
            r"\bwhat\s+(?:is|are)\s+(?:also\s+assume|assume\s+that|because\s+option\s+contracts|answer\s+because)",
            card.front,
            re.IGNORECASE,
        ):
            flags.append("generic_question")
        if re.search(r"\bwhat\s+(?:is|are).*?\bassume\s+that\b", card.front, re.IGNORECASE):
            flags.append("generic_question")
        if re.search(r"\b(\w+)\s+\1\b", card.front, re.IGNORECASE):
            flags.append("generic_question")
        if not card.source_page:
            flags.append("missing_source_page")
        if not card.learning_outcome_id and not card.formula_id:
            flags.append("missing_learning_outcome_link")
        if not card.concept_id and card.card_type != "formula":
            flags.append("missing_concept_link")
        if card.card_type == "formula" and "=" not in card.back:
            flags.append("formula_without_formula")
        if len(card.front.split()) < 3:
            flags.append("generic_question")
        answer = (card.back_concise or card.back).strip()
        if len(answer.split()) < 2:
            flags.append("low_parse_confidence")
        if answer.strip().lower().rstrip(".?!") == card.front.strip().lower().rstrip(".?!"):
            flags.append("low_parse_confidence")
        if self._same_flashcard_text(answer, card.source_excerpt):
            flags.append("answer_is_source_excerpt")
        if card.card_type != "list_recall" and self._answer_sentence_count(answer) > 3:
            flags.append("answer_too_long")
        if not self._front_has_content_anchor(card):
            flags.append("missing_content_anchor")
        return list(dict.fromkeys(flags))

    def _is_allowed_domain_definition_front(self, front: str) -> bool:
        subject = self._definition_subject_from_front(front)
        if not subject:
            return False
        if subject in {"risk management process"}:
            return False
        if re.search(
            r"\b(?:late trading|market timing|basis|prepayment risk|mortgage-backed security|"
            r"futures contract|covered calls?|uncovered calls?|convenience yield|carry market|"
            r"duration gap|convexity|yield curve|spot rate|forward rate)\b",
            subject,
            re.IGNORECASE,
        ):
            return True
        return False

    def _same_flashcard_text(self, answer: str, source_excerpt: str) -> bool:
        if not answer or not source_excerpt:
            return False
        normalized_answer = re.sub(r"\s+", " ", answer).strip().lower()
        normalized_source = re.sub(r"\s+", " ", source_excerpt).strip().lower()
        if len(normalized_source.split()) <= 12:
            return False
        return bool(normalized_answer and normalized_answer == normalized_source)

    def _answer_sentence_count(self, answer: str) -> int:
        if not answer.strip():
            return 0
        numbered_lines = [line for line in answer.splitlines() if re.match(r"^\s*\d+[.)]\s+", line)]
        if numbered_lines:
            return 1
        return len(self._sentences(answer.replace("\n", " ")))

    def _front_has_content_anchor(self, card: StudyFlashcard) -> bool:
        front = card.front.lower()
        source = " ".join(
            value
            for value in [
                card.source_excerpt,
                card.back_concise or card.back,
            ]
            if value
        ).lower()
        if card.formula_id and ("formula" in front or "=" in source):
            return True
        definition_subject = self._definition_subject_from_front(card.front)
        if definition_subject and self._flashcard_subject_supported_by_source(definition_subject, source):
            return True
        for term in FINANCE_ACADEMIC_TERMS:
            if term in front:
                return True
        source_tokens = {
            token.lower()
            for token in TOKEN_RE.findall(source)
            if token.lower() not in CONTENT_ANCHOR_STOPWORDS and len(token) >= 4
        }
        front_tokens = {
            token.lower()
            for token in TOKEN_RE.findall(front)
            if token.lower() not in CONTENT_ANCHOR_STOPWORDS and len(token) >= 4
        }
        return bool(source_tokens & front_tokens)

    def _flashcard_subject_supported_by_source(self, subject: str, source: str) -> bool:
        normalized_source = re.sub(r"[^a-z0-9]+", " ", source.lower()).strip()
        if not normalized_source:
            return False
        variants = {
            subject.lower().strip(),
            self._singularize_flashcard_subject(subject),
            self._canonical_flashcard_definition_subject(subject),
            self._singularize_flashcard_subject(self._canonical_flashcard_definition_subject(subject)),
        }
        for variant in variants:
            cleaned = re.sub(r"[^a-z0-9]+", " ", variant.lower()).strip()
            if len(cleaned) < 4:
                continue
            if re.search(rf"\b{re.escape(cleaned)}\b", normalized_source):
                return True
        return False

    def _reading_number_from_section_title(self, title: str) -> int | None:
        match = WORKBOOK_MODULE_TITLE_RE.match(title)
        if not match:
            return None
        try:
            return int(match.group("reading_number"))
        except (TypeError, ValueError):
            return None

    def _section_source_pages(self, section: SourceSection) -> list[int]:
        page_start = section.locator.page_number
        page_end = section.page_end or page_start
        if page_start is None:
            return []
        if page_end is None or page_end < page_start:
            return [page_start]
        return list(range(page_start, page_end + 1))

    def _concept_title_from_key_concept(self, content: str, *, fallback: str) -> str:
        for line in content.splitlines():
            stripped = line.strip()
            if not stripped or re.match(
                r"^(?:LO\s+\d+\.[a-z]|(?:Learning\s+Objective|Objective)\s*:?.+)$",
                stripped,
                re.IGNORECASE,
            ):
                continue
            sentence = self._first_meaningful_sentence(stripped)
            if sentence:
                words = [
                    word.strip(".,;:()[]")
                    for word in sentence.split()
                    if len(word.strip(".,;:()[]")) > 3
                ]
                title = " ".join(words[:5]).strip()
                if title:
                    return title[:80]
        return fallback

    def _first_meaningful_sentence(self, text: str) -> str:
        for sentence in self._sentences(text.replace("\n", " ")):
            sentence = sentence.strip()
            if sentence and not re.match(
                r"^(?:LO\s+\d+\.[a-z]|(?:Learning\s+Objective|Objective)\s*:?.+)$",
                sentence,
                re.IGNORECASE,
            ):
                return sentence
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return next(
            (
                line
                for line in lines
                if not re.match(
                    r"^(?:LO\s+|Learning\s+Objective\b|Objective\s*:)",
                    line,
                    re.IGNORECASE,
                )
            ),
            "",
        )

    def _terms_from_text(self, text: str, *, limit: int) -> list[str]:
        candidates: list[str] = []
        for match in re.finditer(
            r"\b[A-Z][A-Za-z]*(?:\s+[A-Z][A-Za-z]*){0,3}\b|\b[a-z][a-z]+(?:\s+[a-z][a-z]+){1,2}\b",
            text,
        ):
            term = " ".join(match.group(0).split()).strip(" .,:;")
            if not term or self._is_junk_workbook_keyword(term):
                continue
            if len(term.split()) == 1 and len(term) < 5:
                continue
            candidates.append(self._title_case_term(term))
        return self._unique_items(candidates, limit=limit)

    def _trap_sentences_from_text(self, text: str) -> list[str]:
        markers = ("not ", "except", "however", "avoid", "careful", "conflict", "unexpected")
        traps = [
            sentence
            for sentence in self._sentences(text.replace("\n", " "))
            if any(marker in sentence.lower() for marker in markers)
        ]
        return self._quality_points(traps, "original book concept", limit=3)

    def _formula_like_lines(self, content: str) -> list[str]:
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        formula_lines: list[str] = []
        for line in lines:
            if re.match(r"^\d+\.\s+\S+", line):
                formula_lines.append(line)
                continue
            if re.search(r"\b(?:formula|equation|equals|sum|divide|calculate)\b|[A-Za-z]\s*(?:=|<=|>=|<|>)\s*[-+A-Za-z0-9(]", line, re.IGNORECASE):
                formula_lines.append(line)
        return self._unique_items(formula_lines, limit=8)

    def _normalize_workbook_display_line(self, value: str) -> str:
        replacements = {
            "\ufb00": "ff",
            "\ufb01": "fi",
            "\ufb02": "fl",
            "\ufb03": "ffi",
            "\ufb04": "ffl",
        }
        for bad, good in replacements.items():
            value = value.replace(bad, good)
        value = re.sub(r"\s+", " ", value).strip()
        value = re.sub(r"\b([A-D])\.\s+", r"\1. ", value)
        return value

    def _workbook_summary(
        self,
        section: SourceSection,
        blocks: dict[str, list[str]],
        fallback: str,
    ) -> str:
        candidates = blocks.get("key_concepts", [])
        if not candidates:
            candidates = blocks.get("exam_focus", [])
        text = self._clean_workbook_block_text(candidates)
        sentences = [
            sentence
            for sentence in self._sentences(text)
            if 5 <= len(sentence.split()) <= 42 and not self._is_low_value_text(sentence)
        ]
        if not sentences:
            return self._summary(section, fallback)
        return " ".join(sentences[:3])[:520].strip()

    def _workbook_key_points(
        self,
        blocks: dict[str, list[str]],
        normalized_title: str,
    ) -> list[str]:
        text = self._clean_workbook_block_text(blocks.get("key_concepts", []))
        points = [
            sentence
            for sentence in self._sentences(text)
            if self._is_good_workbook_concept_sentence(sentence)
        ]
        return self._quality_points(points, normalized_title, limit=6)

    def _workbook_keywords(
        self,
        section: SourceSection,
        blocks: dict[str, list[str]],
        normalized_title: str,
    ) -> list[str]:
        concept_text = self._clean_workbook_block_text(blocks.get("key_concepts", []))
        module_match = WORKBOOK_MODULE_TITLE_RE.match(section.section_title)
        title_context = normalized_title
        if module_match:
            title_context = "\n".join(
                [
                    module_match.group("reading_title").strip(),
                    module_match.group("module_title").strip(),
                ]
            )
        source_text = f"{title_context}\n{concept_text}"
        lowered = source_text.lower()
        candidates: list[str] = []

        if module_match:
            candidates.append(module_match.group("module_title").strip())

        for phrase in FRM_MEMORIZE_PHRASES:
            if phrase in lowered:
                candidates.append(self._title_case_term(phrase))

        for match in re.finditer(
            r"\b(?:risk|financial|market|credit|liquidity|operational|interest|foreign|cyber|"
            r"board|corporate|management|hedging|derivative|portfolio|governance)\s+"
            r"[a-z][a-z-]+(?:\s+[a-z][a-z-]+)?\b",
            lowered,
        ):
            candidates.append(self._title_case_term(match.group(0)))

        return self._unique_items(
            [
                candidate
                for candidate in candidates
                if not self._is_junk_workbook_keyword(candidate)
            ],
            limit=10,
        )

    def _workbook_formulas(self, blocks: dict[str, list[str]]) -> list[str]:
        return self._unique_items(
            [
                formula
                for _formula_name, formula, _reading_number in self._parse_workbook_formula_lines(
                    blocks.get("formulas", [])
                )
            ],
            limit=8,
        )

    def _parse_workbook_formula_lines(self, lines: list[str]) -> list[tuple[str | None, str, int | None]]:
        entries: list[tuple[str | None, str, int | None]] = []
        seen: set[str] = set()
        active_reading_number: int | None = None
        for raw_line in lines:
            line = " ".join(raw_line.split()).strip(" -;")
            if not line or line.upper() == "FORMULAS":
                continue
            reading_match = re.match(r"^Reading\s+(?P<number>\d+)\b", line, re.IGNORECASE)
            if reading_match:
                active_reading_number = int(reading_match.group("number"))
                continue
            if FORMULA_IMAGE_CROP_RE.match(line):
                continue
            if re.match(r"^\d+\.\s+", line):
                continue
            label_match = FORMULA_LABEL_RE.match(line)
            if label_match:
                formula_name = self._normalize_formula_label(label_match.group("name").strip())
                formula_text = label_match.group("formula").strip()
            else:
                if "=" not in line:
                    continue
                formula_name = None
                formula_text = line
            formula_text = self._format_code_or_rule(formula_text)
            if not self._looks_like_verified_formula(formula_text):
                continue
            key = formula_text.lower()
            if key in seen:
                continue
            seen.add(key)
            entries.append((formula_name, formula_text, active_reading_number))
        return entries

    def _parse_workbook_formula_image_crops(self, lines: list[str]) -> list[dict[str, object]]:
        entries: list[dict[str, object]] = []
        seen: set[str] = set()
        for raw_line in lines:
            line = " ".join(raw_line.split()).strip()
            match = FORMULA_IMAGE_CROP_RE.match(line)
            if not match:
                continue
            path = match.group("path")
            if path in seen:
                continue
            seen.add(path)
            entries.append(
                {
                    "source_page": int(match.group("page")),
                    "path": path,
                    "label": match.group("label"),
                }
            )
        return entries

    def _normalize_formula_label(self, label: str) -> str:
        cleaned = " ".join(label.split()).strip(" :-")
        lowered = cleaned.lower()
        known_labels = {
            "expected loss": "Expected loss",
            "capital asset pricing model": "Capital asset pricing model",
            "risk-adjusted return on capital": "Risk-adjusted return on capital",
        }
        if lowered in known_labels:
            return known_labels[lowered]
        return self._title_case_term(cleaned)

    def _looks_like_verified_formula(self, formula_text: str) -> bool:
        if "=" not in formula_text:
            return False
        if re.match(r"^\d+\.\s+", formula_text):
            return False
        left_side = formula_text.split("=", 1)[0].strip()
        if not left_side or len(left_side.split()) > 8:
            return False
        return bool(
            re.search(r"[A-Za-zβσρμ]", formula_text)
            or re.search(r"\b(?:E\(|Cov|Var)\b", formula_text)
        )

    def _formula_name_from_text(self, formula_text: str) -> str:
        lowered = formula_text.lower()
        if re.search(r"\bel\s*=", lowered):
            return "Expected loss"
        if "ead" in lowered and "pd" in lowered and "lgd" in lowered:
            return "Expected loss"
        if "e(ri)" in lowered or "βi" in formula_text or "beta" in lowered:
            return "Capital asset pricing model"
        if "raroc" in lowered:
            return "Risk-adjusted return on capital"
        left_side = formula_text.split("=", 1)[0].strip()
        if left_side:
            return self._title_case_term(left_side)
        return "Formula"

    def _variables_from_formula(self, formula_text: str) -> dict[str, str]:
        known_variables = [
            ("EAD", "Exposure at default"),
            ("PD", "Probability of default"),
            ("LGD", "Loss given default"),
            ("EL", "Expected loss"),
            ("RAROC", "Risk-adjusted return on capital"),
            ("RF", "Risk-free rate"),
            ("RM", "Market return"),
            ("Ri", "Return on asset i"),
            ("Rp", "Portfolio return"),
            ("βi", "Beta of asset i"),
            ("σM", "Standard deviation of market return"),
            ("σP", "Standard deviation of portfolio return"),
            ("Covi,M", "Covariance between asset i and the market"),
            ("ρi,M", "Correlation between asset i and the market"),
        ]
        normalized_formula = formula_text.replace("β", "β").replace("σ", "σ").replace("ρ", "ρ")
        found: dict[str, str] = {}
        for variable, meaning in known_variables:
            if re.search(r"[A-Za-z]", variable):
                pattern = rf"(?<![A-Za-z]){re.escape(variable)}(?![A-Za-z])"
                if re.search(pattern, normalized_formula, re.IGNORECASE):
                    found[variable] = meaning
                    continue
            if variable in normalized_formula:
                found[variable] = meaning
        return found

    def _workbook_traps(
        self,
        blocks: dict[str, list[str]],
        normalized_title: str,
    ) -> list[str]:
        text = self._clean_workbook_block_text(
            [*blocks.get("key_concepts", []), *blocks.get("answer_key", [])]
        )
        trap_markers = [
            "not",
            "rather than",
            "instead",
            "except",
            "however",
            "distinguish",
            "conflict",
            "scenario",
            "mistake",
        ]
        candidates: list[str] = []
        for sentence in self._sentences(text):
            cleaned = re.sub(r"^\d+\.\s+[A-D]\s+", "", sentence).strip()
            cleaned = re.sub(r"^[A-D]\s+[A-D]\s+", "", cleaned).strip()
            cleaned = re.sub(r"^[A-D]\s+(?=[A-Z])", "", cleaned).strip()
            lowered = cleaned.lower()
            if not cleaned or self._is_low_value_text(cleaned):
                continue
            if re.search(r"\bwhich of the following\b|\bmodule quiz\b|\banswer key\b", lowered):
                continue
            if re.search(r"\blo\s+\d+\.[a-z]\b|\bkey concepts\b", lowered):
                continue
            if any(marker in lowered for marker in trap_markers):
                candidates.append(cleaned)

        return self._quality_points(candidates, normalized_title, limit=4)

    def _clean_workbook_block_text(self, lines: list[str]) -> str:
        cleaned: list[str] = []
        merging_numbered_list = False

        def finish_numbered_list() -> None:
            nonlocal merging_numbered_list
            if merging_numbered_list and cleaned and cleaned[-1] and cleaned[-1][-1] not in ".!?":
                cleaned[-1] = f"{cleaned[-1]}."
            merging_numbered_list = False

        for line in lines:
            stripped = " ".join(line.split()).strip()
            if not stripped:
                continue
            if re.match(r"^LO\s+\d+\.[a-z]\b", stripped, re.IGNORECASE):
                stripped = self._strip_workbook_learning_objective_prefix(stripped)
                if not stripped:
                    continue
            if re.match(r"^MODULE\s+QUIZ\s+\d+(?:\.\d+)*\b", stripped, re.IGNORECASE):
                continue
            if re.match(r"^\d+\.\s+", stripped) and "?" in stripped:
                continue
            if re.match(r"^[A-D]\.\s+", stripped):
                continue
            numbered_item = re.match(r"^\d+\.\s+(?P<item>.+)$", stripped)
            if numbered_item:
                item = numbered_item.group("item").strip().rstrip(".")
                if item and cleaned and (cleaned[-1].endswith(":") or merging_numbered_list):
                    separator = " " if cleaned[-1].endswith(":") else "; "
                    cleaned[-1] = f"{cleaned[-1]}{separator}{item}"
                    merging_numbered_list = True
                    continue
                stripped = item
            finish_numbered_list()
            cleaned.append(stripped)
        finish_numbered_list()
        return " ".join(cleaned).strip()

    def _strip_workbook_learning_objective_prefix(self, value: str) -> str:
        match = re.match(r"^LO\s+\d+\.[a-z]\b\s*[:.\-]?\s*(?P<body>.*)$", value, re.IGNORECASE)
        if not match:
            return value
        return match.group("body").strip()

    def _is_good_workbook_concept_sentence(self, value: str) -> bool:
        lowered = value.lower()
        if not value or self._is_low_value_text(value):
            return False
        if "module quiz" in lowered or "answer key" in lowered:
            return False
        if re.search(r"\bwhich of the following\b|\b[a-d]\.\s", lowered):
            return False
        if len(value.split()) < 5:
            return False
        return self._has_academic_signal(value) or any(phrase in lowered for phrase in FRM_MEMORIZE_PHRASES)

    def _is_junk_workbook_keyword(self, value: str) -> bool:
        if self._is_junk_term(value):
            return True
        raw_words = [word.lower() for word in re.findall(r"[A-Za-z]+", value)]
        if raw_words and raw_words[-1] in WORKBOOK_KEYWORD_TRAILING_STOP_WORDS:
            return True
        tokens = [token.lower() for token in TOKEN_RE.findall(value)]
        if not tokens:
            return True
        normalized = " ".join(tokens)
        if len(tokens) == 1 and tokens[0] in {"risk", "risks", "process", "could", "they"}:
            return True
        if tokens[-1] in WORKBOOK_KEYWORD_TRAILING_STOP_WORDS:
            return True
        if any(token in {"did", "does", "could", "should", "would", "they"} for token in tokens):
            return True
        if len(tokens) >= 3 and normalized not in set(FRM_MEMORIZE_PHRASES):
            if tokens[-1] in {"events", "exposures", "factor", "factors", "managers", "members"}:
                return True
        return False

    def _title_case_term(self, value: str) -> str:
        return " ".join(
            token.upper() if token.lower() in {"frm", "var"} else token.capitalize()
            for token in value.split()
        )

    def _summary(self, section: SourceSection, fallback: str) -> str:
        sentences = self._sentences(self._clean_academic_text(section.text))
        selected = [
            sentence
            for sentence in sentences
            if 5 <= len(sentence.split()) <= 42 and not self._is_low_value_text(sentence)
        ][:4]
        summary = " ".join(selected[:3]).strip() or fallback.strip()
        if self._is_low_value_text(summary):
            summary = " ".join(self._fallback_key_points(section.text, section.section_title)[:2])
        return summary[:520].strip()

    def _keywords(
        self,
        section: SourceSection,
        concepts: list[KnowledgeConcept],
    ) -> list[str]:
        concept_names = [concept.name for concept in concepts if not self._is_junk_term(concept.name)]
        tokens = [
            token.lower()
            for token in TOKEN_RE.findall(section.text)
            if token.lower() not in self._stop_words() and not self._is_junk_term(token)
        ]
        frequent = [
            token.title()
            for token, _count in Counter(tokens).most_common(16)
            if len(token) > 3
        ]
        return self._unique_items([*concept_names, *frequent], limit=10)

    def _formulas(self, text: str) -> list[str]:
        candidates: list[str] = []
        for raw_line in re.split(r"[\n•●○▪▫]+", text):
            for fragment in self._split_study_fragments(raw_line):
                line = " ".join(fragment.split()).strip(" -;")
                if not line or self._is_low_value_text(line):
                    continue
                if self._looks_like_code_or_rule(line):
                    candidates.append(self._format_code_or_rule(line))
        candidates.extend(
            self._format_code_or_rule(" ".join(match.group(0).split()))
            for match in FORMULA_RE.finditer(text)
        )
        return self._unique_items(candidates, limit=8)

    def _difficulty(
        self,
        text: str,
        key_points: list[str],
        formulas: list[str],
    ) -> StudyDifficulty:
        score = 0
        if len(text) > 2200:
            score += 1
        if len(key_points) >= 4:
            score += 1
        if formulas:
            score += 1
        if score >= 2:
            return StudyDifficulty.HARD
        if score == 1:
            return StudyDifficulty.MEDIUM
        return StudyDifficulty.EASY

    def _hydrate_group_counts(
        self,
        groups: list[MaterialStudyGroup],
        sections: list[MaterialStudySection],
    ) -> list[MaterialStudyGroup]:
        hydrated: list[MaterialStudyGroup] = []
        for group in groups:
            group_sections = [
                section for section in sections if section.parent_group_id == group.group_id
            ]
            hydrated.append(
                group.model_copy(
                    update={
                        "section_count": len(group_sections),
                        "ready_count": sum(1 for section in group_sections if section.quiz_ready),
                        "studied_count": sum(
                            1
                            for section in group_sections
                            if section.studied_status == StudiedStatus.STUDIED
                        ),
                    }
                )
            )
        return hydrated

    def _group_title(self, sections: list[SourceSection], group_number: int) -> str:
        meaningful_titles = [
            cleanSectionDisplayTitle(section.section_title)
            for section in sections
            if not section.section_title.lower().startswith("page ")
        ]
        page_numbers = [section.locator.page_number for section in sections if section.locator.page_number]
        if meaningful_titles:
            return meaningful_titles[0]
        if page_numbers:
            return f"Pages {page_numbers[0]}-{page_numbers[-1]}"
        return f"Study group {group_number}"

    def _workbook_group_title_from_match(self, match: re.Match[str]) -> str:
        return (
            f"Study Session {match.group('session_number')} · "
            f"Reading {match.group('reading_number')}: {match.group('reading_title').strip()}"
        )

    def _build_workbook_groups(
        self,
        material_id: str,
        sections: list[SourceSection],
    ) -> list[MaterialStudyGroup]:
        grouped: dict[tuple[str, str], dict[str, int | str | None]] = {}
        order: list[tuple[str, str]] = []
        for section in sections:
            match = WORKBOOK_MODULE_TITLE_RE.match(section.section_title)
            if not match:
                continue
            key = (match.group("session_number"), match.group("reading_number"))
            page_start = section.locator.page_number
            page_end = section.page_end or page_start
            if key not in grouped:
                grouped[key] = {
                    "title": self._workbook_group_title_from_match(match),
                    "page_start": page_start,
                    "page_end": page_end,
                    "section_count": 1,
                    "ready_count": 1 if self._source_section_is_quiz_ready(section) else 0,
                }
                order.append(key)
                continue

            grouped[key]["section_count"] = int(grouped[key].get("section_count") or 0) + 1
            grouped[key]["ready_count"] = int(grouped[key].get("ready_count") or 0) + (
                1 if self._source_section_is_quiz_ready(section) else 0
            )
            current_start = grouped[key]["page_start"]
            current_end = grouped[key]["page_end"]
            if isinstance(current_start, int) and page_start is not None:
                grouped[key]["page_start"] = min(current_start, page_start)
            elif page_start is not None:
                grouped[key]["page_start"] = page_start
            if isinstance(current_end, int) and page_end is not None:
                grouped[key]["page_end"] = max(current_end, page_end)
            elif page_end is not None:
                grouped[key]["page_end"] = page_end

        groups: list[MaterialStudyGroup] = []
        for index, key in enumerate(order, start=1):
            values = grouped[key]
            stored_page_start = values.get("page_start")
            stored_page_end = values.get("page_end")
            groups.append(
                MaterialStudyGroup(
                    group_id=f"{material_id}-group-{index}",
                    material_id=material_id,
                    title=str(values["title"]),
                    page_start=stored_page_start if isinstance(stored_page_start, int) else None,
                    page_end=stored_page_end if isinstance(stored_page_end, int) else None,
                    display_order=index,
                    section_count=int(values.get("section_count") or 0),
                    ready_count=int(values.get("ready_count") or 0),
                )
            )
        formula_sections = [
            section for section in sections if self._is_formula_source_section(section)
        ]
        if groups and formula_sections:
            page_starts = [
                section.locator.page_number
                for section in formula_sections
                if section.locator.page_number is not None
            ]
            page_ends: list[int] = []
            for formula_section in formula_sections:
                page_end = formula_section.page_end or formula_section.locator.page_number
                if page_end is not None:
                    page_ends.append(page_end)
            groups.append(
                MaterialStudyGroup(
                    group_id=f"{material_id}-formulas",
                    material_id=material_id,
                    title="Formulas",
                    page_start=min(page_starts) if page_starts else None,
                    page_end=max(page_ends) if page_ends else None,
                    display_order=len(groups) + 1,
                    section_count=len(formula_sections),
                    ready_count=sum(
                        1
                        for section in formula_sections
                        if self._formula_source_has_content(section)
                    ),
                )
            )
        return groups

    def _source_section_is_quiz_ready(self, section: SourceSection) -> bool:
        workbook_blocks = self._workbook_support_blocks(section.text)
        return bool(workbook_blocks.get("module_quiz")) or bool(
            re.search(r"\bMODULE\s+QUIZ\s+\d+(?:\.[0-9A-Za-z]+)*\b", section.text, re.IGNORECASE)
        )

    def _normalized_title(
        self,
        section: SourceSection,
        knowledge: SectionKnowledge,
    ) -> str:
        workbook_match = WORKBOOK_MODULE_TITLE_RE.match(section.section_title)
        if workbook_match:
            return f"Module {workbook_match.group('module_number')}: {workbook_match.group('module_title').strip()}"
        candidates = [
            concept.name
            for concept in getattr(knowledge, "concepts", [])
            if not self._is_junk_title(concept.name)
        ]
        candidates.append(section.section_title)
        for candidate in candidates:
            cleaned = cleanSectionDisplayTitle(candidate)
            if cleaned and not self._is_junk_title(cleaned):
                return cleaned
        text = section.text.lower()
        if "type conversion" in text or {"int", "float", "str"} & set(TOKEN_RE.findall(text)):
            return "Type Conversion"
        if "variable" in text:
            return "Variables"
        if "expression" in text:
            return "Expressions"
        if "statement" in text:
            return "Statements"
        if "function" in text:
            return "Functions"
        return "Study section"

    def _looks_like_schedule_or_admin(self, text: str, title: str) -> bool:
        lowered = f"{title}\n{text}".lower()
        admin_hits = sum(
            1
            for marker in [
                "announcement",
                "deadline",
                "due date",
                "homework",
                "office hour",
                "thanksgiving break",
                "final exam",
                "no class",
                "schedule",
                "week of",
                "syllabus",
                "attendance",
                "zoom",
            ]
            if marker in lowered
        )
        month_hits = len(re.findall(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)\b", lowered))
        academic_hits = sum(
            1
            for marker in [
                "variable",
                "expression",
                "statement",
                "function",
                "conversion",
                "operator",
                "loop",
                "data type",
                "comparison",
                "logical",
                "boolean",
                "string",
                "integer",
                "gradient",
                "learning rate",
                "parameter",
                "objective",
                "convergence",
                *FINANCE_ACADEMIC_TERMS,
            ]
            if marker in lowered
        )
        logistics_density = len(
            re.findall(
                r"\b(?:logistics|office|hours|session|practice|notebook|powerpoint|write|"
                r"focus|reading|agenda|announcement|deadline|homework|zoom|holiday)\b",
                lowered,
            )
        )
        return (
            (admin_hits >= 2 and month_hits >= 2)
            or (admin_hits >= 3 and academic_hits <= 1)
            or (logistics_density >= 5 and academic_hits <= 1)
        )

    def _looks_like_title_only(self, section: SourceSection, text: str) -> bool:
        words = [token.lower() for token in TOKEN_RE.findall(text)]
        if not words:
            return True
        if len(words) <= 4 and not self._has_academic_signal(text):
            return True
        title_words = [token.lower() for token in TOKEN_RE.findall(section.section_title)]
        if len(words) <= 12 and title_words and set(words).issubset(set(title_words)):
            return True
        lines = [line.strip() for line in section.text.splitlines() if line.strip()]
        if len(words) <= 14 and len(lines) <= 3 and not self._has_academic_signal(text):
            return True
        return False

    def _has_academic_signal(self, text: str) -> bool:
        lowered = text.lower()
        academic_hits = len(
            re.findall(
                r"\b(?:variable|expression|statement|function|method|class|type conversion|data type|"
                r"operator|comparison|logical|boolean|string|integer|float|loop|iteration|list|"
                r"dictionary|pandas|syntax|return|argument|parameter|gradient|learning rate|"
                r"objective|convergence|descent|ascent|risk|risk management|financial risk|market risk|"
                r"credit risk|liquidity|operational risk|governance|valuation|interest rate|"
                r"foreign exchange|cyber risk|regulation|capital|portfolio|derivative|hedge|"
                r"volatility|probability|stress|scenario|expected loss|unexpected loss|risk factor)\b",
                lowered,
            )
        )
        code_hits = len(
            re.findall(
                r"(?:==|!=|<=|>=|[a-z_][a-z0-9_]*\s*\(|\b(?:int|float|str|print|input|type|len|range)\s*\()",
                lowered,
            )
        )
        teaching_hits = len(
            re.findall(
                r"\b(?:is|are|means|describes|consists?|contains?|includes?|requires?|regulates?|"
                r"produces?|converts?|controls?|supports?|prevents?|causes?|explains?|occurs?|uses?)\b",
                lowered,
            )
        )
        return academic_hits + code_hits >= 2 or (
            teaching_hits >= 2 and len(TOKEN_RE.findall(text)) >= 18
        )

    def _clean_academic_text(self, text: str) -> str:
        lines = []
        for line in re.split(r"[\n•●○▪▫]+", text):
            for fragment in self._split_study_fragments(line):
                cleaned = " ".join(fragment.split()).strip()
                if not cleaned or self._is_low_value_text(cleaned):
                    continue
                lines.append(cleaned)
        return ". ".join(lines) or text

    def _fallback_key_points(self, text: str, title: str) -> list[str]:
        points = []
        for sentence in self._sentences(self._clean_academic_text(text)):
            if self._is_low_value_text(sentence):
                continue
            if self._has_academic_signal(sentence) or self._looks_like_code_or_rule(sentence):
                points.append(sentence)
        return self._quality_points(points, title, limit=5)

    def _looks_like_code_or_rule(self, value: str) -> bool:
        lowered = value.lower()
        if re.search(r"\b[a-z_][a-z0-9_]*\s*\([^)]{0,80}\)", value):
            return True
        if re.search(r"\b[a-z_][a-z0-9_]*\s*(?:==|!=|<=|>=|=|<|>)\s*[^.;]{1,100}", value):
            return True
        return any(
            marker in lowered
            for marker in [
                "comparison operator",
                "logical operator",
                "returns true",
                "returns false",
                "not equal",
                "equal to",
                "case sensitive",
                "cannot use",
                "valid comparison",
            ]
        )

    def _format_code_or_rule(self, value: str) -> str:
        cleaned = " ".join(value.split()).strip(" -;")
        replacements = {
            "greater than": ">",
            "less than": "<",
            "not equal to": "!=",
            "equal to": "==",
        }
        for phrase, symbol in replacements.items():
            cleaned = re.sub(rf"\b{phrase}\b", symbol, cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*([=!<>]=?|==)\s*", r" \1 ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned[:140].strip()

    def _quality_points(
        self,
        values: list[str],
        title: str,
        *,
        limit: int = 5,
    ) -> list[str]:
        expanded = [
            fragment
            for value in values
            for fragment in self._split_study_fragments(value)
        ]
        return self._unique_items(
            [
                value
                for value in expanded
                if not self._is_low_value_text(value)
                and value.lower().strip() != title.lower().strip()
            ],
            limit=limit,
        )

    def _is_low_value_text(self, value: str) -> bool:
        lowered = value.lower()
        if self._looks_like_schedule_or_admin(value, ""):
            return True
        if any(marker in lowered for marker in ["office hours", "thanksgiving", "final exam", "no class"]):
            return True
        tokens = [token.lower() for token in TOKEN_RE.findall(value)]
        return bool(tokens) and sum(1 for token in tokens if token in JUNK_STUDY_TERMS) / len(tokens) > 0.45

    def _is_junk_title(self, value: str) -> bool:
        cleaned = cleanSectionDisplayTitle(value).lower()
        if not cleaned:
            return True
        if cleaned in {"week of (monday): topic", "week of monday", "topic", "study section"}:
            return True
        return self._is_low_value_text(cleaned)

    def _is_junk_term(self, value: str) -> bool:
        cleaned = re.sub(r"[^a-z0-9_()+-]", "", value.lower())
        if not cleaned or cleaned in JUNK_STUDY_TERMS:
            return True
        if any(marker in cleaned for marker in ["weekof", "officehour", "finalexam"]):
            return True
        if re.fullmatch(r"\d{1,4}", cleaned):
            return True
        if re.fullmatch(r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)\d*", cleaned):
            return True
        return False

    def _split_study_fragments(self, value: str) -> list[str]:
        return [
            fragment.strip(" -;")
            for fragment in re.split(r"\s+(?:[•●○▪▫]|o)\s+", value)
            if fragment.strip(" -;")
        ]

    def _sentences(self, text: str) -> list[str]:
        cleaned = " ".join(text.split())
        return [
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?])\s+", cleaned)
            if sentence.strip()
        ]

    def _unique_items(self, values: list[str], *, limit: int) -> list[str]:
        unique: list[str] = []
        seen: set[str] = set()
        for value in values:
            cleaned = " ".join(value.split()).strip(" -:;")
            if not cleaned:
                continue
            key = cleaned.lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(self._limit_display_item(cleaned))
            if len(unique) >= limit:
                break
        return unique

    def _limit_display_item(self, value: str, *, max_length: int = 240) -> str:
        cleaned = " ".join(value.split()).strip()
        if len(cleaned) <= max_length:
            return cleaned
        boundary = cleaned.rfind(" ", 0, max_length)
        if boundary < max_length * 0.65:
            boundary = max_length
        trimmed = cleaned[:boundary].rstrip(" ,;:-")
        if re.search(r"[.!?]$", cleaned) and not re.search(r"[.!?]$", trimmed):
            trimmed = f"{trimmed}."
        return trimmed

    def _stop_words(self) -> set[str]:
        return {
            "about",
            "after",
            "also",
            "because",
            "before",
            "between",
            "course",
            "from",
            "have",
            "into",
            "more",
            "that",
            "their",
            "there",
            "these",
            "this",
            "using",
            "when",
            "with",
            "would",
            "topic",
            "week",
            "monday",
            "final",
            "exam",
            "hours",
        }
