from exam_prep.schemas.materials import (
    ContentLabel,
    FormulaAsset,
    MaterialRecord,
    ParsedMaterialDocument,
    OriginalBookContent,
    SectionKind,
    SourceChunk,
    SourceLocator,
    SourceSection,
    StudyConceptCard,
    StudyFlashcard,
)
from exam_prep.repositories.local.material_store import LocalMaterialStore
from exam_prep.retrieval.chunking import ChunkingService
from exam_prep.schemas.quiz import QuestionType, QuizQuestion, QuizQuestionOption
from exam_prep.services.question_pipeline import (
    buildSemanticSections,
    classifyChunk,
    cleanSectionDisplayTitle,
    extractKnowledge,
    generateExamStyleQuestion,
    sanitizeExplanationText,
    sanitizeOptionText,
    sanitizeQuestionText,
    validateQuestion,
)
from exam_prep.services.section_study_service import SectionStudyService


def _build_section(
    *,
    title: str = "Python Basics | Python Basics | slides 1-2",
    text: str = (
        "Variables store values. Expressions return a value. "
        "Statements perform an action. For example, x = 3 * 2 assigns a value."
    ),
) -> SourceSection:
    return SourceSection(
        source_id="source-1",
        material_id="mat-1",
        course_id="course-1",
        file_name="session1.pdf",
        content_type="application/pdf",
        section_title=title,
        text=text,
        content_label=ContentLabel.TESTABLE_CONTENT,
        locator=SourceLocator(section_index=1, page_number=1),
        citation_label="session1.pdf | Python Basics | slides 1-2",
    )


def _build_citation(section: SourceSection, *, chunk_id: str = "chunk-workbook") -> SourceChunk:
    return SourceChunk(
        chunk_id=chunk_id,
        source_id=section.source_id,
        material_id=section.material_id,
        course_id=section.course_id,
        module_id=section.module_id,
        file_name=section.file_name,
        content_type=section.content_type,
        section_title=section.section_title,
        text=section.text,
        section_kind=section.section_kind,
        content_label=section.content_label,
        priority_score=section.priority_score,
        is_default=section.is_default,
        locator=section.locator,
        citation_label=section.citation_label,
    )


def test_sanitizers_remove_metadata_and_duplicate_labels() -> None:
    assert cleanSectionDisplayTitle("Python Basics | Python Basics | slides 1-2") == "Python Basics"
    sanitized_prompt = sanitizeQuestionText("Which statement is true on slides 1-2 of session1.pdf?")
    assert "slides" not in sanitized_prompt.lower()
    assert "session1.pdf" not in sanitized_prompt.lower()
    assert sanitizeOptionText("Option A: session1.pdf | Variables store values") == "Variables store values"
    assert "session1.pdf" not in sanitizeExplanationText("Source: session1.pdf | Variables store values")


def test_generate_exam_style_question_uses_clean_titles_and_options() -> None:
    section = _build_section()
    knowledge = extractKnowledge(section)
    citation = SourceChunk(
        chunk_id="chunk-1",
        source_id=section.source_id,
        material_id=section.material_id,
        course_id=section.course_id,
        module_id=section.module_id,
        file_name=section.file_name,
        content_type=section.content_type,
        section_title=section.section_title,
        text=section.text,
        section_kind=section.section_kind,
        content_label=section.content_label,
        priority_score=section.priority_score,
        is_default=section.is_default,
        locator=section.locator,
        citation_label=section.citation_label,
    )

    question, correct_answer, correct_option_id = generateExamStyleQuestion(
        knowledge=knowledge,
        question_type=QuestionType.MCQ,
        question_id="q-1",
        concept=section.section_title,
        section_title=section.section_title,
        difficulty=0.4,
        citations=[citation],
        sequence_index=1,
    )

    assert question.section_title == "Python Basics"
    assert question.concept == "Python Basics"
    assert len(question.options) == 4
    assert len({option.text for option in question.options}) == 4
    assert all("slides" not in option.text.lower() for option in question.options)
    assert "session1.pdf" not in question.prompt.lower()
    assert correct_option_id in {"A", "B", "C", "D"}
    assert "session1.pdf" not in correct_answer.lower()


def test_workbook_module_quiz_generates_new_high_quality_questions_from_key_concepts() -> None:
    text = (
        "KEY CONCEPTS\n"
        "LO 29.a\n"
        "Open-end mutual funds issue and redeem shares at net asset value. "
        "Closed-end funds issue a fixed number of shares that may trade at a premium or discount to net asset value. "
        "Exchange-traded funds trade intraday on exchanges and use creation and redemption to keep prices close to net asset value. "
        "LO 29.b\n"
        "Fund investors compare expense ratios, sales loads, 12b-1 fees, and portfolio turnover. "
        "Higher turnover can increase trading costs and taxable distributions for fund investors.\n"
        "MODULE QUIZ 29.1\n"
        "1. How does diversification reduce total portfolio risk?\n"
        "A. It eliminates all market risk.\n"
        "B. It combines assets whose specific risks offset each other.\n"
        "C. It guarantees outperformance.\n"
        "D. It increases concentration.\n"
        "2. Which statement best describes the primary disadvantage of exchange-traded funds?\n"
        "A. ETFs cannot be traded intraday.\n"
        "B. ETF prices may deviate from NAV during market stress.\n"
        "C. ETFs must always charge sales loads.\n"
        "D. ETFs cannot track indexes.\n"
        "ANSWER KEY FOR MODULE QUIZZES\n"
        "MODULE QUIZ 29.1\n"
        "1. B Diversification reduces unsystematic risk because specific risks can offset each other.\n"
        "2. B ETF prices can temporarily deviate from NAV during stressed markets.\n"
    )
    section = _build_section(
        title="Study Session 8: Financial Markets / Reading 29: Fund Management / Module 29.1: Mutual Funds and ETFs",
        text=text,
    )
    knowledge = extractKnowledge(section)
    citation = SourceChunk(
        chunk_id="chunk-workbook-1",
        source_id=section.source_id,
        material_id=section.material_id,
        course_id=section.course_id,
        module_id=section.module_id,
        file_name=section.file_name,
        content_type=section.content_type,
        section_title=section.section_title,
        text=section.text,
        section_kind=section.section_kind,
        content_label=section.content_label,
        priority_score=section.priority_score,
        is_default=section.is_default,
        locator=section.locator,
        citation_label=section.citation_label,
    )

    generated = [
        generateExamStyleQuestion(
            knowledge=knowledge,
            question_type=QuestionType.MCQ,
            question_id=f"q-{index}",
            concept="Mutual funds and exchange-traded funds",
            section_title=section.section_title,
            difficulty=0.6,
            citations=[citation],
            sequence_index=index,
        )
        for index in (1, 2)
    ]
    questions = [item[0] for item in generated]
    answer_keys = {item[0].question_id: item[1:] for item in generated}

    original_phrases = [
        "diversification reduce total portfolio risk",
        "primary disadvantage of exchange-traded funds",
        "combines assets whose specific risks offset each other",
        "ETF prices may deviate from NAV during market stress",
    ]
    generic_low_quality_phrases = [
        "best response depends",
        "all risks should be eliminated",
        "same response works for every exposure",
        "risk management ignores implementation tradeoffs",
        "module quiz answer key",
    ]
    joined_output = " ".join(
        [
            *[question.prompt for question in questions],
            *[option.text for question in questions for option in question.options],
            *[question.rationale or "" for question in questions],
        ]
    ).lower()

    assert len({question.prompt for question in questions}) == 2
    assert all(question.question_type == QuestionType.MCQ for question in questions)
    assert all(len(question.options) == 4 for question in questions)
    assert all(len({option.text.lower() for option in question.options}) == 4 for question in questions)
    assert all(phrase.lower() not in joined_output for phrase in original_phrases)
    assert all(phrase not in joined_output for phrase in generic_low_quality_phrases)
    assert any(
        term in joined_output
        for term in ("open-end", "closed-end", "expense ratio", "portfolio turnover", "creation and redemption")
    )
    for question in questions:
        correct_answer, correct_option_id = answer_keys[question.question_id]
        option_by_id = {option.option_id: option.text for option in question.options}
        assert correct_option_id in option_by_id
        assert option_by_id[correct_option_id] == correct_answer


def test_workbook_module_quiz_rejects_generic_firm_stems_and_truncated_answers() -> None:
    text = (
        "KEY CONCEPTS\n"
        "LO 2.a\n"
        "Firms can pick from four different risk management strategies: accept, avoid, "
        "mitigate, or transfer risk.\n"
        "LO 2.b\n"
        "A firm's risk appetite is its willingness to retain risk and can be expressed "
        "qualitatively or quantitatively.\n"
        "MODULE QUIZ 2.1\n"
        "1. Bank Y has decided to use currency futures and forward to offset its entire "
        "estimated foreign sales exposure. Which high-level risk mitigation strategy does "
        "this description represent?\n"
        "A. Retain risk.\n"
        "B. Avoid risk.\n"
        "C. Mitigate risk.\n"
        "D. Transfer risk.\n"
        "2. The involvement of the board of directors is important within the context of "
        "a firm's decision to hedge specific risk factors. Which of the following statements "
        "regarding the setting of risk appetite is correct?\n"
        "I. Risk appetite may be conveyed strictly in a qualitative manner.\n"
        "II. Debtholders and shareholders are both likely to desire minimizing the firm's "
        "risk appetite.\n"
        "A. I only.\n"
        "B. II only.\n"
        "C. Both I and II.\n"
        "D. Neither I nor II.\n"
        "ANSWER KEY FOR MODULE QUIZZES\n"
        "MODULE QUIZ 2.1\n"
        "1. D Bank Y chose to transfer foreign currency risk to a third party. (LO 2.a)\n"
        "2. A Risk appetite may be conveyed in qualitative and/or quantitative terms. (LO 2.b)\n"
    )
    section = _build_section(
        title="Study Session 1: Foundations / Reading 2: Risk Management / Module 2.1: Corporate Risk Management",
        text=text,
    )
    knowledge = extractKnowledge(section)
    citation = SourceChunk(
        chunk_id="chunk-workbook-risk",
        source_id=section.source_id,
        material_id=section.material_id,
        course_id=section.course_id,
        module_id=section.module_id,
        file_name=section.file_name,
        content_type=section.content_type,
        section_title=section.section_title,
        text=section.text,
        section_kind=section.section_kind,
        content_label=section.content_label,
        priority_score=section.priority_score,
        is_default=section.is_default,
        locator=section.locator,
        citation_label=section.citation_label,
    )

    question, correct_answer, _ = generateExamStyleQuestion(
        knowledge=knowledge,
        question_type=QuestionType.MCQ,
        question_id="q-risk-style",
        concept=knowledge.concepts[0].name,
        section_title=section.section_title,
        difficulty=0.65,
        citations=[citation],
        sequence_index=1,
    )

    option_text = " ".join(option.text for option in question.options).lower()

    assert "best describes firms" not in question.prompt.lower()
    assert "risk-management strateg" in question.prompt.lower() or "risk response" in question.prompt.lower()
    assert correct_answer in {
        "Accept the exposure",
        "Avoid the exposure",
        "Mitigate the exposure",
        "Transfer the exposure",
    }
    assert "strategies: 1" not in option_text
    assert all(not option.text.endswith(": 1") for option in question.options)
    assert all("bank y" not in option.text.lower() for option in question.options)


