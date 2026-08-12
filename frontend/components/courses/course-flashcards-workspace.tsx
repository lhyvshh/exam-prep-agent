"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";

import { fetchCourseMaterials, fetchMaterialStudy, recordFlashcardReview } from "@/lib/api";
import { useCourseSelection } from "@/components/shared/course-context";
import { writeCourseResume } from "@/lib/course-resume";
import type { MaterialRecord, MaterialStudySection, StudyDifficulty, StudyFlashcard } from "@/lib/schemas";

type ReviewRating = "forgot" | "hard" | "good" | "easy";

type FlashcardItem = StudyFlashcard & {
  material: MaterialRecord;
  section: MaterialStudySection;
  sectionTitle: string;
};

type FlashcardOverride = Pick<
  StudyFlashcard,
  | "front"
  | "back"
  | "back_concise"
  | "card_type"
  | "source_page"
  | "source_excerpt"
  | "difficulty"
  | "learning_outcome_id"
  | "formula_id"
  | "confidence_group"
  | "interval_days"
  | "ease_factor"
  | "repetitions"
  | "due_at"
  | "last_reviewed_at"
  | "archived"
>;

type FlashcardEditorState = {
  mode: "create" | "edit";
  flashcardId?: string;
  front: string;
  back: string;
  cardType: string;
  difficulty: StudyDifficulty;
  sourcePage: string;
};

type HistoryMode = "push" | "replace";
type UpcomingStatusFilter = "all" | "due" | "new";

const RATING_LABELS: Record<ReviewRating, string> = {
  forgot: "Again",
  hard: "Hard",
  good: "Good",
  easy: "Easy"
};

const FLASHCARD_TYPE_OPTIONS = [
  { value: "all", label: "All card types" },
  { value: "definition", label: "Definition" },
  { value: "formula", label: "Formula" },
  { value: "list_recall", label: "List Recall" },
  { value: "comparison", label: "Comparison" },
  { value: "exam_trap", label: "Exam Trap" },
  { value: "calculation_step", label: "Calculation Step" },
  { value: "short_answer_recall", label: "Short Recall" }
];

const CONFIDENCE_OPTIONS = [
  { value: "all", label: "All confidence groups" },
  { value: "new", label: "New" },
  { value: "need_to_review", label: "Need to Review" },
  { value: "learning", label: "Learning" },
  { value: "confident", label: "Confident" }
];

const LOW_QUALITY_FLASHCARD_FRONT_RE = new RegExp(
  [
    "what exact rule",
    "what does this module say",
    "what is the key idea",
    "what does the book give here",
    "summarize this section",
    "what exam trap should you remember for",
    "what is event is",
    "what is of the",
    "what is all the",
    "what is and reward",
    "what is opportunities with lower",
    "what is risk have lower",
    "what is to the risk",
    "what are models",
    "what are quotes",
    "what are spot quotes",
    "what is so portfolio currency risk",
    "what is a less costly alternative",
    "what is answer because",
    "what is trading",
    "what is if a time series",
    "what is such a time series",
    "what are if the observations",
    "what is also assume",
    "what are assume",
    "what are assume that there",
    "what is also assume that the",
    "what is also",
    "what are because option contracts",
    "what are no payments",
    "what are no payment",
    "what is payment",
    "what is payments",
    "what are not all",
    "what are because",
    "what are if",
    "what are countries",
    "what is because",
    "what is if",
    "what is no ",
    "what do because",
    "what do if",
    "what is a special type of serially uncorrelated series",
    "methods include scenario relate to value risk economic capital ways",
    "^what\\s+(?:is|are|do)\\s+(?:because|if|when|where|while|although|suppose|given|some|payment|payments|countries|models|quotes|spot\\s+quotes|trading)\\b",
    "^what\\s+is\\s+(?:so\\s+portfolio\\s+currency\\s+risk|a\\s+less\\s+costly\\s+alternative|answer\\s+because)\\b",
    "^what\\s+(?:is|are)\\s+(?:also\\s+)?assume\\b",
    "^what\\s+(?:is|are)\\s+assume\\s+that\\s+there\\b",
    "^what\\s+(?:is|are)\\s+also\\s+assume\\s+that\\s+the\\b",
    "^what\\s+(?:is|are).*\\bassume\\s+that\\b",
    "^what\\s+(?:is|are)\\s+also\\b",
    "^what\\s+are\\s+no\\s+payments?\\b",
    "^what\\s+are\\s+because\\b",
    "^what\\s+is\\s+if\\b",
    "^what\\s+is\\s+payment\\b"
  ].join("|"),
  "i"
);

const LOW_QUALITY_BARE_DEFINITION_TERMS = new Set([
  "also",
  "assume",
  "because",
  "borrower",
  "contract",
  "correlation",
  "country",
  "coverage",
  "if",
  "model",
  "payment",
  "quote",
  "there",
  "trading"
]);

const STRONG_CONCEPT_ANCHOR_RE =
  /\b(?:apt|basis|beta|bond|borrower concentration|capm|capital|cml|convexity|correlation coefficient|credit|default|duration|ead|erm|expected loss|exposure|formula|futures|hedge|lgd|liquidity|loss|margin|market|model|option|portfolio|premium|rate|ratio|return|risk|sml|spread|var|volatility)\b/i;

