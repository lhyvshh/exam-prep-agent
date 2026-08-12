from exam_prep.schemas.materials import (
    OriginalBookContent,
    SourceLocator,
    SourceSection,
    StudyConceptCard,
    StudyFlashcard,
    StudyFormulaCard,
)
from exam_prep.services.section_study_service import SectionStudyService


def test_rejects_broken_question_fragments() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]

    for front in (
        "What is event is one?",
        "What is of the possible?",
        "What is all the subsets?",
        "What is and reward?",
        "What is opportunities with lower?",
        "What is risk have lower?",
        "What does some of the qualitative methods include?",
        "How does general term relate to general term “risk” subcategorized market?",
        "What is a common exam trap about four different risk?",
        "How does role and responsibilities relate to risk management role responsibilities?",
        "What are their goals?",
        "How does operational risks attempts relate to hedging operational risks attempts insulate?",
        "What should you remember about as market risks?",
        "What should you remember about firms pick from four different?",
        "What should you remember about to insulate revenues?",
        "What should you remember about its business?",
        "What should you remember about maximize return per?",
        "What should you remember about existence of credit?",
        "What is a CDO is a structured product that?",
        "What does best practices for risk management include?",
        "What is domino effect where?",
        "What is retain risk?",
        "What are frontline managers?",
        "What is various functional units?",
        "What is borrower defaulting?",
        "What is derive the capital?",
        "What is both treynor?",
        "What is pricing theory?",
        "What are they?",
        "What are these opinions?",
        "What is there?",
        "What are when the assets?",
        "What is another option?",
        "What are vaR and the associated economic capital measurement?",
        "What is banks should ensure that the data?",
        "What are while the scenarios for DFAST and CCAR?",
        "What is risk management process?",
        "What are late trading occurs when orders?",
        "What are market timing occurs because some fund assets?",
        "What are european options?",
        "What is also assume that the Treasury bond futures contract?",
        "What are assume that there?",
        "What is also assume that?",
        "What are assume that the short position?",
        "What is electricity?",
        "What is interest?",
        "What are t-bond prices?",
        "What are because option contracts?",
        "What are models?",
        "What are quotes?",
        "What are spot quotes?",
        "What is so portfolio currency risk?",
        "What is a less costly alternative?",
        "What is answer Because inflation in Europe?",
        "What is trading?",
        "What are two events?",
        "What is use the t-test if the population variance?",
        "What are each of these assumptions?",
        "What are a parametric model typically assumes asset returns?",
        "What is a positive butterfly means the yield curve?",
        "What are sometimes we?",
        "What are note that the three levels of education attainment?",
        "What are note also that the three categories?",
        "What do sequence of random variables include?",
        "What are variables?",
        "What is x variables?",
        "What is explain how principal components analysis?",
        "What is the two most important explanatory components?",
        "What are applications?",
        "What is the formula?",
        "What is also assume that the Treasury bond futures contract?",
        "What are assume that there?",
        "What are assume that the short position?",
        "What is determine if the slope coefficient?",
        "What is the term linear?",
        "What is each data point?",
        "What is the centers of the data clusters?",
        "What is the bsm model suggests that stock prices?",
        "What is the plot?",
        "What is borrowers?",
        "What is correlations?",
        "What is payments?",
        "What are no payments?",
        "What is coverage?",
        "What are benefits?",
        "What is benefit?",
        "What are premiums?",
        "What is premium?",
        "What does regression analysis seeks to measure?",
    ):
        card = _flashcard(front=front)
        assert "generic_question" in service._flashcard_quality_flags(card)


def test_deduplicates_singular_plural_definition_questions() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]

    cards = [
        _flashcard(
            front="What are borrowers?",
            back="Borrowers are entities that owe debt.",
        ).model_copy(
            update={
                "learning_outcome_id": "lo-52-h",
                "concept_id": "concept-lo-52-h",
                "source_page": 80,
                "source_excerpt": "Borrowers are entities that owe debt.",
                "anchor_text": "borrowers",
            }
        ),
        _flashcard(
            front="What is borrowers?",
            back="Borrowers are entities that owe debt.",
        ).model_copy(
            update={
                "learning_outcome_id": "lo-52-h",
                "concept_id": "concept-lo-52-h",
                "source_page": 80,
                "source_excerpt": "Borrowers are entities that owe debt.",
                "anchor_text": "borrowers",
            }
        ),
        _flashcard(
            front="What are correlations?",
            back="Correlations measure co-movement between variables.",
        ).model_copy(
            update={
                "learning_outcome_id": "lo-52-h",
                "concept_id": "concept-lo-52-h",
                "source_page": 80,
                "source_excerpt": "Correlations measure co-movement between variables.",
                "anchor_text": "correlations",
            }
        ),
        _flashcard(
            front="What is correlations?",
            back="Correlations measure co-movement between variables.",
        ).model_copy(
            update={
                "learning_outcome_id": "lo-52-h",
                "concept_id": "concept-lo-52-h",
                "source_page": 80,
                "source_excerpt": "Correlations measure co-movement between variables.",
                "anchor_text": "correlations",
            }
        ),
    ]

    fronts = [card.front for card in service._valid_unique_flashcards(cards, limit=10)]

    assert "What is borrowers?" not in fronts
    assert "What is correlations?" not in fronts
    assert not any("borrowers" in front.lower() for front in fronts)
    assert not any("correlations" in front.lower() for front in fronts)


def test_flashcards_from_original_book_does_not_drop_later_learning_outcomes() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 2: Quantitative Analysis / "
            "Reading 7: Risk Measures / "
            "Module 7.1: Value at Risk"
        ),
        text="Value at risk source text",
        page_number=101,
    )
    _, value_at_risk_concept = _value_at_risk_section_and_concept()
    leading_concepts = [
        _concept(
            section,
            concept_id=f"concept-leading-{index}",
            lo=f"LO 7.{chr(96 + index)}",
            title=f"Leading Risk Anchor {index}",
            excerpt=(
                f"LO 7.{chr(96 + index)}\n"
                f"Leading Risk Anchor {index} defines a bounded exam concept with a complete "
                f"source sentence. Leading Risk Anchor {index} has two components: measurement "
                f"and interpretation."
            ),
            key_terms=[f"Leading Risk Anchor {index}", "measurement", "interpretation"],
        )
        for index in range(1, 13)
    ]
    late_concept = value_at_risk_concept.model_copy(
        update={
            "concept_id": "concept-late-var",
            "material_id": section.material_id,
            "module_id": section.module_id,
            "learning_outcome": "LO 7.m",
            "related_original_key_concept_id": "lo-7-m",
        }
    )

    cards = service._flashcards_from_original_book(
        section,
        OriginalBookContent(),
        [*leading_concepts, late_concept],
        [],
    )
    fronts = {card.front for card in cards}

    assert "What is value at risk (VaR)?" in fronts


def test_learning_outcome_coverage_tops_up_each_key_concept_anchor() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 8: Financial Institutions, Markets, and Central Clearing / "
            "Reading 29: Fund Management / "
            "Module 29.1: Mutual Funds and Exchange-Traded Funds"
        ),
        text=(
            "LO 29.a\n"
            "Open-end mutual funds issue and redeem shares at net asset value. "
            "Closed-end funds have a fixed number of shares and may trade at premiums or discounts. "
            "Exchange-traded funds trade intraday on exchanges and often have lower expenses. "
            "Net asset value is the per-share value of the fund's assets minus liabilities. "
            "Premiums and discounts compare market price with net asset value."
        ),
        page_number=36,
    )
    open_end = _concept(
        section,
        concept_id="concept-open-end",
        lo="LO 29.a",
        title="Open-end mutual funds",
        excerpt=(
            "Open-end mutual funds issue and redeem shares directly with investors at net asset value. "
            "Investors buy shares from the fund and redeem shares back to the fund at the end-of-day NAV."
        ),
        key_terms=["open-end mutual funds", "net asset value", "redeem shares"],
    )
    closed_end = _concept(
        section,
        concept_id="concept-closed-end",
        lo="LO 29.a",
        title="Closed-end mutual funds",
        excerpt=(
            "Closed-end mutual funds have a fixed number of shares that trade on exchanges. "
            "Their market price can differ from net asset value, creating premiums or discounts."
        ),
        key_terms=["closed-end mutual funds", "fixed shares", "premium", "discount"],
    )
    existing_cards = [
        _flashcard(
            front=f"What open-end mutual fund fact {index} is tested?",
            back="Open-end mutual funds issue and redeem shares at net asset value.",
        ).model_copy(
            update={
                "learning_outcome_id": "lo-29-a-anchor",
                "lo_code": "29.a",
                "concept_id": "concept-open-end",
                "source_excerpt": open_end.source_excerpt,
                "source_text_snippet": open_end.source_excerpt,
                "anchor_text": open_end.title,
            }
        )
        for index in range(10)
    ]
    existing_cards.append(
        _flashcard(
            front="How do closed-end mutual funds trade?",
            back="Closed-end mutual funds trade on exchanges and can trade at premiums or discounts to NAV.",
        ).model_copy(
            update={
                "learning_outcome_id": "lo-29-a-anchor",
                "lo_code": "29.a",
                "concept_id": "concept-closed-end",
                "source_excerpt": closed_end.source_excerpt,
                "source_text_snippet": closed_end.source_excerpt,
                "anchor_text": closed_end.title,
            }
        )
    )

    repaired = service._ensure_learning_outcome_flashcard_coverage(  # noqa: SLF001
        section,
        [open_end, closed_end],
        existing_cards,
    )
    counts_by_concept = {
        concept_id: sum(card.concept_id == concept_id for card in repaired)
        for concept_id in ["concept-open-end", "concept-closed-end"]
    }

    assert counts_by_concept == {"concept-open-end": 10, "concept-closed-end": 10}
    assert all(card.source_excerpt or card.source_text_snippet for card in repaired)


def test_generates_card_from_bold_value_at_risk() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section, concept = _value_at_risk_section_and_concept()

    fronts = [card.front for card in service._content_specific_flashcards_for_concept(section, concept)]

    assert "What is value at risk (VaR)?" in fronts
    assert "How do you interpret a one-day VaR of $2.5 million at the 95% confidence level?" in fronts


def test_generates_expected_loss_formula_card() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 1: Risk Management Overview / "
            "Reading 1: The Building Blocks of Risk Management / "
            "Module 1.1: Introduction to Risk Management"
        ),
        text=(
            "KEY CONCEPTS\n"
            "LO 1.a\n"
            "Expected loss is the average normal-course loss.\n"
            "FORMULAS\n"
            "Expected loss: EL = EAD × PD × LGD"
        ),
        page_number=13,
    )

    study_section = service._build_study_section(section, display_order=1, parent_group_id=None, previous=None)

    assert any(card.card_type == "formula" and "expected loss" in card.front.lower() for card in study_section.flashcards)
    assert any("EL = EAD × PD × LGD" in (card.back_concise or card.back) for card in study_section.flashcards)


def test_generates_capm_formula_card() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 2: Quantitative Analysis / "
            "Reading 5: Modern Portfolio Theory (MPT) and the Capital Asset Pricing Model (CAPM) / "
            "Module 5.2: Deriving and Applying the Capital Asset Pricing Model"
        ),
        text=(
            "KEY CONCEPTS\n"
            "LO 5.c\n"
            "The CAPM links required return to systematic risk.\n"
            "FORMULAS\n"
            "Capital asset pricing model: E(Ri) = RF + [E(RM) − RF]βi"
        ),
        page_number=82,
    )

    study_section = service._build_study_section(section, display_order=1, parent_group_id=None, previous=None)

    assert any("capital asset pricing model" in card.front.lower() for card in study_section.flashcards)
    assert any("E(Ri)" in (card.back_concise or card.back) for card in study_section.flashcards)


def test_option_pricing_factors_generate_specific_cards() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 9: Financial Markets and Products / "
            "Reading 39: Options Markets / "
            "Module 39.1: Option Pricing Factors"
        ),
        text="Option pricing factors source text",
        page_number=151,
    )
    concept = StudyConceptCard(
        concept_id="concept-option-pricing",
        material_id=section.material_id,
        module_id=section.module_id,
        title="Option pricing factors",
        learning_outcome="LO 39.a",
        related_original_key_concept_id="lo-39-a",
        source_pages=[151],
        source_excerpt=(
            "LO 39.a\n"
            "Six factors influence the value of an option: current value of the underlying asset, "
            "the strike price, the time to expiration of the option, the volatility of the stock price, "
            "the risk-free rate, and dividends. An increase in the stock price increases call option "
            "value and decreases put option value. Higher volatility generally increases the value of "
            "both calls and puts."
        ),
        simplified_explanation="Six inputs drive option values.",
        key_terms=["option pricing factors", "volatility", "strike price"],
        formulas=[],
        exam_focus="Identify option pricing factors.",
        common_traps=[],
    )

    fronts = [card.front for card in service._content_specific_flashcards_for_concept(section, concept)]

    assert len(fronts) >= 8
    assert "What six factors influence the value of an option?" in fronts
    assert "How does an increase in the underlying stock price affect call and put option values?" in fronts
    assert "How does higher volatility affect option values?" in fronts


def test_interest_rate_swaps_generate_specific_cards() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 11: Financial Markets and Products / "
            "Reading 46: Swaps / "
            "Module 46.1: Mechanics of Interest Rate Swaps"
        ),
        text="Interest rate swaps source text",
        page_number=244,
    )
    concept = StudyConceptCard(
        concept_id="concept-interest-rate-swap",
        material_id=section.material_id,
        module_id=section.module_id,
        title="Plain vanilla interest rate swap",
        learning_outcome="LO 46.a",
        related_original_key_concept_id="lo-46-a",
        source_pages=[244],
        source_excerpt=(
            "LO 46.a\n"
            "A plain vanilla interest rate swap is an agreement in which one party pays a fixed rate "
            "and receives a floating rate based on SOFR on a notional principal amount. The parties "
            "exchange only the net payment, and notional principal is not exchanged. Swaps can transform "
            "floating-rate liabilities into fixed-rate liabilities. Dealers act as intermediaries and use "
            "confirmations and ISDA master agreements. Comparative advantage can motivate a swap."
        ),
        simplified_explanation="Interest rate swaps exchange fixed and floating payments.",
        key_terms=["plain vanilla interest rate swap", "notional principal", "SOFR", "ISDA master agreements"],
        formulas=[],
        exam_focus="Explain interest rate swap mechanics.",
        common_traps=[],
    )

    fronts = [card.front for card in service._content_specific_flashcards_for_concept(section, concept)]

    assert len(fronts) >= 9
    assert "What is a plain vanilla interest rate swap?" in fronts
    assert "What payment is exchanged in an interest rate swap?" in fronts
    assert "Why is notional principal not exchanged in a plain vanilla interest rate swap?" in fronts