def test_workbook_module_quiz_quality_gate_rejects_shallow_fact_templates() -> None:
    text = (
        "KEY CONCEPTS\n"
        "LO 2.a\n"
        "Firms can pick from four different risk management strategies: accept, avoid, mitigate, or transfer risk.\n"
        "LO 2.b\n"
        "A firm's risk appetite is its willingness to retain risk and can be expressed qualitatively or quantitatively.\n"
        "MODULE QUIZ 2.1\n"
        "1. Bank Y has decided to use currency futures and forward to offset its entire estimated foreign sales exposure. "
        "Which high-level risk mitigation strategy does this description represent?\n"
        "A. Retain risk.\n"
        "B. Avoid risk.\n"
        "C. Mitigate risk.\n"
        "D. Transfer risk.\n"
        "2. The involvement of the board of directors is important within the context of a firm's decision to hedge specific risk factors. "
        "Which of the following statements regarding the setting of risk appetite is correct?\n"
        "I. Risk appetite may be conveyed strictly in a qualitative manner.\n"
        "II. Debtholders and shareholders are both likely to desire minimizing the firm's risk appetite.\n"
        "A. I only.\n"
        "B. II only.\n"
        "C. Both I and II.\n"
        "D. Neither I nor II.\n"
        "ANSWER KEY FOR MODULE QUIZZES\n"
        "MODULE QUIZ 2.1\n"
        "1. D Bank Y chose to transfer foreign currency risk to a third party. (LO 2.a)\n"
        "2. A Risk appetite may be conveyed in qualitative and/or quantitative terms. (LO 2.b)\n"
    )
    section = _build_section(
        title="Study Session 1: Foundations / Reading 2: Risk Management / Module 2.1: Corporate Risk Management",
        text=text,
    )
    knowledge = extractKnowledge(section)
    shallow_question = QuizQuestion(
        question_id="q-shallow-workbook",
        question_type=QuestionType.MCQ,
        concept="Corporate Risk Management",
        section_title=section.section_title,
        difficulty=0.65,
        prompt="Which statement best describes firms?",
        options=[
            QuizQuestionOption(option_id="A", text="They can pick from four different risk management strategies"),
            QuizQuestionOption(option_id="B", text="They should always avoid risk"),
            QuizQuestionOption(option_id="C", text="They transfer all risk without tradeoffs"),
            QuizQuestionOption(option_id="D", text="They eliminate uncertainty before hedging"),
        ],
        citations=[],
        rationale="Firms can accept, avoid, mitigate, or transfer risk.",
    )

    result = validateQuestion(
        shallow_question,
        source_text=section.text,
        knowledge=knowledge,
        correct_answer="They can pick from four different risk management strategies",
    )

    assert result.accepted is False
    assert any("book-level" in note.lower() for note in result.notes)


def test_workbook_generator_matches_module_quiz_quality_patterns_across_frm_modules() -> None:
    risk_text = (
        "KEY CONCEPTS\n"
        "LO 2.a\n"
        "Firms can pick from four different risk management strategies: accept, avoid, mitigate, or transfer risk.\n"
        "LO 2.b\n"
        "A firm's risk appetite is its willingness to retain risk and can be expressed qualitatively or quantitatively.\n"
        "MODULE QUIZ 2.1\n"
        "1. Bank Y has decided to use currency futures and forward to offset its entire estimated foreign sales exposure. "
        "Which high-level risk mitigation strategy does this description represent?\n"
        "A. Retain risk.\n"
        "B. Avoid risk.\n"
        "C. Mitigate risk.\n"
        "D. Transfer risk.\n"
        "2. The involvement of the board of directors is important within the context of a firm's decision to hedge specific risk factors. "
        "Which of the following statements regarding the setting of risk appetite is correct?\n"
        "I. Risk appetite may be conveyed strictly in a qualitative manner.\n"
        "II. Debtholders and shareholders are both likely to desire minimizing the firm's risk appetite.\n"
        "A. I only.\n"
        "B. II only.\n"
        "C. Both I and II.\n"
        "D. Neither I nor II.\n"
        "ANSWER KEY FOR MODULE QUIZZES\n"
        "MODULE QUIZ 2.1\n"
        "1. D Bank Y chose to transfer foreign currency risk to a third party. (LO 2.a)\n"
        "2. A Risk appetite may be conveyed in qualitative and/or quantitative terms. (LO 2.b)\n"
    )
    fund_text = (
        "KEY CONCEPTS\n"
        "LO 29.a\n"
        "Open-end mutual funds issue and redeem shares at net asset value. "
        "Closed-end funds issue a fixed number of shares that may trade at a premium or discount to net asset value. "
        "Exchange-traded funds trade intraday on exchanges and use creation and redemption to keep prices close to net asset value.\n"
        "MODULE QUIZ 29.1\n"
        "1. Which of the following statements is not correct regarding investment funds available to all investors?\n"
        "A. Open-end mutual funds always transact at the next available NAV.\n"
        "B. Stop orders can be used on closed-end funds.\n"
        "C. Open-end mutual funds can be purchased with a limit order.\n"
        "D. Short selling is available for some ETFs.\n"
        "ANSWER KEY FOR MODULE QUIZZES\n"
        "MODULE QUIZ 29.1\n"
        "1. C Open-end mutual funds are bought and redeemed at the next available NAV. (LO 29.a)\n"
    )
    hedging_text = (
        "KEY CONCEPTS\n"
        "LO 34.a\n"
        "A short hedge locks in a sale price but can limit upside if the asset price increases. "
        "Basis risk remains when spot and futures prices do not move together. "
        "A cross hedge uses a futures contract on a related but different asset, which can increase basis risk.\n"
        "MODULE QUIZ 34.1\n"
        "1. Which of the following situations describe a hedger with exposure to basis risk?\n"
        "I. A portfolio manager receives cash next month and wants to pre-invest using stock index futures.\n"
        "II. A farmer has a large crop of corn to sell before June 30 and uses a June corn futures contract.\n"
        "A. I only.\n"
        "B. II only.\n"
        "C. Both I and II.\n"
        "D. Neither I nor II.\n"
        "ANSWER KEY FOR MODULE QUIZZES\n"
        "MODULE QUIZ 34.1\n"
        "1. A The portfolio manager is exposed to basis risk because the futures do not perfectly match the exposure. (LO 34.a)\n"
    )
    cases = [
        (
            "risk",
            "Study Session 1: Foundations / Reading 2: Risk Management / Module 2.1: Corporate Risk Management",
            risk_text,
            1,
        ),
        (
            "funds",
            "Study Session 8: Financial Markets / Reading 29: Fund Management / Module 29.1: Mutual Funds and Exchange-Traded Funds",
            fund_text,
            1,
        ),
        (
            "hedging",
            "Study Session 8: Financial Markets / Reading 34: Futures Markets / Module 34.1: Principles of Hedging",
            hedging_text,
            1,
        ),
    ]

    generated: dict[str, QuizQuestion] = {}
    for name, title, text, sequence_index in cases:
        section = _build_section(title=title, text=text)
        knowledge = extractKnowledge(section)
        question, correct_answer, correct_option_id = generateExamStyleQuestion(
            knowledge=knowledge,
            question_type=QuestionType.MCQ,
            question_id=f"q-{name}",
            concept=knowledge.concepts[0].name,
            section_title=section.section_title,
            difficulty=0.65,
            citations=[_build_citation(section, chunk_id=f"chunk-{name}")],
            sequence_index=sequence_index,
        )
        validation = validateQuestion(
            question,
            source_text=section.text,
            knowledge=knowledge,
            correct_answer=correct_answer,
        )

        assert validation.accepted is True, validation.notes
        assert validation.score >= 0.82
        assert correct_option_id in {"A", "B", "C", "D"}
        generated[name] = question

    risk_prompt = generated["risk"].prompt.lower()
    fund_prompt = generated["funds"].prompt.lower()
    hedging_prompt = generated["hedging"].prompt.lower()

    assert any(token in risk_prompt for token in ("decides", "expects", "chooses"))
    assert "bank y" not in risk_prompt
    assert "which statement best describes firms" not in risk_prompt
    assert "not correct" in fund_prompt or "least accurate" in fund_prompt
    assert "I." in generated["hedging"].prompt
    assert "II." in generated["hedging"].prompt
    assert any(token in hedging_prompt for token in ("airline", "manufacturer", "manager", "farmer"))


def test_question_validation_rejects_metadata_leakage() -> None:
    section = _build_section()
    knowledge = extractKnowledge(section)
    question = QuizQuestion(
        question_id="q-2",
        question_type=QuestionType.MCQ,
        concept="Python Basics",
        section_title="Python Basics",
        difficulty=0.5,
        prompt="Which statement from session1.pdf slides 1-2 is correct?",
        options=[
            QuizQuestionOption(option_id="A", text="Variables store values"),
            QuizQuestionOption(option_id="B", text="slides 1-2"),
            QuizQuestionOption(option_id="C", text="Schedule update"),
            QuizQuestionOption(option_id="D", text="Office hours"),
        ],
        citations=[],
        rationale="Because it matches the grounded concept.",
    )

    result = validateQuestion(
        question,
        source_text=section.text,
        knowledge=knowledge,
        correct_answer="Variables store values",
    )

    assert result.accepted is False
    assert any("metadata" in note.lower() for note in result.notes)


def test_question_validation_rejects_generic_module_quiz_filler() -> None:
    section = _build_section(
        title="Risk Management",
        text=(
            "Firms can accept, avoid, mitigate, or transfer risk. "
            "The correct response depends on the exposure and the firm's objective."
        ),
    )
    knowledge = extractKnowledge(section)
    question = QuizQuestion(
        question_id="q-generic",
        question_type=QuestionType.MCQ,
        concept="Risk Management",
        section_title="Risk Management",
        difficulty=0.5,
        prompt="Which statement best applies risk management in this module?",
        options=[
            QuizQuestionOption(option_id="A", text="The best response depends on the specific risk exposure"),
            QuizQuestionOption(option_id="B", text="All risks should be eliminated before analysis"),
            QuizQuestionOption(option_id="C", text="The same response works for every exposure"),
            QuizQuestionOption(option_id="D", text="Risk management ignores implementation tradeoffs"),
        ],
        citations=[],
        rationale="The module quiz answer key supports the response.",
    )

    result = validateQuestion(
        question,
        source_text=section.text,
        knowledge=knowledge,
        correct_answer="The best response depends on the specific risk exposure",
    )

    assert result.accepted is False
    assert any("generic quiz filler" in note.lower() for note in result.notes)


def test_question_validation_rejects_copied_module_quiz_items() -> None:
    source_text = (
        "KEY CONCEPTS\n"
        "LO 34.a\n"
        "A short hedge locks in a sale price but can limit upside if the asset price increases. "
        "Basis risk remains when spot and futures prices do not move together.\n"
        "MODULE QUIZ 34.1\n"
        "1. Which statement best describes the primary disadvantage of implementing a short hedge?\n"
        "A. It eliminates all uncertainty regarding future profitability without any cost.\n"
        "B. It guarantees a profit regardless of whether spot prices rise or fall.\n"
        "C. It limits potential profitability if the price of the hedged asset increases.\n"
        "D. It creates basis risk only when the maturity dates perfectly match.\n"
        "ANSWER KEY FOR MODULE QUIZZES\n"
        "MODULE QUIZ 34.1\n"
        "1. C A short hedge protects the sale price but sacrifices upside when the asset price rises. (LO 34.a)\n"
    )
    section = _build_section(
        title="Module 34.1: Hedging with Futures",
        text=source_text,
    )
    knowledge = extractKnowledge(section)
    question = QuizQuestion(
        question_id="q-copied-module-quiz",
        question_type=QuestionType.MCQ,
        concept="Hedging with Futures",
        section_title="Hedging with Futures",
        difficulty=0.5,
        prompt="Which statement best describes the primary disadvantage of implementing a short hedge?",
        options=[
            QuizQuestionOption(option_id="A", text="It eliminates all uncertainty regarding future profitability without any cost"),
            QuizQuestionOption(option_id="B", text="It guarantees a profit regardless of whether spot prices rise or fall"),
            QuizQuestionOption(option_id="C", text="It limits potential profitability if the price of the hedged asset increases"),
            QuizQuestionOption(option_id="D", text="It creates basis risk only when the maturity dates perfectly match"),
        ],
        citations=[],
        rationale="A short hedge protects the sale price but sacrifices upside when the asset price rises.",
    )

    result = validateQuestion(
        question,
        source_text=source_text,
        knowledge=knowledge,
        correct_answer="It limits potential profitability if the price of the hedged asset increases",
    )

    assert result.accepted is False
    assert any("original module quiz" in note.lower() for note in result.notes)