export function CourseFlashcardsWorkspace({ courseId }: { courseId: string }): JSX.Element {
  const { selectedModuleId } = useCourseSelection();
  const searchParams = useSearchParams();
  const routeMaterialId = searchParams?.get("materialId") ?? "";
  const routeGroupId = searchParams?.get("groupId") ?? "";
  const routeSectionId = searchParams?.get("sectionId") ?? "";
  const routeLearningOutcomeId = searchParams?.get("learningOutcomeId") ?? "";
  const routeFormulaOnly = searchParams?.get("formula") === "1";
  const routeActiveCardId = searchParams?.get("cardId") ?? "";
  const [cards, setCards] = useState<FlashcardItem[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [currentIndex, setCurrentIndex] = useState<number>(0);
  const [isFlipped, setIsFlipped] = useState<boolean>(false);
  const [isSourceOpen, setIsSourceOpen] = useState<boolean>(false);
  const [isBrowseOpen, setIsBrowseOpen] = useState<boolean>(false);
  const [browseQuery, setBrowseQuery] = useState<string>("");
  const [browseCardType, setBrowseCardType] = useState<string>("all");
  const [browseConfidence, setBrowseConfidence] = useState<string>("all");
  const [browseModule, setBrowseModule] = useState<string>("all");
  const [browseLearningOutcome, setBrowseLearningOutcome] = useState<string>("all");
  const [browseSourcePage, setBrowseSourcePage] = useState<string>("all");
  const [browseFormulaOnly, setBrowseFormulaOnly] = useState<boolean>(false);
  const [upcomingStatusFilter, setUpcomingStatusFilter] = useState<UpcomingStatusFilter>("all");
  const [upcomingModuleFilter, setUpcomingModuleFilter] = useState<string>("all");
  const [upcomingLearningOutcomeFilter, setUpcomingLearningOutcomeFilter] = useState<string>("all");
  const [upcomingCardTypeFilter, setUpcomingCardTypeFilter] = useState<string>("all");
  const [editor, setEditor] = useState<FlashcardEditorState | null>(null);
  const [touchStartX, setTouchStartX] = useState<number | null>(null);

  useEffect(() => {
    void loadFlashcards();
  }, [
    courseId,
    selectedModuleId,
    routeActiveCardId,
    routeFormulaOnly,
    routeGroupId,
    routeLearningOutcomeId,
    routeMaterialId,
    routeSectionId
  ]);

  async function loadFlashcards(): Promise<void> {
    setIsLoading(true);
    try {
      const courseMaterials = await fetchCourseMaterials(courseId, selectedModuleId);
      const overrides = readStoredOverrides(courseId);
      const scopedMaterials = routeMaterialId
        ? courseMaterials.records.filter((record) => record.material_id === routeMaterialId)
        : courseMaterials.records;
      const loadedGroups = await Promise.all(
        scopedMaterials.map(async (record) => {
          const collected: FlashcardItem[] = [];
          let offset = 0;
          let hasMore = true;
          while (hasMore) {
            const study = await fetchMaterialStudy(record.material_id, {
              groupId: routeGroupId || null,
              offset,
              limit: 60
            });
            study.sections.forEach((section) => {
              if (!sectionMatchesRoute(section, { routeGroupId, routeSectionId })) {
                return;
              }
              (section.flashcards ?? []).forEach((flashcard) => {
                if (!flashcardMatchesRoute(flashcard, { routeFormulaOnly, routeLearningOutcomeId })) {
                  return;
                }
                const override = overrides[flashcard.flashcard_id];
                const merged = { ...flashcard, ...override };
                if (merged.archived) {
                  return;
                }
                collected.push({
                  ...merged,
                  material: study.record,
                  section,
                  sectionTitle: section.normalized_title || section.title
                });
              });
            });
            hasMore = study.has_more;
            offset += study.limit;
          }
          return collected;
        })
      );
      const loadedCards = loadedGroups.flat();
      const template = loadedCards[0] ?? null;
      const customCards = template
        ? readStoredCustomCards(courseId)
            .filter((card) => !card.archived)
            .filter((card) => customFlashcardMatchesRoute(card, {
              routeFormulaOnly,
              routeLearningOutcomeId,
              routeMaterialId,
              routeGroupId,
              routeSectionId
            }))
            .map((card) => ({
              ...card,
              material: template.material,
              section: template.section,
              sectionTitle: template.sectionTitle
            }))
        : [];
      const sortedCards = sortCardsForReview(filterDisplayableFlashcards([...loadedCards, ...customCards]));
      const nextIndex = initialFlashcardIndex(sortedCards, routeActiveCardId);
      setCards(sortedCards);
      setError(null);
      setCurrentIndex(nextIndex);
      updateActiveCardIdInUrl(sortedCards[nextIndex]?.flashcard_id ?? "", "replace");
      setIsFlipped(false);
      setIsBrowseOpen(false);
      setBrowseQuery("");
      setBrowseCardType("all");
      setBrowseConfidence("all");
      setBrowseModule("all");
      setBrowseLearningOutcome("all");
      setBrowseSourcePage("all");
      setBrowseFormulaOnly(routeFormulaOnly);
      setUpcomingStatusFilter("all");
      setUpcomingModuleFilter("all");
      setUpcomingLearningOutcomeFilter("all");
      setUpcomingCardTypeFilter("all");
      setEditor(null);
      setIsSourceOpen(false);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Unable to load flashcards.");
      setCards([]);
    } finally {
      setIsLoading(false);
    }
  }

  const metrics = useMemo(() => buildFlashcardMetrics(cards), [cards]);
  const currentCard = cards[currentIndex] ?? null;
  const progressPercent = cards.length > 0 ? Math.round(((currentIndex + 1) / cards.length) * 100) : 0;
  const moduleOptions = useMemo(
    () => uniqueLabels(cards.map((card) => cardModuleLabel(card)).filter(Boolean)),
    [cards]
  );
  const learningOutcomeOptions = useMemo(
    () => uniqueLabels(cards.map((card) => cardLearningOutcomeLabel(card)).filter(Boolean)),
    [cards]
  );
  const sourcePageOptions = useMemo(
    () =>
      uniqueLabels(
        cards
          .map((card) => (card.source_page ? String(card.source_page) : ""))
          .filter(Boolean)
      ).sort((left, right) => Number(left) - Number(right)),
    [cards]
  );
  const browsedCards = useMemo(() => {
    const query = browseQuery.trim().toLowerCase();
    return cards.filter((card) => {
      if (browseCardType !== "all" && card.card_type !== browseCardType) {
        return false;
      }
      if (browseConfidence !== "all" && card.confidence_group !== browseConfidence) {
        return false;
      }
      if (browseModule !== "all" && cardModuleLabel(card) !== browseModule) {
        return false;
      }
      if (browseLearningOutcome !== "all" && cardLearningOutcomeLabel(card) !== browseLearningOutcome) {
        return false;
      }
      if (browseFormulaOnly && card.card_type !== "formula") {
        return false;
      }
      if (browseSourcePage !== "all" && String(card.source_page ?? "") !== browseSourcePage) {
        return false;
      }
      if (!query) {
        return true;
      }
      return [
        card.front,
        cardAnswer(card),
        card.sectionTitle,
        cardModuleLabel(card),
        cardLearningOutcomeLabel(card),
        card.card_type,
        card.confidence_group,
        card.source_excerpt ?? "",
        card.source_page ? `page ${card.source_page}` : ""
      ]
        .join(" ")
        .toLowerCase()
        .includes(query);
    });
  }, [browseCardType, browseConfidence, browseFormulaOnly, browseLearningOutcome, browseModule, browseQuery, browseSourcePage, cards]);
  const upcomingCards = useMemo(() => {
    const today = startOfToday();
    const seenIds = new Set<string>();
    return cards.filter((card) => {
      if (seenIds.has(card.flashcard_id)) {
        return false;
      }
      seenIds.add(card.flashcard_id);
      if (upcomingStatusFilter === "due" && !isDue(card, today)) {
        return false;
      }
      if (upcomingStatusFilter === "new" && card.confidence_group !== "new") {
        return false;
      }
      if (upcomingModuleFilter !== "all" && cardModuleLabel(card) !== upcomingModuleFilter) {
        return false;
      }
      if (upcomingLearningOutcomeFilter !== "all" && cardLearningOutcomeLabel(card) !== upcomingLearningOutcomeFilter) {
        return false;
      }
      if (upcomingCardTypeFilter !== "all" && card.card_type !== upcomingCardTypeFilter) {
        return false;
      }
      return true;
    });
  }, [cards, upcomingCardTypeFilter, upcomingLearningOutcomeFilter, upcomingModuleFilter, upcomingStatusFilter]);

  useEffect(() => {
    if (cards.length === 0) {
      setCurrentIndex(0);
      return;
    }
    if (currentIndex >= cards.length) {
      setCurrentIndex(cards.length - 1);
    }
  }, [cards.length, currentIndex]);

  useEffect(() => {
    if (!currentCard) {
      return;
    }
    writeCourseResume(courseId, {
      lastStudyCard: {
        title: currentCard.front,
        href: flashcardResumeUrl(courseId, currentCard),
        meta: `${currentIndex + 1} / ${cards.length} · ${currentCard.sectionTitle}`,
        updatedAt: new Date().toISOString()
      }
    });
  }, [cards.length, courseId, currentCard, currentIndex]);

  useEffect(() => {
    function handlePopState(): void {
      const cardId = new URLSearchParams(window.location.search).get("cardId") ?? "";
      if (!cardId) {
        return;
      }
      const cardIndex = cards.findIndex((card) => card.flashcard_id === cardId);
      if (cardIndex >= 0) {
        setCurrentIndex(cardIndex);
        setIsFlipped(false);
        setIsSourceOpen(false);
      }
    }

    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, [cards]);

  const goToCard = useCallback(
    (index: number, mode: HistoryMode = "push"): void => {
      if (cards.length === 0) {
        return;
      }
      const nextIndex = Math.max(0, Math.min(index, cards.length - 1));
      setCurrentIndex(nextIndex);
      setIsFlipped(false);
      setIsSourceOpen(false);
      updateActiveCardIdInUrl(cards[nextIndex]?.flashcard_id ?? "", mode);
    },
    [cards]
  );

  const goNext = useCallback((): void => {
    if (cards.length === 0) {
      return;
    }
    goToCard(currentIndex + 1);
  }, [cards.length, currentIndex, goToCard]);

  const goPrevious = useCallback((): void => {
    goToCard(currentIndex - 1);
  }, [currentIndex, goToCard]);

  const shuffleCards = useCallback((): void => {
    setCards((current) => {
      const shuffled = [...current];
      for (let index = shuffled.length - 1; index > 0; index -= 1) {
        const swapIndex = Math.floor(Math.random() * (index + 1));
        [shuffled[index], shuffled[swapIndex]] = [shuffled[swapIndex], shuffled[index]];
      }
      updateActiveCardIdInUrl(shuffled[0]?.flashcard_id ?? "", "replace");
      return shuffled;
    });
    setCurrentIndex(0);
    setIsFlipped(false);
    setIsSourceOpen(false);
  }, []);

  const restartDeck = useCallback((): void => {
    goToCard(0, "replace");
  }, [goToCard]);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent): void {
      const target = event.target as HTMLElement | null;
      if (target && ["INPUT", "TEXTAREA", "SELECT", "BUTTON"].includes(target.tagName)) {
        return;
      }
      if (event.key === " " || event.code === "Space") {
        event.preventDefault();
        setIsFlipped((current) => !current);
      } else if (event.key === "ArrowRight") {
        goNext();
      } else if (event.key === "ArrowLeft") {
        goPrevious();
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [goNext, goPrevious]);

  function handleRating(card: FlashcardItem, rating: ReviewRating): void {
    const updatedCard = scheduleFlashcard(card, rating);
    setCards((current) =>
      current.map((candidate) =>
        candidate.flashcard_id === card.flashcard_id ? updatedCard : candidate
      )
    );
    writeStoredOverride(courseId, updatedCard);
    void recordFlashcardReview({
      user_id: "demo-user",
      course_id: courseId,
      module_id: card.module_id ?? null,
      material_id: card.material_id,
      section_id: card.section.section_id,
      concept_id: card.concept_id ?? null,
      flashcard_id: card.flashcard_id,
      rating,
      previous_interval_days: card.interval_days ?? 0,
      new_interval_days: updatedCard.interval_days ?? 0,
      previous_confidence_group: card.confidence_group,
      new_confidence_group: updatedCard.confidence_group,
      metadata_json: {
        card_type: card.card_type,
        source_page: card.source_page ?? null
      }
    }).catch(() => undefined);
    setIsFlipped(false);
    const nextIndex = Math.min(currentIndex + 1, Math.max(cards.length - 1, 0));
    setCurrentIndex(nextIndex);
    updateActiveCardIdInUrl(cards[nextIndex]?.flashcard_id ?? "", "replace");
  }

  function openCreateCard(): void {
    const template = currentCard ?? cards[0];
    if (!template) {
      return;
    }
    setEditor({
      mode: "create",
      front: "",
      back: "",
      cardType: "short_answer_recall",
      difficulty: template.difficulty,
      sourcePage: template.source_page ? String(template.source_page) : ""
    });
  }

  function openEditCard(): void {
    if (!currentCard) {
      return;
    }
    setEditor({
      mode: "edit",
      flashcardId: currentCard.flashcard_id,
      front: currentCard.front,
      back: cardAnswer(currentCard),
      cardType: currentCard.card_type,
      difficulty: currentCard.difficulty,
      sourcePage: currentCard.source_page ? String(currentCard.source_page) : ""
    });
  }

  function saveEditor(): void {
    const template = currentCard ?? cards[0];
    if (!editor || !template) {
      return;
    }
    const sourcePage = editor.sourcePage.trim() ? Number(editor.sourcePage.trim()) : null;
    if (editor.mode === "create") {
      const created: FlashcardItem = {
        ...template,
        flashcard_id: `manual-${Date.now()}`,
        front: editor.front.trim(),
        back: editor.back.trim(),
        back_concise: editor.back.trim(),
        card_type: editor.cardType,
        source_page: Number.isFinite(sourcePage) ? sourcePage : null,
        source_excerpt: "",
        difficulty: editor.difficulty,
        confidence_group: "new",
        interval_days: 0,
        ease_factor: 2.5,
        repetitions: 0,
        due_at: null,
        last_reviewed_at: null,
        archived: false,
        content_origin: "ai_generated_from_original"
      };
      const nextCards = [...cards, created];
      setCards(nextCards);
      writeStoredCustomCards(courseId, [
        ...readStoredCustomCards(courseId),
        stripFlashcardItem(created)
      ]);
      setCurrentIndex(nextCards.length - 1);
      updateActiveCardIdInUrl(created.flashcard_id);
    } else if (editor.flashcardId) {
      setCards((current) =>
        current.map((card) => {
          if (card.flashcard_id !== editor.flashcardId) {
            return card;
          }
          const updated = {
            ...card,
            front: editor.front.trim(),
            back: editor.back.trim(),
            back_concise: editor.back.trim(),
            card_type: editor.cardType,
            source_page: Number.isFinite(sourcePage) ? sourcePage : null,
            difficulty: editor.difficulty
          };
          writeStoredOverride(courseId, updated);
          writeStoredCustomCards(
            courseId,
            readStoredCustomCards(courseId).map((customCard) =>
              customCard.flashcard_id === updated.flashcard_id ? stripFlashcardItem(updated) : customCard
            )
          );
          return updated;
        })
      );
    }
    setEditor(null);
    setIsFlipped(false);
    setIsSourceOpen(false);
  }

  function archiveCurrentCard(): void {
    if (!currentCard) {
      return;
    }
    const archived = { ...currentCard, archived: true };
    writeStoredOverride(courseId, archived);
    writeStoredCustomCards(
      courseId,
      readStoredCustomCards(courseId).map((customCard) =>
        customCard.flashcard_id === currentCard.flashcard_id ? { ...customCard, archived: true } : customCard
      )
    );
    setCards((current) => current.filter((card) => card.flashcard_id !== currentCard.flashcard_id));
    setCurrentIndex(0);
    updateActiveCardIdInUrl(cards.find((card) => card.flashcard_id !== currentCard.flashcard_id)?.flashcard_id ?? "", "replace");
    setIsFlipped(false);
    setEditor(null);
  }

  return (
    <div className="stack flashcards-workspace">
      <section className="card flashcards-hero-card">
        <div>
          <p className="eyebrow">Flashcards</p>
          <h2>Flashcards</h2>
          <p>
            Review cards generated from original key concepts, formulas, learning outcomes, and weak concepts.
          </p>
        </div>
        <a className="secondary-button" href={`/courses/${encodeURIComponent(courseId)}/materials`}>
          Open book library
        </a>
      </section>

      {isLoading ? <p className="subtle">Loading flashcards...</p> : null}
      {error ? (
        <div className="status-panel error-panel" aria-live="polite">
          <strong>Issue:</strong> {error}
        </div>
      ) : null}

      <section className="flashcard-metric-grid" aria-label="Flashcard review status">
        {metrics.map((metric) => (
          <article className="card flashcard-metric-card" key={metric.label}>
            <span className="eyebrow">{metric.label}</span>
            <strong>{metric.value}</strong>
          </article>
        ))}
      </section>

      {cards.length === 0 && !isLoading ? (
        <section className="course-empty-card">
          <h3>No flashcards ready</h3>
          <p>Open a book module after parsing finishes. Flashcards are created from original book anchors and study layers.</p>
        </section>
      ) : null}

      {currentCard ? (
        <section className="card flashcard-review-card" aria-label="Flashcard review">
          <div className="flashcard-review-header">
            <div>
              <p className="eyebrow">Review deck</p>
              <h3>{currentIndex + 1} / {cards.length}</h3>
            </div>
            <div className="flashcard-source-stack">
              <span className="origin-badge">{cardModuleLabel(currentCard)}</span>
              {cardLearningOutcomeLabel(currentCard) ? (
                <span className="origin-badge">{cardLearningOutcomeLabel(currentCard)}</span>
              ) : null}
              <a className="source-page-badge source-page-link" href={moduleSourceUrl(courseId, currentCard)}>
                {cardSourcePageLabel(currentCard)}
              </a>
            </div>
          </div>

          <div className="flashcard-progress-track" aria-label="Deck progress">
            <span style={{ width: `${progressPercent}%` }} />
          </div>

          <div className="flashcard-study-card-shell">
            <button
              aria-label="Move left"
              className="flashcard-side-nav flashcard-side-nav-left"
              disabled={currentIndex === 0}
              onClick={goPrevious}
              type="button"
            >
              <span aria-hidden="true">&lt;</span>
            </button>
            <button
              aria-label="Flashcard card. Press to flip."
              className={`flashcard-study-card-button ${isFlipped ? "is-flipped" : ""}`}
              type="button"
              onClick={() => setIsFlipped((current) => !current)}
              onTouchStart={(event) => setTouchStartX(event.touches[0]?.clientX ?? null)}
              onTouchEnd={(event) => {
                if (touchStartX === null) {
                  return;
                }
                const delta = (event.changedTouches[0]?.clientX ?? touchStartX) - touchStartX;
                setTouchStartX(null);
                if (Math.abs(delta) < 40) {
                  return;
                }
                if (delta < 0) {
                  goNext();
                } else {
                  goPrevious();
                }
              }}
            >
              <span className="flashcard-study-card-content">
                <span className="eyebrow">{isFlipped ? "Answer" : "Prompt"}</span>
                <strong className={isFlipped ? "flashcard-answer-text" : "flashcard-question-text"}>
                  {isFlipped ? cardAnswer(currentCard) : currentCard.front}
                </strong>
                {!isFlipped ? (
                  <span className="subtle">
                    {currentCard.sectionTitle} · {currentCard.material.display_name ?? currentCard.material.file_name}
                  </span>
                ) : null}
              </span>
            </button>
            <button
              aria-label="Move right"
              className="flashcard-side-nav flashcard-side-nav-right"
              disabled={currentIndex >= cards.length - 1}
              onClick={goNext}
              type="button"
            >
              <span aria-hidden="true">&gt;</span>
            </button>
          </div>

          {isFlipped && currentCard.source_excerpt ? (
            <div className="flashcard-source-details">
              <button
                className="secondary-button source-toggle"
                type="button"
                aria-expanded={isSourceOpen}
                onClick={() => setIsSourceOpen((current) => !current)}
              >
                View source excerpt
              </button>
              {isSourceOpen ? (
                <p>{currentCard.source_excerpt}</p>
              ) : null}
            </div>
          ) : null}

          <div className="flashcard-deck-controls" aria-label="Flashcard navigation">
            <button className="secondary-button" type="button" onClick={goPrevious} disabled={currentIndex === 0}>
              Previous
            </button>
            <button className="primary-button" type="button" onClick={() => setIsFlipped((current) => !current)}>
              Flip card
            </button>
            <button className="secondary-button" type="button" onClick={goNext} disabled={currentIndex >= cards.length - 1}>
              Next
            </button>
            <button className="secondary-button" type="button" onClick={shuffleCards}>
              Shuffle
            </button>
            <button className="secondary-button" type="button" onClick={restartDeck}>
              Restart deck
            </button>
            <button className="secondary-button" type="button" onClick={() => setIsBrowseOpen((current) => !current)}>
              Browse all cards
            </button>
            <a className="secondary-button" href={moduleReturnUrl(courseId, currentCard)}>
              Return to module
            </a>
            <button className="secondary-button" type="button" onClick={openCreateCard}>
              Create card
            </button>
            <button className="secondary-button" type="button" onClick={openEditCard}>
              Edit card
            </button>
            <button className="secondary-button danger-button-soft" type="button" onClick={archiveCurrentCard}>
              Delete card
            </button>
            <a className="secondary-button" href={`/courses/${encodeURIComponent(courseId)}/overview`}>
              Exit review
            </a>
          </div>

          {editor ? (
            <section className="card flashcard-editor-panel" aria-label="Flashcard editor">
              <div className="flashcard-review-header">
                <div>
                  <h3>{editor.mode === "create" ? "Create card" : "Edit card"}</h3>
                  <p className="subtle">Keep cards specific, source-linked, and useful for recall.</p>
                </div>
                <button className="secondary-button" type="button" onClick={() => setEditor(null)}>
                  Cancel
                </button>
              </div>
              <label className="field-label">
                Card front
                <textarea
                  value={editor.front}
                  onChange={(event) => setEditor((current) => current ? { ...current, front: event.target.value } : current)}
                  rows={3}
                />
              </label>
              <label className="field-label">
                Card back
                <textarea
                  value={editor.back}
                  onChange={(event) => setEditor((current) => current ? { ...current, back: event.target.value } : current)}
                  rows={4}
                />
              </label>
              <div className="flashcard-editor-grid">
                <label className="field-label">
                  Card type
                  <select
                    value={editor.cardType}
                    onChange={(event) => setEditor((current) => current ? { ...current, cardType: event.target.value } : current)}
                  >
                    {FLASHCARD_TYPE_OPTIONS.filter((option) => option.value !== "all").map((option) => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                  </select>
                </label>
                <label className="field-label">
                  Source page
                  <input
                    inputMode="numeric"
                    value={editor.sourcePage}
                    onChange={(event) => setEditor((current) => current ? { ...current, sourcePage: event.target.value } : current)}
                  />
                </label>
              </div>
              <button
                className="primary-button"
                type="button"
                onClick={saveEditor}
                disabled={!editor.front.trim() || !editor.back.trim()}
              >
                Save card
              </button>
            </section>
          ) : null}

          {isFlipped ? (
            <div className="flashcard-rating-row" aria-label="Rate flashcard">
              {(Object.keys(RATING_LABELS) as ReviewRating[]).map((rating) => (
                <button
                  className={`secondary-button flashcard-rating-${rating}`}
                  key={rating}
                  type="button"
                  onClick={() => handleRating(currentCard, rating)}
                >
                  {RATING_LABELS[rating]}
                </button>
              ))}
            </div>
          ) : null}

          {isBrowseOpen ? (
            <section className="card flashcard-browse-panel" role="region" aria-label="Browse flashcards">
              <div className="flashcard-review-header">
                <div>
                  <h3>Browse flashcards</h3>
                  <p className="subtle">Jump around freely, then come back to focused review.</p>
                </div>
                <label className="field-label">
                  Search
                  <input
                    aria-label="Search flashcards"
                    type="search"
                    value={browseQuery}
                    onChange={(event) => setBrowseQuery(event.target.value)}
                    placeholder="Concept, module, page..."
                  />
                </label>
              </div>
              <div className="flashcard-browse-filters">
                <label className="field-label">
                  Filter by card type
                  <select
                    value={browseCardType}
                    onChange={(event) => setBrowseCardType(event.target.value)}
                  >
                    {FLASHCARD_TYPE_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                  </select>
                </label>
                <label className="field-label">
                  Filter by confidence
                  <select
                    value={browseConfidence}
                    onChange={(event) => setBrowseConfidence(event.target.value)}
                  >
                    {CONFIDENCE_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                  </select>
                </label>
                <label className="field-label">
                  Filter by module
                  <select
                    value={browseModule}
                    onChange={(event) => setBrowseModule(event.target.value)}
                  >
                    <option value="all">All modules</option>
                    {moduleOptions.map((option) => (
                      <option key={option} value={option}>{option}</option>
                    ))}
                  </select>
                </label>
                <label className="field-label">
                  Filter by learning outcome
                  <select
                    value={browseLearningOutcome}
                    onChange={(event) => setBrowseLearningOutcome(event.target.value)}
                  >
                    <option value="all">All learning outcomes</option>
                    {learningOutcomeOptions.map((option) => (
                      <option key={option} value={option}>{option}</option>
                    ))}
                  </select>
                </label>
                <label className="field-label">
                  Filter by source page
                  <select
                    value={browseSourcePage}
                    onChange={(event) => setBrowseSourcePage(event.target.value)}
                  >
                    <option value="all">All pages</option>
                    {sourcePageOptions.map((option) => (
                      <option key={option} value={option}>page {option}</option>
                    ))}
                  </select>
                </label>
                <label className="field-label checkbox-field">
                  <input
                    checked={browseFormulaOnly}
                    type="checkbox"
                    onChange={(event) => setBrowseFormulaOnly(event.target.checked)}
                  />
                  Formula cards only
                </label>
              </div>
              <div className="flashcard-browse-list">
                {browsedCards.map((card) => {
                  const cardIndex = cards.findIndex((candidate) => candidate.flashcard_id === card.flashcard_id);
                  return (
                    <button
                      aria-label={`Jump to card ${cardIndex + 1}: ${card.front}`}
                      className={`flashcard-browse-item ${cardIndex === currentIndex ? "active" : ""}`}
                      key={card.flashcard_id}
                      type="button"
                      onClick={() => goToCard(cardIndex)}
                    >
                      <strong>{card.front}</strong>
                      <span className="subtle">Card {cardIndex + 1}</span>
                      <span>{cardModuleLabel(card)}</span>
                      {cardLearningOutcomeLabel(card) ? <span>{cardLearningOutcomeLabel(card)}</span> : null}
                      <span>{cardSourcePageLabel(card)}</span>
                    </button>
                  );
                })}
              </div>
            </section>
          ) : null}
        </section>
      ) : null}

      {cards.length > 1 ? (
        <section className="card flashcard-session-index" aria-label="Upcoming cards">
          <div className="flashcard-review-header">
            <div>
              <h3>Upcoming cards</h3>
              <p className="subtle">{upcomingCards.length} of {cards.length} cards in this session</p>
            </div>
            <div className="flashcard-upcoming-filters">
              <label className="field-label">
                Filter upcoming cards
                <select
                  value={upcomingStatusFilter}
                  onChange={(event) => setUpcomingStatusFilter(event.target.value as UpcomingStatusFilter)}
                >
                  <option value="all">All</option>
                  <option value="due">Due</option>
                  <option value="new">New</option>
                </select>
              </label>
              <label className="field-label">
                By module
                <select
                  aria-label="Filter upcoming cards by module"
                  value={upcomingModuleFilter}
                  onChange={(event) => setUpcomingModuleFilter(event.target.value)}
                >
                  <option value="all">All modules</option>
                  {moduleOptions.map((option) => (
                    <option key={option} value={option}>{option}</option>
                  ))}
                </select>
              </label>
              <label className="field-label">
                By LO
                <select
                  aria-label="Filter upcoming cards by LO"
                  value={upcomingLearningOutcomeFilter}
                  onChange={(event) => setUpcomingLearningOutcomeFilter(event.target.value)}
                >
                  <option value="all">All learning outcomes</option>
                  {learningOutcomeOptions.map((option) => (
                    <option key={option} value={option}>{option}</option>
                  ))}
                </select>
              </label>
              <label className="field-label">
                By card type
                <select
                  aria-label="Filter upcoming cards by card type"
                  value={upcomingCardTypeFilter}
                  onChange={(event) => setUpcomingCardTypeFilter(event.target.value)}
                >
                  {FLASHCARD_TYPE_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
              </label>
            </div>
          </div>
          <div className="flashcard-upcoming-list">
            {upcomingCards.map((card) => {
              const cardIndex = cards.findIndex((candidate) => candidate.flashcard_id === card.flashcard_id);
              const isActive = cardIndex === currentIndex;
              return (
                <button
                  aria-current={isActive ? "true" : undefined}
                  aria-label={`Card ${cardIndex + 1}: ${card.front}`}
                  className={`preview-item flashcard-upcoming-card${isActive ? " active" : ""}`}
                  key={card.flashcard_id}
                  type="button"
                  onClick={() => goToCard(cardIndex)}
                >
                  <strong>{card.front}</strong>
                  <div className="flashcard-upcoming-meta">
                    <span className="origin-badge">{cardModuleLabel(card)}</span>
                    {cardLearningOutcomeLabel(card) ? (
                      <span className="origin-badge">{cardLearningOutcomeLabel(card)}</span>
                    ) : null}
                    <span className="source-page-badge">{cardSourcePageLabel(card)}</span>
                  </div>
                </button>
              );
            })}
          </div>
        </section>
      ) : null}
    </div>
  );
}

function buildFlashcardMetrics(cards: FlashcardItem[]): Array<{ label: string; value: string }> {
  const today = startOfToday();
  return [
    { label: "Due Today", value: String(cards.filter((card) => isDue(card, today)).length) },
    { label: "Need to Review", value: String(cards.filter((card) => ["need_to_review", "new"].includes(card.confidence_group)).length) },
    { label: "Learning", value: String(cards.filter((card) => card.confidence_group === "learning").length) },
    { label: "Confident", value: String(cards.filter((card) => card.confidence_group === "confident").length) },
    { label: "New Cards", value: String(cards.filter((card) => card.confidence_group === "new").length) },
    { label: "Overdue Cards", value: String(cards.filter((card) => isOverdue(card, today)).length) }
  ];
}

function initialFlashcardIndex(cards: FlashcardItem[], activeCardId: string): number {
  if (cards.length === 0) {
    return 0;
  }
  if (activeCardId) {
    const activeIndex = cards.findIndex((card) => card.flashcard_id === activeCardId);
    if (activeIndex >= 0) {
      return activeIndex;
    }
  }
  const today = startOfToday();
  const firstDueIndex = cards.findIndex((card) => isDue(card, today));
  return firstDueIndex >= 0 ? firstDueIndex : 0;
}

function updateActiveCardIdInUrl(cardId: string, mode: HistoryMode = "push"): void {
  if (typeof window === "undefined" || !cardId) {
    return;
  }
  const url = new URL(window.location.href);
  url.searchParams.set("cardId", cardId);
  const nextUrl = `${url.pathname}${url.search}${url.hash}`;
  if (mode === "replace") {
    window.history.replaceState(window.history.state, "", nextUrl);
  } else {
    window.history.pushState(window.history.state, "", nextUrl);
  }
}

function uniqueLabels(labels: string[]): string[] {
  return Array.from(new Set(labels.map((label) => label.trim()).filter(Boolean)));
}

function cardModuleLabel(card: FlashcardItem): string {
  const moduleMatch = card.sectionTitle.match(/Module\s+\d+(?:\.\d+)?:\s*[^/]+/i);
  if (moduleMatch) {
    return cleanBadgeLabel(moduleMatch[0]);
  }
  return cleanBadgeLabel(card.sectionTitle || "Module");
}

function cardLearningOutcomeLabel(card: FlashcardItem): string {
  const sourceKeyConceptTitles = card.section.original_book_content?.key_concepts
    ?.map((item) => item.title)
    .filter(Boolean) ?? [];
  const sectionOutcomeTitles = card.section.learning_outcomes
    ?.map((outcome) => outcome.outcome_title)
    .filter(Boolean) ?? [];
  const directMatch = [
    card.front,
    card.back,
    card.source_excerpt ?? "",
    ...sourceKeyConceptTitles,
    ...sectionOutcomeTitles
  ]
    .join(" ")
    .match(/\bLO\s+\d+\.[a-z]\b/i);
  if (directMatch) {
    return directMatch[0].replace(/\blo\b/i, "LO");
  }
  const matchedOutcome = card.learning_outcome_id
    ? card.section.learning_outcomes?.find((outcome) => outcome.outcome_id === card.learning_outcome_id)
    : null;
  const fallbackOutcome = matchedOutcome ?? card.section.learning_outcomes?.[0] ?? null;
  if (fallbackOutcome?.outcome_title) {
    const outcomeMatch = fallbackOutcome.outcome_title.match(/\bLO\s+\d+\.[a-z]\b/i);
    return outcomeMatch ? outcomeMatch[0].replace(/\blo\b/i, "LO") : cleanBadgeLabel(fallbackOutcome.outcome_title);
  }
  return "";
}

function cardSourcePageLabel(card: FlashcardItem): string {
  const pageStart = card.section.page_start ?? card.source_page ?? null;
  const pageEnd = card.section.page_end ?? card.source_page ?? null;
  if (pageStart && pageEnd && pageEnd !== pageStart) {
    return `pages ${pageStart}-${pageEnd}`;
  }
  const singlePage = pageStart ?? pageEnd ?? card.source_page ?? null;
  return singlePage ? `page ${singlePage}` : "source pages";
}

function moduleReturnUrl(courseId: string, card: FlashcardItem): string {
  return materialsUrl(courseId, {
    materialId: card.material_id || card.material.material_id,
    groupId: card.section.parent_group_id,
    sectionId: card.section.section_id
  });
}

function moduleSourceUrl(courseId: string, card: FlashcardItem): string {
  return materialsUrl(courseId, {
    materialId: card.material_id || card.material.material_id,
    groupId: card.section.parent_group_id,
    sectionId: card.section.section_id,
    source: "1",
    sourceId: card.section.section_id
  });
}

function flashcardResumeUrl(courseId: string, card: FlashcardItem): string {
  const query = new URLSearchParams({
    materialId: card.material_id || card.material.material_id,
    sectionId: card.section.section_id,
    cardId: card.flashcard_id
  });
  if (card.section.parent_group_id) {
    query.set("groupId", card.section.parent_group_id);
  }
  if (card.formula_id || card.card_type === "formula") {
    query.set("formula", "1");
  }
  return `/courses/${encodeURIComponent(courseId)}/flashcards?${query.toString()}`;
}

function materialsUrl(courseId: string, params: Record<string, string | null | undefined>): string {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value) {
      query.set(key, value);
    }
  });
  const suffix = query.toString();
  return `/courses/${encodeURIComponent(courseId)}/materials${suffix ? `?${suffix}` : ""}`;
}

function cardAnswer(card: StudyFlashcard): string {
  return (card.back_concise?.trim() || card.back || "").trim();
}

function filterDisplayableFlashcards(cards: FlashcardItem[]): FlashcardItem[] {
  const seenQuestions = new Set<string>();
  return cards.filter((card) => {
    if (!isDisplayableFlashcard(card)) {
      return false;
    }
    const key = flashcardSemanticKey(card);
    if (seenQuestions.has(key)) {
      return false;
    }
    seenQuestions.add(key);
    return true;
  });
}

function isDisplayableFlashcard(card: StudyFlashcard): boolean {
  const front = card.front.trim();
  const answer = cardAnswer(card);
  if (card.archived || !front || !answer) {
    return false;
  }
  if (!front.endsWith("?")) {
    return false;
  }
  if (LOW_QUALITY_FLASHCARD_FRONT_RE.test(front)) {
    return false;
  }
  if (isLowQualityBareDefinitionQuestion(front)) {
    return false;
  }
  if (/\b(\w+)\s+\1\b/i.test(front)) {
    return false;
  }
  if (front.split(/\s+/).length < 3) {
    return false;
  }
  if (answer.split(/\s+/).filter(Boolean).length < 2) {
    return false;
  }
  if (answer.toLowerCase().replace(/[.?!]+$/, "") === front.toLowerCase().replace(/[.?!]+$/, "")) {
    return false;
  }
  return true;
}

function flashcardSemanticKey(card: StudyFlashcard): string {
  const subject = definitionQuestionSubject(card.front);
  if (subject) {
    return `definition:${subject}`;
  }
  return card.front.toLowerCase().replace(/\W+/g, " ").trim();
}

function definitionQuestionSubject(front: string): string | null {
  const match = front.trim().match(/^What\s+(?:is|are)\s+(.+?)\?$/i);
  return match ? normalizeDefinitionSubject(match[1]) : null;
}

function normalizeDefinitionSubject(subject: string): string {
  return subject
    .toLowerCase()
    .replace(/[^\w\s-]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^(?:a|an|the)\s+/, "")
    .split(" ")
    .map(singularizeDefinitionToken)
    .join(" ");
}

function singularizeDefinitionToken(token: string): string {
  if (token.endsWith("ies") && token.length > 4) {
    return `${token.slice(0, -3)}y`;
  }
  if (token.endsWith("sses")) {
    return token.slice(0, -2);
  }
  if (token.endsWith("s") && !/(ss|us|is|risk)$/.test(token) && token.length > 3) {
    return token.slice(0, -1);
  }
  return token;
}

function isLowQualityBareDefinitionQuestion(front: string): boolean {
  const subject = definitionQuestionSubject(front);
  if (!subject) {
    return false;
  }
  const words = subject.split(/\s+/).filter(Boolean);
  if (words.length === 0) {
    return true;
  }
  if (/^(?:also|because|if|when|where|while|although|suppose|given|some|there|of|all)\b/.test(subject)) {
    return true;
  }
  if (/^(?:also\s+)?assume(?:\s+that)?(?:\s+there|\s+the)?/.test(subject)) {
    return true;
  }
  if (words.length === 1 && LOW_QUALITY_BARE_DEFINITION_TERMS.has(words[0])) {
    return true;
  }
  if (
    words.length <= 2 &&
    words.some((word) => LOW_QUALITY_BARE_DEFINITION_TERMS.has(word)) &&
    !STRONG_CONCEPT_ANCHOR_RE.test(subject)
  ) {
    return true;
  }
  return false;
}

function cleanBadgeLabel(label: string): string {
  return label.replace(/\s+/g, " ").trim();
}

function scheduleFlashcard(card: FlashcardItem, rating: ReviewRating): FlashcardItem {
  const now = new Date();
  let intervalDays = card.interval_days ?? 0;
  let easeFactor = card.ease_factor || 2.5;
  let repetitions = card.repetitions ?? 0;
  let confidenceGroup = card.confidence_group || "new";

  if (rating === "forgot") {
    repetitions = 0;
    intervalDays = 0;
    confidenceGroup = "need_to_review";
  } else if (rating === "hard") {
    intervalDays = Math.max(1, Math.round(intervalDays * 0.6) || 1);
    easeFactor = Math.max(1.3, easeFactor - 0.15);
    confidenceGroup = "need_to_review";
  } else if (rating === "good") {
    repetitions += 1;
    intervalDays = repetitions === 1 ? 3 : Math.max(3, Math.round(intervalDays * easeFactor));
    confidenceGroup = "learning";
  } else {
    repetitions += 1;
    easeFactor += 0.15;
    intervalDays = repetitions === 1 ? 7 : Math.max(7, Math.round(intervalDays * easeFactor * 1.3));
    confidenceGroup = "confident";
  }

  const dueAt = addDays(now, intervalDays);

  return {
    ...card,
    interval_days: intervalDays,
    ease_factor: Number(easeFactor.toFixed(2)),
    repetitions,
    confidence_group: confidenceGroup,
    due_at: dueAt.toISOString(),
    last_reviewed_at: now.toISOString()
  };
}

function sortCardsForReview(cards: FlashcardItem[]): FlashcardItem[] {
  return [...cards].sort((left, right) => dueTimestamp(left) - dueTimestamp(right));
}

function sectionMatchesRoute(
  section: MaterialStudySection,
  filters: { routeGroupId: string; routeSectionId: string }
): boolean {
  if (filters.routeSectionId && section.section_id !== filters.routeSectionId) {
    return false;
  }
  if (filters.routeGroupId && section.parent_group_id !== filters.routeGroupId) {
    return false;
  }
  return true;
}

function flashcardMatchesRoute(
  card: StudyFlashcard,
  filters: { routeFormulaOnly: boolean; routeLearningOutcomeId: string }
): boolean {
  if (filters.routeFormulaOnly && card.card_type !== "formula" && !card.formula_id) {
    return false;
  }
  if (filters.routeLearningOutcomeId && card.learning_outcome_id !== filters.routeLearningOutcomeId) {
    return false;
  }
  return true;
}

function customFlashcardMatchesRoute(
  card: StudyFlashcard,
  filters: {
    routeFormulaOnly: boolean;
    routeLearningOutcomeId: string;
    routeMaterialId: string;
    routeGroupId: string;
    routeSectionId: string;
  }
): boolean {
  if (filters.routeMaterialId && card.material_id !== filters.routeMaterialId) {
    return false;
  }
  if (!flashcardMatchesRoute(card, filters)) {
    return false;
  }
  // Locally-created cards do not currently persist section/group ids, so avoid
  // leaking them into scoped decks when the route asks for a specific section.
  if (filters.routeGroupId || filters.routeSectionId) {
    return false;
  }
  return true;
}

function dueTimestamp(card: StudyFlashcard): number {
  if (!card.due_at) {
    return 0;
  }
  return new Date(card.due_at).getTime();
}

function buildDueLabel(card: StudyFlashcard): string {
  if (!card.due_at) {
    return "Due Today";
  }
  const due = new Date(card.due_at);
  const today = startOfToday();
  const differenceDays = Math.ceil((startOfDay(due).getTime() - today.getTime()) / 86_400_000);
  if (differenceDays <= 0) {
    return "Due Today";
  }
  return `Due in ${differenceDays} ${differenceDays === 1 ? "day" : "days"}`;
}

function cardReviewStatusLabel(card: StudyFlashcard): string {
  if (card.confidence_group === "new") {
    return "New";
  }
  if (isDue(card, startOfToday())) {
    return "Due Today";
  }
  if (card.confidence_group === "learning") {
    return "Learning";
  }
  return "Reviewed";
}

function isDue(card: StudyFlashcard, today: Date): boolean {
  return !card.due_at || startOfDay(new Date(card.due_at)).getTime() <= today.getTime();
}

function isOverdue(card: StudyFlashcard, today: Date): boolean {
  return Boolean(card.due_at) && startOfDay(new Date(card.due_at as string)).getTime() < today.getTime();
}

function startOfToday(): Date {
  return startOfDay(new Date());
}

function startOfDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

function addDays(date: Date, days: number): Date {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

function formatConfidence(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatFlashcardType(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function storageKey(courseId: string): string {
  return `exam-prep-flashcard-review:${courseId}`;
}

function customStorageKey(courseId: string): string {
  return `exam-prep-flashcard-custom:${courseId}`;
}

function readStoredOverrides(courseId: string): Record<string, FlashcardOverride> {
  if (typeof window === "undefined") {
    return {};
  }
  try {
    const raw = window.localStorage.getItem(storageKey(courseId));
    return raw ? (JSON.parse(raw) as Record<string, FlashcardOverride>) : {};
  } catch {
    return {};
  }
}

function writeStoredOverride(courseId: string, card: StudyFlashcard): void {
  if (typeof window === "undefined") {
    return;
  }
  const current = readStoredOverrides(courseId);
  current[card.flashcard_id] = {
    front: card.front,
    back: card.back,
    back_concise: card.back_concise ?? card.back,
    card_type: card.card_type,
    source_page: card.source_page,
    source_excerpt: card.source_excerpt,
    difficulty: card.difficulty,
    learning_outcome_id: card.learning_outcome_id,
    formula_id: card.formula_id,
    confidence_group: card.confidence_group,
    interval_days: card.interval_days,
    ease_factor: card.ease_factor,
    repetitions: card.repetitions,
    due_at: card.due_at,
    last_reviewed_at: card.last_reviewed_at,
    archived: card.archived
  };
  window.localStorage.setItem(storageKey(courseId), JSON.stringify(current));
}

function readStoredCustomCards(courseId: string): StudyFlashcard[] {
  if (typeof window === "undefined") {
    return [];
  }
  try {
    const raw = window.localStorage.getItem(customStorageKey(courseId));
    return raw ? (JSON.parse(raw) as StudyFlashcard[]) : [];
  } catch {
    return [];
  }
}

function writeStoredCustomCards(courseId: string, cards: StudyFlashcard[]): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(customStorageKey(courseId), JSON.stringify(cards));
}

function stripFlashcardItem(card: FlashcardItem): StudyFlashcard {
  return {
    flashcard_id: card.flashcard_id,
    course_id: card.course_id,
    material_id: card.material_id,
    module_id: card.module_id,
    learning_outcome_id: card.learning_outcome_id,
    concept_id: card.concept_id,
    formula_id: card.formula_id,
    front: card.front,
    back: card.back,
    back_concise: card.back_concise ?? card.back,
    card_type: card.card_type,
    source_page: card.source_page,
    source_excerpt: card.source_excerpt,
    difficulty: card.difficulty,
    confidence_group: card.confidence_group,
    interval_days: card.interval_days,
    ease_factor: card.ease_factor,
    repetitions: card.repetitions,
    due_at: card.due_at,
    last_reviewed_at: card.last_reviewed_at,
    archived: card.archived,
    content_origin: card.content_origin
  };
}
