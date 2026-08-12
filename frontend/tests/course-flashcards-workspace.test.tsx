import React from "react";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CourseFlashcardsWorkspace } from "@/components/courses/course-flashcards-workspace";
import { CourseWorkspaceFrame } from "@/components/courses/course-workspace-frame";
import { fetchMaterialStudy, recordFlashcardReview } from "@/lib/api";
import type { CourseMaterialsResponse, MaterialStudyResponse } from "@/lib/schemas";

const navigationMock = vi.hoisted(() => ({
  searchParams: new URLSearchParams()
}));

const material = {
  material_id: "mat-workbook",
  course_id: "course-demo",
  module_id: null,
  file_name: "FRM 2025 Part 1 KAPLAN Book 1.PDF",
  display_name: "FRM 2025 Part 1 KAPLAN Book 1.PDF",
  file_path: "/tmp/frm.pdf",
  uploaded_at: "2026-05-07T10:00:00Z",
  content_type: "application/pdf",
  status: "completed",
  page_count: 167,
  chunk_count: 3,
  section_count: 1,
  error_message: null
} as const;

const studyResponse: MaterialStudyResponse = {
  record: material,
  groups: [],
  sections: [
    {
      section_id: "section-1",
      material_id: "mat-workbook",
      parent_group_id: "reading-1",
      title: "Module 1.1: Introduction to Risk Management",
      normalized_title: "Module 1.1: Introduction to Risk Management",
      page_start: 13,
      page_end: 18,
      source_anchor: "FRM 2025 Part 1 KAPLAN Book 1.PDF | Module 1.1",
      summary: "",
      key_points: [],
      memorize_keywords: [],
      memorize_functions_or_formulas: [],
      traps: [],
      original_book_content: {
        key_concepts: [
          {
            item_id: "kc-1",
            title: "LO 1.a",
            content: "LO 1.a\nRisk is uncertainty surrounding outcomes.",
            source_pages: [13],
            original_order: 1,
            content_origin: "original_book",
            source_block_ids: ["block-1"]
          }
        ],
        module_quiz: [],
        answers: []
      },
      learning_outcomes: [],
      concepts: [],
      formulas: [],
      flashcards: [
        {
          flashcard_id: "flashcard-1",
          material_id: "mat-workbook",
          module_id: "module-1.1",
          learning_outcome_id: "outcome-1",
          formula_id: null,
          concept_id: "concept-1",
          front: "What is risk?",
          back: "LO 1.a Risk is uncertainty surrounding outcomes. A risk management process is a series of actions designed to reduce or eliminate potential loss. Risk taking refers to the active acceptance of incremental risk in pursuit of incremental gains.",
          back_concise: "Risk is uncertainty surrounding outcomes.",
          card_type: "definition",
          source_page: 13,
          source_excerpt: "LO 1.a Risk is uncertainty surrounding outcomes. A risk management process is a series of actions designed to reduce or eliminate potential loss. Risk taking refers to the active acceptance of incremental risk in pursuit of incremental gains.",
          difficulty: "medium",
          confidence_group: "new",
          interval_days: 0,
          ease_factor: 2.5,
          repetitions: 0,
          due_at: null,
          last_reviewed_at: null,
          archived: false,
          content_origin: "ai_generated_from_original"
        },
        {
          flashcard_id: "flashcard-2",
          material_id: "mat-workbook",
          module_id: "module-1.1",
          learning_outcome_id: "outcome-1",
          formula_id: null,
          concept_id: "concept-2",
          front: "What are the four components of the risk management process?",
          back: "1. Identify risks\n2. Analyze and measure risks\n3. Evaluate the impact from risk events\n4. Manage risks",
          back_concise: "1. Identify risks\n2. Analyze and measure risks\n3. Evaluate the impact from risk events\n4. Manage risks",
          card_type: "list_recall",
          source_page: 13,
          source_excerpt: "The four components of the risk management process are as follows.",
          difficulty: "medium",
          confidence_group: "confident",
          interval_days: 0,
          ease_factor: 2.5,
          repetitions: 0,
          due_at: null,
          last_reviewed_at: null,
          archived: false,
          content_origin: "ai_generated_from_original"
        },
        {
          flashcard_id: "flashcard-3",
          material_id: "mat-workbook",
          module_id: "module-1.1",
          learning_outcome_id: "outcome-1",
          formula_id: "formula-expected-loss",
          concept_id: "concept-1",
          front: "What is the formula for expected loss?",
          back: "EL = EAD x PD x LGD",
          back_concise: "EL = EAD x PD x LGD",
          card_type: "formula",
          source_page: 160,
          source_excerpt: "Expected loss: EL = EAD x PD x LGD",
          difficulty: "medium",
          confidence_group: "learning",
          interval_days: 3,
          ease_factor: 2.5,
          repetitions: 1,
          due_at: "2999-05-10T12:00:00Z",
          last_reviewed_at: "2026-05-07T12:00:00Z",
          archived: false,
          content_origin: "ai_generated_from_original"
        }
      ],
      due_flashcard_count: 2,
      mastery_percent: 0,
      weakest_concepts: ["Risk uncertainty"],
      difficulty: "medium",
      studied_status: "not_started",
      quiz_ready: true,
      display_order: 1,
      enrichment_status: "completed",
      source_ids: ["source-1"]
    }
  ],
  total_sections: 1,
  offset: 0,
  limit: 60,
  has_more: false,
  ready_sections: 1,
  studied_sections: 0
};