def test_workbook_chunking_creates_lo_linked_quiz_and_answer_chunks() -> None:
    section = _build_section(
        title="Study Session 1: Risk Management Overview / Reading 2 / Module 2.1: Corporate Risk Management",
        text=(
            "LEARNING OBJECTIVES\n"
            "LO 2.a Explain high-level risk responses.\n"
            "LO 2.b Explain risk appetite governance.\n\n"
            "KEY CONCEPTS\n"
            "LO 2.a\n"
            "Firms can accept, avoid, mitigate, or transfer risk.\n"
            "LO 2.b\n"
            "Risk appetite can be stated using qualitative guidance or quantitative limits.\n\n"
            "MODULE QUIZ 2.1\n"
            "1. Bank Y hedges foreign sales exposure with forward contracts. Which high-level risk response is illustrated?\n"
            "A. Retain risk.\n"
            "B. Avoid risk.\n"
            "C. Mitigate risk.\n"
            "D. Transfer risk.\n"
            "2. Which statements about risk appetite are correct?\n"
            "I. Risk appetite may be expressed qualitatively.\n"
            "II. Risk appetite requires eliminating all retained risk.\n"
            "A. I only.\n"
            "B. II only.\n"
            "C. Both I and II.\n"
            "D. Neither I nor II.\n\n"
            "ANSWER KEY FOR MODULE QUIZZES\n"
            "MODULE QUIZ 2.1\n"
            "1. D Forward contracts transfer foreign currency exposure to another party. (LO 2.a)\n"
            "2. A Risk appetite may be conveyed in qualitative and/or quantitative terms. (LO 2.b)\n"
        ),
    )

    chunks = ChunkingService(chunk_size=10_000).chunk_sections([section])

    quiz_chunks = [chunk for chunk in chunks if chunk.workbook_block_type == "module_quiz"]
    answer_chunks = [chunk for chunk in chunks if chunk.workbook_block_type == "answer_key"]
    key_concept_chunks = [chunk for chunk in chunks if chunk.workbook_block_type == "key_concepts"]
    assert len(quiz_chunks) == 1
    assert len(answer_chunks) == 1
    assert len(key_concept_chunks) == 1

    quiz_chunk = quiz_chunks[0]
    assert quiz_chunk.workbook_module_number == "2.1"
    assert quiz_chunk.learning_outcome_ids == ["LO 2.a", "LO 2.b"]
    assert quiz_chunk.module_quiz_question_numbers == [1, 2]
    assert set(quiz_chunk.module_quiz_style_profiles) >= {
        "scenario_application",
        "roman_statement",
        "statement_selection",
    }
    assert "MODULE QUIZ 2.1" in quiz_chunk.text

    answer_chunk = answer_chunks[0]
    assert answer_chunk.workbook_module_number == "2.1"
    assert answer_chunk.learning_outcome_ids == ["LO 2.a", "LO 2.b"]
    assert answer_chunk.module_quiz_answer_numbers == [1, 2]
    assert "Forward contracts transfer foreign currency exposure" in answer_chunk.text


def test_validate_question_uses_torch_semantic_gate_for_module_quiz_copies() -> None:
    source_text = (
        "KEY CONCEPTS\n"
        "LO 34.a\n"
        "A short hedge locks in a sale price but can limit upside if the asset price increases. "
        "Basis risk remains when spot and futures prices do not move together.\n"
        "MODULE QUIZ 34.1\n"
        "1. Which statement best describes the primary disadvantage of implementing a short hedge?\n"
        "A. It eliminates all uncertainty regarding future profitability without any cost.\n"
        "B. It guarantees a profit regardless of whether spot prices rise or fall.\n"
        "C. It limits potential profitability if the price of the hedged asset increases.\n"
        "D. It creates basis risk only when the maturity dates perfectly match.\n"
        "ANSWER KEY FOR MODULE QUIZZES\n"
        "MODULE QUIZ 34.1\n"
        "1. C A short hedge protects the sale price but sacrifices upside when the asset price rises. (LO 34.a)\n"
    )
    section = _build_section(title="Module 34.1: Hedging with Futures", text=source_text)
    knowledge = extractKnowledge(section)
    question = QuizQuestion(
        question_id="q-semantic-copy",
        question_type=QuestionType.MCQ,
        concept="Hedging with Futures",
        section_title="Hedging with Futures",
        difficulty=0.5,
        prompt="Which statement best describes the main disadvantage of implementing a short hedge?",
        options=[
            QuizQuestionOption(option_id="A", text="It removes every source of uncertainty without cost"),
            QuizQuestionOption(option_id="B", text="It guarantees profit under all spot price paths"),
            QuizQuestionOption(option_id="C", text="It can limit upside if the hedged asset price increases"),
            QuizQuestionOption(option_id="D", text="It creates basis risk only with matching maturity dates"),
        ],
        citations=[],
        rationale="The hedge protects the sale price but can sacrifice upside.",
    )

    result = validateQuestion(
        question,
        source_text=source_text,
        knowledge=knowledge,
        correct_answer="It can limit upside if the hedged asset price increases",
    )

    assert result.accepted is False
    assert any("pytorch semantic" in note.lower() for note in result.notes)


def test_schedule_pages_are_filtered_as_administrative_content() -> None:
    section = _build_section(
        title="Week Of (Monday): Topic",
        text=(
            "Week Of (Monday): Topic 23 Oct 2023 Introduction to Python | Python Basics I: Syntax, "
            "Types, Variables, Expressions, Statements 30 Oct 2023 Python Basics II: Functions "
            "6 Nov 2023 Control Statements 13 Nov 2023 Iteration 20 Nov 2023 Thanksgiving Break "
            "No Office Hours 11 Dec 2023 Final Exam."
        ),
    )

    assert classifyChunk(section) == ContentLabel.ADMINISTRATIVE_CONTENT
    assert buildSemanticSections(
        [section],
        file_name="session.pdf",
        content_type="application/pdf",
        file_suffix=".pdf",
    ) == []


def test_title_only_pages_are_not_promoted_to_study_sections() -> None:
    title_page = _build_section(
        title="Python Basics",
        text="Python Basics",
    )
    content_page = _build_section(
        title="Type Conversion",
        text=(
            "Type conversion changes a value from one data type to another. "
            "Python commonly uses int(), float(), and str() for conversion."
        ),
    ).model_copy(update={"source_id": "source-2", "locator": SourceLocator(section_index=2, page_number=2)})

    sections = buildSemanticSections(
        [title_page, content_page],
        file_name="session.pdf",
        content_type="application/pdf",
        file_suffix=".pdf",
    )

    assert len(sections) == 1
    assert sections[0].source_id == "source-2"
    assert sections[0].content_label == ContentLabel.TESTABLE_CONTENT
    assert "Type Conversion" in sections[0].section_title


def test_frm_risk_content_is_classified_as_testable() -> None:
    section = _build_section(
        title="Module 1.1: Introduction to Risk Management",
        text=(
            "Risk management is a formal process for identifying, analyzing, "
            "evaluating, and managing risk. Expected loss and unexpected loss "
            "are important exam concepts in financial risk management."
        ),
    )

    assert classifyChunk(section) == ContentLabel.TESTABLE_CONTENT


def test_study_section_rejects_existing_title_only_cached_sections() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    title_only = _build_section(title="Python Basics", text="Python Basics")

    assert service._is_usable_section(title_only) is False


def test_study_section_rejects_logistics_and_preserves_code_rules() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    logistics = _build_section(
        title="In Class and Practice Sessions",
        text=(
            "Logistics In Class vs Practice Sessions vs Office Hours. No more powerpoints. "
            "All Jupyter notebooks. Focus on reading and writing during class sessions."
        ),
    )
    academic = _build_section(
        title="Operators: Comparison Operators",
        text=(
            "Comparison operators compare two values of the same data type. "
            "x == 2 checks equality while x = 2 assigns a value. "
            "5 != 4 returns True. Valid comparisons include ints to ints, floats to floats, "
            "and strings to strings."
        ),
    )

    assert service._is_usable_section(logistics) is False
    study_section = service._build_study_section(
        academic,
        display_order=1,
        parent_group_id=None,
        previous=None,
    )

    joined_rules = " ".join(study_section.memorize_functions_or_formulas)
    assert "==" in joined_rules
    assert "!=" in joined_rules
    assert "assigns a value" in joined_rules.lower()
    assert study_section.quiz_ready is True


def test_study_service_groups_workbook_modules_by_reading_and_marks_risk_content_ready() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section_one = _build_section(
        title=(
            "Study Session 1: Risk Management Overview / "
            "Reading 1: The Building Blocks of Risk Management / "
            "Module 1.1: Introduction to Risk Management"
        ),
        text=(
            "EXAM FOCUS Risk management is a formal process for identifying, analyzing, "
            "evaluating, and managing expected and unexpected loss. KEY CONCEPTS Risk is "
            "uncertainty surrounding outcomes. MODULE QUIZ 1.1 Which statement is correct?"
        ),
    )
    section_two = section_one.model_copy(
        update={
            "source_id": "source-2",
            "section_title": (
                "Study Session 1: Risk Management Overview / "
                "Reading 1: The Building Blocks of Risk Management / "
                "Module 1.2: Types of Risk"
            ),
            "locator": SourceLocator(section_index=2, page_number=7),
            "page_end": 9,
        }
    )
    section_three = section_one.model_copy(
        update={
            "source_id": "source-3",
            "section_title": (
                "Study Session 1: Risk Management Overview / "
                "Reading 2: How Do Firms Manage Financial Risk? / "
                "Module 2.1: Corporate Risk Management"
            ),
            "locator": SourceLocator(section_index=3, page_number=9),
            "page_end": 15,
        }
    )

    groups = service._build_groups("mat-frm", [section_one, section_two, section_three])
    study_section = service._build_study_section(
        section_one,
        display_order=1,
        parent_group_id=groups[0].group_id,
        previous=None,
    )

    assert [group.title for group in groups] == [
        "Study Session 1 · Reading 1: The Building Blocks of Risk Management",
        "Study Session 1 · Reading 2: How Do Firms Manage Financial Risk?",
    ]
    mapping = service._group_id_by_section(groups, [section_one, section_two, section_three])
    assert mapping["source-3"] == groups[1].group_id
    assert study_section.normalized_title == "Module 1.1: Introduction to Risk Management"
    assert study_section.quiz_ready is True


def test_study_service_keeps_single_workbook_reading_group() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _build_section(
        title=(
            "Study Session 1: Risk Management Overview / "
            "Reading 1: The Building Blocks of Risk Management / "
            "Module 1.1: Introduction to Risk Management"
        ),
        text=(
            "KEY CONCEPTS\n"
            "LO 1.a\n"
            "Risk is uncertainty surrounding outcomes.\n"
            "MODULE QUIZ 1.1\n"
            "1. Which statement about risk is correct?\n"
            "A. Risk is uncertainty surrounding outcomes.\n"
            "ANSWER KEY FOR MODULE QUIZZES\n"
            "1. A Risk is uncertainty surrounding outcomes."
        ),
    )

    groups = service._build_groups("mat-single-reading", [section])

    assert [group.title for group in groups] == [
        "Study Session 1 · Reading 1: The Building Blocks of Risk Management"
    ]
    assert groups[0].page_start == 1
    assert groups[0].ready_count == 1