def test_mutual_fund_trading_terms_generate_clean_cards() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 8: Financial Markets and Products / "
            "Reading 29: Investment Companies / "
            "Module 29.1: Mutual Funds and Exchange-Traded Funds"
        ),
        text="Mutual funds source text",
        page_number=36,
    )
    concept = StudyConceptCard(
        concept_id="concept-mutual-funds",
        material_id=section.material_id,
        module_id=section.module_id,
        title="Mutual funds",
        learning_outcome="LO 29.a",
        related_original_key_concept_id="lo-29-a",
        source_pages=[36],
        source_excerpt=(
            "LO 29.a\n"
            "Mutual funds are pooled investment vehicles that invest shareholder money in diversified "
            "portfolios. Potential undesirable trading behaviors include late trading and market timing. "
            "Late trading occurs when orders placed after the market close receive the same-day NAV. "
            "Market timing occurs because some fund assets may be priced using stale values. ETFs trade "
            "on exchanges and typically have lower fees than mutual funds."
        ),
        simplified_explanation="Mutual funds pool investor capital and can face trading-abuse risks.",
        key_terms=["mutual funds", "late trading", "market timing", "ETFs"],
        formulas=[],
        exam_focus="Explain fund structures and trading concerns.",
        common_traps=[],
    )

    fronts = [card.front for card in service._content_specific_flashcards_for_concept(section, concept)]

    assert len(fronts) >= 8
    assert "What are mutual funds?" in fronts
    assert "What is late trading in mutual funds?" in fronts
    assert "What is market timing in mutual funds?" in fronts
    assert all("occurs when" not in front.lower() for front in fronts)


def test_module_flashcards_generate_at_least_ten_cards_for_each_mutual_fund_lo() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 8: Financial Institutions, Markets, and Central Clearing / "
            "Reading 29: Fund Management / "
            "Module 29.1: Mutual Funds and Exchange-Traded Funds"
        ),
        text=(
            "LO 29.a\n"
            "Open-end mutual funds issue and redeem shares at NAV, closed-end mutual funds trade "
            "on exchanges, and exchange-traded funds combine exchange trading with diversified fund exposure. "
            "LO 29.b\n"
            "Net asset value equals fund assets minus liabilities divided by shares outstanding. "
            "Share classes can differ by fees, loads, and distribution charges. "
            "LO 29.c\n"
            "Diversification reduces total portfolio risk when imperfectly correlated holdings offset "
            "firm-specific risks. Mutual funds and ETFs diversify across securities, sectors, and issuers. "
            "Diversification does not eliminate market risk."
        ),
        page_number=36,
    )
    concepts = [
        _concept(
            section,
            concept_id="concept-open-closed-etf",
            lo="LO 29.a",
            title="Mutual fund and ETF structures",
            excerpt=(
                "LO 29.a\n"
                "Open-end mutual funds issue and redeem shares at NAV, closed-end mutual funds trade "
                "on exchanges, and exchange-traded funds combine exchange trading with diversified fund exposure."
            ),
            key_terms=["open-end mutual funds", "closed-end mutual funds", "exchange-traded funds", "NAV"],
        ),
        _concept(
            section,
            concept_id="concept-nav-share-classes",
            lo="LO 29.b",
            title="NAV and share classes",
            excerpt=(
                "LO 29.b\n"
                "Net asset value equals fund assets minus liabilities divided by shares outstanding. "
                "Share classes can differ by fees, loads, and distribution charges."
            ),
            key_terms=["net asset value", "shares outstanding", "share classes", "distribution charges"],
        ),
        _concept(
            section,
            concept_id="concept-diversification-risk",
            lo="LO 29.c",
            title="Diversification and portfolio risk",
            excerpt=(
                "LO 29.c\n"
                "Diversification reduces total portfolio risk when imperfectly correlated holdings offset "
                "firm-specific risks. Mutual funds and ETFs diversify across securities, sectors, and issuers. "
                "Diversification does not eliminate market risk."
            ),
            key_terms=[
                "diversification",
                "portfolio risk",
                "imperfectly correlated holdings",
                "firm-specific risks",
                "market risk",
            ],
        ),
    ]

    cards = service._flashcards_from_original_book(section, OriginalBookContent(), concepts, [])
    counts_by_lo = {
        concept.learning_outcome: sum(
            1 for card in cards if card.learning_outcome_id == concept.related_original_key_concept_id
        )
        for concept in concepts
    }

    assert counts_by_lo.keys() == {"LO 29.a", "LO 29.b", "LO 29.c"}
    assert all(count >= 10 for count in counts_by_lo.values())
    assert not any(card.needs_more_source for card in cards if card.lo_code in counts_by_lo)
    assert not any(service._flashcard_quality_flags(card) for card in cards)


def test_ccp_risks_generate_specific_cards() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 8: Financial Markets and Products / "
            "Reading 32: Central Clearing / "
            "Module 32.2: Risks of Central Counterparties"
        ),
        text="Central counterparty risk source text",
        page_number=64,
    )
    concept = StudyConceptCard(
        concept_id="concept-ccp-risk",
        material_id=section.material_id,
        module_id=section.module_id,
        title="Risks of central counterparties",
        learning_outcome="LO 32.b",
        related_original_key_concept_id="lo-32-b",
        source_pages=[64],
        source_excerpt=(
            "LO 32.b\n"
            "A central counterparty (CCP) interposes itself between buyers and sellers. "
            "CCPs face clearing member default risk, liquidity risk, model risk, legal risk, "
            "investment risk, and the risk that defaults are correlated. A default fund can "
            "absorb losses from a clearing member default. Non-members reduce exposure to CCP "
            "default losses by clearing through members."
        ),
        simplified_explanation="CCPs reduce bilateral counterparty risk but introduce their own risks.",
        key_terms=["central counterparty", "default fund", "clearing member default risk"],
        formulas=[],
        exam_focus="Identify and interpret CCP risks.",
        common_traps=[],
    )

    fronts = [card.front for card in service._content_specific_flashcards_for_concept(section, concept)]

    assert len(fronts) >= 8
    assert "What is a central counterparty (CCP)?" in fronts
    assert "What risks can a central counterparty (CCP) face?" in fronts
    assert "What role does a CCP default fund play?" in fronts


def test_futures_characteristics_generate_specific_cards() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 10: Financial Markets and Products / "
            "Reading 33: Futures Markets / "
            "Module 33.1: Futures Contract Characteristics"
        ),
        text="Futures contract source text",
        page_number=75,
    )
    concept = StudyConceptCard(
        concept_id="concept-futures-basics",
        material_id=section.material_id,
        module_id=section.module_id,
        title="Futures contract characteristics",
        learning_outcome="LO 33.a",
        related_original_key_concept_id="lo-33-a",
        source_pages=[75],
        source_excerpt=(
            "LO 33.a\n"
            "A futures contract is a standardized exchange-traded contract. The long futures "
            "position agrees to buy the underlying asset, and the short futures position agrees "
            "to sell it. The spot price is the current cash market price, while the futures price "
            "is the price agreed to for future delivery. Basis is the spot price minus the futures "
            "price. Open interest measures the number of outstanding contracts."
        ),
        simplified_explanation="Futures contracts standardize future delivery exposure.",
        key_terms=["futures contract", "long futures position", "basis", "open interest"],
        formulas=[],
        exam_focus="Interpret futures contract terminology.",
        common_traps=[],
    )

    fronts = [card.front for card in service._content_specific_flashcards_for_concept(section, concept)]

    assert len(fronts) >= 9
    assert "What is a futures contract?" in fronts
    assert "What is basis in futures markets?" in fronts
    assert "What does open interest measure?" in fronts


def test_commodity_terms_generate_specific_cards() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 10: Financial Markets and Products / "
            "Reading 37: Commodity Forwards and Futures / "
            "Module 37.1: Commodity Forward and Futures Pricing"
        ),
        text="Commodity futures source text",
        page_number=117,
    )
    concept = StudyConceptCard(
        concept_id="concept-commodities",
        material_id=section.material_id,
        module_id=section.module_id,
        title="Commodity futures pricing",
        learning_outcome="LO 37.a",
        related_original_key_concept_id="lo-37-a",
        source_pages=[117],
        source_excerpt=(
            "LO 37.a\n"
            "Commodity futures differ from financial futures because commodities may have storage "
            "costs, transportation costs, shorting costs, lease rates, and convenience yield. A carry "
            "market exists when futures prices exceed spot prices enough to cover carrying costs. "
            "Agricultural commodities can have seasonal prices, and electricity can be difficult to store."
        ),
        simplified_explanation="Commodity futures pricing depends on physical carrying costs and benefits.",
        key_terms=["commodity futures", "storage costs", "convenience yield", "carry market"],
        formulas=[],
        exam_focus="Explain commodity futures pricing drivers.",
        common_traps=[],
    )

    fronts = [card.front for card in service._content_specific_flashcards_for_concept(section, concept)]

    assert len(fronts) >= 9
    assert "How do commodity futures differ from financial futures?" in fronts
    assert "What is convenience yield in commodity markets?" in fronts
    assert "What is a carry market in commodities?" in fronts


def test_day_count_conventions_generate_specific_cards() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 12: Valuation and Risk Models / "
            "Reading 45: Interest Rate Futures / "
            "Module 45.1: Bond Pricing and Day Count Conventions"
        ),
        text="Day count source text",
        page_number=231,
    )
    concept = StudyConceptCard(
        concept_id="concept-day-count",
        material_id=section.material_id,
        module_id=section.module_id,
        title="Day count conventions",
        learning_outcome="LO 45.a",
        related_original_key_concept_id="lo-45-a",
        source_pages=[231],
        source_excerpt=(
            "LO 45.a\n"
            "Day count conventions determine how interest accrues between coupon dates. "
            "US Treasury bonds commonly use actual/actual, corporate and municipal bonds use 30/360, "
            "and money market instruments often use actual/360. The dirty price equals the clean price "
            "plus accrued interest."
        ),
        simplified_explanation="Day count conventions affect accrued interest and quoted prices.",
        key_terms=["day count conventions", "actual/actual", "30/360", "dirty price"],
        formulas=[],
        exam_focus="Apply fixed-income day count conventions.",
        common_traps=[],
    )

    fronts = [card.front for card in service._content_specific_flashcards_for_concept(section, concept)]

    assert len(fronts) >= 8
    assert "What are day count conventions used for in fixed income?" in fronts
    assert "How does dirty price differ from clean price?" in fronts
    assert "Which day count convention do US Treasury bonds commonly use?" in fronts


def test_duration_hedging_generates_specific_cards() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 12: Valuation and Risk Models / "
            "Reading 45: Interest Rate Futures / "
            "Module 45.3: Duration-Based Hedging"
        ),
        text="Duration hedge source text",
        page_number=248,
    )
    concept = StudyConceptCard(
        concept_id="concept-duration-hedge",
        material_id=section.material_id,
        module_id=section.module_id,
        title="Duration-based hedge ratio",
        learning_outcome="LO 45.h",
        related_original_key_concept_id="lo-45-h",
        source_pages=[248],
        source_excerpt=(
            "LO 45.h\n"
            "A duration-based hedge uses futures contracts to offset bond price risk. The hedge ratio "
            "uses the duration and value of the bond portfolio and the duration and price of the futures "
            "contract. Duration hedges are less effective when yield changes are large, when yield curve "
            "shifts are nonparallel, or when convexity is important."
        ),
        simplified_explanation="Duration hedges use futures to offset interest rate risk.",
        key_terms=["duration-based hedge", "hedge ratio", "nonparallel shifts", "convexity"],
        formulas=[],
        exam_focus="Apply duration-based hedge logic.",
        common_traps=[],
    )

    fronts = [card.front for card in service._content_specific_flashcards_for_concept(section, concept)]

    assert len(fronts) >= 8
    assert "What is a duration-based hedge?" in fronts
    assert "What inputs are needed for a duration-based hedge ratio?" in fronts
    assert "Why can nonparallel yield curve shifts weaken a duration hedge?" in fronts


def test_banking_risks_generate_at_least_ten_specific_cards() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 8: Financial Markets and Products / "
            "Reading 27: Banks / "
            "Module 27.1: Risks and Capital for Banks"
        ),
        text="Banking risks source text",
        page_number=11,
    )
    concept = StudyConceptCard(
        concept_id="concept-banking-risks",
        material_id=section.material_id,
        module_id=section.module_id,
        title="Bank risks and capital",
        learning_outcome="LO 27.a",
        related_original_key_concept_id="lo-27-a",
        source_pages=[11],
        source_excerpt=(
            "LO 27.a\n"
            "Banks face credit risk, market risk, liquidity risk, operational risk, and solvency risk. "
            "Regulatory capital is the minimum capital required by regulators, while economic capital is "
            "internally estimated capital needed to absorb unexpected losses. Deposit insurance protects "
            "depositors but can create moral hazard because insured depositors monitor banks less. The "
            "banking book contains loans and deposits held to maturity, while the trading book contains "
            "positions marked to market. The originate-to-distribute model originates loans and sells or "
            "securitizes the exposure."
        ),
        simplified_explanation="Banks manage multiple risks and hold capital against unexpected losses.",
        key_terms=["bank risks", "regulatory capital", "economic capital", "deposit insurance"],
        formulas=[],
        exam_focus="Explain bank risks and capital.",
        common_traps=[],
    )

    fronts = [card.front for card in service._content_specific_flashcards_for_concept(section, concept)]

    assert len(fronts) >= 10
    assert "What are the main risks faced by banks?" in fronts
    assert "How does economic capital differ from regulatory capital?" in fronts
    assert "Why can deposit insurance create moral hazard?" in fronts
    assert "How does the banking book differ from the trading book?" in fronts


def test_foreign_exchange_terms_generate_at_least_ten_specific_cards() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 10: Financial Markets and Products / "
            "Reading 35: Foreign Exchange Markets / "
            "Module 35.1: Foreign Exchange Markets"
        ),
        text="Foreign exchange source text",
        page_number=99,
    )
    concept = StudyConceptCard(
        concept_id="concept-fx-quotes",
        material_id=section.material_id,
        module_id=section.module_id,
        title="Foreign exchange quotes",
        learning_outcome="LO 35.a",
        related_original_key_concept_id="lo-35-a",
        source_pages=[99],
        source_excerpt=(
            "LO 35.a\n"
            "In an FX quote, the base currency is the currency being bought or sold and the quote "
            "currency is the price currency. The bid price is the price at which a dealer buys the "
            "base currency; the ask price is the price at which the dealer sells it. Spot transactions "
            "settle shortly after trade date. An outright forward locks in an exchange rate for future "
            "delivery. An FX swap combines a spot transaction with an offsetting forward. Foreign exchange "
            "exposure includes transaction risk, translation risk, and economic risk."
        ),
        simplified_explanation="FX quotes identify base and quote currencies plus bid and ask prices.",
        key_terms=["FX quote", "base currency", "quote currency", "bid price", "ask price"],
        formulas=[],
        exam_focus="Interpret FX market terminology.",
        common_traps=[],
    )

    fronts = [card.front for card in service._content_specific_flashcards_for_concept(section, concept)]

    assert len(fronts) >= 10
    assert "What is the base currency in an FX quote?" in fronts
    assert "What is the quote currency in an FX quote?" in fronts
    assert "How does the bid price differ from the ask price in an FX quote?" in fronts
    assert "How does an FX swap differ from an outright forward transaction?" in fronts


def test_exchange_rate_parity_generates_at_least_ten_specific_cards() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 10: Financial Markets and Products / "
            "Reading 35: Foreign Exchange Markets / "
            "Module 35.2: Exchange Rate Determination"
        ),
        text="Exchange rate parity source text",
        page_number=104,
    )
    concept = StudyConceptCard(
        concept_id="concept-fx-parity",
        material_id=section.material_id,
        module_id=section.module_id,
        title="Exchange rate parity relationships",
        learning_outcome="LO 35.b",
        related_original_key_concept_id="lo-35-b",
        source_pages=[104],
        source_excerpt=(
            "LO 35.b\n"
            "Purchasing power parity (PPP) links exchange rates to relative price levels. Currency "
            "appreciation means a currency gains value relative to another currency, while depreciation "
            "means it loses value. Nominal interest rates reflect real interest rates plus expected "
            "inflation. Covered interest rate parity uses forward contracts to eliminate exchange-rate "
            "risk, while uncovered interest rate parity relies on expected future spot rates without hedging."
        ),
        simplified_explanation="Parity relationships connect exchange rates, inflation, and interest rates.",
        key_terms=["purchasing power parity", "covered interest rate parity", "uncovered interest rate parity"],
        formulas=[],
        exam_focus="Explain exchange rate parity conditions.",
        common_traps=[],
    )

    fronts = [card.front for card in service._content_specific_flashcards_for_concept(section, concept)]

    assert len(fronts) >= 10
    assert "What does purchasing power parity (PPP) state?" in fronts
    assert "What does currency appreciation mean?" in fronts
    assert "How do nominal interest rates relate to real interest rates and expected inflation?" in fronts
    assert "How does covered interest rate parity differ from uncovered interest rate parity?" in fronts