const courseMaterials: CourseMaterialsResponse = {
  course_id: "course-demo",
  records: [material],
  sections: [],
  quiz_sources: [],
  default_source_ids: [],
  default_quiz_source_ids: []
};

vi.mock("@/lib/api", () => ({
  fetchCourseMaterials: vi.fn(async () => courseMaterials),
  fetchMaterialStudy: vi.fn(async () => studyResponse),
  recordFlashcardReview: vi.fn(async (payload) => ({
    id: "review-1",
    reviewed_at: "2026-05-07T12:00:00Z",
    ...payload
  }))
}));

vi.mock("@/components/agents/agent-coach-panel", () => ({
  AgentCoachPanel: () => null
}));

vi.mock("@/components/shared/course-context", () => ({
  CourseSelectionProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  findLibraryCourse: vi.fn(() => null),
  useCourseSelection: () => ({
    library: [],
    selectedCourseId: "course-demo",
    selectedCourse: {
      course_id: "course-demo",
      course_code: "FRM",
      display_name: "FRM",
      description: null,
      created_at: "2026-05-07T10:00:00Z",
      updated_at: "2026-05-07T10:00:00Z"
    },
    selectedModuleId: null,
    selectedModule: null,
    setSelection: vi.fn(async () => undefined),
    isLoading: false,
    error: null
  })
}));

vi.mock("next/navigation", () => ({
  useSearchParams: () => navigationMock.searchParams
}));

afterEach(() => {
  cleanup();
  window.localStorage.clear();
  vi.clearAllMocks();
  navigationMock.searchParams = new URLSearchParams();
});