def test_workbook_study_section_uses_structured_blocks_without_quiz_leakage() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _build_section(
        title=(
            "Study Session 1: Risk Management Overview / "
            "Reading 2: How Do Firms Manage Financial Risk? / "
            "Module 2.1: Corporate Risk Management"
        ),
        text=(
            "EXAM FOCUS\n"
            "This reading explains corporate risk management and how firms choose risk responses.\n\n"
            "KEY CONCEPTS\n"
            "LO 2.a\n"
            "Risk transfer is not risk elimination, so scenario questions often test the exact distinction.\n"
            "Firms can choose four different risk management strategies: accept, avoid, mitigate, and transfer risk.\n"
            "1. Accept the risk.\n"
            "2. Avoid the risk.\n"
            "Risk appetite is the willingness to retain risk and should be set with board oversight.\n\n"
            "MODULE QUIZ 2.1\n"
            "1. Rank Y has decided to use currency futures and forwards to offset foreign sales. "
            "Which risk management strategy does this represent?\n"
            "A. Retain risk. B. Avoid risk. C. Mitigate risk. D. Transfer risk.\n\n"
            "ANSWER KEY FOR MODULE QUIZZES\n"
            "MODULE QUIZ 2.1\n"
            "1. C The futures position mitigates the exposure rather than eliminating risk.\n"
            "A A futures contract does not provide customization, so it should not be confused with a forward.\n"
            "A GARP Members must not accept gifts that compromise independence."
        ),
    )

    study_section = service._build_study_section(
        section,
        display_order=1,
        parent_group_id=None,
        previous=None,
    )

    assert study_section.normalized_title == "Module 2.1: Corporate Risk Management"
    assert study_section.summary == "Official workbook blocks extracted from key concepts, module quiz, and answer key."
    assert study_section.key_points == []
    assert study_section.memorize_keywords == []
    assert study_section.memorize_functions_or_formulas == []
    assert study_section.traps == []
    assert "Risk transfer is not risk elimination" in "\n".join(study_section.workbook_key_concepts)
    assert "Rank Y has decided to use currency futures" in "\n".join(study_section.workbook_module_quiz)
    assert "The futures position mitigates the exposure" in "\n".join(study_section.workbook_answer_key)
    assert "GARP Members" not in "\n".join(study_section.workbook_answer_key)
    assert study_section.quiz_ready is True


def test_workbook_study_section_does_not_treat_learning_objectives_as_key_concepts() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _build_section(
        title=(
            "Study Session 13: Credit Risk / "
            "Reading 51: Country Risk / "
            "Module 51.1: Country Risk"
        ),
        text=(
            "LEARNING OBJECTIVES\n"
            "LO 51.a: Explain the sources of country risk.\n"
            "LO 51.b: Evaluate composite country-risk measures.\n"
            "Country risk analysis considers economic, political, and legal conditions.\n"
            "LO 51.d\n"
            "LO 51.e\n\n"
            "KEY CONCEPTS\n"
            "LO 51.a\n"
            "Country risk includes economic growth, political risk, legal risk, and economic structure.\n"
            "LO 51.b\n"
            "Composite measures are most useful as rankings because providers use different inputs.\n\n"
            "MODULE QUIZ 51.1\n"
            "1. Which source is most relevant to country risk?\n"
            "A. Political stability.\n\n"
            "ANSWER KEY FOR MODULE QUIZZES\n"
            "MODULE QUIZ 51.1\n"
            "1. A Political stability is a component of country risk. (LO 51.a)"
        ),
    )

    study_section = service._build_study_section(
        section,
        display_order=1,
        parent_group_id=None,
        previous=None,
    )

    assert [outcome.outcome_title for outcome in study_section.learning_outcomes] == [
        "LO 51.a",
        "LO 51.b",
    ]
    assert all(
        len(concept.source_excerpt) > len(concept.learning_outcome)
        for concept in study_section.concepts
    )


def test_generic_exam_book_section_builds_grounded_concepts_and_cards() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _build_section(
        title="Chapter 3: Cell Membranes and Transport",
        text=(
            "Cell membranes are selectively permeable barriers that regulate movement into and "
            "out of the cell. The phospholipid bilayer consists of hydrophilic heads and "
            "hydrophobic tails. Small nonpolar molecules cross by simple diffusion, while ions "
            "and large polar molecules require transport proteins. Active transport uses energy "
            "to move substances against a concentration gradient."
        ),
    )

    study_section = service._build_study_section(
        section,
        display_order=1,
        parent_group_id=None,
        previous=None,
    )

    assert study_section.concepts
    assert study_section.learning_outcomes
    assert "Cell" in study_section.learning_outcomes[0].outcome_title
    assert len(study_section.flashcards) >= 10
    assert all(card.source_page is not None for card in study_section.flashcards)


def test_workbook_study_section_preserves_inline_lo_concept_text() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _build_section(
        title=(
            "Study Session 1: Risk Management Overview / "
            "Reading 1: The Building Blocks of Risk Management / "
            "Module 1.1: Introduction to Risk Management"
        ),
        text=(
            "KEY CONCEPTS\n"
            "LO 1.a Risk is uncertainty surrounding outcomes. A risk management process "
            "is a series of actions designed to reduce or eliminate loss.\n"
            "LO 1.b The risk management process includes identifying, analyzing, evaluating, "
            "and managing risks.\n\n"
            "MODULE QUIZ 1.1\n"
            "1. Which statement regarding risk management is correct?\n"
            "A. Risk is uncertainty surrounding outcomes.\n\n"
            "ANSWER KEY FOR MODULE QUIZZES\n"
            "MODULE QUIZ 1.1\n"
            "1. A Risk is uncertainty surrounding outcomes. (LO 1.a)"
        ),
    )

    study_section = service._build_study_section(
        section,
        display_order=1,
        parent_group_id=None,
        previous=None,
    )

    assert study_section.key_points == []
    assert study_section.memorize_keywords == []
    assert study_section.workbook_key_concepts == [
        "LO 1.a Risk is uncertainty surrounding outcomes. A risk management process is a series of actions designed to reduce or eliminate loss.",
        "LO 1.b The risk management process includes identifying, analyzing, evaluating, and managing risks.",
    ]
    assert study_section.workbook_module_quiz[0] == "MODULE QUIZ 1.1"
    assert study_section.workbook_answer_key[-1] == "1. A Risk is uncertainty surrounding outcomes. (LO 1.a)"


def test_workbook_study_section_filters_fragment_keywords() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _build_section(
        title=(
            "Study Session 2: Risk Management Overview / "
            "Reading 4: Credit Risk Transfer / "
            "Module 4.2: Credit Derivatives Market and Securitization"
        ),
        text=(
            "EXAM FOCUS\n"
            "This reading explains credit derivatives, securitization, and the financial crisis.\n\n"
            "KEY CONCEPTS\n"
            "LO 4.b\n"
            "The existence of credit derivatives did not cause the financial crisis of 2007-2009, "
            "but misuse of these products increased risk.\n"
            "Financial crisis of 2007-2009 questions often test risk transfer and securitization.\n"
            "The financial crisis began after market conditions weakened and credit losses rose.\n"
            "Capital market line rational investors use market portfolios to compare risk and return.\n"
            "Dodd-Frank was formed to better regulate the credit derivatives space.\n\n"
            "MODULE QUIZ 4.2\n"
            "1. Which statement about credit derivatives is most accurate?\n"
            "A. They can transfer credit risk.\n"
            "B. They eliminate all risk.\n\n"
            "ANSWER KEY FOR MODULE QUIZZES\n"
            "MODULE QUIZ 4.2\n"
            "1. A Credit derivatives can transfer credit risk but do not eliminate it."
        ),
    )

    study_section = service._build_study_section(
        section,
        display_order=1,
        parent_group_id=None,
        previous=None,
    )

    assert study_section.memorize_keywords == []
    assert study_section.key_points == []
    assert "Credit Derivatives Market and Securitization" not in study_section.workbook_key_concepts
    assert "The existence of credit derivatives did not cause" in "\n".join(study_section.workbook_key_concepts)
    assert "Capital market line rational investors" in "\n".join(study_section.workbook_key_concepts)


def test_workbook_study_section_does_not_clip_key_points_mid_word() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _build_section(
        title=(
            "Study Session 2: Portfolio Theory / "
            "Reading 5: Modern Portfolio Theory / "
            "Module 5.1: Modern Portfolio Theory and the Capital Market Line"
        ),
        text=(
            "EXAM FOCUS\n"
            "This reading tests portfolio risk and diversification.\n\n"
            "KEY CONCEPTS\n"
            "LO 5.a\n"
            "A sufficiently large portfolio can reduce company-specific risk through diversification, "
            "but it remains exposed to broad market risk that cannot be diversified away by simply "
            "adding more securities to the portfolio.\n\n"
            "MODULE QUIZ 5.1\n"
            "1. Which statement about diversification is correct?\n"
            "A. It reduces company-specific risk.\n\n"
            "ANSWER KEY FOR MODULE QUIZZES\n"
            "MODULE QUIZ 5.1\n"
            "1. A Diversification reduces company-specific risk."
        ),
    )

    study_section = service._build_study_section(
        section,
        display_order=1,
        parent_group_id=None,
        previous=None,
    )

    assert study_section.key_points == []
    assert study_section.workbook_key_concepts == [
        "LO 5.a",
        "A sufficiently large portfolio can reduce company-specific risk through diversification, but it remains exposed to broad market risk that cannot be diversified away by simply adding more securities to the portfolio.",
    ]


def test_workbook_study_section_exposes_official_blocks_for_ui() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _build_section(
        title=(
            "Study Session 1: Risk Management Overview / "
            "Reading 1: The Building Blocks of Risk Management / "
            "Module 1.2: Types of Risk"
        ),
        text=(
            "KEY CONCEPTS\n"
            "LO 1.a\n"
            "Risk is uncertainty surrounding outcomes. A risk management process is a series "
            "of actions designed to reduce or eliminate loss.\n\n"
            "MODULE QUIZ 1.2\n"
            "1. In considering the major classes of risks, which risk would best describe an entity "
            "with weak internal controls?\n"
            "A. Business risk.\n"
            "B. Legal and regulatory risk.\n"
            "C. Operational risk.\n"
            "D. Strategic risk.\n\n"
            "ANSWER KEY FOR MODULE QUIZZES\n"
            "MODULE QUIZ 1.2\n"
            "1. C Operational risk includes failures of people, processes, systems, or internal controls."
        ),
    )

    study_section = service._build_study_section(
        section,
        display_order=1,
        parent_group_id=None,
        previous=None,
    )

    assert study_section.workbook_key_concepts[0] == "LO 1.a"
    assert any("Risk is uncertainty surrounding outcomes" in line for line in study_section.workbook_key_concepts)
    assert study_section.workbook_module_quiz[0] == "MODULE QUIZ 1.2"
    assert any("which risk would best describe" in line for line in study_section.workbook_module_quiz)
    assert any("C. Operational risk." == line for line in study_section.workbook_module_quiz)
    assert study_section.workbook_answer_key[0] == "ANSWER KEY FOR MODULE QUIZZES"
    assert any(line.startswith("MODULE QUIZ 1.2") for line in study_section.workbook_answer_key)
    assert any(line.startswith("1. C Operational risk") for line in study_section.workbook_answer_key)


def test_workbook_study_section_keeps_original_book_content_separate_from_ai_layers() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _build_section(
        title=(
            "Study Session 1: Risk Management Overview / "
            "Reading 1: The Building Blocks of Risk Management / "
            "Module 1.1: Introduction to Risk Management"
        ),
        text=(
            "KEY CONCEPTS\n"
            "LO 1.a\n"
            "Risk is uncertainty surrounding outcomes. A risk management process is a series "
            "of actions designed to reduce or eliminate loss.\n"
            "The four components of the risk management process are as follows:\n"
            "1. Identify risks.\n"
            "2. Analyze and measure risks.\n"
            "3. Evaluate the impact from risk events.\n"
            "4. Manage risks.\n\n"
            "MODULE QUIZ 1.1\n"
            "1. Which statement regarding risk management is correct?\n"
            "A. Risk management eliminates all uncertainty.\n"
            "B. Risk is uncertainty surrounding outcomes.\n"
            "C. Risk only refers to expected losses.\n"
            "D. Risk is unrelated to reward.\n\n"
            "ANSWER KEY FOR MODULE QUIZZES\n"
            "MODULE QUIZ 1.1\n"
            "1. B Risk is uncertainty surrounding outcomes. (LO 1.a)"
        ),
    )

    study_section = service._build_study_section(
        section,
        display_order=1,
        parent_group_id=None,
        previous=None,
    )

    assert study_section.original_book_content.key_concepts[0].content_origin == "original_book"
    assert study_section.original_book_content.key_concepts[0].title == "LO 1.a"
    assert "Risk is uncertainty surrounding outcomes" in study_section.original_book_content.key_concepts[0].content
    assert study_section.original_book_content.module_quiz[0].content_origin == "original_book"
    assert study_section.original_book_content.answers[0].content_origin == "original_book"
    assert study_section.learning_outcomes[0].content_origin == "original_book"
    assert study_section.concepts[0].content_origin == "ai_generated_from_original"
    assert study_section.flashcards[0].content_origin == "ai_generated_from_original"
    assert study_section.flashcards[0].source_page == study_section.page_start
    assert study_section.formulas == []