def test_mortgage_backed_securities_generate_at_least_ten_specific_cards() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 11: Financial Markets and Products / "
            "Reading 44: Mortgage-Backed Securities / "
            "Module 44.2: Mortgage-Backed Securities"
        ),
        text="Mortgage-backed securities source text",
        page_number=221,
    )
    concept = StudyConceptCard(
        concept_id="concept-mbs",
        material_id=section.material_id,
        module_id=section.module_id,
        title="Mortgage-backed securities",
        learning_outcome="LO 44.b",
        related_original_key_concept_id="lo-44-b",
        source_pages=[221],
        source_excerpt=(
            "LO 44.b\n"
            "A mortgage-backed security (MBS) pools mortgage loans and passes through principal and "
            "interest payments to investors. Weighted average coupon (WAC) is the average mortgage rate "
            "in the pool, while weighted average maturity (WAM) is the average time to final maturity. "
            "Prepayment risk arises when borrowers repay mortgages early. Prepayment can be measured with "
            "single monthly mortality (SMM) or the conditional prepayment rate (CPR). Collateralized "
            "mortgage obligations (CMOs) create tranches with different prepayment exposure."
        ),
        simplified_explanation="MBS pools mortgages and exposes investors to prepayment behavior.",
        key_terms=["mortgage-backed security", "WAC", "WAM", "prepayment risk", "CMO"],
        formulas=[],
        exam_focus="Explain mortgage-backed security structure and prepayment measures.",
        common_traps=[],
    )

    fronts = [card.front for card in service._content_specific_flashcards_for_concept(section, concept)]

    assert len(fronts) >= 10
    assert "What is a mortgage-backed security (MBS)?" in fronts
    assert "What do WAC and WAM measure in mortgage-backed securities?" in fronts
    assert "What is prepayment risk in mortgage-backed securities?" in fronts
    assert "How do CMOs change mortgage-backed security cash-flow exposure?" in fronts


def test_swap_valuation_generates_at_least_ten_specific_cards() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 12: Valuation and Risk Models / "
            "Reading 46: Swaps / "
            "Module 46.2: Swap Valuation"
        ),
        text="Swap valuation source text",
        page_number=251,
    )
    concept = StudyConceptCard(
        concept_id="concept-swap-valuation",
        material_id=section.material_id,
        module_id=section.module_id,
        title="Swap valuation",
        learning_outcome="LO 46.b",
        related_original_key_concept_id="lo-46-b",
        source_pages=[251],
        source_excerpt=(
            "LO 46.b\n"
            "A plain vanilla interest rate swap can be valued as the difference between a fixed-rate "
            "bond and a floating-rate bond or as a sequence of forward rate agreements. Future net cash "
            "flows are discounted using the appropriate discount curve. The value is zero at initiation "
            "when the fixed rate is the fair swap rate, but changes as rates move."
        ),
        simplified_explanation="Interest rate swaps are valued from discounted net cash flows.",
        key_terms=["swap valuation", "fixed-rate bond", "floating-rate bond", "forward rate agreements"],
        formulas=[],
        exam_focus="Value plain vanilla interest rate swaps.",
        common_traps=[],
    )

    fronts = [card.front for card in service._content_specific_flashcards_for_concept(section, concept)]

    assert len(fronts) >= 10
    assert "How can a plain vanilla interest rate swap be valued?" in fronts
    assert "How can a swap be valued as a bond position?" in fronts
    assert "How can a swap be valued as a sequence of forward rate agreements?" in fronts
    assert "What happens to swap value after market rates move?" in fronts


def test_interest_rate_curve_terms_generate_at_least_ten_specific_cards() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 12: Valuation and Risk Models / "
            "Reading 42: Fixed Income Valuation / "
            "Module 42.1: Spot Rates and Forward Rates"
        ),
        text="Interest-rate curve source text",
        page_number=181,
    )
    concept = StudyConceptCard(
        concept_id="concept-rate-curve",
        material_id=section.material_id,
        module_id=section.module_id,
        title="Spot rates and forward rates",
        learning_outcome="LO 42.a",
        related_original_key_concept_id="lo-42-a",
        source_pages=[181],
        source_excerpt=(
            "LO 42.a\n"
            "A spot rate is the yield on a zero-coupon bond for a specific maturity. "
            "Forward rates are future interest rates implied by current spot rates. "
            "Forward rate agreements (FRAs) lock in a future borrowing or lending rate. "
            "Discount factors convert future cash flows to present value, and yield to maturity "
            "is the single discount rate that equates bond cash flows to price."
        ),
        simplified_explanation="Spot and forward rates connect fixed-income cash flows to valuation.",
        key_terms=["spot rate", "forward rate", "forward rate agreement", "discount factor"],
        formulas=[],
        exam_focus="Interpret spot rates, forward rates, and discount factors.",
        common_traps=[],
    )

    fronts = [card.front for card in service._content_specific_flashcards_for_concept(section, concept)]

    assert len(fronts) >= 10
    assert "What is a spot rate?" in fronts
    assert "How does a spot rate differ from a forward rate?" in fronts
    assert "What does a forward rate agreement (FRA) lock in?" in fronts


def test_duration_convexity_terms_generate_at_least_ten_specific_cards() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 12: Valuation and Risk Models / "
            "Reading 42: Fixed Income Valuation / "
            "Module 42.3: Duration and Convexity"
        ),
        text="Duration and convexity source text",
        page_number=190,
    )
    concept = StudyConceptCard(
        concept_id="concept-duration-convexity",
        material_id=section.material_id,
        module_id=section.module_id,
        title="Duration and convexity",
        learning_outcome="LO 42.e",
        related_original_key_concept_id="lo-42-e",
        source_pages=[190],
        source_excerpt=(
            "LO 42.e\n"
            "Duration measures a bond's price sensitivity to a change in yield. Modified duration "
            "approximates the percentage price change for a small yield change. Effective duration "
            "is used when cash flows can change with interest rates. Convexity improves the duration "
            "price approximation for larger yield changes because the price-yield relationship is curved."
        ),
        simplified_explanation="Duration and convexity estimate fixed-income price sensitivity.",
        key_terms=["duration", "modified duration", "effective duration", "convexity"],
        formulas=[],
        exam_focus="Apply duration and convexity price sensitivity.",
        common_traps=[],
    )

    fronts = [card.front for card in service._content_specific_flashcards_for_concept(section, concept)]

    assert len(fronts) >= 10
    assert "What does duration measure?" in fronts
    assert "How does convexity improve the duration price approximation?" in fronts
    assert "How does effective duration differ from modified duration?" in fronts


def test_credit_bond_terms_generate_at_least_ten_specific_cards() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 12: Valuation and Risk Models / "
            "Reading 43: Corporate Bonds / "
            "Module 43.2: Corporate Bond Credit Risk"
        ),
        text="Credit bond source text",
        page_number=203,
    )
    concept = StudyConceptCard(
        concept_id="concept-credit-bonds",
        material_id=section.material_id,
        module_id=section.module_id,
        title="Corporate bond credit risk",
        learning_outcome="LO 43.d",
        related_original_key_concept_id="lo-43-d",
        source_pages=[203],
        source_excerpt=(
            "LO 43.d\n"
            "Corporate bonds expose investors to credit risk, default risk, event risk, and rating "
            "migration risk. Credit spreads compensate investors for credit risk. Recovery rate affects "
            "loss severity after default. High-yield bonds have lower credit quality than investment-grade "
            "bonds and generally require wider credit spreads."
        ),
        simplified_explanation="Corporate bonds compensate investors for credit and default exposure.",
        key_terms=["credit risk", "default risk", "event risk", "credit spread", "high-yield bonds"],
        formulas=[],
        exam_focus="Explain corporate bond credit risk.",
        common_traps=[],
    )

    fronts = [card.front for card in service._content_specific_flashcards_for_concept(section, concept)]

    assert len(fronts) >= 10
    assert "What is credit risk for a corporate bond?" in fronts
    assert "What does a credit spread compensate investors for?" in fronts
    assert "How do high-yield bonds differ from investment-grade bonds?" in fronts


def test_credit_default_and_spread_definitions_reach_ten_grounded_cards() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 12: Valuation and Risk Models / "
            "Reading 43: Corporate Bonds / "
            "Module 43.1: Corporate Bond Fundamentals and Types"
        ),
        text="Credit default risk and credit spread risk source text",
        page_number=201,
    )
    concept = StudyConceptCard(
        concept_id="concept-credit-default-spread",
        material_id=section.material_id,
        module_id=section.module_id,
        title="Credit default risk and credit spread risk",
        learning_outcome="LO 43.d",
        related_original_key_concept_id="lo-43-d",
        source_pages=[201],
        source_excerpt=(
            "LO 43.d\n"
            "Credit default risk is the possibility that the issuer does not make the payments "
            "specified in the indenture. Credit spread risk is the price risk from changes in the "
            "spread of a bond's interest rate over the corresponding Treasury rate."
        ),
        simplified_explanation="Distinguish default risk from credit spread risk.",
        key_terms=["credit default risk", "credit spread risk", "indenture", "Treasury rate"],
        formulas=[],
        exam_focus="Distinguish default risk from credit spread risk.",
        common_traps=[],
    )

    cards = service._flashcards_from_original_book(
        section,
        OriginalBookContent(),
        [concept],
        [],
    )

    assert len(cards) >= 10
    assert "What event realizes credit default risk?" in [card.front for card in cards]
    assert "What market change creates credit spread risk?" in [card.front for card in cards]


def test_module_level_top_up_uses_multiple_valid_anchors_to_reach_ten_cards() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 5: Quantitative Analysis / "
            "Reading 19: Regression / "
            "Module 19.1: Multiple Regression"
        ),
        text="Multiple regression source text",
        page_number=121,
    )
    concepts = [
        _concept(
            section,
            concept_id="concept-multiple-regression",
            lo="LO 19.a",
            title="Multiple regression",
            excerpt=(
                "LO 19.a\n"
                "Multiple regression uses two or more independent variables to explain a dependent variable. "
                "The coefficient of determination measures the proportion of variation explained by the regression. "
                "Adjusted R-squared penalizes a model for adding independent variables that do not improve explanatory power."
            ),
            key_terms=[
                "multiple regression",
                "dependent variable",
                "independent variable",
                "coefficient of determination",
                "adjusted R-squared",
            ],
        ),
        _concept(
            section,
            concept_id="concept-dummy-variables",
            lo="LO 19.b",
            title="Dummy variables",
            excerpt=(
                "LO 19.b\n"
                "A dummy variable is a binary variable used to represent categories in a regression model. "
                "An interaction term allows the effect of one independent variable to depend on another independent variable. "
                "Multicollinearity occurs when independent variables are highly correlated."
            ),
            key_terms=["dummy variable", "interaction term", "multicollinearity"],
        ),
        _concept(
            section,
            concept_id="concept-regression-assumptions",
            lo="LO 19.c",
            title="Regression assumptions",
            excerpt=(
                "LO 19.c\n"
                "Regression assumptions include linearity, homoscedasticity, independent errors, and normally distributed errors. "
                "Heteroskedasticity occurs when the variance of the errors is not constant. "
                "Serial correlation occurs when regression errors are correlated across observations."
            ),
            key_terms=["regression assumptions", "heteroskedasticity", "serial correlation"],
        ),
    ]

    cards = service._flashcards_from_original_book(section, OriginalBookContent(), concepts, [])
    fronts = {card.front for card in cards}

    assert len(cards) >= 10
    assert not any(card.needs_more_source for card in cards)
    assert "What is multiple regression?" in fronts
    assert "What is a dummy variable?" in fronts
    assert "What is multicollinearity?" in fronts
    assert "What is heteroskedasticity?" in fronts
    assert "What is serial correlation?" in fronts
    assert not any(service._flashcard_quality_flags(card) for card in cards)


def test_module_flashcards_top_up_each_learning_outcome_independently() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 14: Valuation and Risk Models / "
            "Reading 52: Measuring Credit Losses and Modeling Credit Risk / "
            "Module 52.2: Measuring Credit Losses and Modeling Credit Risk"
        ),
        text="Credit portfolio modeling source text",
        page_number=80,
    )
    concepts = [
        _concept(
            section,
            concept_id="concept-expected-credit-loss",
            lo="LO 52.f",
            title="Expected credit loss",
            excerpt=(
                "LO 52.f\n"
                "Expected loss is the average credit loss expected over a given time horizon. "
                "The expected loss formula uses probability of default, exposure at default, and loss given default. "
                "Unexpected loss is the amount by which actual losses can exceed expected losses."
            ),
            key_terms=["expected loss", "probability of default", "exposure at default", "loss given default"],
        ),
        _concept(
            section,
            concept_id="concept-default-probability",
            lo="LO 52.g",
            title="Default probability",
            excerpt=(
                "LO 52.g\n"
                "Probability of default measures the likelihood that a borrower will fail to meet debt obligations. "
                "Credit spreads compensate lenders for default risk and expected recovery uncertainty. "
                "Default risk increases when borrower cash flows weaken or collateral values decline."
            ),
            key_terms=["probability of default", "borrower", "credit spread", "default risk"],
        ),
        _concept(
            section,
            concept_id="concept-credit-correlations",
            lo="LO 52.h",
            title="Credit correlations",
            excerpt=(
                "LO 52.h\n"
                "Credit portfolio models consider borrowers, default correlations, and concentration risk. "
                "Correlations measure how borrower defaults may move together during economic stress. "
                "Higher default correlation reduces diversification benefits and can increase portfolio credit losses."
            ),
            key_terms=["borrowers", "default correlations", "concentration risk", "diversification benefits"],
        ),
    ]

    cards = service._flashcards_from_original_book(section, OriginalBookContent(), concepts, [])
    counts_by_lo = {
        concept.related_original_key_concept_id: sum(
            1 for card in cards if card.learning_outcome_id == concept.related_original_key_concept_id
        )
        for concept in concepts
    }

    assert all(count >= 10 for count in counts_by_lo.values())
    assert len(counts_by_lo) == 3
    assert not any(card.needs_more_source for card in cards if card.learning_outcome_id in counts_by_lo)
    assert not any(
        card.front
        in {
            "What is borrowers?",
            "What are borrowers?",
            "What is correlations?",
            "What are correlations?",
        }
        for card in cards
    )
    fronts = {card.front for card in cards}
    assert "What inputs does the expected loss formula use?" in fronts
    assert "How does unexpected loss differ from expected loss?" in fronts
    assert "What factors do credit portfolio models consider?" in fronts
    assert "What do default correlations measure?" in fronts
    assert "How do higher default correlations affect diversification benefits?" in fronts
    assert not any(service._flashcard_quality_flags(card) for card in cards)