describe("CourseFlashcardsWorkspace", () => {
  it("lets students freely flip, navigate, browse, and jump through the deck", async () => {
    const user = userEvent.setup();
    render(<CourseFlashcardsWorkspace courseId="course-demo" />);

    expect(await screen.findByRole("heading", { name: "Flashcards" })).toBeInTheDocument();
    expect(await screen.findByText("1 / 3")).toBeInTheDocument();
    expect(
      within(screen.getByRole("button", { name: "Flashcard card. Press to flip." })).getByText("What is risk?")
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Flip card" }));
    expect(screen.getAllByText("Risk is uncertainty surrounding outcomes.").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByText("2 / 3")).toBeInTheDocument();
    expect(
      within(screen.getByRole("button", { name: "Flashcard card. Press to flip." })).getByText(
        "What are the four components of the risk management process?"
      )
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Previous" }));
    expect(screen.getByText("1 / 3")).toBeInTheDocument();

    fireEvent.keyDown(window, { key: " ", code: "Space" });
    expect(screen.getAllByText("Risk is uncertainty surrounding outcomes.").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: "Browse all cards" }));
    const browsePanel = screen.getByRole("region", { name: "Browse flashcards" });
    await user.click(within(browsePanel).getByRole("button", { name: /Jump to card 2/i }));

    expect(screen.getByText("2 / 3")).toBeInTheDocument();
    expect(
      within(screen.getByRole("button", { name: "Flashcard card. Press to flip." })).getByText(
        "What are the four components of the risk management process?"
      )
    ).toBeInTheDocument();
  });

  it("shows transparent side arrow controls for moving through cards", async () => {
    const user = userEvent.setup();
    render(<CourseFlashcardsWorkspace courseId="course-demo" />);

    expect(await screen.findByRole("heading", { name: "Flashcards" })).toBeInTheDocument();
    const reviewCard = screen.getByRole("region", { name: "Flashcard review" });

    expect(within(reviewCard).getByRole("button", { name: "Move left" })).toBeDisabled();
    await user.click(within(reviewCard).getByRole("button", { name: "Move right" }));
    expect(screen.getByText("2 / 3")).toBeInTheDocument();

    await user.click(within(reviewCard).getByRole("button", { name: "Move left" }));
    expect(screen.getByText("1 / 3")).toBeInTheDocument();
  });

  it("aggregates flashcards from study sections and schedules review ratings", async () => {
    const user = userEvent.setup();
    render(<CourseFlashcardsWorkspace courseId="course-demo" />);

    expect(await screen.findByRole("heading", { name: "Flashcards" })).toBeInTheDocument();
    expect(screen.getAllByText("Due Today").length).toBeGreaterThan(0);
    expect(screen.getByText("Need to Review")).toBeInTheDocument();
    expect(screen.getAllByText("What is risk?").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: "Flip card" }));
    expect(screen.getAllByText("Risk is uncertainty surrounding outcomes.").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: "Good" }));

    await waitFor(() => {
      expect(recordFlashcardReview).toHaveBeenCalledWith(
        expect.objectContaining({
          flashcard_id: "flashcard-1",
          rating: "good",
          previous_interval_days: 0,
          new_interval_days: 3,
          previous_confidence_group: "new",
          new_confidence_group: "learning"
        })
      );
      expect(screen.getAllByText("Learning").length).toBeGreaterThan(0);
    });
  });

  it("shows concise bold answers and keeps full source text collapsed", async () => {
    const user = userEvent.setup();
    render(<CourseFlashcardsWorkspace courseId="course-demo" />);

    expect(await screen.findByRole("heading", { name: "Flashcards" })).toBeInTheDocument();
    expect(screen.getAllByText("What is risk?").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Module 1.1: Introduction to Risk Management").length).toBeGreaterThan(0);
    expect(screen.getAllByText("LO 1.a").length).toBeGreaterThan(0);
    const reviewCard = screen.getByRole("region", { name: "Flashcard review" });
    expect(within(reviewCard).queryByText("Definition")).not.toBeInTheDocument();
    expect(within(reviewCard).queryByText("New")).not.toBeInTheDocument();
    expect(within(reviewCard).queryByText("Due Today")).not.toBeInTheDocument();
    expect(within(reviewCard).getByRole("link", { name: "pages 13-18" })).toHaveAttribute(
      "href",
      "/courses/course-demo/materials?materialId=mat-workbook&groupId=reading-1&sectionId=section-1&source=1&sourceId=section-1"
    );
    expect(within(reviewCard).getByRole("link", { name: "Return to module" })).toHaveAttribute(
      "href",
      "/courses/course-demo/materials?materialId=mat-workbook&groupId=reading-1&sectionId=section-1"
    );
    await user.click(screen.getByRole("button", { name: "Flip card" }));

    const conciseAnswer = screen.getByText("Risk is uncertainty surrounding outcomes.");
    expect(conciseAnswer).toBeVisible();
    expect(conciseAnswer.tagName).toBe("STRONG");
    expect(screen.queryByText(/Risk taking refers to the active acceptance/i)).not.toBeInTheDocument();

    const sourceToggle = screen.getByRole("button", { name: /View source excerpt/i });
    await user.click(sourceToggle);
    expect(screen.getByText(/Risk taking refers to the active acceptance/i)).toBeVisible();
  });

  it("shows specific upcoming cards with location metadata only", async () => {
    const user = userEvent.setup();
    render(<CourseFlashcardsWorkspace courseId="course-demo" />);

    expect(await screen.findByRole("heading", { name: "Flashcards" })).toBeInTheDocument();
    const upcoming = screen.getByRole("region", { name: "Upcoming cards" });
    const activeCard = within(upcoming).getByRole("button", { name: /Card 1: What is risk/i });
    expect(activeCard).toHaveAttribute("aria-current", "true");
    expect(within(upcoming).getByText("What is risk?")).toBeVisible();
    expect(
      within(upcoming).getByText("What are the four components of the risk management process?")
    ).toBeVisible();
    expect(within(upcoming).getByText("What is the formula for expected loss?")).toBeVisible();
    expect(within(upcoming).getAllByText("Module 1.1: Introduction to Risk Management").length).toBeGreaterThan(0);
    expect(within(upcoming).getAllByText("LO 1.a").length).toBeGreaterThan(0);
    const upcomingList = upcoming.querySelector(".flashcard-upcoming-list");
    expect(upcomingList).not.toBeNull();
    expect(within(upcomingList as HTMLElement).queryByText("List Recall")).not.toBeInTheDocument();
    expect(within(upcomingList as HTMLElement).queryByText("Definition")).not.toBeInTheDocument();
    expect(within(upcomingList as HTMLElement).queryByText("New")).not.toBeInTheDocument();
    expect(within(upcomingList as HTMLElement).queryByText("Due Today")).not.toBeInTheDocument();
    expect(within(upcoming).getAllByText("pages 13-18").length).toBeGreaterThan(0);

    await user.click(within(upcoming).getByRole("button", { name: /Card 3: What is the formula for expected loss/i }));
    expect(screen.getByText("3 / 3")).toBeInTheDocument();
    expect(window.location.search).toContain("cardId=flashcard-3");
    expect(within(upcoming).getByRole("button", { name: /Card 3: What is the formula for expected loss/i }))
      .toHaveAttribute("aria-current", "true");

    await user.selectOptions(within(upcoming).getByLabelText("Filter upcoming cards"), "due");
    expect(within(upcoming).queryByText("What is the formula for expected loss?")).not.toBeInTheDocument();

    await user.selectOptions(within(upcoming).getByLabelText("Filter upcoming cards"), "all");
    expect(within(upcoming).getByText("What is the formula for expected loss?")).toBeVisible();
  });

  it("starts on cardId from the route so browser navigation can restore position", async () => {
    navigationMock.searchParams = new URLSearchParams("cardId=flashcard-3");
    window.history.replaceState(null, "", "/courses/course-demo/flashcards?cardId=flashcard-3");

    render(<CourseFlashcardsWorkspace courseId="course-demo" />);

    expect(await screen.findByRole("heading", { name: "Flashcards" })).toBeInTheDocument();
    expect(screen.getByText("3 / 3")).toBeInTheDocument();
    expect(screen.getAllByText("What is the formula for expected loss?").length).toBeGreaterThan(0);

    const upcoming = screen.getByRole("region", { name: "Upcoming cards" });
    expect(within(upcoming).getByRole("button", { name: /Card 3: What is the formula for expected loss/i }))
      .toHaveAttribute("aria-current", "true");
  });

  it("filters the browse panel by card type and confidence", async () => {
    const user = userEvent.setup();
    render(<CourseFlashcardsWorkspace courseId="course-demo" />);

    expect(await screen.findByRole("heading", { name: "Flashcards" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Browse all cards" }));
    const browsePanel = screen.getByRole("region", { name: "Browse flashcards" });

    await user.selectOptions(within(browsePanel).getByLabelText("Filter by card type"), "list_recall");
    expect(within(browsePanel).getByRole("button", { name: /four components/i })).toBeInTheDocument();
    expect(within(browsePanel).queryByRole("button", { name: /What is risk/i })).not.toBeInTheDocument();

    await user.selectOptions(within(browsePanel).getByLabelText("Filter by card type"), "all");
    await user.selectOptions(within(browsePanel).getByLabelText("Filter by confidence"), "confident");
    expect(within(browsePanel).getByRole("button", { name: /four components/i })).toBeInTheDocument();
    expect(within(browsePanel).queryByRole("button", { name: /What is risk/i })).not.toBeInTheDocument();
  });

  it("shows module badges and filters browse results by module, learning outcome, formula, and source page", async () => {
    const user = userEvent.setup();
    render(<CourseFlashcardsWorkspace courseId="course-demo" />);

    expect(await screen.findByRole("heading", { name: "Flashcards" })).toBeInTheDocument();
    expect(screen.getAllByText("Module 1.1: Introduction to Risk Management").length).toBeGreaterThan(0);
    expect(screen.getAllByText("LO 1.a").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: "Browse all cards" }));
    const browsePanel = screen.getByRole("region", { name: "Browse flashcards" });

    await user.selectOptions(
      within(browsePanel).getByLabelText("Filter by module"),
      "Module 1.1: Introduction to Risk Management"
    );
    expect(within(browsePanel).getByRole("button", { name: /What is risk/i })).toBeInTheDocument();

    await user.selectOptions(within(browsePanel).getByLabelText("Filter by learning outcome"), "LO 1.a");
    expect(within(browsePanel).getByRole("button", { name: /four components/i })).toBeInTheDocument();

    await user.click(within(browsePanel).getByLabelText("Formula cards only"));
    expect(within(browsePanel).getByRole("button", { name: /formula for expected loss/i })).toBeInTheDocument();
    expect(within(browsePanel).queryByRole("button", { name: /What is risk/i })).not.toBeInTheDocument();

    await user.selectOptions(within(browsePanel).getByLabelText("Filter by source page"), "160");
    expect(within(browsePanel).getByRole("button", { name: /formula for expected loss/i })).toBeInTheDocument();
  });

  it("opens route-scoped decks for a study session or formulas card", async () => {
    navigationMock.searchParams = new URLSearchParams("materialId=mat-workbook&groupId=reading-1");
    render(<CourseFlashcardsWorkspace courseId="course-demo" />);

    expect(await screen.findByRole("heading", { name: "Flashcards" })).toBeInTheDocument();
    expect(fetchMaterialStudy).toHaveBeenCalledWith(
      "mat-workbook",
      expect.objectContaining({ groupId: "reading-1" })
    );
    expect(screen.getByText("1 / 3")).toBeInTheDocument();

    cleanup();
    vi.clearAllMocks();
    navigationMock.searchParams = new URLSearchParams("materialId=mat-workbook&formula=1");
    render(<CourseFlashcardsWorkspace courseId="course-demo" />);

    expect(await screen.findByRole("heading", { name: "Flashcards" })).toBeInTheDocument();
    expect(screen.getByText("1 / 1")).toBeInTheDocument();
    expect(screen.getByText("What is the formula for expected loss?")).toBeInTheDocument();
    expect(screen.queryByText("What is risk?")).not.toBeInTheDocument();
  });

  it("opens route-scoped decks for an exact study section", async () => {
    const secondSection = {
      ...studyResponse.sections[0],
      section_id: "section-2",
      parent_group_id: "reading-2",
      title: "Module 2.1: Corporate Risk Management",
      normalized_title: "Module 2.1: Corporate Risk Management",
      page_start: 30,
      page_end: 35,
      flashcards: [
        {
          ...studyResponse.sections[0].flashcards![0],
          flashcard_id: "flashcard-4",
          module_id: "module-2.1",
          learning_outcome_id: "outcome-2",
          concept_id: "concept-economic-capital",
          front: "What is economic capital?",
          back: "Economic capital is capital held to absorb unexpected losses.",
          back_concise: "Economic capital is capital held to absorb unexpected losses.",
          source_page: 30,
          source_excerpt: "Economic capital helps absorb unexpected losses.",
          confidence_group: "new"
        }
      ]
    };
    vi.mocked(fetchMaterialStudy).mockResolvedValueOnce({
      ...studyResponse,
      sections: [studyResponse.sections[0], secondSection],
      total_sections: 2,
      ready_sections: 2
    });
    navigationMock.searchParams = new URLSearchParams("materialId=mat-workbook&sectionId=section-2");

    render(<CourseFlashcardsWorkspace courseId="course-demo" />);

    expect(await screen.findByRole("heading", { name: "Flashcards" })).toBeInTheDocument();
    expect(screen.getByText("1 / 1")).toBeInTheDocument();
    expect(screen.getByText("What is economic capital?")).toBeInTheDocument();
    expect(screen.queryByText("What is risk?")).not.toBeInTheDocument();
  });

  it("test_upcoming_cards_shows_all_session_cards", async () => {
    render(<CourseFlashcardsWorkspace courseId="course-demo" />);

    expect(await screen.findByRole("heading", { name: "Flashcards" })).toBeInTheDocument();
    const upcoming = screen.getByRole("region", { name: "Upcoming cards" });
    expect(within(upcoming).getByText("What is risk?")).toBeVisible();
    expect(within(upcoming).getByText("What are the four components of the risk management process?")).toBeVisible();
    expect(within(upcoming).getByText("What is the formula for expected loss?")).toBeVisible();
  });

  it("test_clicking_upcoming_card_changes_active_card", async () => {
    const user = userEvent.setup();
    render(<CourseFlashcardsWorkspace courseId="course-demo" />);

    expect(await screen.findByRole("heading", { name: "Flashcards" })).toBeInTheDocument();
    const upcoming = screen.getByRole("region", { name: "Upcoming cards" });
    await user.click(within(upcoming).getByRole("button", { name: /Card 3: What is the formula for expected loss/i }));

    expect(screen.getByText("3 / 3")).toBeInTheDocument();
    expect(window.location.search).toContain("cardId=flashcard-3");
  });

  it("test_active_card_highlighted", async () => {
    render(<CourseFlashcardsWorkspace courseId="course-demo" />);

    expect(await screen.findByRole("heading", { name: "Flashcards" })).toBeInTheDocument();
    const upcoming = screen.getByRole("region", { name: "Upcoming cards" });
    expect(within(upcoming).getByRole("button", { name: /Card 1: What is risk/i }))
      .toHaveAttribute("aria-current", "true");
  });

  it("test_filter_by_module", async () => {
    const user = userEvent.setup();
    render(<CourseFlashcardsWorkspace courseId="course-demo" />);

    expect(await screen.findByRole("heading", { name: "Flashcards" })).toBeInTheDocument();
    const upcoming = screen.getByRole("region", { name: "Upcoming cards" });
    await user.selectOptions(
      within(upcoming).getByLabelText("Filter upcoming cards by module"),
      "Module 1.1: Introduction to Risk Management"
    );

    expect(within(upcoming).getByText("What is risk?")).toBeVisible();
    expect(within(upcoming).getByText("What is the formula for expected loss?")).toBeVisible();
  });

  it("test_filter_by_lo", async () => {
    const user = userEvent.setup();
    render(<CourseFlashcardsWorkspace courseId="course-demo" />);

    expect(await screen.findByRole("heading", { name: "Flashcards" })).toBeInTheDocument();
    const upcoming = screen.getByRole("region", { name: "Upcoming cards" });
    await user.selectOptions(within(upcoming).getByLabelText("Filter upcoming cards by LO"), "LO 1.a");

    expect(within(upcoming).getByText("What is risk?")).toBeVisible();
    expect(within(upcoming).getByText("What are the four components of the risk management process?")).toBeVisible();
  });

  it("filters stale low-quality generated cards before showing the deck", async () => {
    vi.mocked(fetchMaterialStudy).mockResolvedValueOnce({
      ...studyResponse,
      sections: [
        {
          ...studyResponse.sections[0],
          flashcards: [
            ...studyResponse.sections[0].flashcards!,
            {
              ...studyResponse.sections[0].flashcards![0],
              flashcard_id: "flashcard-bad-options",
              module_id: "module-38.1",
              learning_outcome_id: "outcome-38-b",
              concept_id: "concept-options",
              front: "What are because option contracts?",
              back: "Because option contracts have margin rules.",
              back_concise: "Because option contracts have margin rules.",
              card_type: "definition",
              source_page: 138,
              source_excerpt: "Options with maturities of nine months or fewer cannot be purchased on margin."
            },
            {
              ...studyResponse.sections[0].flashcards![0],
              flashcard_id: "flashcard-bad-payment",
              module_id: "module-28.1",
              learning_outcome_id: "outcome-28-e",
              concept_id: "concept-insurance",
              front: "What is payment?",
              back: "Payment.",
              back_concise: "Payment.",
              card_type: "definition",
              source_page: 22,
              source_excerpt: "Insurance companies make payments when covered losses occur."
            },
            {
              ...studyResponse.sections[0].flashcards![0],
              flashcard_id: "flashcard-bad-treasury-assume",
              module_id: "module-45.2",
              learning_outcome_id: "outcome-45-g",
              concept_id: "concept-treasury-futures",
              front: "What is also assume that the Treasury bond futures contract?",
              back: "Treasury bond futures delivery assumptions.",
              back_concise: "Treasury bond futures delivery assumptions.",
              card_type: "definition",
              source_page: 236,
              source_excerpt: "Assume that the Treasury bond futures contract..."
            },
            {
              ...studyResponse.sections[0].flashcards![0],
              flashcard_id: "flashcard-bad-assume-there",
              module_id: "module-45.2",
              learning_outcome_id: "outcome-45-g",
              concept_id: "concept-treasury-futures",
              front: "What are assume that there?",
              back: "Assume that there are delivery options.",
              back_concise: "Assume that there are delivery options.",
              card_type: "definition",
              source_page: 236,
              source_excerpt: "Assume that there..."
            },
            {
              ...studyResponse.sections[0].flashcards![0],
              flashcard_id: "flashcard-bad-quotes",
              module_id: "module-30.1",
              learning_outcome_id: "outcome-30-a",
              concept_id: "concept-quotes",
              front: "What are quotes?",
              back: "Quotes.",
              back_concise: "Quotes.",
              card_type: "definition",
              source_page: 58,
              source_excerpt: "Spot and forward quotes are used in foreign exchange markets."
            },
            {
              ...studyResponse.sections[0].flashcards![0],
              flashcard_id: "flashcard-bad-trading",
              module_id: "module-31.1",
              learning_outcome_id: "outcome-31-a",
              concept_id: "concept-trading",
              front: "What is trading?",
              back: "Trading.",
              back_concise: "Trading.",
              card_type: "definition",
              source_page: 72,
              source_excerpt: "Trading systems route orders through market centers."
            },
            {
              ...studyResponse.sections[0].flashcards![0],
              flashcard_id: "flashcard-bad-borrowers-plural",
              module_id: "module-52.2",
              learning_outcome_id: "outcome-52-h",
              concept_id: "concept-borrowers",
              front: "What are borrowers?",
              back: "Borrowers.",
              back_concise: "Borrowers.",
              card_type: "definition",
              source_page: 77,
              source_excerpt: "Borrowers in the credit portfolio may be correlated."
            },
            {
              ...studyResponse.sections[0].flashcards![0],
              flashcard_id: "flashcard-bad-borrowers-singular",
              module_id: "module-52.2",
              learning_outcome_id: "outcome-52-h",
              concept_id: "concept-borrowers",
              front: "What is borrowers?",
              back: "Borrowers.",
              back_concise: "Borrowers.",
              card_type: "definition",
              source_page: 77,
              source_excerpt: "Borrowers in the credit portfolio may be correlated."
            },
            {
              ...studyResponse.sections[0].flashcards![0],
              flashcard_id: "flashcard-bad-correlations-singular",
              module_id: "module-52.2",
              learning_outcome_id: "outcome-52-h",
              concept_id: "concept-correlations",
              front: "What is correlations?",
              back: "Correlations.",
              back_concise: "Correlations.",
              card_type: "definition",
              source_page: 77,
              source_excerpt: "Correlations between borrowers affect credit portfolio loss."
            },
            {
              ...studyResponse.sections[0].flashcards![0],
              flashcard_id: "flashcard-bad-correlations-plural",
              module_id: "module-52.2",
              learning_outcome_id: "outcome-52-h",
              concept_id: "concept-correlations",
              front: "What are correlations?",
              back: "Correlations.",
              back_concise: "Correlations.",
              card_type: "definition",
              source_page: 77,
              source_excerpt: "Correlations between borrowers affect credit portfolio loss."
            },
            {
              ...studyResponse.sections[0].flashcards![0],
              flashcard_id: "flashcard-good-borrower-risk",
              module_id: "module-52.2",
              learning_outcome_id: "outcome-52-h",
              concept_id: "concept-borrower-concentration-risk",
              front: "What is borrower concentration risk?",
              back: "Borrower concentration risk is elevated exposure to a small group of related borrowers.",
              back_concise: "Borrower concentration risk is elevated exposure to a small group of related borrowers.",
              card_type: "definition",
              source_page: 77,
              source_excerpt: "Borrower concentration risk occurs when credit exposure is concentrated in a small group of related borrowers."
            }
          ]
        }
      ]
    });

    render(<CourseFlashcardsWorkspace courseId="course-demo" />);

    expect(await screen.findByRole("heading", { name: "Flashcards" })).toBeInTheDocument();
    expect(screen.getByText("1 / 4")).toBeInTheDocument();
    expect(screen.queryByText("What are because option contracts?")).not.toBeInTheDocument();
    expect(screen.queryByText("What is payment?")).not.toBeInTheDocument();
    expect(screen.queryByText("What is also assume that the Treasury bond futures contract?")).not.toBeInTheDocument();
    expect(screen.queryByText("What are assume that there?")).not.toBeInTheDocument();
    expect(screen.queryByText("What are quotes?")).not.toBeInTheDocument();
    expect(screen.queryByText("What is trading?")).not.toBeInTheDocument();
    expect(screen.queryByText("What are borrowers?")).not.toBeInTheDocument();
    expect(screen.queryByText("What is borrowers?")).not.toBeInTheDocument();
    expect(screen.queryByText("What is correlations?")).not.toBeInTheDocument();
    expect(screen.queryByText("What are correlations?")).not.toBeInTheDocument();
    expect(screen.getByText("What is borrower concentration risk?")).toBeInTheDocument();
    const upcoming = screen.getByRole("region", { name: "Upcoming cards" });
    expect(within(upcoming).queryByText("What are because option contracts?")).not.toBeInTheDocument();
    expect(within(upcoming).queryByText("What is payment?")).not.toBeInTheDocument();
    expect(within(upcoming).queryByText("What is also assume that the Treasury bond futures contract?")).not.toBeInTheDocument();
    expect(within(upcoming).queryByText("What are assume that there?")).not.toBeInTheDocument();
    expect(within(upcoming).queryByText("What are quotes?")).not.toBeInTheDocument();
    expect(within(upcoming).queryByText("What is trading?")).not.toBeInTheDocument();
    expect(within(upcoming).queryByText("What are borrowers?")).not.toBeInTheDocument();
    expect(within(upcoming).queryByText("What is borrowers?")).not.toBeInTheDocument();
    expect(within(upcoming).queryByText("What is correlations?")).not.toBeInTheDocument();
    expect(within(upcoming).queryByText("What are correlations?")).not.toBeInTheDocument();
    expect(within(upcoming).getByText("What is borrower concentration risk?")).toBeVisible();
  });

  it("lets students create, edit, and delete cards without leaving the deck", async () => {
    const user = userEvent.setup();
    render(<CourseFlashcardsWorkspace courseId="course-demo" />);

    expect(await screen.findByRole("heading", { name: "Flashcards" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Create card" }));
    await user.clear(screen.getByLabelText("Card front"));
    await user.type(screen.getByLabelText("Card front"), "What is tail risk?");
    await user.clear(screen.getByLabelText("Card back"));
    await user.type(screen.getByLabelText("Card back"), "Tail risk is an extreme unexpected loss event.");
    await user.click(screen.getByRole("button", { name: "Save card" }));

    expect(screen.getByText("4 / 4")).toBeInTheDocument();
    expect(screen.getAllByText("What is tail risk?").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: "Edit card" }));
    await user.clear(screen.getByLabelText("Card front"));
    await user.type(screen.getByLabelText("Card front"), "What does tail risk mean?");
    await user.click(screen.getByRole("button", { name: "Save card" }));

    expect(screen.getAllByText("What does tail risk mean?").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: "Delete card" }));
    expect(screen.queryByText("What does tail risk mean?")).not.toBeInTheDocument();
    expect(screen.getByText("1 / 3")).toBeInTheDocument();
  });
});

describe("CourseWorkspaceFrame flashcard tab", () => {
  it("keeps Flashcards out of the crowded top nav while preserving the direct page route", async () => {
    render(
      <CourseWorkspaceFrame courseId="course-demo" activeTab="flashcards">
        <p>Flashcard body</p>
      </CourseWorkspaceFrame>
    );

    expect(await screen.findByText("Flashcard body")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Flashcards" })).not.toBeInTheDocument();
  });
});