def test_workbook_study_section_generates_content_specific_flashcards_and_strict_formulas() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _build_section(
        title=(
            "Study Session 1: Risk Management Overview / "
            "Reading 1: The Building Blocks of Risk Management / "
            "Module 1.1: Introduction to Risk Management"
        ),
        text=(
            "KEY CONCEPTS\n"
            "LO 1.a\n"
            "Risk is uncertainty surrounding outcomes. A risk management process is a series "
            "of actions designed to reduce or eliminate loss. Risk taking accepts incremental "
            "risk in pursuit of incremental gains.\n"
            "The four components of the risk management process are as follows:\n"
            "1. Identify risks.\n"
            "2. Analyze and measure risks.\n"
            "3. Evaluate the impact from risk events.\n"
            "4. Manage risks.\n\n"
            "FORMULAS\n"
            "Expected loss: EL = EAD × PD × LGD\n\n"
            "MODULE QUIZ 1.1\n"
            "1. Which statement regarding risk management is correct?\n"
            "A. Risk management eliminates all uncertainty.\n"
            "B. Risk is uncertainty surrounding outcomes.\n"
            "C. Risk only refers to expected losses.\n"
            "D. Risk is unrelated to reward.\n\n"
            "ANSWER KEY FOR MODULE QUIZZES\n"
            "MODULE QUIZ 1.1\n"
            "1. B Risk is uncertainty surrounding outcomes. (LO 1.a)"
        ),
    )

    study_section = service._build_study_section(
        section,
        display_order=1,
        parent_group_id=None,
        previous=None,
    )

    fronts = [card.front.lower() for card in study_section.flashcards]
    assert not any("what exact rule" in front for front in fronts)
    assert not any("what does this module say" in front for front in fronts)
    assert not any("what is the key idea" in front for front in fronts)
    assert any("what is risk" in front for front in fronts)
    assert any("four components of the risk management process" in front for front in fronts)
    concept_cards = [card for card in study_section.flashcards if card.concept_id and not card.formula_id]
    assert len(concept_cards) >= 10
    assert any("what does risk taking involve" in front for front in fronts)
    assert any("which step comes first in the risk management process" in front for front in fronts)
    assert any("what does a risk management process try to reduce or eliminate" in front for front in fronts)
    assert all(
        len(card.back.split()) <= 32 or card.card_type == "list_recall"
        for card in concept_cards
    )

    formula_texts = [formula.formula_text for formula in study_section.formulas]
    assert formula_texts == ["EL = EAD × PD × LGD"]
    formula = study_section.formulas[0]
    assert formula.formula_name == "Expected loss"
    assert formula.variables_json["PD"] == "Probability of default"
    assert formula.reading_number == 1
    assert formula.formula_section_page == formula.source_page
    assert formula.parse_confidence == "high"
    assert formula.needs_review is False
    assert formula.source_image_crop_path is None
    formula_card = next(card for card in study_section.flashcards if card.formula_id == formula.formula_id)
    assert formula_card.anchor_type == "formula"
    assert formula_card.anchor_text == "Expected loss"
    assert formula_card.source_text_snippet
    assert formula_card.quality_score >= 0.8
    assert len(formula_card.source_hash) == 64

    formula_cards = [card for card in study_section.flashcards if card.card_type == "formula"]
    assert formula_cards
    assert formula_cards[0].formula_id == formula.formula_id
    assert any("formula for expected loss" in card.front.lower() for card in formula_cards)
    assert any("in expected loss, what does pd mean" in card.front.lower() for card in study_section.flashcards)
    assert not any("Identify risks" in formula.formula_text for formula in study_section.formulas)


def test_study_document_preserves_final_formula_session_from_formula_assets(tmp_path) -> None:
    store = LocalMaterialStore(tmp_path)
    material_id = "mat-formula-study"
    record = MaterialRecord(
        material_id=material_id,
        course_id="course-1",
        file_name="frm-book.pdf",
        content_type="application/pdf",
        page_count=12,
        section_count=2,
        content_hash="formula-study-hash",
    )
    module_section = _build_section(
        title=(
            "Study Session 1: Risk Management Overview / "
            "Reading 1: The Building Blocks of Risk Management / "
            "Module 1.1: Introduction to Risk Management"
        ),
        text=(
            "KEY CONCEPTS\n"
            "LO 1.a\n"
            "Risk is uncertainty surrounding outcomes. The risk management process has four "
            "components: identify risks, analyze and measure risks, evaluate risk events, and manage risks.\n"
            "MODULE QUIZ 1.1\n"
            "1. Which statement regarding risk management is correct?\n"
            "A. Risk management eliminates all uncertainty.\n"
            "B. Risk is uncertainty surrounding outcomes.\n"
            "C. Risk only refers to expected losses.\n"
            "D. Risk is unrelated to reward.\n"
            "ANSWER KEY FOR MODULE QUIZZES\n"
            "MODULE QUIZ 1.1\n"
            "1. B Risk is uncertainty surrounding outcomes. (LO 1.a)"
        ),
    )
    formula_section = SourceSection(
        source_id="source-formulas",
        material_id=material_id,
        course_id="course-1",
        file_name="frm-book.pdf",
        content_type="application/pdf",
        section_title="Formulas",
        text="FORMULAS\n\nReading 1\n\nReading 5",
        page_end=12,
        section_kind=SectionKind.REFERENCE,
        content_label=ContentLabel.TESTABLE_CONTENT,
        formula_assets=[
            FormulaAsset(
                source_page=12,
                path="formula-crop://mat-formula-study/page-12-image-1.png",
                label="Expected loss formula crop",
                confidence=0.72,
                reading_number=1,
                extracted_text="expected loss: EL = EAD × PD × LGD",
                extracted_latex=r"\text{expected loss}: EL = EAD \times PD \times LGD",
                extracted_latex_blocks=[r"EL = EAD \times PD \times LGD"],
                ocr_engine="test-ocr",
                ocr_confidence=0.91,
                needs_review=False,
            )
        ],
        locator=SourceLocator(section_index=2, page_number=12),
        citation_label="frm-book.pdf page 12",
    )
    module_section = module_section.model_copy(
        update={
            "material_id": material_id,
            "course_id": "course-1",
            "locator": SourceLocator(section_index=1, page_number=1),
            "page_end": 5,
        }
    )
    store.save_parsed_document(
        ParsedMaterialDocument(record=record, sections=[module_section, formula_section], chunks=[]),
        raw_bytes=b"",
    )

    study_document = SectionStudyService(store).ensure_study_document(material_id, force=True)

    assert study_document is not None
    assert [group.title for group in study_document.groups] == [
        "Study Session 1 · Reading 1: The Building Blocks of Risk Management",
        "Formulas",
    ]
    assert study_document.groups[-1].page_start == 12
    assert study_document.groups[-1].page_end == 12
    formula_study_section = study_document.sections[-1]
    assert formula_study_section.title == "Formulas"
    assert formula_study_section.parent_group_id == study_document.groups[-1].group_id
    assert formula_study_section.formulas
    assert formula_study_section.formulas[0].source_image_crop_path == (
        "/api/v1/materials/mat-formula-study/formula-crops/page-12-image-1.png"
    )
    assert formula_study_section.formulas[0].reading_number == 1
    assert formula_study_section.formulas[0].formula_text == "expected loss: EL = EAD × PD × LGD"
    assert formula_study_section.formulas[0].formula_latex == (
        r"\text{expected loss}: EL = EAD \times PD \times LGD"
    )
    assert formula_study_section.formulas[0].parse_confidence == "high"
    assert formula_study_section.formulas[0].needs_review is False
    assert "formula-crop://" not in formula_study_section.summary
    assert "formula-crop://" not in "\n".join(formula_study_section.key_points)


def test_flashcard_generation_attempts_ten_cards_per_learning_outcome_without_junk() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _build_section(
        title=(
            "Study Session 1: Risk Management Overview / "
            "Reading 1: The Building Blocks of Risk Management / "
            "Module 1.1: Introduction to Risk Management"
        ),
        text="Module 1.1 source text",
    )
    rich_excerpt = (
        "LO 1.a\n"
        "Risk is uncertainty surrounding outcomes. A risk management process is a series "
        "of actions designed to reduce or eliminate the potential to incur loss. "
        "Risk taking refers to the active acceptance of incremental risk in the pursuit of incremental gains. "
        "The risk management process is a formal series of actions designed to determine if the perceived "
        "reward justifies the expected risks.\n"
        "The four components of the risk management process are as follows:\n"
        "1. Identify risks.\n"
        "2. Analyze and measure risks.\n"
        "3. Evaluate the impact from risk events.\n"
        "4. Manage risks."
    )
    rich_concept = StudyConceptCard(
        concept_id="concept-lo-1-a",
        material_id=section.material_id,
        module_id=section.module_id,
        title="LO 1.a",
        learning_outcome="LO 1.a",
        related_original_key_concept_id="lo-1-a",
        source_pages=[13],
        source_excerpt=rich_excerpt,
        simplified_explanation="Risk management balances potential reward against expected risks.",
        key_terms=["Risk", "Risk management process", "Risk taking", "Expected risks"],
        formulas=[],
        exam_focus="Know the components and distinction between risk management and risk taking.",
        common_traps=[
            "Do not assume risk management eliminates all uncertainty; it reduces or manages potential loss."
        ],
    )

    cards = service._flashcards_from_original_book(
        section,
        OriginalBookContent(),
        [rich_concept],
        [],
    )

    concept_cards = [card for card in cards if card.concept_id == rich_concept.concept_id]
    fronts = [card.front.lower() for card in concept_cards]
    assert len(concept_cards) >= 10
    assert len(fronts) == len(set(fronts))
    assert not any("what exact rule" in front for front in fronts)
    assert not any("what does this module say" in front for front in fronts)
    assert all(card.learning_outcome_id == "lo-1-a" for card in concept_cards)
    assert all(card.source_page == 13 for card in concept_cards)
    assert all(card.source_excerpt == rich_excerpt for card in concept_cards)
    assert not any(card.needs_more_source for card in concept_cards)


def test_short_learning_outcome_flashcards_are_marked_as_needing_more_source() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _build_section()
    short_concept = StudyConceptCard(
        concept_id="concept-short-lo",
        material_id=section.material_id,
        module_id=section.module_id,
        title="LO 1.z",
        learning_outcome="LO 1.z",
        related_original_key_concept_id="lo-1-z",
        source_pages=[14],
        source_excerpt="LO 1.z\nRisk matters.",
        simplified_explanation="Risk matters.",
        key_terms=["Risk"],
        formulas=[],
        exam_focus="",
        common_traps=[],
    )

    cards = service._content_specific_flashcards_for_concept(section, short_concept)

    assert len(cards) < 10
    assert cards
    assert all(card.needs_more_source for card in cards)
    assert not any("what exact rule" in card.front.lower() for card in cards)


def test_flashcards_store_concise_answers_separately_from_source_excerpt() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _build_section()
    source_excerpt = (
        "LO 1.a\n"
        "Risk is uncertainty surrounding outcomes. A risk management process is a series of actions "
        "designed to reduce or eliminate the potential to incur loss. Risk taking refers to the active "
        "acceptance of incremental risk in the pursuit of incremental gains.\n"
        "The risk management process is a formal series of actions designed to determine if the perceived "
        "reward justifies the expected risks. The four components of the risk management process are as follows:\n"
        "1. Identify risks.\n"
        "2. Analyze and measure risks.\n"
        "3. Evaluate the impact from risk events.\n"
        "4. Manage risks."
    )
    concept = StudyConceptCard(
        concept_id="concept-risk-management",
        material_id=section.material_id,
        module_id=section.module_id,
        title="LO 1.a Risk management",
        learning_outcome="LO 1.a",
        related_original_key_concept_id="lo-1-a",
        source_pages=[13],
        source_excerpt=source_excerpt,
        simplified_explanation="Risk management is the process of identifying, measuring, evaluating, and managing risks.",
        key_terms=["risk", "risk management", "risk taking"],
        formulas=[],
        exam_focus="Know the components of the risk management process.",
        common_traps=[],
    )

    cards = service._content_specific_flashcards_for_concept(section, concept)
    definition_card = next(card for card in cards if card.front == "What is risk?")
    list_card = next(
        card for card in cards
        if card.front == "What are the four components of the risk management process?"
    )

    assert definition_card.back_concise == "Risk is uncertainty surrounding outcomes."
    assert definition_card.back == definition_card.back_concise
    assert definition_card.source_excerpt == source_excerpt
    assert "Risk taking refers" not in definition_card.back_concise
    assert list_card.back_concise == (
        "1. Identify risks.\n"
        "2. Analyze and measure risks.\n"
        "3. Evaluate the impact from risk events.\n"
        "4. Manage risks."
    )
    assert "Risk taking refers" not in list_card.back_concise