def test_module_flashcards_repair_underfilled_insurance_learning_outcomes_without_junk() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 16: Financial Markets and Products / "
            "Reading 28: Insurance Companies and Pension Plans / "
            "Module 28.1: Insurance Companies and Pension Plans"
        ),
        text="Insurance company and pension plan source text",
        page_number=22,
    )
    concepts = [
        _concept(
            section,
            concept_id="concept-insurance-company-types",
            lo="LO 28.a",
            title="Insurance company types",
            excerpt=(
                "LO 28.a\n"
                "Insurance companies pool risks and collect premiums. "
                "Life insurance companies provide death benefits and annuity products. "
                "Property and casualty insurers cover losses from accidents, liability, and property damage. "
                "Health insurers cover medical expenses. "
                "Reinsurance transfers part of insurer risk to another insurer. "
                "Premiums compensate insurers for expected claims and expenses. "
                "Reserves support future claim payments. "
                "Diversification reduces total portfolio risk by pooling independent exposures."
            ),
            key_terms=[
                "insurance companies",
                "life insurance companies",
                "property and casualty insurers",
                "health insurers",
                "reinsurance",
                "premium payments",
                "reserves",
                "diversification",
            ],
        ),
        _concept(
            section,
            concept_id="concept-insurance-coverage-payments",
            lo="LO 28.e",
            title="Insurance coverage and payments",
            excerpt=(
                "LO 28.e\n"
                "Diversification reduces total portfolio risk because independent policyholder claims are pooled across many exposures. "
                "Insurance coverage is the protection provided by an insurance contract. "
                "Premium payments are amounts policyholders pay for insurance coverage. "
                "Benefit payments are amounts insurers pay to policyholders when covered events occur. "
                "Pension plans promise retirement benefits and must manage asset-liability risk."
            ),
            key_terms=[
                "diversification",
                "insurance coverage",
                "premium payments",
                "benefit payments",
                "policyholder claims",
                "pension plans",
                "asset-liability risk",
            ],
        ),
    ]

    cards = service._flashcards_from_original_book(section, OriginalBookContent(), concepts, [])
    counts_by_lo = {
        concept.related_original_key_concept_id: sum(
            1 for card in cards if card.learning_outcome_id == concept.related_original_key_concept_id
        )
        for concept in concepts
    }
    fronts = {card.front for card in cards}

    assert all(count >= 10 for count in counts_by_lo.values())
    assert not any(card.needs_more_source for card in cards if card.learning_outcome_id in counts_by_lo)
    assert "What is insurance coverage?" in fronts
    assert "What are premium payments?" in fronts
    assert "What are benefit payments?" in fronts
    for bad_front in {
        "What is coverage?",
        "What are premiums?",
        "What are benefits?",
        "What is payment?",
        "What are no payments?",
    }:
        assert bad_front not in fronts
    assert not any(service._flashcard_quality_flags(card) for card in cards)


def test_option_strategy_terms_generate_at_least_ten_specific_cards() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 11: Financial Markets and Products / "
            "Reading 40: Option Strategies / "
            "Module 40.1: Option Spreads and Combinations"
        ),
        text="Option strategy source text",
        page_number=163,
    )
    concept = StudyConceptCard(
        concept_id="concept-option-strategies",
        material_id=section.material_id,
        module_id=section.module_id,
        title="Option strategies",
        learning_outcome="LO 40.a",
        related_original_key_concept_id="lo-40-a",
        source_pages=[163],
        source_excerpt=(
            "LO 40.a\n"
            "A protective put combines a long asset position with a long put option. A covered call "
            "combines a long asset position with a short call option. Bull spreads profit when the "
            "underlying price rises, while bear spreads profit when it falls. A straddle combines a call "
            "and put with the same strike and expiration, while a strangle uses different strikes. "
            "A butterfly spread combines bull and bear spreads to profit from limited price movement."
        ),
        simplified_explanation="Option strategies combine options to shape payoff exposure.",
        key_terms=["protective put", "covered call", "bull spread", "bear spread", "straddle", "strangle"],
        formulas=[],
        exam_focus="Compare option strategy payoffs.",
        common_traps=[],
    )

    fronts = [card.front for card in service._content_specific_flashcards_for_concept(section, concept)]

    assert len(fronts) >= 10
    assert "What is a protective put?" in fronts
    assert "How does a protective put differ from a covered call?" in fronts
    assert "How does a straddle differ from a strangle?" in fronts


def test_card_has_source_page_module_lo() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section, concept = _value_at_risk_section_and_concept()

    cards = service._content_specific_flashcards_for_concept(section, concept)
    card = next(card for card in cards if card.front == "What is value at risk (VaR)?")

    assert card.source_page == 101
    assert card.module_number == "7.1"
    assert card.lo_code == "LO 7.a"


def test_no_empty_answer_cards() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section, concept = _value_at_risk_section_and_concept()

    cards = service._content_specific_flashcards_for_concept(section, concept)

    assert cards
    assert all((card.back_concise or card.back).strip() for card in cards)


def test_no_duplicate_semantic_cards() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    cards = [
        _flashcard(front="What is value at risk (VaR)?", back="VaR estimates a loss threshold."),
        _flashcard(front="What is value at risk (VaR)?", back="VaR estimates a loss threshold."),
        _flashcard(front="How should value at risk (VaR) be interpreted?", back="VaR is a threshold loss estimate."),
    ]

    published = service._valid_unique_flashcards(cards, limit=10)

    assert [card.front for card in published] == [
        "What is value at risk (VaR)?",
        "How should value at risk (VaR) be interpreted?",
    ]


def test_population_moments_concept_generates_ten_specific_cards() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 4: Quantitative Analysis / "
            "Reading 21: Random Variables and Probability Distributions / "
            "Module 21.1: Covariance Stationarity"
        ),
        text="Population moments source text",
        page_number=144,
    )
    concept = StudyConceptCard(
        concept_id="concept-population-moments",
        material_id=section.material_id,
        module_id=section.module_id,
        title="Population moments",
        learning_outcome="LO 21.a",
        related_original_key_concept_id="lo-21-a",
        source_pages=[144],
        source_excerpt=(
            "LO 21.a\n"
            "The population moments most often used in time series analysis are mean, variance, "
            "skewness, and kurtosis. The first moment, the mean of a random variable, is its "
            "expected value, E(X). The second central moment is variance. Skewness measures "
            "symmetry. Kurtosis measures the proportion of outcomes in the tails."
        ),
        simplified_explanation="Population moments summarize location, dispersion, symmetry, and tail thickness.",
        key_terms=["population moments", "mean", "variance", "skewness", "kurtosis", "expected value"],
        formulas=[],
    )

    cards = service._content_specific_flashcards_for_concept(section, concept)
    fronts = {card.front for card in cards}

    assert len(cards) >= 10
    assert "What are the four common population moments?" in fronts
    assert "What is the mean of a random variable?" in fronts
    assert "What does variance measure?" in fronts
    assert "What does skewness measure?" in fronts
    assert "What does kurtosis measure?" in fronts
    assert not any(service._flashcard_quality_flags(card) for card in cards)


def test_compounding_concept_generates_ten_specific_cards() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 7: Valuation and Risk Models / "
            "Reading 35: Fixed-Income Valuation / "
            "Module 35.1: Interest Rates and Compounding"
        ),
        text="Compounding source text",
        page_number=214,
    )
    concept = StudyConceptCard(
        concept_id="concept-compounding-frequency",
        material_id=section.material_id,
        module_id=section.module_id,
        title="Compounding frequency",
        learning_outcome="LO 35.a",
        related_original_key_concept_id="lo-35-a",
        source_pages=[214],
        source_excerpt=(
            "LO 35.a\n"
            "Compounding frequency describes how often interest is credited or charged. Common "
            "frequencies include annual, semiannual, quarterly, monthly, and continuous compounding. "
            "Increasing compounding frequency increases a future value for the same stated rate "
            "and decreases the present value of a future cash flow. Bond valuation requires matching "
            "the discount rate and cash flow timing to the compounding frequency."
        ),
        simplified_explanation="Compounding frequency changes how rates accumulate and how cash flows are discounted.",
        key_terms=[
            "compounding frequency",
            "annual compounding",
            "semiannual compounding",
            "quarterly compounding",
            "monthly compounding",
            "continuous compounding",
            "present value",
            "future value",
        ],
        formulas=[],
    )

    cards = service._content_specific_flashcards_for_concept(section, concept)
    fronts = {card.front for card in cards}

    assert len(cards) >= 10
    assert "What is compounding frequency?" in fronts
    assert "How does compounding frequency affect future value?" in fronts
    assert "How does compounding frequency affect present value?" in fronts
    assert "Which compounding frequencies commonly appear in bond valuation?" in fronts
    assert not any(service._flashcard_quality_flags(card) for card in cards)


def test_module_level_top_up_reaches_ten_from_multiple_valid_anchors() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 4: Quantitative Analysis / "
            "Reading 17: Hypothesis Testing / "
            "Module 17.2: Hypothesis Testing Results"
        ),
        text="Hypothesis testing source text",
        page_number=64,
    )
    concepts = [
        _concept(
            section,
            concept_id="concept-confidence-interval",
            lo="LO 17.e",
            title="Confidence interval",
            excerpt=(
                "LO 17.e\n"
                "A confidence interval gives a range of plausible values for a population parameter. "
                "A wider confidence interval indicates greater uncertainty about the parameter estimate."
            ),
            key_terms=["confidence interval", "population parameter"],
        ),
        _concept(
            section,
            concept_id="concept-p-value",
            lo="LO 17.f",
            title="P-value",
            excerpt=(
                "LO 17.f\n"
                "A p-value measures how extreme the sample result is under the null hypothesis. "
                "A small p-value provides evidence against the null hypothesis."
            ),
            key_terms=["p-value", "null hypothesis"],
        ),
        _concept(
            section,
            concept_id="concept-t-test",
            lo="LO 17.g",
            title="t-test",
            excerpt=(
                "LO 17.g\n"
                "A t-test is used when the population variance is unknown and the sample standard "
                "deviation estimates uncertainty. The test statistic compares the estimate with the "
                "hypothesized value."
            ),
            key_terms=["t-test", "population variance", "test statistic"],
        ),
        _concept(
            section,
            concept_id="concept-type-errors",
            lo="LO 17.h",
            title="Type I and Type II errors",
            excerpt=(
                "LO 17.h\n"
                "A Type I error rejects a true null hypothesis. A Type II error fails to reject a false "
                "null hypothesis. Test power is the probability of rejecting a false null hypothesis."
            ),
            key_terms=["Type I error", "Type II error", "test power"],
        ),
    ]

    cards = service._flashcards_from_original_book(section, OriginalBookContent(), concepts, [])
    fronts = {card.front for card in cards}

    assert len(cards) >= 10
    assert "What does a confidence interval give?" in fronts
    assert "What does a p-value measure?" in fronts
    assert "When is a t-test used?" in fronts
    assert "How does a Type I error differ from a Type II error?" in fronts
    assert not any(service._flashcard_quality_flags(card) for card in cards)


def test_learning_outcome_coverage_groups_same_lo_across_split_key_concepts() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 4: Quantitative Analysis / "
            "Reading 18: Linear Regression / "
            "Module 18.1: Regression Analysis"
        ),
        text="Regression analysis source text",
        page_number=98,
    )
    concepts = [
        _concept(
            section,
            concept_id="concept-regression-fit",
            lo="LO 18.a",
            title="Regression model fit",
            excerpt=(
                "LO 18.a\n"
                "Regression analysis models the relationship between a dependent variable and one or "
                "more independent variables. The dependent variable is the outcome being explained, "
                "while independent variables are the explanatory inputs. The coefficient of "
                "determination, R-squared, measures how much variation in the dependent variable is "
                "explained by the regression."
            ),
            key_terms=["regression analysis", "dependent variable", "independent variables", "R-squared"],
        ).model_copy(update={"related_original_key_concept_id": "lo-18-a-regression-fit"}),
        _concept(
            section,
            concept_id="concept-regression-diagnostics",
            lo="LO 18.a",
            title="Regression diagnostics",
            excerpt=(
                "LO 18.a\n"
                "Residuals are the differences between observed values and fitted values from a "
                "regression model. Outliers can distort coefficient estimates and fitted values. "
                "A scatter plot can help identify unusual observations and nonlinear patterns."
            ),
            key_terms=["residuals", "outliers", "fitted values", "scatter plot"],
        ).model_copy(update={"related_original_key_concept_id": "lo-18-a-regression-diagnostics"}),
    ]

    cards = service._flashcards_from_original_book(section, OriginalBookContent(), concepts, [])
    lo_cards = [card for card in cards if card.lo_code == "LO 18.a"]
    fronts = {card.front for card in lo_cards}

    assert len(lo_cards) >= 10
    assert not any(card.needs_more_source for card in lo_cards)
    assert "What does R-squared measure in regression?" in fronts
    assert "What is a residual in regression analysis?" in fronts
    assert not any(service._flashcard_quality_flags(card) for card in lo_cards)


def test_deduplicates_duplicate_fronts_across_split_concepts_in_same_visible_lo() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    first = _flashcard(
        front="What does regression analysis model?",
        back="Regression analysis models the relationship between a dependent variable and independent variables.",
    ).model_copy(
        update={
            "module_id": "module-18-1",
            "learning_outcome_id": "lo-18-a-regression-fit",
            "concept_id": "concept-regression-fit",
            "lo_code": "LO 18.a",
            "source_page": 144,
        }
    )
    duplicate = first.model_copy(
        update={
            "learning_outcome_id": "lo-18-a-regression-diagnostics",
            "concept_id": "concept-regression-diagnostics",
        }
    )

    unique = service._valid_unique_flashcards([first, duplicate], limit=10)

    assert [card.front for card in unique].count("What does regression analysis model?") == 1


def test_deduplicates_regression_measurement_paraphrases_and_rejects_ungrammatical_variant() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    base = {
        "module_id": "module-18-1",
        "learning_outcome_id": "lo-18-a",
        "concept_id": "concept-regression-analysis",
        "lo_code": "LO 18.a",
        "source_page": 108,
        "source_excerpt": (
            "Regression analysis seeks to measure the relationship between one dependent "
            "variable and one or more independent variables."
        ),
    }
    polished = _flashcard(
        front="What does regression analysis seek to measure?",
        back="Regression analysis seeks to measure the relationship between a dependent variable and one or more independent variables.",
    ).model_copy(update=base)
    overlapping = _flashcard(
        front="What does regression analysis attempt to measure?",
        back="Regression analysis measures the relationship between one dependent variable and one or more independent variables.",
    ).model_copy(update=base | {"quality_score": 0.1})
    ungrammatical = _flashcard(
        front="What does regression analysis seeks to measure?",
        back="Regression analysis seeks to measure the relationship between variables.",
    ).model_copy(update=base)

    unique = service._valid_unique_flashcards([polished, overlapping, ungrammatical], limit=10)

    fronts = [card.front for card in unique]
    assert fronts == ["What does regression analysis attempt to measure?"]
    assert "generic_question" in service._flashcard_quality_flags(ungrammatical)