def test_generated_flashcard_quality_flags_reject_generic_and_invalid_cards() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]

    def build_card(
        *,
        front: str,
        back: str = "Risk is uncertainty surrounding outcomes.",
        card_type: str = "definition",
        source_page: int | None = 13,
        concept_id: str | None = "concept-risk",
        learning_outcome_id: str | None = "lo-1-a",
        formula_id: str | None = None,
        source_excerpt: str | None = None,
    ) -> StudyFlashcard:
        return StudyFlashcard(
            flashcard_id=f"card-{abs(hash((front, back, card_type))) % 100000}",
            material_id="mat-1",
            learning_outcome_id=learning_outcome_id,
            concept_id=concept_id,
            formula_id=formula_id,
            front=front,
            back=back,
            card_type=card_type,
            source_page=source_page,
            source_excerpt=source_excerpt if source_excerpt is not None else "Risk is uncertainty surrounding outcomes.",
        )

    generic_fronts = [
        "What exact rule, formula, or step does the book give here?",
        "What does this module say?",
        "What is the key idea in this LO?",
        "What does the book give here?",
        "Summarize this section.",
        "What exam trap should you remember for Value risk economic capital ways?",
    ]
    for front in generic_fronts:
        assert "generic_question" in service._flashcard_quality_flags(build_card(front=front))

    assert "missing_source_page" in service._flashcard_quality_flags(
        build_card(front="What is risk?", source_page=None)
    )
    assert "missing_learning_outcome_link" in service._flashcard_quality_flags(
        build_card(front="What is risk?", learning_outcome_id=None)
    )
    assert "missing_concept_link" in service._flashcard_quality_flags(
        build_card(front="What is risk?", concept_id=None)
    )
    assert "missing_content_anchor" in service._flashcard_quality_flags(
        build_card(front="How should you prepare?", back="Review the section.")
    )
    full_excerpt = (
        "Risk is uncertainty surrounding outcomes. A risk management process is a series of actions. "
        "Risk taking accepts incremental risk."
    )
    assert "answer_is_source_excerpt" in service._flashcard_quality_flags(
        build_card(front="What is risk?", back=full_excerpt, source_excerpt=full_excerpt)
    )
    assert "answer_too_long" in service._flashcard_quality_flags(
        build_card(
            front="What is risk?",
            back="Risk is uncertainty. It can vary. It affects reward. It must be managed.",
            source_excerpt="Risk is uncertainty surrounding outcomes.",
        )
    )
    assert "formula_without_formula" in service._flashcard_quality_flags(
        build_card(
            front="What is the formula for expected loss?",
            back="Use three inputs.",
            card_type="formula",
            learning_outcome_id=None,
        )
    )
    assert service._flashcard_quality_flags(
        build_card(front="What are the four components of the risk management process?")
    ) == []
    assert service._flashcard_quality_flags(build_card(front="What is risk?")) == []
    assert service._flashcard_quality_flags(
        build_card(
            front="What is the expected loss formula?",
            back="EL = EAD × PD × LGD",
            card_type="formula",
            concept_id=None,
            learning_outcome_id=None,
            formula_id="formula-expected-loss",
            source_excerpt="Expected loss: EL = EAD × PD × LGD",
        )
    ) == []
    assert service._flashcard_quality_flags(
        build_card(
            front="What does beta measure?",
            back="Beta measures systematic risk relative to the market.",
            source_excerpt="Beta measures systematic risk relative to the market.",
        )
    ) == []


def test_exam_trap_flashcards_use_clean_academic_prompts() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _build_section()
    concept = StudyConceptCard(
        concept_id="concept-expected-loss",
        material_id=section.material_id,
        module_id=section.module_id,
        title="Expected losses average loss expected",
        learning_outcome="LO 1.c",
        related_original_key_concept_id="lo-1-c",
        source_pages=[14],
        source_excerpt=(
            "LO 1.c\n"
            "Expected losses are the average loss expected over a given time horizon. "
            "Unexpected losses are losses that exceed the average result expected."
        ),
        simplified_explanation="Expected loss is the average loss expected over a time horizon.",
        key_terms=["expected loss", "unexpected loss"],
        formulas=[],
        exam_focus="Distinguish expected losses from unexpected losses.",
        common_traps=[
            "Do not confuse expected losses with unexpected losses that exceed the average result expected."
        ],
    )

    cards = service._content_specific_flashcards_for_concept(section, concept)
    fronts = [card.front for card in cards]

    assert "What is a common mistake when interpreting expected loss?" in fronts
    assert not any("What exam trap should you remember for" in front for front in fronts)
    assert all(service._flashcard_quality_flags(card) == [] for card in cards)


def test_flashcard_generation_strips_lo_labels_and_phrase_soup_from_prompts() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _build_section()
    concept = StudyConceptCard(
        concept_id="concept-risk-appetite",
        material_id=section.material_id,
        module_id=section.module_id,
        title="LO 2.b Risk appetite",
        learning_outcome="LO 2.b",
        related_original_key_concept_id="lo-2-b",
        source_pages=[30],
        source_excerpt=(
            "LO 2.b\n"
            "A firm's risk appetite is its willingness to retain risk. It is usually influenced "
            "by line managers right on up to senior managers."
        ),
        simplified_explanation="Risk appetite is willingness to retain risk.",
        key_terms=[
            "firms",
            "management strategies",
            "retain risk",
            "is usually influenced",
            "line managers right",
            "senior managers",
            "risk appetite",
        ],
        formulas=[],
        exam_focus="Explain how risk appetite affects corporate risk management.",
        common_traps=[],
    )

    cards = service._content_specific_flashcards_for_concept(section, concept)
    fronts = [card.front for card in cards]

    assert fronts
    assert all("LO 2.b" not in front for front in fronts)
    assert all("LO2" not in front.replace(" ", "") for front in fronts)
    assert not any("Why does firms matter" in front for front in fronts)
    assert not any("line managers right" in front.lower() for front in fronts)
    assert any("risk appetite" in front.lower() for front in fronts)
    assert "generic_question" in service._flashcard_quality_flags(
        StudyFlashcard(
            flashcard_id="bad-lo-prompt",
            material_id=section.material_id,
            learning_outcome_id="lo-2-b",
            concept_id=concept.concept_id,
            front="Why does firms matter for LO 2.b?",
            back="Risk appetite is willingness to retain risk.",
            card_type="application",
            source_page=30,
            source_excerpt=concept.source_excerpt,
        )
    )
    assert all(service._flashcard_quality_flags(card) == [] for card in cards)


def test_probability_flashcards_are_source_grounded_and_reject_fragment_terms() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _build_section()
    concept = StudyConceptCard(
        concept_id="concept-probability",
        material_id=section.material_id,
        module_id=section.module_id,
        title="Probability events",
        learning_outcome="LO 2.a",
        related_original_key_concept_id="lo-2-a",
        source_pages=[22],
        source_excerpt=(
            "LO 2.a\n"
            "The event space is the set of all possible outcomes. A random event is one or more "
            "outcomes from the event space. Two events A and B are independent if "
            "P(A ∩ B) = P(A)P(B). Equivalently, P(A|B) = P(A) when P(B) > 0. "
            "Two events are mutually exclusive if P(A ∩ B) = 0."
        ),
        simplified_explanation="Events, independence, and mutual exclusivity describe probability relationships.",
        key_terms=[
            "event is one",
            "of the possible",
            "all the subsets",
            "event space",
            "random event",
            "independent events",
            "mutually exclusive events",
        ],
        formulas=[],
        exam_focus="Compare independent and mutually exclusive events.",
        common_traps=[],
    )

    cards = service._content_specific_flashcards_for_concept(section, concept)
    fronts = [card.front for card in cards]
    answers = {card.front: card.back_concise or card.back for card in cards}

    assert "What condition defines independence between events A and B?" in fronts
    assert "What condition defines mutually exclusive events?" in fronts
    assert "What is the key difference between independent and mutually exclusive events?" in fronts
    assert "What is the event space in probability?" in fronts
    assert "What is a random event?" in fronts
    assert not any("What is event is one" in front for front in fronts)
    assert not any("What is of the possible" in front for front in fronts)
    assert not any("What is all the subsets" in front for front in fronts)
    assert "P(A ∩ B) = P(A)P(B)" in answers["What condition defines independence between events A and B?"]
    assert "P(A ∩ B) = 0" in answers["What condition defines mutually exclusive events?"]
    assert all(service._flashcard_quality_flags(card) == [] for card in cards)
    for card in cards:
        StudyFlashcard.model_validate(card.model_dump())
        assert card.source_page == 22
        assert (card.back_concise or card.back).strip()


def test_time_series_flashcards_reject_conditional_phrase_soup() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _build_section(
        title=(
            "Study Session 6: Quantitative Analysis / "
            "Reading 21: Stationarity / "
            "Module 21.1: Covariance Stationary"
        ),
        text="Time series source text",
    )
    concept = StudyConceptCard(
        concept_id="concept-lo-21",
        material_id=section.material_id,
        module_id=section.module_id,
        title="Define white noise describe independent",
        learning_outcome="LO 21.c",
        related_original_key_concept_id="lo-21-c",
        source_pages=[144],
        source_excerpt=(
            "LO 21.c\n"
            "Define white noise, and describe independent white noise and normal (Gaussian) white noise.\n"
            "A time series might exhibit zero correlation among any of its lagged values. Such a time "
            "series is said to be serially uncorrelated. A special type of serially uncorrelated series "
            "is one that has a mean of zero and a constant variance. This condition is referred to as "
            "white noise, or zero-mean white noise, and the time series is said to follow a white noise "
            "process. If the observations in a white noise process are independent, as well as "
            "uncorrelated, the process is referred to as independent white noise. Not all independent "
            "white noise processes are normally distributed, but all normal white noise processes are "
            "also independent white noise."
        ),
        simplified_explanation=(
            "White noise is a serially uncorrelated series with mean zero and constant variance."
        ),
        key_terms=[
            "White",
            "Serially Uncorrelated Series",
            "Mean Of Zero",
            "Constant Variance",
            "White Noise Process",
            "Normal Distribution",
        ],
        formulas=[],
        exam_focus="Define white noise and distinguish independent white noise.",
        common_traps=[],
    )

    cards = service._content_specific_flashcards_for_concept(section, concept)
    fronts = {card.front for card in cards}

    assert "What is white noise?" in fronts
    assert "What is independent white noise?" in fronts
    assert "What condition defines a serially uncorrelated time series?" in fronts
    assert "What is the relationship between normal white noise and independent white noise?" in fronts
    assert not any("What is if a time series" in front for front in fronts)
    assert not any("What is such a time series" in front for front in fronts)
    assert not any("What are if the observations" in front for front in fronts)
    assert not any("What are not all" in front for front in fronts)
    assert not any("What is a special type of serially uncorrelated series" in front for front in fronts)
    assert all(service._flashcard_quality_flags(card) == [] for card in cards)


def test_flashcard_quality_flags_reject_broken_fragment_questions() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]

    def card(front: str) -> StudyFlashcard:
        return StudyFlashcard(
            flashcard_id=f"bad-{abs(hash(front)) % 10000}",
            material_id="mat-1",
            learning_outcome_id="lo-2-a",
            concept_id="concept-probability",
            front=front,
            back="Events are subsets of the event space.",
            card_type="definition",
            source_page=22,
            source_excerpt="The event space is the set of all possible outcomes.",
        )

    for front in [
        "What is event is one?",
        "What is of the possible?",
        "What is all the subsets?",
        "What is the following conditions?",
        "What is random event?",
    ]:
        assert "generic_question" in service._flashcard_quality_flags(card(front))

    assert service._flashcard_quality_flags(card("What is a random event?")) == []