def test_regression_lo_top_up_uses_general_source_anchors() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 4: Quantitative Analysis / "
            "Reading 18: Linear Regression / "
            "Module 18.1: Regression Analysis"
        ),
        text="Regression source text",
        page_number=144,
    )
    concepts = [
        _concept(
            section,
            concept_id="concept-regression-model-types",
            lo="LO 18.a",
            title="Regression model types",
            excerpt=(
                "LO 18.a\n"
                "Describe the models which can be estimated using linear regression and differentiate "
                "them from those which cannot. Regression analysis attempts to measure the relationship "
                "between one dependent variable and one or more independent variables. Simple linear "
                "regression uses one independent variable. Multiple regression uses two or more "
                "independent variables. Linear regression models a continuous dependent variable. "
                "A linear probability model can estimate a binary dependent variable. Logistic "
                "regression is used when the dependent variable is categorical. Probit regression is "
                "used for limited dependent variables. The model choice depends on the dependent "
                "variable and the objective of the analysis."
            ),
            key_terms=[
                "regression analysis",
                "simple linear regression",
                "multiple regression",
                "linear probability model",
                "logistic regression",
                "probit regression",
            ],
        ).model_copy(update={"related_original_key_concept_id": "lo-18-a-model-types"}),
        _concept(
            section,
            concept_id="concept-regression-dependent-independent",
            lo="LO 18.a",
            title="Dependent and independent variables",
            excerpt=(
                "LO 18.a\n"
                "Regression analysis seeks to measure the relationship between one dependent variable "
                "and one or more independent variables. Independent variables explain changes in the "
                "dependent variable. Regression models can be linear or nonlinear depending on the "
                "relationship being estimated."
            ),
            key_terms=["dependent variable", "independent variables", "linear models", "nonlinear models"],
        ).model_copy(update={"related_original_key_concept_id": "lo-18-a-variables"}),
    ]

    cards = service._flashcards_from_original_book(section, OriginalBookContent(), concepts, [])
    lo_cards = [card for card in cards if card.lo_code == "LO 18.a"]
    fronts = {card.front for card in lo_cards}

    assert len(fronts) >= 10
    assert len(fronts) == len(lo_cards)
    assert not any(card.needs_more_source for card in lo_cards)
    assert "What does regression analysis attempt to measure?" in fronts
    assert "How many independent variables does simple linear regression use?" in fronts
    assert "What can a linear probability model estimate?" in fronts
    assert "When is logistic regression used?" in fronts
    assert "What determines the appropriate regression model choice?" in fronts
    assert "What does a linear probability model?" not in fronts
    assert not any(service._flashcard_quality_flags(card) for card in lo_cards)


def test_book_two_regression_analysis_conditions_top_up_reaches_ten_specific_cards() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 5: Quantitative Analysis / "
            "Reading 18: Linear Regression / "
            "Module 18.1: Regression Analysis"
        ),
        text=(
            "LO 18.a Describe the models which can be estimated using linear regression and "
            "differentiate them from those which cannot. Regression analysis seeks to measure "
            "the linear relationship between a dependent variable and one or more independent "
            "variables. Linear Regression Conditions 1. The relationship between Y and X should "
            "be linear. 2. The error term should be additive and its variance should not depend "
            "on the independent variable. 3. All X variables should be observable. The term "
            "linear means that the dependent variable is modeled as a linear function of the "
            "regression coefficients. Transforming an independent variable can make a nonlinear "
            "variable relationship fit a linear regression model. Linear regression is "
            "inappropriate if an unknown parameter enters the model multiplicatively or in an exponent."
        ),
        page_number=108,
    )
    concepts = [
        _concept(
            section,
            concept_id="concept-regression-analysis-body",
            lo="LO 18.a",
            title="Regression analysis",
            excerpt=(
                "LO 18.a\n"
                "Describe the models which can be estimated using linear regression and "
                "differentiate them from those which cannot. Regression analysis seeks to measure "
                "the linear relationship between a dependent variable and one or more independent "
                "variables. The dependent variable is the variable being explained, and the "
                "independent variables are used to explain it. Linear Regression Conditions "
                "1. The relationship between Y and X should be linear. "
                "2. The error term should be additive and its variance should not depend on the "
                "independent variable. 3. All X variables should be observable. The term linear "
                "means that the dependent variable is modeled as a linear function of the "
                "regression coefficients. Transforming an independent variable can make a "
                "nonlinear variable relationship fit a linear regression model. Linear regression "
                "is inappropriate if an unknown parameter enters the model multiplicatively or in an exponent."
            ),
            key_terms=[
                "regression analysis",
                "dependent variable",
                "independent variables",
                "linear regression conditions",
                "additive error term",
                "observable independent variables",
                "linear relationship",
                "transformation",
            ],
        ).model_copy(update={"related_original_key_concept_id": "lo-18-a-regression-analysis"}),
        _concept(
            section,
            concept_id="concept-regression-analysis-key-concept",
            lo="LO 18.a",
            title="Linear regression conditions",
            excerpt=(
                "LO 18.a\n"
                "Regression analysis attempts to measure the relationship between one dependent "
                "variable and one or more independent variables. The conditions for linear "
                "regression are that the relationship between Y and X is linear, the error term "
                "is additive, and all X variables are observable."
            ),
            key_terms=[
                "linear regression conditions",
                "dependent variable",
                "independent variables",
                "additive error term",
                "observable X variables",
            ],
        ).model_copy(update={"related_original_key_concept_id": "lo-18-a-regression-conditions"}),
    ]

    cards = service._flashcards_from_original_book(section, OriginalBookContent(), concepts, [])
    lo_cards = [card for card in cards if card.lo_code == "LO 18.a"]
    fronts = {card.front for card in lo_cards}

    assert len(lo_cards) >= 10
    assert "What conditions must be satisfied to use linear regression?" in fronts
    assert "What does it mean for a regression relationship to be linear?" in fronts
    assert "Why can transforming an independent variable help a linear regression model?" in fronts
    assert "Why must the error term be additive in linear regression?" in fronts
    assert "Why must all X variables be observable in linear regression?" in fronts
    assert "What is specifies that the dependent variable?" not in fronts
    assert not any(service._flashcard_quality_flags(card) for card in lo_cards)


def test_book_two_live_regression_wording_top_up_reaches_ten_specific_cards() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 5: Quantitative Analysis / "
            "Reading 18: Linear Regression / "
            "Module 18.1: Regression Analysis"
        ),
        text=(
            "LO 18.a Describe the models which can be estimated using linear regression and "
            "differentiate them from those which cannot. Regression analysis seeks to measure "
            "how changes in one variable, called a dependent variable, can be explained by "
            "changes in one or more other variables called the independent variables. Linear "
            "Regression Conditions To use linear regression, three conditions need to be "
            "satisfied. The relationship between Y and X should be linear. The error term "
            "must be additive. All X variables should be observable. If the independent "
            "variable has a nonlinear relationship with the dependent variable, the model "
            "can use a transformed value of the independent variable. The term linear means "
            "that the dependent variable is a linear function of the coefficients."
        ),
        page_number=108,
    )
    concepts = [
        _concept(
            section,
            concept_id="concept-live-regression-model-types",
            lo="LO 18.a",
            title="Describe models which can be estimated using linear regression",
            excerpt=(
                "LO 18.a Describe the models which can be estimated using linear regression and "
                "differentiate them from those which cannot. Regression analysis seeks to measure "
                "how changes in one variable, called a dependent variable, can be explained by "
                "changes in one or more other variables called the independent variables. Linear "
                "Regression Conditions To use linear regression, three conditions need to be "
                "satisfied. The relationship between Y and X should be linear. The error term "
                "must be additive. All X variables should be observable. If the independent "
                "variable has a nonlinear relationship with the dependent variable, the model "
                "can use a transformed value of the independent variable. The term linear means "
                "that the dependent variable is a linear function of the coefficients."
            ),
            key_terms=[
                "regression analysis",
                "dependent variable",
                "independent variables",
                "linear regression conditions",
                "linear function of the coefficients",
                "additive error term",
                "observable X variables",
                "transformed value",
            ],
        ).model_copy(update={"related_original_key_concept_id": "lo-18-a-live-wording"}),
        _concept(
            section,
            concept_id="concept-live-regression-summary",
            lo="LO 18.a",
            title="Regression analysis attempts measure relationship",
            excerpt=(
                "LO 18.a Regression analysis attempts to measure the relationship between a "
                "dependent variable and one or more independent variables. To use linear "
                "regression, the following three conditions need to be satisfied: the "
                "relationship between Y and X is linear, the error term must be additive, "
                "and all X variables are observable."
            ),
            key_terms=[
                "regression analysis",
                "dependent variable",
                "independent variables",
                "linear regression",
                "additive error term",
            ],
        ).model_copy(update={"related_original_key_concept_id": "lo-18-a-live-summary"}),
    ]

    cards = service._flashcards_from_original_book(section, OriginalBookContent(), concepts, [])
    lo_cards = [card for card in cards if card.lo_code == "LO 18.a"]
    fronts = {card.front for card in lo_cards}

    assert len(lo_cards) >= 10
    assert "What does it mean for a regression relationship to be linear?" in fronts
    assert "Why must the error term be additive in linear regression?" in fronts
    assert "How can a transformed independent variable help linear regression?" in fronts
    assert not any(service._flashcard_quality_flags(card) for card in lo_cards)


def test_valid_unique_flashcards_removes_visible_duplicate_fronts_across_los() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    first = _flashcard(
        front="What is risk tolerance?",
        back="Risk tolerance is the acceptable variation around risk appetite.",
    ).model_copy(
        update={
            "module_id": "module-90-1",
            "learning_outcome_id": "lo-90-a",
            "concept_id": "concept-risk-tolerance-a",
            "lo_code": "LO 90.a",
            "source_page": 200,
        }
    )
    duplicate = first.model_copy(
        update={
            "learning_outcome_id": "lo-90-b",
            "concept_id": "concept-risk-tolerance-b",
            "lo_code": "LO 90.b",
        }
    )

    unique = service._valid_unique_flashcards([first, duplicate], limit=10)

    assert [card.front for card in unique].count("What is risk tolerance?") == 1


def test_aggregate_learning_outcome_top_up_uses_clean_sentences() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 9: Risk Management / "
            "Reading 90: Enterprise Risk Governance / "
            "Module 90.1: Risk Appetite and Limits"
        ),
        text="Risk appetite source text",
        page_number=200,
    )
    concept = _concept(
        section,
        concept_id="concept-risk-appetite-limits",
        lo="LO 90.a",
        title="Risk appetite and limits",
        excerpt=(
            "LO 90.a\n"
            "Risk appetite is the amount of risk an organization is willing to accept. "
            "Risk tolerance is the acceptable variation around risk appetite. "
            "Stress testing evaluates resilience under extreme scenarios. "
            "Scenario analysis considers plausible future states. "
            "Risk limits translate appetite into measurable constraints. "
            "Governance assigns accountability for risk decisions."
        ),
        key_terms=[
            "risk appetite",
            "risk tolerance",
            "stress testing",
            "scenario analysis",
            "risk limits",
            "governance",
        ],
    )

    cards = service._aggregate_learning_outcome_top_up_flashcards(section, "LO 90.a", [concept])
    fronts = {card.front for card in cards}

    assert len(cards) >= 5
    assert "What is risk appetite?" in fronts
    assert "What is risk tolerance?" in fronts
    assert "What does stress testing evaluate?" in fronts
    assert "What does scenario analysis consider?" in fronts
    assert "What do risk limits translate appetite into?" in fronts
    assert not any(service._flashcard_quality_flags(card) for card in cards)


def test_aggregate_learning_outcome_top_up_reaches_ten_from_general_action_sentences() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 9: Risk Management / "
            "Reading 90: Enterprise Risk Governance / "
            "Module 90.2: Risk Monitoring and Controls"
        ),
        text="Risk monitoring source text",
        page_number=202,
    )
    concept = _concept(
        section,
        concept_id="concept-risk-monitoring-controls",
        lo="LO 90.b",
        title="Risk monitoring and controls",
        excerpt=(
            "LO 90.b\n"
            "Risk appetite is the amount of risk an organization is willing to accept. "
            "Risk tolerance is the acceptable variation around risk appetite. "
            "Stress testing evaluates resilience under extreme scenarios. "
            "Scenario analysis considers plausible future states. "
            "Risk limits translate appetite into measurable constraints. "
            "Governance assigns accountability for risk decisions. "
            "Risk dashboards display current exposures and limit usage. "
            "Escalation rules identify breaches that need management attention. "
            "Limit monitoring reduces unmanaged risk across business units. "
            "Capital planning calculates resources needed under stress conditions."
        ),
        key_terms=[
            "risk appetite",
            "risk tolerance",
            "stress testing",
            "scenario analysis",
            "risk limits",
            "governance",
            "risk dashboards",
            "escalation rules",
            "limit monitoring",
            "capital planning",
        ],
    )

    cards = service._aggregate_learning_outcome_top_up_flashcards(section, "LO 90.b", [concept])
    fronts = {card.front for card in cards}

    assert len(cards) >= 10
    assert "What do risk dashboards display?" in fronts
    assert "What do escalation rules identify?" in fronts
    assert "What does capital planning calculate?" in fronts
    assert not any(card.needs_more_source for card in cards)
    assert not any(service._flashcard_quality_flags(card) for card in cards)


def test_learning_outcome_top_up_uses_module_text_when_concept_excerpt_is_short() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 9: Financial Markets and Products / "
            "Reading 38: Options Markets / "
            "Module 38.1: Option Types, Positions, and Underlying Assets"
        ),
        text=(
            "LO 38.a Options define contractual rights. "
            "LO 38.b Option contracts give holders rights related to an underlying asset. "
            "Call options give the holder the right to buy the underlying asset. "
            "Put options give the holder the right to sell the underlying asset. "
            "Margin requirements control leverage in option trading. "
            "Clearinghouses guarantee exchange-traded option performance. "
            "Option premiums compensate sellers for taking option risk. "
            "Covered calls reduce risk because the seller owns the underlying asset. "
            "Uncovered calls create higher risk because the seller does not own the underlying asset. "
            "Bid-ask spreads measure trading costs in option markets. "
            "Exchange-traded options reduce default risk through the Options Clearing Corporation. "
            "LO 38.c Option strategies combine positions to shape payoff exposure."
        ),
        page_number=138,
    )
    concept = _concept(
        section,
        concept_id="concept-lo-38-b",
        lo="LO 38.b",
        title="Option contracts and trading mechanics",
        excerpt="LO 38.b Option contracts are derivative contracts.",
        key_terms=[
            "option contracts",
            "call options",
            "put options",
            "margin requirements",
            "clearinghouses",
            "option premiums",
            "covered calls",
            "uncovered calls",
            "bid-ask spreads",
            "Options Clearing Corporation",
        ],
    )

    cards = service._ensure_learning_outcome_flashcard_coverage(section, [concept], [])
    lo_cards = [card for card in cards if card.lo_code == "LO 38.b"]
    fronts = {card.front for card in lo_cards}

    assert len(lo_cards) >= 10
    assert "What right do call options give the holder?" in fronts
    assert "What do margin requirements control?" in fronts
    assert "What do clearinghouses guarantee?" in fronts
    assert "What do exchange-traded options reduce?" in fronts
    assert not any(card.needs_more_source for card in lo_cards)
    assert not any(service._flashcard_quality_flags(card) for card in lo_cards)