def test_flashcard_quality_flags_reject_book_three_and_four_fragment_questions() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]

    def card(front: str) -> StudyFlashcard:
        return StudyFlashcard(
            flashcard_id=f"bad-{abs(hash(front)) % 10000}",
            material_id="mat-1",
            learning_outcome_id="lo-38-b",
            concept_id="concept-options",
            front=front,
            back="Option writers must maintain margin because written options can create high potential losses.",
            card_type="definition",
            source_page=138,
            source_excerpt=(
                "Options with maturities of nine months or fewer cannot be purchased on margin. "
                "Investors who engage in writing options must have a margin account due to the high "
                "potential losses and potential default."
            ),
        )

    for front in [
        "What are because option contracts?",
        "What are no payments?",
        "What is payment?",
        "What are if the observations in a white noise process?",
        "What are suppose that simulated data for 300 days?",
        "What are some?",
        "What are countries?",
        "What is also assume that the Treasury bond futures contract?",
        "What are assume that there?",
        "What is also assume that?",
        "What are assume that the short position?",
    ]:
        assert "generic_question" in service._flashcard_quality_flags(card(front))

    assert service._flashcard_quality_flags(
        card("Why must option writers maintain a margin account?")
    ) == []


def test_treasury_bond_futures_excerpt_generates_ten_specific_cards_without_assume_fragments() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _build_section(
        title=(
            "Study Session 10: Financial Markets and Products / "
            "Reading 45: Treasury Bond Futures / "
            "Module 45.2: Treasury Bond Futures"
        ),
        text="Treasury bond futures source text",
    )
    concept = StudyConceptCard(
        concept_id="concept-treasury-bond-futures",
        material_id=section.material_id,
        module_id=section.module_id,
        title="Treasury bond futures contract",
        learning_outcome="LO 45.g",
        related_original_key_concept_id="lo-45-g",
        source_pages=[236],
        source_excerpt=(
            "LO 45.g\n"
            "Treasury bond futures contracts require the short position to deliver an eligible "
            "Treasury security. The long position pays the futures price plus accrued interest. "
            "Delivery options include quality, timing, and wild card options. The conversion "
            "factor adjusts quoted prices for different deliverable bonds. The cheapest-to-deliver "
            "bond is selected by the short position to minimize delivery cost. The basis is the "
            "cash bond price minus the futures price adjusted by the conversion factor. Treasury "
            "bond futures can hedge interest rate risk, but delivery choices and contract "
            "assumptions affect the hedge. Also assume that the Treasury bond futures contract "
            "satisfies exchange eligibility rules."
        ),
        simplified_explanation=(
            "Treasury bond futures use deliverable bonds, conversion factors, and delivery options "
            "that affect hedging outcomes."
        ),
        key_terms=[
            "Treasury bond futures contract",
            "short position",
            "long position",
            "delivery options",
            "quality option",
            "timing option",
            "wild card option",
            "conversion factor",
            "cheapest-to-deliver bond",
            "basis",
            "accrued interest",
            "interest rate risk",
            "deliverable bond",
        ],
        formulas=[],
        exam_focus="Explain Treasury bond futures delivery, conversion factors, basis, and hedging.",
        common_traps=[],
    )

    cards = service._content_specific_flashcards_for_concept(section, concept)
    fronts = {card.front for card in cards}

    assert len(cards) >= 10
    assert "What is a Treasury bond futures contract?" in fronts
    assert "What does the short position deliver in a Treasury bond futures contract?" in fronts
    assert "What does the long position pay in a Treasury bond futures contract?" in fronts
    assert "What do delivery options include in Treasury bond futures?" in fronts
    assert "What does the conversion factor adjust in Treasury bond futures?" in fronts
    assert "What is the cheapest-to-deliver bond?" in fronts
    assert "What is basis in Treasury bond futures?" in fronts
    assert "What risk can Treasury bond futures hedge?" in fronts
    assert "Why do delivery choices matter in Treasury bond futures hedges?" in fronts
    assert "What eligibility rule matters for a delivered bond in a Treasury bond futures contract?" in fronts
    assert not any("assume that" in front.lower() for front in fronts)
    assert not any(front.lower().startswith(("what is also", "what are assume")) for front in fronts)
    assert all(service._flashcard_quality_flags(card) == [] for card in cards)


def test_options_excerpt_generates_specific_cards_without_phrase_soup() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _build_section(
        title=(
            "Study Session 9: Financial Markets and Products / "
            "Reading 38: Options Markets / "
            "Module 38.1: Option Types, Positions, and Underlying Assets"
        ),
        text="Options source text",
    )
    concept = StudyConceptCard(
        concept_id="concept-options-margin-occ",
        material_id=section.material_id,
        module_id=section.module_id,
        title="Option margin requirements and clearing",
        learning_outcome="LO 38.b",
        related_original_key_concept_id="lo-38-b",
        source_pages=[138],
        source_excerpt=(
            "LO 38.b\n"
            "Margin Requirements. Options with maturities of nine months or fewer cannot be purchased "
            "on margin because the leverage would become too high. For options with longer maturities, "
            "investors can borrow a maximum of 25% of the option value. Investors who engage in writing "
            "options must have a margin account due to the high potential losses and potential default. "
            "Uncovered calls are those in which the writer does not also own a position in the underlying "
            "asset. Writing covered calls is far less risky than uncovered call writing and requires no "
            "margin. Options Clearing Corporation (OCC) guarantees that buyers and sellers in the "
            "exchange-traded options market will honor their obligations and records all option positions."
        ),
        simplified_explanation="Option writers face margin requirements and OCC clearing reduces default risk.",
        key_terms=[
            "Margin Requirements",
            "Option writers",
            "Uncovered calls",
            "Covered calls",
            "Options Clearing Corporation (OCC)",
            "Default risk",
        ],
        formulas=[],
        exam_focus="Describe margin requirements and clearing for exchange-traded options.",
        common_traps=[],
    )

    cards = service._content_specific_flashcards_for_concept(section, concept)
    fronts = {card.front for card in cards}

    assert "Why must option writers maintain a margin account?" in fronts
    assert "What is an uncovered call?" in fronts
    assert "How does covered call writing differ from uncovered call writing?" in fronts
    assert "What does the Options Clearing Corporation (OCC) guarantee?" in fronts
    assert "What margin rule applies to options with maturities of nine months or fewer?" in fronts
    assert len(cards) >= 8
    assert not any("What are because option contracts" in front for front in fronts)
    assert not any("What are no payments" in front for front in fronts)
    assert all(service._flashcard_quality_flags(card) == [] for card in cards)


def test_insurance_excerpt_generates_specific_cards_without_payment_fragments() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _build_section(
        title=(
            "Study Session 7: Financial Markets and Products / "
            "Reading 28: Insurance Companies and Pension Plans / "
            "Module 28.1: Insurance Companies and Pension Plans"
        ),
        text="Insurance source text",
    )
    concept = StudyConceptCard(
        concept_id="concept-insurance-pension",
        material_id=section.material_id,
        module_id=section.module_id,
        title="Insurance companies and pension plans",
        learning_outcome="LO 28.e",
        related_original_key_concept_id="lo-28-e",
        source_pages=[22],
        source_excerpt=(
            "LO 28.e\n"
            "Insurance companies provide coverage by collecting premiums and making payments when "
            "covered losses occur. Diversification reduces total portfolio risk because losses are "
            "not perfectly correlated across policyholders. Three categories of insurance companies "
            "include life insurance, property and casualty insurance, and health insurance. Pension "
            "plans accumulate contributions and invest assets to meet future retirement obligations."
        ),
        simplified_explanation="Insurance companies pool risks and pension plans invest assets for future obligations.",
        key_terms=[
            "Insurance coverage",
            "Premiums",
            "Diversification",
            "Life insurance",
            "Property and casualty insurance",
            "Health insurance",
            "Pension plans",
        ],
        formulas=[],
        exam_focus="Explain insurance company types, risk pooling, and pension plan obligations.",
        common_traps=[],
    )

    cards = service._content_specific_flashcards_for_concept(section, concept)
    fronts = {card.front for card in cards}

    assert "What is insurance coverage?" in fronts
    assert "How does diversification reduce total portfolio risk?" in fronts
    assert "What are the three categories of insurance companies?" in fronts
    assert "What do pension plans accumulate contributions for?" in fronts
    assert len(cards) >= 8
    assert not any(front in {"What are no payments?", "What is payment?"} for front in fronts)
    assert all(service._flashcard_quality_flags(card) == [] for card in cards)


def test_flashcard_generation_skips_invalid_source_units_before_prompting() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _build_section()
    concept = StudyConceptCard(
        concept_id="concept-fragments",
        material_id=section.material_id,
        module_id=section.module_id,
        title="Fragment concept",
        learning_outcome="LO 2.z",
        related_original_key_concept_id="lo-2-z",
        source_pages=[23],
        source_excerpt="LO 2.z\nEvent is one. Of the possible. All the subsets.",
        simplified_explanation="Event is one.",
        key_terms=["event is one", "of the possible", "all the subsets"],
        formulas=[],
        exam_focus="",
        common_traps=[],
    )

    assert service._content_specific_flashcards_for_concept(section, concept) == []


def test_flashcard_publish_gate_discards_low_quality_first_output() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]

    def card(front: str, *, answer: str = "Risk is uncertainty surrounding outcomes.") -> StudyFlashcard:
        return StudyFlashcard(
            flashcard_id=f"card-{abs(hash(front)) % 10000}",
            material_id="mat-1",
            learning_outcome_id="lo-1-a",
            concept_id="concept-risk",
            front=front,
            back=answer,
            back_concise=answer,
            card_type="definition",
            source_page=13,
            source_excerpt="Risk is uncertainty surrounding outcomes.",
        )

    published = service._valid_unique_flashcards(
        [
            card("What is event is one?", answer="Event is one."),
            card("What is of the possible?", answer="Of the possible."),
            card("What is risk?"),
        ],
        limit=10,
    )

    assert [card.front for card in published] == ["What is risk?"]


def test_flashcard_quality_flags_reject_dangling_phrase_questions() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]

    def card(front: str) -> StudyFlashcard:
        return StudyFlashcard(
            flashcard_id=f"bad-{abs(hash(front)) % 10000}",
            material_id="mat-1",
            learning_outcome_id="lo-1-d",
            concept_id="concept-risk-reward",
            front=front,
            back="Lower-risk opportunities usually have lower reward potential.",
            card_type="application",
            source_page=15,
            source_excerpt=(
                "There is an observed trade-off between risk and reward; "
                "opportunities with lower risk have lower reward potential."
            ),
        )

    for front in [
        "What is and reward?",
        "What is opportunities with lower?",
        "What is risk have lower?",
        "What is to the risk?",
        "What are or the bonds?",
        "What is order?",
        "How does methods include scenario relate to value risk economic capital ways?",
    ]:
        assert "generic_question" in service._flashcard_quality_flags(card(front))

    assert service._flashcard_quality_flags(
        card("Why do lower-risk opportunities usually have lower reward potential?")
    ) == []