def test_learning_outcome_top_up_handles_learning_objective_marker_variants() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 14: Valuation and Risk Models / "
            "Reading 52: Credit Risk Models / "
            "Module 52.2: Measuring Credit Losses and Modeling Credit Risk"
        ),
        text=(
            "Learning Objective 52.g: Explain how expected loss and unexpected loss "
            "are used in credit portfolios. "
            "Learning Objective 52.h: Explain how default correlation affects credit "
            "portfolio loss distributions. Default correlation measures the tendency "
            "of borrowers to default together during economic stress. Higher default "
            "correlation increases portfolio tail risk and reduces diversification "
            "benefits. Credit portfolio models use borrower default probabilities, "
            "exposures, loss given default, and correlations to estimate portfolio "
            "losses. Stress testing evaluates how correlated defaults affect extreme "
            "credit losses. Granularity reduces idiosyncratic credit risk when borrower "
            "exposures are diversified. Concentration risk increases when exposures "
            "are large or highly correlated. Unexpected loss measures variation around "
            "expected credit losses. Economic capital covers unexpected losses at a "
            "target confidence level. Learning Objective 52.i: Explain a neighboring "
            "credit risk topic."
        ),
        page_number=80,
    )
    concept = _concept(
        section,
        concept_id="concept-lo-52-h",
        lo="Learning Objective 52.h",
        title="Default correlation and portfolio credit losses",
        excerpt="Learning Objective 52.h Default correlation affects credit portfolio loss distributions.",
        key_terms=[
            "default correlation",
            "portfolio tail risk",
            "diversification benefits",
            "credit portfolio models",
            "stress testing",
            "granularity",
            "concentration risk",
            "unexpected loss",
            "economic capital",
        ],
    )

    cards = service._ensure_learning_outcome_flashcard_coverage(section, [concept], [])
    lo_cards = [card for card in cards if card.lo_code == "LO 52.h"]
    fronts = {card.front for card in lo_cards}

    assert len(lo_cards) >= 10
    assert "What does default correlation measure?" in fronts
    assert "How does higher default correlation affect portfolio tail risk?" in fronts
    assert "What do credit portfolio models use?" in fronts
    assert "What does stress testing evaluate?" in fronts
    assert "What does economic capital cover?" in fronts
    assert not any(card.needs_more_source for card in lo_cards)
    assert not any(service._flashcard_quality_flags(card) for card in lo_cards)


def test_module_top_up_evenly_covers_multiple_learning_outcome_subsections() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 14: Valuation and Risk Models / "
            "Reading 61: Portfolio Credit Risk / "
            "Module 61.1: Portfolio Credit Risk Measurement"
        ),
        text=(
            "LO 61.a: Define credit exposure and explain how exposure profiles affect portfolio losses. "
            "Credit exposure measures the amount at risk if a borrower defaults. "
            "Current exposure reflects the loss if default occurs today. "
            "Potential future exposure estimates possible exposure over the life of the transaction. "
            "Collateral reduces credit exposure by providing a recovery source. "
            "Netting agreements reduce exposure across offsetting transactions. "
            "Credit limits constrain borrower exposures before concentrations become excessive. "
            "Exposure profiles display how credit exposure changes over time. "
            "Counterparty credit risk combines exposure with default likelihood. "
            "Wrong-way risk increases exposure when counterparty credit quality deteriorates. "
            "Stress testing evaluates credit exposure under adverse market conditions. "
            "Learning Objective 61.b: Explain default probability and loss given default in portfolio credit models. "
            "Default probability measures the likelihood that a borrower fails to meet obligations. "
            "Loss given default measures the percentage of exposure not recovered after default. "
            "Recovery rate offsets loss given default because recovered value reduces loss severity. "
            "Expected loss uses probability of default, exposure at default, and loss given default. "
            "Unexpected loss measures variation around expected credit losses. "
            "Credit migration models estimate changes in borrower credit quality. "
            "Rating transitions show how credit quality can improve or deteriorate. "
            "Default intensity models estimate default risk over time. "
            "Credit spreads compensate lenders for expected credit losses and liquidity risk. "
            "Economic capital covers unexpected losses at a target confidence level. "
            "L O 61 c: Describe concentration risk and default correlation in credit portfolios. "
            "Concentration risk increases when exposures are large or linked to related borrowers. "
            "Default correlation measures how borrower defaults move together during economic stress. "
            "Higher default correlation increases portfolio tail risk and reduces diversification benefits. "
            "Credit portfolio models use borrower default probabilities, exposures, loss given default, and correlations to estimate portfolio losses. "
            "Granularity reduces idiosyncratic credit risk when borrower exposures are diversified. "
            "Sector concentration creates losses when one industry experiences stress. "
            "Geographic concentration creates losses when one region experiences stress. "
            "Name concentration exposes the portfolio to a single large borrower. "
            "Correlation assumptions affect estimated economic capital. "
            "Diversification benefits decline when defaults are highly correlated. "
            "LO 61 d: Explain credit risk mitigation and portfolio monitoring tools. "
            "Credit risk mitigation reduces expected and unexpected credit losses. "
            "Collateral mitigates loss severity by increasing recoveries after default. "
            "Guarantees transfer credit risk to a protection provider. "
            "Credit derivatives transfer credit exposure without selling the underlying loan. "
            "Loan covenants constrain borrower behavior and reduce credit deterioration. "
            "Portfolio monitoring tracks exposures, limits, ratings, and concentrations. "
            "Early warning indicators identify borrowers that need management attention. "
            "Limit monitoring reduces unmanaged credit risk across business units. "
            "Hedging strategies reduce credit exposure but may introduce counterparty risk. "
            "Risk reports summarize portfolio credit risk for senior management."
        ),
        page_number=121,
    )
    concepts = [
        _concept(
            section,
            concept_id="concept-lo-61-a",
            lo="LO 61.a",
            title="Credit exposure",
            excerpt="LO 61.a Credit exposure measures the amount at risk if a borrower defaults.",
            key_terms=[
                "credit exposure",
                "current exposure",
                "potential future exposure",
                "collateral",
                "netting agreements",
                "credit limits",
                "exposure profiles",
                "counterparty credit risk",
                "wrong-way risk",
                "stress testing",
            ],
        ),
        _concept(
            section,
            concept_id="concept-lo-61-b",
            lo="Learning Objective 61.b",
            title="Default probability and loss given default",
            excerpt="Learning Objective 61.b Default probability and loss given default are inputs in credit models.",
            key_terms=[
                "default probability",
                "loss given default",
                "recovery rate",
                "expected loss",
                "unexpected loss",
                "credit migration models",
                "rating transitions",
                "default intensity models",
                "credit spreads",
                "economic capital",
            ],
        ),
        _concept(
            section,
            concept_id="concept-lo-61-c",
            lo="L O 61 c",
            title="Concentration risk and default correlation",
            excerpt="L O 61 c Concentration risk and default correlation shape credit portfolio losses.",
            key_terms=[
                "concentration risk",
                "default correlation",
                "portfolio tail risk",
                "diversification benefits",
                "credit portfolio models",
                "granularity",
                "sector concentration",
                "geographic concentration",
                "name concentration",
                "economic capital",
            ],
        ),
        _concept(
            section,
            concept_id="concept-lo-61-d",
            lo="LO 61 d",
            title="Credit risk mitigation and portfolio monitoring",
            excerpt="LO 61 d Credit risk mitigation and portfolio monitoring reduce credit risk.",
            key_terms=[
                "credit risk mitigation",
                "collateral",
                "guarantees",
                "credit derivatives",
                "loan covenants",
                "portfolio monitoring",
                "early warning indicators",
                "limit monitoring",
                "hedging strategies",
                "risk reports",
            ],
        ),
    ]

    cards = service._ensure_learning_outcome_flashcard_coverage(section, concepts, [])
    counts = {lo: len([card for card in cards if card.lo_code == lo]) for lo in ("LO 61.a", "LO 61.b", "LO 61.c", "LO 61.d")}
    fronts_by_lo = {
        lo: {card.front for card in cards if card.lo_code == lo}
        for lo in counts
    }

    assert all(count >= 10 for count in counts.values())
    assert "What does credit exposure measure?" in fronts_by_lo["LO 61.a"]
    assert "What is the expected loss formula in credit risk?" in fronts_by_lo["LO 61.b"]
    assert "What does default correlation measure?" in fronts_by_lo["LO 61.c"]
    assert "What do credit portfolio models use?" in fronts_by_lo["LO 61.c"]
    assert "What does portfolio monitoring track?" in fronts_by_lo["LO 61.d"]
    assert not any(card.needs_more_source for card in cards)
    assert not any(service._flashcard_quality_flags(card) for card in cards)


def test_module_level_top_up_keeps_junk_anchors_out() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 9: Financial Markets and Products / "
            "Reading 38: Options Markets / "
            "Module 38.1: Option Types, Positions, and Underlying Assets"
        ),
        text="Options source text",
        page_number=138,
    )
    concepts = [
        _concept(
            section,
            concept_id="concept-good-option",
            lo="LO 38.b",
            title="Option margin requirements",
            excerpt=(
                "LO 38.b\n"
                "Margin requirements apply differently to option buyers and writers. "
                "Uncovered calls are written without owning the underlying asset. "
                "Covered calls are written on stock already owned by the option seller."
            ),
            key_terms=["margin requirements", "uncovered calls", "covered calls"],
        ),
        _concept(
            section,
            concept_id="concept-junk-option",
            lo="LO 38.b",
            title="Because option contracts",
            excerpt=(
                "LO 38.b\n"
                "Because option contracts. What are because option contracts? Also assume that there."
            ),
            key_terms=["because option contracts", "also assume that there"],
        ),
    ]

    cards = service._flashcards_from_original_book(section, OriginalBookContent(), concepts, [])
    fronts = [card.front for card in cards]

    assert "What are uncovered calls?" in fronts
    assert "What are covered calls?" in fronts
    assert not any("because option contracts" in front.lower() for front in fronts)
    assert not any(service._flashcard_quality_flags(card) for card in cards)


def test_formula_junk_entries_do_not_generate_formula_cards() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title="Formulas",
        text="FORMULAS\nIf EPS = $7.25, the significance level is 5%.",
        page_number=238,
    )
    junk_formulas = [
        StudyFormulaCard(
            formula_id="formula-if-eps",
            material_id=section.material_id,
            formula_name="If Eps",
            formula_text="If EPS = $7.25, calculate the confidence interval.",
            source_page=238,
            source_excerpt="If EPS = $7.25, calculate the confidence interval.",
        ),
        StudyFormulaCard(
            formula_id="formula-significance",
            material_id=section.material_id,
            formula_name="The Significance Level",
            formula_text="The significance level = 5%.",
            source_page=238,
            source_excerpt="The significance level = 5%.",
        ),
    ]

    cards = service._flashcards_from_original_book(section, OriginalBookContent(), [], junk_formulas)

    assert not any("If Eps" in card.front for card in cards)
    assert not any("Significance Level" in card.front for card in cards)


def test_formula_junk_entries_do_not_surface_as_study_formulas() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title="Formulas",
        text="FORMULAS\nIf EPS = $7.25, the significance level is 5%.\nPrice = Value + Accrued interest",
        page_number=238,
    )
    formulas = service._formula_cards_from_original_book(
        section,
        OriginalBookContent(),
        [],
        workbook_blocks={
            "formulas": [
                "If EPS = $7.25, calculate the confidence interval.",
                "The significance level = 5%.",
                "bond invoice price: invoice price = futures settlement price × conversion factor + accrued interest",
            ]
        },
    )

    names = [formula.formula_name for formula in formulas]

    assert "If Eps" not in names
    assert "The Significance Level" not in names
    assert any("invoice price" in (formula.formula_text or "").lower() for formula in formulas)


def test_options_margin_terms_generate_clean_cards() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 10: Financial Markets and Products / "
            "Reading 38: Options Markets / "
            "Module 38.1: Option Types, Positions, and Underlying Assets"
        ),
        text="Options margin source text",
        page_number=138,
    )
    concept = StudyConceptCard(
        concept_id="concept-options-margin",
        material_id=section.material_id,
        module_id=section.module_id,
        title="Option margin requirements",
        learning_outcome="LO 38.b",
        related_original_key_concept_id="lo-38-b",
        source_pages=[138],
        source_excerpt=(
            "LO 38.b\n"
            "Margin requirements apply differently to option buyers and writers. Options with "
            "maturities of nine months or fewer cannot be purchased on margin because leverage "
            "would become too high. Investors who write options must have a margin account due "
            "to high potential losses and potential default. Uncovered calls are written without "
            "owning the underlying asset, while covered calls are written on stock already owned "
            "by the option seller and therefore require no margin."
        ),
        simplified_explanation="Option margin rules differ for buyers, writers, uncovered calls, and covered calls.",
        key_terms=[
            "margin requirements",
            "option buyers",
            "option writers",
            "uncovered calls",
            "covered calls",
        ],
        formulas=[],
        exam_focus="Explain margin requirements for option positions.",
        common_traps=[],
    )

    cards = service._content_specific_flashcards_for_concept(section, concept)
    fronts = {card.front for card in cards}

    assert len(cards) >= 8
    assert "Why are short-maturity options generally not purchased on margin?" in fronts
    assert "How do covered calls differ from uncovered calls?" in fronts
    assert not any(service._flashcard_quality_flags(card) for card in cards)


def test_module_top_up_generates_ten_cards_from_valid_lo_anchors() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 4: Quantitative Analysis / "
            "Reading 12: Probability Distributions / "
            "Module 12.1: Discrete Random Variables"
        ),
        text=(
            "KEY CONCEPTS\n"
            "LO 12.a\n"
            "A Bernoulli random variable has one trial with success probability p.\n"
            "A binomial random variable counts the number of successes in a fixed number of independent trials.\n"
            "The expected value of a binomial random variable is np.\n"
            "The variance of a binomial random variable is np(1-p).\n"
            "The binomial distribution is used when trials are independent and each trial has the same probability of success.\n"
            "An event is a set of possible outcomes.\n"
            "Mutually exclusive events cannot occur together.\n"
            "Independent events do not change each other's probabilities."
        ),
        page_number=50,
    )

    study_section = service._build_study_section(section, display_order=1, parent_group_id=None, previous=None)
    fronts = {card.front for card in study_section.flashcards}

    assert len(study_section.flashcards) >= 10
    assert "What is a Bernoulli random variable?" in fronts
    assert "What does a binomial random variable count?" in fronts
    assert "What is the expected value of a binomial random variable?" in fronts
    assert "What is the variance of a binomial random variable?" in fronts
    assert "When is the binomial distribution used?" in fronts
    assert not any(service._flashcard_quality_flags(card) for card in study_section.flashcards)


def test_distribution_source_top_up_generates_ten_specific_cards() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 4: Quantitative Analysis / "
            "Reading 14: Common Probability Distributions / "
            "Module 14.1: Discrete and Continuous Distributions"
        ),
        text="Distribution source text",
        page_number=63,
    )
    concept = StudyConceptCard(
        concept_id="concept-distributions",
        material_id=section.material_id,
        module_id=section.module_id,
        title="Probability distributions",
        learning_outcome="LO 14.a",
        related_original_key_concept_id="lo-14-a",
        source_pages=[63],
        source_excerpt=(
            "LO 14.a\n"
            "A uniform distribution gives equal probability to all outcomes in a range. "
            "A Bernoulli trial has two possible outcomes: success and failure. "
            "A binomial distribution models the number of successes in a fixed number of independent Bernoulli trials. "
            "A Poisson distribution models the number of events occurring over an interval. "
            "The standard normal distribution has mean 0 and variance 1. "
            "The cumulative distribution function gives the probability that a random variable is less than or equal to a value."
        ),
        simplified_explanation="Common probability distributions model different random-variable behavior.",
        key_terms=[
            "uniform distribution",
            "Bernoulli trial",
            "binomial distribution",
            "Poisson distribution",
            "standard normal distribution",
            "cumulative distribution function",
        ],
        formulas=[],
    )

    cards = service._content_specific_flashcards_for_concept(section, concept)
    fronts = {card.front for card in cards}

    assert len(cards) >= 10
    assert "What is a uniform distribution?" in fronts
    assert "What are the two outcomes of a Bernoulli trial?" in fronts
    assert "What does a binomial distribution model?" in fronts
    assert "What does a Poisson distribution model?" in fronts
    assert "What are the mean and variance of the standard normal distribution?" in fronts
    assert "What does the cumulative distribution function give?" in fronts
    assert not any(service._flashcard_quality_flags(card) for card in cards)