def test_value_at_risk_flashcards_use_term_anchor_and_exam_questions() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _build_section(
        title=(
            "Study Session 2: Quantitative Analysis / "
            "Reading 7: Risk Measures / "
            "Module 7.1: Value at Risk"
        ),
        text="Value at risk source text",
    )
    source_excerpt = (
        "LO 7.a\n"
        "Value at risk (VaR) estimates the loss amount that may be exceeded with a specified "
        "probability over a defined time horizon. A one-day VaR of $2.5 million at the 95% "
        "confidence level means there is a 5% chance the one-day loss will exceed $2.5 million. "
        "VaR does not show loss severity beyond the threshold and depends on distribution and "
        "liquidity assumptions. Expected shortfall measures the average loss beyond the VaR threshold."
    )
    concept = StudyConceptCard(
        concept_id="concept-var",
        material_id=section.material_id,
        module_id=section.module_id,
        title="Value at risk (VaR)",
        learning_outcome="LO 7.a",
        related_original_key_concept_id="lo-7-a",
        source_pages=[101],
        source_excerpt=source_excerpt,
        simplified_explanation="Value at risk estimates a loss threshold over a time horizon.",
        key_terms=["Value at risk (VaR)", "Expected shortfall", "confidence level"],
        formulas=[],
        exam_focus="Interpret VaR and distinguish it from expected shortfall.",
        common_traps=[
            "Do not treat VaR as the maximum possible loss; it does not show severity beyond the threshold."
        ],
    )

    cards = service._content_specific_flashcards_for_concept(section, concept)
    fronts = [card.front for card in cards]
    answers = {card.front: card.back_concise or card.back for card in cards}

    assert "What is value at risk (VaR)?" in fronts
    assert "How do you interpret a one-day VaR of $2.5 million at the 95% confidence level?" in fronts
    assert "What are the main limitations of value at risk (VaR)?" in fronts
    assert "How does value at risk (VaR) differ from expected shortfall?" in fronts
    assert "5% chance" in answers[
        "How do you interpret a one-day VaR of $2.5 million at the 95% confidence level?"
    ]
    assert all(service._flashcard_quality_flags(card) == [] for card in cards)


def test_generated_flashcards_store_source_anchor_metadata_and_quality_score() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _build_section(
        title=(
            "Study Session 2: Quantitative Analysis / "
            "Reading 7: Risk Measures / "
            "Module 7.1: Value at Risk"
        ),
        text="Value at risk source text",
    )
    source_excerpt = (
        "LO 7.a\n"
        "Value at risk (VaR) estimates the loss amount that may be exceeded with a specified "
        "probability over a defined time horizon. A one-day VaR of $2.5 million at the 95% "
        "confidence level means there is a 5% chance the one-day loss will exceed $2.5 million."
    )
    concept = StudyConceptCard(
        concept_id="concept-var",
        material_id=section.material_id,
        module_id=section.module_id,
        title="Value at risk (VaR)",
        learning_outcome="LO 7.a",
        related_original_key_concept_id="lo-7-a",
        source_pages=[101, 102],
        source_excerpt=source_excerpt,
        simplified_explanation="Value at risk estimates a loss threshold over a time horizon.",
        key_terms=["Value at risk (VaR)", "confidence level"],
        formulas=[],
        exam_focus="Interpret VaR.",
        common_traps=[],
    )

    cards = service._content_specific_flashcards_for_concept(section, concept)
    definition = next(card for card in cards if card.front == "What is value at risk (VaR)?")

    assert definition.study_session == "Study Session 2"
    assert definition.reading_number == 7
    assert definition.module_number == "7.1"
    assert definition.lo_code == "LO 7.a"
    assert definition.page_start == 101
    assert definition.page_end == 102
    assert definition.anchor_type == "bold_term"
    assert definition.anchor_text == "Value at risk (VaR)"
    assert "Value at risk (VaR) estimates" in definition.source_text_snippet
    assert definition.quality_score >= 0.8
    assert len(definition.source_hash) == 64
    assert "Reading 7" in definition.tags
    assert "Module 7.1" in definition.tags
    assert "LO 7.a" in definition.tags


def test_flashcard_llm_prompt_requires_validated_source_anchor_json() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]

    system_prompt, user_prompt = service._flashcard_llm_prompts_for_anchor(
        book_title="FRM 2025 Part 1 KAPLAN Book 1",
        reading_number=7,
        module_number="7.1",
        lo_code="LO 7.a",
        page_start=101,
        page_end=102,
        anchor_type="bold_term",
        anchor_text="Value at risk (VaR)",
        source_text=(
            "Value at risk (VaR) estimates the loss amount that may be exceeded "
            "with a specified probability over a defined time horizon."
        ),
    )

    assert "You generate exam-prep flashcards only from validated source anchors." in system_prompt
    assert "You must not invent content, use broken fragments, or create generic cards." in system_prompt
    assert "Every card must be tied to a source page, module, and learning objective" in system_prompt
    assert "Generate high-quality exam flashcards from the following source anchor." in user_prompt
    assert "Use only the provided source anchor and surrounding source text." in user_prompt
    assert "Never generate a question from a broken phrase or partial sentence." in user_prompt
    assert "Return only valid JSON." in user_prompt
    assert '"bookTitle": "FRM 2025 Part 1 KAPLAN Book 1"' in user_prompt
    assert '"readingNumber": "7"' in user_prompt
    assert '"moduleNumber": "7.1"' in user_prompt
    assert '"loCode": "LO 7.a"' in user_prompt
    assert '"pageStart": "101"' in user_prompt
    assert '"pageEnd": "102"' in user_prompt
    assert '"anchorType": "bold_term"' in user_prompt
    assert '"anchorText": "Value at risk (VaR)"' in user_prompt
    assert '"sourceText": "Value at risk (VaR) estimates' in user_prompt
    assert '"qualityRationale": "..."' in user_prompt
    assert "Reject the card and return an empty cards array if the source anchor is not meaningful." in user_prompt


def test_code_of_conduct_flashcards_cover_module_11_application_anchors() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _build_section(
        title=(
            "Study Session 3: Current Issues / "
            "Reading 11: GARP Code of Conduct / "
            "Module 11.1: GARP Code of Conduct"
        ),
        text="GARP Code of Conduct source text",
    )
    source_excerpt = (
        "LO 11.a\n"
        "GARP Members must act with integrity, competence, diligence, respect, and in an ethical manner. "
        "Members must maintain confidentiality, disclose conflicts of interest, and comply with "
        "professional standards.\n"
        "LO 11.b\n"
        "Violations of the GARP Code of Conduct may lead to consequences including suspension, "
        "revocation of membership, or referral to regulators."
    )
    concept = StudyConceptCard(
        concept_id="concept-garp-code",
        material_id=section.material_id,
        module_id=section.module_id,
        title="GARP Code of Conduct",
        learning_outcome="LO 11.a",
        related_original_key_concept_id="lo-11-a",
        source_pages=[153],
        source_excerpt=source_excerpt,
        simplified_explanation="The GARP Code of Conduct defines professional duties and consequences.",
        key_terms=[
            "GARP Code of Conduct",
            "confidentiality",
            "conflicts of interest",
            "integrity",
            "professional standards",
            "violations",
            "consequences",
        ],
        formulas=[],
        exam_focus="Apply Code of Conduct duties and consequences to scenarios.",
        common_traps=[],
    )

    cards = service._content_specific_flashcards_for_concept(section, concept)
    fronts = [card.front for card in cards]

    assert "What duties does the GARP Code of Conduct emphasize for members?" in fronts
    assert "How should a GARP member handle conflicts of interest?" in fronts
    assert "Why is confidentiality important under the GARP Code of Conduct?" in fronts
    assert "What can happen after a violation of the GARP Code of Conduct?" in fronts
    assert any("integrity" in front.lower() for front in fronts)
    assert all(service._flashcard_quality_flags(card) == [] for card in cards)


def test_capm_learning_outcome_generates_specific_capm_mrp_sml_cards() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _build_section(
        title=(
            "Study Session 2: Portfolio Theory / "
            "Reading 5: Modern Portfolio Theory (MPT) and the Capital Asset Pricing Model (CAPM) / "
            "Module 5.1: Modern Portfolio Theory and the Capital Market Line"
        ),
        text="Module 5.1 source text",
    )
    concept = StudyConceptCard(
        concept_id="concept-lo-5-b",
        material_id=section.material_id,
        module_id=section.module_id,
        title="Capital asset pricing model CAPM",
        learning_outcome="LO 5.b",
        related_original_key_concept_id="lo-5-b",
        source_pages=[71],
        source_excerpt=(
            "LO 5.b\n"
            "To derive the capital asset pricing model (CAPM), we must recognize that "
            "expected return only depends on beta because company-specific risk can be "
            "diversified away, and expected return is a linear function of beta. "
            "The capital asset pricing model (CAPM) equation is "
            "E(Ri) = RF + [E(RM) - RF] beta_i. "
            "The beta of the market is equal to 1, and the slope of the security market line "
            "(SML) is equal to the market risk premium (MRP). The SML is the graphical "
            "depiction of CAPM."
        ),
        simplified_explanation="CAPM links expected return to beta and the market risk premium.",
        key_terms=[
            "capital asset pricing model (CAPM)",
            "beta",
            "security market line (SML)",
            "market risk premium (MRP)",
        ],
        formulas=[],
        exam_focus="Derive and interpret CAPM, beta, the SML, and MRP.",
        common_traps=[],
    )

    cards = service._content_specific_flashcards_for_concept(section, concept)
    fronts = {card.front for card in cards}

    assert "What is the capital asset pricing model (CAPM)?" in fronts
    assert "What is the market risk premium (MRP)?" in fronts
    assert "What does the slope of the security market line (SML) represent?" in fronts
    assert "What does beta measure in the capital asset pricing model (CAPM)?" in fronts
    assert "What does the security market line (SML) depict?" in fronts
    assert "How is the market risk premium (MRP) used in CAPM?" in fronts
    assert "Why does CAPM focus on beta instead of company-specific risk?" in fronts
    assert all(service._flashcard_quality_flags(card) == [] for card in cards)


def test_module_flashcards_dedupe_overlapping_capm_learning_outcomes() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _build_section(
        title=(
            "Study Session 2: Portfolio Theory / "
            "Reading 5: Modern Portfolio Theory (MPT) and the Capital Asset Pricing Model (CAPM) / "
            "Module 5.1: Modern Portfolio Theory and the Capital Market Line"
        ),
        text="Module 5.1 source text",
    )
    common = (
        "To derive the capital asset pricing model (CAPM), expected return only depends on beta because "
        "company-specific risk can be diversified away. The beta of the market is equal to 1, and the "
        "slope of the security market line (SML) is equal to the market risk premium (MRP). "
        "The SML is the graphical depiction of CAPM."
    )
    concepts = [
        StudyConceptCard(
            concept_id="concept-lo-5-b",
            material_id=section.material_id,
            module_id=section.module_id,
            title="Capital asset pricing model CAPM",
            learning_outcome="LO 5.b",
            related_original_key_concept_id="lo-5-b",
            source_pages=[71],
            source_excerpt=f"LO 5.b {common}",
            simplified_explanation="CAPM links expected return to beta and MRP.",
            key_terms=["capital asset pricing model (CAPM)", "market risk premium (MRP)", "security market line"],
            formulas=[],
            exam_focus="Derive and interpret CAPM.",
            common_traps=[],
        ),
        StudyConceptCard(
            concept_id="concept-lo-5-c",
            material_id=section.material_id,
            module_id=section.module_id,
            title="CAPM assumptions and the SML",
            learning_outcome="LO 5.c",
            related_original_key_concept_id="lo-5-c",
            source_pages=[72],
            source_excerpt=f"LO 5.c {common}",
            simplified_explanation="CAPM assumptions support the SML.",
            key_terms=["CAPM", "SML", "beta", "MRP"],
            formulas=[],
            exam_focus="Recognize CAPM assumptions.",
            common_traps=[],
        ),
    ]

    cards = service._flashcards_from_original_book(section, OriginalBookContent(), concepts, [])
    fronts = [card.front for card in cards]

    assert "What is the capital asset pricing model (CAPM)?" in fronts
    assert "What is the market risk premium (MRP)?" in fronts
    assert len(fronts) == len(set(fronts))
    assert all(service._flashcard_quality_flags(card) == [] for card in cards)


def test_workbook_display_lines_preserves_late_learning_outcome_blocks() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    lines = [f"filler source line {index}" for index in range(100)]
    lines.extend(
        [
            "LO 5.b",
            "To derive the capital asset pricing model (CAPM), expected return only depends on beta.",
            "The slope of the security market line (SML) is the market risk premium (MRP).",
        ]
    )

    display_lines = service._workbook_display_lines(lines)

    assert "LO 5.b" in display_lines
    assert any("security market line" in line for line in display_lines)