def test_var_approach_source_top_up_generates_ten_specific_cards() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 14: Valuation and Risk Models / "
            "Reading 49: Value-at-Risk Models / "
            "Module 49.2: VaR Methods"
        ),
        text="VaR method source text",
        page_number=109,
    )
    concept = StudyConceptCard(
        concept_id="concept-var-methods",
        material_id=section.material_id,
        module_id=section.module_id,
        title="VaR methods",
        learning_outcome="LO 49.b",
        related_original_key_concept_id="lo-49-b",
        source_pages=[109],
        source_excerpt=(
            "LO 49.b\n"
            "Historical-based VaR approaches fall into two subcategories: parametric and nonparametric. "
            "A parametric approach typically assumes asset returns follow a normal or lognormal distribution. "
            "A nonparametric approach is less restrictive because it uses observed historical returns. "
            "Historical simulation estimates VaR directly from past return data. "
            "Implied volatility uses option prices to infer market expectations about future volatility. "
            "Filtered historical simulation combines historical returns with volatility scaling."
        ),
        simplified_explanation="VaR approaches differ by distribution assumptions and data source.",
        key_terms=[
            "historical-based VaR approaches",
            "parametric approach",
            "nonparametric approach",
            "historical simulation",
            "implied volatility",
            "filtered historical simulation",
        ],
        formulas=[],
    )

    cards = service._content_specific_flashcards_for_concept(section, concept)
    fronts = {card.front for card in cards}

    assert len(cards) >= 10
    assert "What are the two subcategories of historical-based VaR approaches?" in fronts
    assert "What does a parametric VaR approach typically assume?" in fronts
    assert "Why is a nonparametric VaR approach less restrictive?" in fronts
    assert "How does historical simulation estimate VaR?" in fronts
    assert "What does implied volatility infer from option prices?" in fronts
    assert not any(service._flashcard_quality_flags(card) for card in cards)


def test_yield_curve_shape_source_top_up_generates_ten_specific_cards() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 16: Valuation and Risk Models / "
            "Reading 56: Interest Rate Risk / "
            "Module 56.3: Yield Curve Shapes"
        ),
        text="Yield curve source text",
        page_number=197,
    )
    concept = StudyConceptCard(
        concept_id="concept-yield-curve-shapes",
        material_id=section.material_id,
        module_id=section.module_id,
        title="Yield curve shapes",
        learning_outcome="LO 56.c",
        related_original_key_concept_id="lo-56-c",
        source_pages=[197],
        source_excerpt=(
            "LO 56.c\n"
            "A normal yield curve is upward sloping because longer maturities have higher yields. "
            "A flat yield curve means short-term and long-term yields are similar. "
            "An inverted yield curve is downward sloping because short-term yields exceed long-term yields. "
            "A positive butterfly means the yield curve becomes more curved. "
            "A negative butterfly means the yield curve becomes less curved. "
            "A twist changes the slope of the yield curve."
        ),
        simplified_explanation="Yield curve shapes describe level, slope, and curvature changes.",
        key_terms=[
            "normal yield curve",
            "flat yield curve",
            "inverted yield curve",
            "positive butterfly",
            "negative butterfly",
            "twist",
        ],
        formulas=[],
    )

    cards = service._content_specific_flashcards_for_concept(section, concept)
    fronts = {card.front for card in cards}

    assert len(cards) >= 10
    assert "What is a normal yield curve?" in fronts
    assert "What does a flat yield curve mean?" in fronts
    assert "What is an inverted yield curve?" in fronts
    assert "What does a positive butterfly indicate for the yield curve?" in fronts
    assert "What does a twist change in the yield curve?" in fronts
    assert not any(service._flashcard_quality_flags(card) for card in cards)


def test_hypothesis_testing_lo_top_up_generates_steps_and_multiple_testing_cards() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 4: Quantitative Analysis / "
            "Reading 17: Hypothesis Testing / "
            "Module 17.2: Hypothesis Testing Results"
        ),
        text="Hypothesis testing source text",
        page_number=64,
    )
    concept = StudyConceptCard(
        concept_id="concept-hypothesis-testing-results",
        material_id=section.material_id,
        module_id=section.module_id,
        title="Hypothesis testing results",
        learning_outcome="LO 17.h",
        related_original_key_concept_id="lo-17-h",
        source_pages=[64],
        source_excerpt=(
            "LO 17.h Explain the problem of multiple testing and how it can bias hypothesis test results. "
            "Multiple testing means testing multiple different hypotheses on the same data set. "
            "As the number of tests increases, the probability of at least one Type I error increases. "
            "Step 1: State the null and alternative hypotheses. "
            "Step 2: Choose the test statistic and significance level. "
            "Step 3: Calculate the test statistic and p-value. "
            "Step 4: Reject or fail to reject the null hypothesis."
        ),
        simplified_explanation="Multiple testing can increase false positives in hypothesis tests.",
        key_terms=["multiple testing", "Type I error", "p-value", "test statistic"],
        formulas=[],
        exam_focus="Interpret hypothesis testing results.",
        common_traps=[],
    )

    cards = service._content_specific_flashcards_for_concept(section, concept)
    fronts = {card.front for card in cards}

    assert len(cards) >= 10
    assert "What is the problem of multiple testing?" in fronts
    assert "How does multiple testing affect Type I error probability?" in fronts
    assert "What are the steps in a hypothesis test?" in fronts
    assert not any(service._flashcard_quality_flags(card) for card in cards)


def test_bsm_and_delta_hedging_lo_top_up_generates_ten_specific_cards() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 15: Valuation and Risk Models / "
            "Reading 62: Option Sensitivities / "
            "Module 62.2: Delta Hedging"
        ),
        text="Delta hedging source text",
        page_number=248,
    )
    concept = StudyConceptCard(
        concept_id="concept-delta-hedging",
        material_id=section.material_id,
        module_id=section.module_id,
        title="Delta hedging",
        learning_outcome="LO 62.b",
        related_original_key_concept_id="lo-62-b",
        source_pages=[248],
        source_excerpt=(
            "LO 62.b Explain delta hedging and interpret option delta. "
            "The Black-Scholes-Merton model assumes that stock prices are lognormally distributed. "
            "The continuously compounded realized return is normally distributed. "
            "Historical volatility is estimated from realized returns and annualized using the square root of the number of trading days. "
            "The delta of an option is the ratio of the change in option value to the change in the value of the underlying asset. "
            "Delta hedging creates a delta-neutral portfolio by combining an option position with shares of the underlying asset. "
            "A delta-neutral hedge must be rebalanced as the option delta changes."
        ),
        simplified_explanation="Delta hedging offsets option price sensitivity to the underlying asset.",
        key_terms=[
            "Black-Scholes-Merton model",
            "lognormal distribution",
            "realized return",
            "historical volatility",
            "option delta",
            "delta hedging",
            "delta-neutral portfolio",
        ],
        formulas=[],
        exam_focus="Interpret option delta and delta hedging.",
        common_traps=[],
    )

    cards = service._content_specific_flashcards_for_concept(section, concept)
    fronts = {card.front for card in cards}

    assert len(cards) >= 10
    assert "What does the Black-Scholes-Merton model assume about stock prices?" in fronts
    assert "What is option delta?" in fronts
    assert "What is delta hedging?" in fronts
    assert "Why must a delta-neutral hedge be rebalanced?" in fronts
    assert not any(service._flashcard_quality_flags(card) for card in cards)


def test_probability_relationships_top_up_generates_ten_specific_cards() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 4: Quantitative Analysis / "
            "Reading 12: Probability / "
            "Module 12.2: Conditional, Unconditional, and Joint Probabilities"
        ),
        text="Probability source text",
        page_number=41,
    )
    concept = StudyConceptCard(
        concept_id="concept-probability-relationships",
        material_id=section.material_id,
        module_id=section.module_id,
        title="Probability relationships",
        learning_outcome="LO 12.b",
        related_original_key_concept_id="lo-12-b",
        source_pages=[41],
        source_excerpt=(
            "LO 12.b Distinguish between independent events and mutually exclusive events. "
            "The event space is the set of all possible outcomes. A random event is a subset of the event space. "
            "Conditional probability measures the probability of event A given event B. "
            "Two events A and B are independent if P(A ∩ B) = P(A)P(B), equivalently P(A|B) = P(A). "
            "Two events are mutually exclusive if they cannot occur together, so P(A ∩ B) = 0. "
            "Mutual exclusivity usually implies dependence when both events have positive probability."
        ),
        simplified_explanation="Probability relationships define event spaces, independence, and mutual exclusivity.",
        key_terms=[
            "event space",
            "random event",
            "conditional probability",
            "independent events",
            "mutually exclusive events",
        ],
        formulas=[],
        exam_focus="Distinguish probability relationships.",
        common_traps=[],
    )

    cards = service._content_specific_flashcards_for_concept(section, concept)
    fronts = {card.front for card in cards}

    assert len(cards) >= 10
    assert "What is the event space in probability?" in fronts
    assert "What is a random event?" in fronts
    assert "What condition defines independence between events A and B?" in fronts
    assert "What condition defines mutually exclusive events?" in fronts
    assert "How do independent events differ from mutually exclusive events?" in fronts
    assert not any(service._flashcard_quality_flags(card) for card in cards)


def test_bivariate_iid_top_up_generates_ten_specific_cards() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 4: Quantitative Analysis / "
            "Reading 15: Bivariate Distributions / "
            "Module 15.4: Independent and Identically Distributed Random Variables"
        ),
        text="Bivariate distribution source text",
        page_number=55,
    )
    concept = StudyConceptCard(
        concept_id="concept-bivariate-iid",
        material_id=section.material_id,
        module_id=section.module_id,
        title="Bivariate distributions and IID random variables",
        learning_outcome="LO 15.d",
        related_original_key_concept_id="lo-15-d",
        source_pages=[55],
        source_excerpt=(
            "LO 15.d Explain marginal distributions, conditional distributions, covariance, correlation, and independent and identically distributed random variables. "
            "A probability matrix displays the joint probability distribution for two random variables. "
            "A marginal distribution gives the probability distribution of one random variable. "
            "A conditional distribution gives the distribution of one variable given the value of another variable. "
            "Covariance measures how two random variables move together. "
            "The correlation coefficient standardizes covariance and ranges from -1 to +1. "
            "Independent and identically distributed random variables have the same distribution and are mutually independent. "
            "For IID variables, the expected value of the sum is n times the mean and the variance of the sum is n times the variance."
        ),
        simplified_explanation="Bivariate distributions describe relationships between two random variables.",
        key_terms=[
            "probability matrix",
            "marginal distribution",
            "conditional distribution",
            "covariance",
            "correlation coefficient",
            "independent and identically distributed random variables",
        ],
        formulas=[],
        exam_focus="Interpret bivariate distribution measures.",
        common_traps=[],
    )

    cards = service._content_specific_flashcards_for_concept(section, concept)
    fronts = {card.front for card in cards}

    assert len(cards) >= 10
    assert "What does a probability matrix display?" in fronts
    assert "What is a marginal distribution?" in fronts
    assert "What is a conditional distribution?" in fronts
    assert "What does covariance measure?" in fronts
    assert "What does it mean for random variables to be independent and identically distributed?" in fronts
    assert not any(service._flashcard_quality_flags(card) for card in cards)


def test_regression_time_series_top_up_generates_ten_specific_cards() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 5: Quantitative Analysis / "
            "Reading 21: Time-Series Analysis / "
            "Module 21.1: Covariance Stationary"
        ),
        text="Regression and time-series source text",
        page_number=144,
    )
    concept = StudyConceptCard(
        concept_id="concept-regression-time-series",
        material_id=section.material_id,
        module_id=section.module_id,
        title="Regression and covariance stationary time series",
        learning_outcome="LO 21.a",
        related_original_key_concept_id="lo-21-a",
        source_pages=[144],
        source_excerpt=(
            "LO 21.a Explain regression analysis and covariance stationary time series. "
            "Regression analysis models the relationship between a dependent variable and one or more independent variables. "
            "A regression coefficient measures the change in the dependent variable for a one-unit change in an independent variable. "
            "A residual is the difference between the observed value and the fitted value. "
            "R-squared measures the proportion of variation in the dependent variable explained by the regression. "
            "A covariance stationary time series has a constant mean, constant variance, and autocovariances that depend only on lag. "
            "Autocorrelation measures correlation between observations of a time series at different lags. "
            "An autoregressive model uses lagged values of the dependent variable. A moving average model uses lagged error terms. "
            "A unit root indicates nonstationarity, while seasonality is a repeating pattern over calendar periods."
        ),
        simplified_explanation="Regression and time-series models explain relationships and serial dependence.",
        key_terms=[
            "regression analysis",
            "dependent variable",
            "independent variable",
            "regression coefficient",
            "residual",
            "R-squared",
            "covariance stationary time series",
            "autocorrelation",
            "autoregressive model",
            "moving average model",
            "unit root",
            "seasonality",
        ],
        formulas=[],
        exam_focus="Interpret regression and time-series concepts.",
        common_traps=[],
    )

    cards = service._content_specific_flashcards_for_concept(section, concept)
    fronts = {card.front for card in cards}

    assert len(cards) >= 10
    assert "What does regression analysis model?" in fronts
    assert "What does a regression coefficient measure?" in fronts
    assert "What is a residual in regression analysis?" in fronts
    assert "What are the conditions for covariance stationarity?" in fronts
    assert "How does an autoregressive model differ from a moving average model?" in fronts
    assert not any(service._flashcard_quality_flags(card) for card in cards)


def test_risk_measure_and_operational_loss_top_up_generates_ten_specific_cards() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 13: Valuation and Risk Models / "
            "Reading 53: Operational Risk / "
            "Module 53.2: Standardized Measurement Approach and Loss Distribution"
        ),
        text="Risk measure and operational loss source text",
        page_number=214,
    )
    concept = StudyConceptCard(
        concept_id="concept-risk-measures-operational-loss",
        material_id=section.material_id,
        module_id=section.module_id,
        title="Coherent risk measures and operational loss distributions",
        learning_outcome="LO 53.b",
        related_original_key_concept_id="lo-53-b",
        source_pages=[214],
        source_excerpt=(
            "LO 53.b Explain coherent risk measures, expected shortfall, and operational loss distributions. "
            "A coherent risk measure satisfies monotonicity, subadditivity, positive homogeneity, and translational invariance. "
            "Expected shortfall measures the average loss conditional on losses exceeding the VaR threshold. "
            "VaR is not coherent because it can violate subadditivity. "
            "Operational loss modeling separates loss frequency from loss severity. "
            "Loss frequency is often modeled with a Poisson distribution, while loss severity is often modeled with a lognormal distribution. "
            "Monte Carlo simulation can combine frequency and severity to estimate the loss distribution."
        ),
        simplified_explanation="Coherent risk and operational loss models describe tail risk and loss distributions.",
        key_terms=[
            "coherent risk measure",
            "expected shortfall",
            "VaR",
            "subadditivity",
            "loss frequency",
            "loss severity",
            "Poisson distribution",
            "lognormal distribution",
            "Monte Carlo simulation",
        ],
        formulas=[],
        exam_focus="Apply coherent risk and operational loss concepts.",
        common_traps=[],
    )

    cards = service._content_specific_flashcards_for_concept(section, concept)
    fronts = {card.front for card in cards}

    assert len(cards) >= 10
    assert "What properties must a coherent risk measure satisfy?" in fronts
    assert "What does expected shortfall measure?" in fronts
    assert "Why is VaR not always a coherent risk measure?" in fronts
    assert "How does loss frequency differ from loss severity?" in fronts
    assert "How can Monte Carlo simulation be used in operational loss modeling?" in fronts
    assert not any(service._flashcard_quality_flags(card) for card in cards)


def test_conditional_probability_bayes_top_up_generates_ten_specific_cards() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 4: Quantitative Analysis / "
            "Reading 12: Probability / "
            "Module 12.2: Conditional, Unconditional, and Joint Probabilities"
        ),
        text="Conditional probability and Bayes source text",
        page_number=41,
    )
    concept = StudyConceptCard(
        concept_id="concept-bayes-probability",
        material_id=section.material_id,
        module_id=section.module_id,
        title="Conditional probability and Bayes' rule",
        learning_outcome="LO 12.g",
        related_original_key_concept_id="lo-12-g",
        source_pages=[41],
        source_excerpt=(
            "LO 12.g Explain conditional probability, unconditional probability, mutually exclusive events, "
            "collectively exhaustive events, discrete probability functions, and Bayes' rule. "
            "A discrete probability function gives the probability of each possible outcome. "
            "Conditional probability measures the probability of event A given event B. "
            "Unconditional probability is the probability of an event without conditioning on another event. "
            "Events are mutually exclusive if they cannot occur together. "
            "Events are collectively exhaustive if they cover all possible outcomes. "
            "Bayes' rule uses prior probabilities and new information to update probabilities. "
            "Bayes' rule follows from P(A|B)P(B) = P(B|A)P(A)."
        ),
        simplified_explanation="Conditional probability and Bayes' rule update probabilities using event information.",
        key_terms=[
            "discrete probability function",
            "conditional probability",
            "unconditional probability",
            "mutually exclusive events",
            "collectively exhaustive events",
            "Bayes' rule",
        ],
        formulas=[],
        exam_focus="Apply probability relationships and Bayes' rule.",
        common_traps=[],
    )

    cards = service._content_specific_flashcards_for_concept(section, concept)
    fronts = {card.front for card in cards}

    assert len(cards) >= 10
    assert "What is a discrete probability function?" in fronts
    assert "What does conditional probability measure?" in fronts
    assert "How does conditional probability differ from unconditional probability?" in fronts
    assert "What does it mean for events to be collectively exhaustive?" in fronts
    assert "What does Bayes' rule allow you to update?" in fronts
    assert "What relationship leads to Bayes' rule?" in fronts
    assert not any(service._flashcard_quality_flags(card) for card in cards)


def test_pmf_cdf_expected_value_top_up_generates_ten_specific_cards() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 4: Quantitative Analysis / "
            "Reading 13: Common Probability Distributions / "
            "Module 13.1: Probability Mass Functions and Cumulative Distribution Functions"
        ),
        text="PMF CDF expected value source text",
        page_number=48,
    )
    concept = StudyConceptCard(
        concept_id="concept-pmf-cdf-expected-value",
        material_id=section.material_id,
        module_id=section.module_id,
        title="PMF, CDF, and expected value",
        learning_outcome="LO 13.a",
        related_original_key_concept_id="lo-13-a",
        source_pages=[48],
        source_excerpt=(
            "LO 13.a Distinguish between discrete and continuous random variables, probability mass functions, "
            "cumulative distribution functions, Bernoulli random variables, and expected value. "
            "A discrete random variable has countable possible outcomes. "
            "A probability mass function (PMF) gives the probability of each value of a discrete random variable. "
            "A cumulative distribution function (CDF) gives the probability that a random variable is less than or equal to a value. "
            "A Bernoulli random variable takes the value 1 for success and 0 for failure. "
            "A continuous random variable can take any value in an interval. "
            "The expected value is the probability-weighted average of possible outcomes. "
            "The expectations operator indicates the expected value of a random variable."
        ),
        simplified_explanation="PMFs, CDFs, and expected value describe probability distributions.",
        key_terms=[
            "discrete random variable",
            "probability mass function",
            "cumulative distribution function",
            "Bernoulli random variable",
            "continuous random variable",
            "expected value",
            "expectations operator",
        ],
        formulas=[],
        exam_focus="Interpret probability distribution functions and expected values.",
        common_traps=[],
    )

    cards = service._content_specific_flashcards_for_concept(section, concept)
    fronts = {card.front for card in cards}

    assert len(cards) >= 10
    assert "What is a discrete random variable?" in fronts
    assert "What does a probability mass function (PMF) give?" in fronts
    assert "How does a probability mass function differ from a cumulative distribution function?" in fronts
    assert "What is a Bernoulli random variable?" in fronts
    assert "What is the expected value of a random variable?" in fronts
    assert not any(service._flashcard_quality_flags(card) for card in cards)


def test_multiple_regression_assumptions_top_up_generates_ten_specific_cards() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 5: Quantitative Analysis / "
            "Reading 19: Multiple Regression / "
            "Module 19.1: Multiple Regression"
        ),
        text="Multiple regression source text",
        page_number=119,
    )
    concept = StudyConceptCard(
        concept_id="concept-multiple-regression",
        material_id=section.material_id,
        module_id=section.module_id,
        title="Multiple regression",
        learning_outcome="LO 19.a",
        related_original_key_concept_id="lo-19-a",
        source_pages=[119],
        source_excerpt=(
            "LO 19.a Explain multiple regression assumptions, coefficients, and model fit. "
            "Multiple regression models one dependent variable using two or more explanatory variables. "
            "A partial slope coefficient measures the effect of one independent variable while holding other independent variables constant. "
            "Ordinary least squares minimizes the sum of squared residuals. "
            "Homoskedasticity means the error variance is constant. "
            "Multicollinearity occurs when independent variables are highly correlated. "
            "Outliers can distort coefficient estimates. "
            "Adjusted R-squared penalizes adding variables that do not improve model fit."
        ),
        simplified_explanation="Multiple regression explains one dependent variable with several explanatory variables.",
        key_terms=[
            "multiple regression",
            "explanatory variables",
            "partial slope coefficient",
            "ordinary least squares",
            "homoskedasticity",
            "multicollinearity",
            "outliers",
            "adjusted R-squared",
        ],
        formulas=[],
        exam_focus="Interpret multiple regression coefficients and assumptions.",
        common_traps=[],
    )

    cards = service._content_specific_flashcards_for_concept(section, concept)
    fronts = {card.front for card in cards}

    assert len(cards) >= 10
    assert "What is multiple regression?" in fronts
    assert "What does a partial slope coefficient measure?" in fronts
    assert "What does ordinary least squares minimize?" in fronts
    assert "What is multicollinearity?" in fronts
    assert "Why do outliers matter in multiple regression?" in fronts
    assert not any(service._flashcard_quality_flags(card) for card in cards)


def test_pca_kmeans_top_up_generates_ten_specific_cards() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 7: Quantitative Analysis / "
            "Reading 25: Machine Learning Methods / "
            "Module 25.2: Principal Components Analysis and K-Means"
        ),
        text="PCA and K-means source text",
        page_number=181,
    )
    concept = StudyConceptCard(
        concept_id="concept-pca-kmeans",
        material_id=section.material_id,
        module_id=section.module_id,
        title="Principal components analysis and K-means clustering",
        learning_outcome="LO 25.b",
        related_original_key_concept_id="lo-25-b",
        source_pages=[181],
        source_excerpt=(
            "LO 25.b Explain principal components analysis and K-means clustering. "
            "Principal components analysis (PCA) reduces dimensionality by transforming correlated variables into uncorrelated principal components. "
            "In yield curve applications, the first principal component often represents a parallel shift and the second component often represents a twist. "
            "K-means clustering partitions data into K clusters. "
            "A cluster center is the mean location of the observations assigned to that cluster. "
            "The algorithm updates cluster assignments and cluster centers until fit stops improving. "
            "Inertia measures within-cluster variation and is used to assess model fit."
        ),
        simplified_explanation="PCA reduces dimensions and K-means clusters observations.",
        key_terms=[
            "principal components analysis",
            "principal components",
            "parallel shift",
            "twist",
            "K-means clustering",
            "cluster center",
            "inertia",
        ],
        formulas=[],
        exam_focus="Interpret PCA and K-means outputs.",
        common_traps=[],
    )

    cards = service._content_specific_flashcards_for_concept(section, concept)
    fronts = {card.front for card in cards}

    assert len(cards) >= 10
    assert "What is the goal of principal components analysis (PCA)?" in fronts
    assert "How does PCA reduce dimensionality?" in fronts
    assert "How does a parallel shift differ from a twist in yield-curve PCA?" in fronts
    assert "What does K represent in K-means clustering?" in fronts
    assert "What does inertia measure in K-means clustering?" in fronts
    assert not any(service._flashcard_quality_flags(card) for card in cards)


def test_operational_loss_only_top_up_generates_ten_specific_cards() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 13: Valuation and Risk Models / "
            "Reading 53: Operational Risk / "
            "Module 53.2: Standardized Measurement Approach and Loss Distribution"
        ),
        text="Operational loss source text",
        page_number=214,
    )
    concept = StudyConceptCard(
        concept_id="concept-operational-loss-frequency-severity",
        material_id=section.material_id,
        module_id=section.module_id,
        title="Operational loss frequency and severity",
        learning_outcome="LO 53.d",
        related_original_key_concept_id="lo-53-d",
        source_pages=[214],
        source_excerpt=(
            "LO 53.d Explain operational loss modeling. "
            "Operational loss modeling separates loss frequency from loss severity. "
            "Loss frequency is the number of losses over a time period. "
            "Loss severity is the size of a loss. "
            "Loss frequency is often modeled with a Poisson distribution. "
            "Loss severity is often modeled with a lognormal distribution. "
            "Monte Carlo simulation can combine frequency and severity to estimate an operational loss distribution."
        ),
        simplified_explanation="Operational loss models combine loss frequency and severity.",
        key_terms=[
            "operational loss modeling",
            "loss frequency",
            "loss severity",
            "Poisson distribution",
            "lognormal distribution",
            "Monte Carlo simulation",
        ],
        formulas=[],
        exam_focus="Apply operational loss frequency and severity.",
        common_traps=[],
    )

    cards = service._content_specific_flashcards_for_concept(section, concept)
    fronts = {card.front for card in cards}

    assert len(cards) >= 10
    assert "What two components does operational loss modeling separate?" in fronts
    assert "What is loss frequency?" in fronts
    assert "What is loss severity?" in fronts
    assert "Why is loss frequency modeled separately from loss severity?" in fronts
    assert "What is a common exam trap about operational loss frequency and severity?" in fronts
    assert not any(service._flashcard_quality_flags(card) for card in cards)


def test_bsm_stock_price_distribution_top_up_generates_ten_specific_cards() -> None:
    service = SectionStudyService(store=None)  # type: ignore[arg-type]
    section = _section(
        title=(
            "Study Session 15: Valuation and Risk Models / "
            "Reading 61: Black-Scholes-Merton / "
            "Module 61.1: Stock Price and Return Distributions"
        ),
        text="BSM stock price distribution source text",
        page_number=198,
    )
    concept = StudyConceptCard(
        concept_id="concept-bsm-stock-price-distribution",
        material_id=section.material_id,
        module_id=section.module_id,
        title="Black-Scholes-Merton stock price and return distributions",
        learning_outcome="LO 61.a",
        related_original_key_concept_id="lo-61-a",
        source_pages=[198],
        source_excerpt=(
            "LO 61.a Explain the Black-Scholes-Merton assumptions about stock price and return distributions. "
            "The Black-Scholes-Merton model assumes that stock prices are lognormally distributed. "
            "The natural logarithm of the stock price at expiration is normally distributed. "
            "Continuously compounded realized returns are normally distributed. "
            "Historical volatility is estimated from realized returns and annualized using the square root of the number of trading days. "
            "Ex-dividend stock price changes should be removed when estimating volatility."
        ),
        simplified_explanation="BSM assumes lognormal stock prices and normally distributed continuously compounded returns.",
        key_terms=[
            "Black-Scholes-Merton model",
            "lognormal stock prices",
            "normally distributed returns",
            "realized return",
            "historical volatility",
            "annualized volatility",
        ],
        formulas=[],
        exam_focus="Interpret BSM distribution assumptions and volatility estimates.",
        common_traps=[],
    )

    cards = service._content_specific_flashcards_for_concept(section, concept)
    fronts = {card.front for card in cards}

    assert len(cards) >= 10
    assert "What does the Black-Scholes-Merton model assume about stock prices?" in fronts
    assert "How are continuously compounded realized returns distributed in the Black-Scholes-Merton setting?" in fronts
    assert "How is historical volatility estimated?" in fronts
    assert "Why is historical volatility annualized?" in fronts
    assert "What is a common exam trap about Black-Scholes-Merton stock-price and return distributions?" in fronts
    assert not any(service._flashcard_quality_flags(card) for card in cards)


def _value_at_risk_section_and_concept() -> tuple[SourceSection, StudyConceptCard]:
    section = _section(
        title=(
            "Study Session 2: Quantitative Analysis / "
            "Reading 7: Risk Measures / "
            "Module 7.1: Value at Risk"
        ),
        text="Value at risk source text",
        page_number=101,
    )
    source_excerpt = (
        "LO 7.a\n"
        "Value at risk (VaR) estimates the loss amount that may be exceeded with a specified "
        "probability over a defined time horizon. A one-day VaR of $2.5 million at the 95% "
        "confidence level means there is a 5% chance the one-day loss will exceed $2.5 million. "
        "VaR does not show loss severity beyond the threshold and depends on distribution and liquidity assumptions."
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
        key_terms=["Value at risk (VaR)", "confidence level"],
        formulas=[],
        exam_focus="Interpret VaR.",
        common_traps=["Do not treat VaR as the maximum possible loss."],
    )
    return section, concept


def _section(*, title: str, text: str, page_number: int) -> SourceSection:
    return SourceSection(
        source_id="source-part6",
        material_id="mat-part6",
        course_id="course-frm",
        file_name="frm-book.pdf",
        content_type="application/pdf",
        section_title=title,
        text=text,
        page_end=page_number,
        locator=SourceLocator(section_index=1, page_number=page_number),
        citation_label=f"frm-book.pdf page {page_number}",
    )


def _concept(
    section: SourceSection,
    *,
    concept_id: str,
    lo: str,
    title: str,
    excerpt: str,
    key_terms: list[str],
) -> StudyConceptCard:
    return StudyConceptCard(
        concept_id=concept_id,
        material_id=section.material_id,
        module_id=section.module_id,
        title=title,
        learning_outcome=lo,
        related_original_key_concept_id=f"{lo.lower().replace(' ', '-')}-anchor",
        source_pages=[section.locator.page_number],
        source_excerpt=excerpt,
        simplified_explanation=title,
        key_terms=key_terms,
        formulas=[],
        exam_focus=title,
        common_traps=[],
    )


def _flashcard(
    *,
    front: str,
    back: str = "Value at risk estimates a threshold loss.",
) -> StudyFlashcard:
    return StudyFlashcard(
        flashcard_id=f"card-{abs(hash((front, back))) % 100000}",
        material_id="mat-part6",
        learning_outcome_id="lo-7-a",
        concept_id="concept-var",
        front=front,
        back=back,
        back_concise=back,
        card_type="definition",
        source_page=101,
        source_excerpt="Value at risk (VaR) estimates the loss amount that may be exceeded.",
        source_text_snippet="Value at risk (VaR) estimates the loss amount that may be exceeded.",
        anchor_text="Value at risk (VaR)",
    )
