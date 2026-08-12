import React from "react";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CourseMaterialsWorkspace } from "@/components/courses/course-materials-workspace";
import type { CourseMaterialsResponse, MaterialRecord, MaterialStudyResponse, MaterialStudySection } from "@/lib/schemas";

const apiMocks = vi.hoisted(() => ({
  fetchMaterialStudy: vi.fn()
}));

const workbookMaterial: MaterialRecord = {
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
};

const workbookSection: MaterialStudySection = {
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
  workbook_key_concepts: ["LO 1.a Risk is uncertainty surrounding outcomes."],
  workbook_module_quiz: [],
  workbook_answer_key: [],
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
  formulas: [
    {
      formula_id: "formula-expected-loss",
      course_id: "course-demo",
      material_id: "mat-workbook",
      module_id: "module-1.1",
      concept_id: "concept-risk",
      formula_name: "Expected loss",
      formula_text: "EL = EAD x PD x LGD",
      formula_latex: null,
      variables_json: {
        EAD: "Exposure at default",
        PD: "Probability of default",
        LGD: "Loss given default"
      },
      source_page: 160,
      reading_number: 1,
      formula_section_page: 160,
      source_image_crop_path: "/formula-crops/expected-loss.png",
      parse_confidence: "high",
      needs_review: false,
      source_excerpt: "Expected loss: EL = EAD x PD x LGD",
      usage_note: "Use expected loss to calculate credit loss.",
      example_if_available: null,
      content_origin: "original_book"
    }
  ],
  flashcards: [],
  due_flashcard_count: 0,
  mastery_percent: 0,
  weakest_concepts: [],
  difficulty: "medium",
  studied_status: "not_started",
  quiz_ready: true,
  display_order: 1,
  enrichment_status: "completed",
  source_ids: ["source-1"]
};

const courseMaterials: CourseMaterialsResponse = {
  course_id: "course-demo",
  records: [workbookMaterial],
  sections: [],
  quiz_sources: [],
  default_source_ids: [],
  default_quiz_source_ids: []
};

const studyResponse: MaterialStudyResponse = {
  record: workbookMaterial,
  groups: [
    {
      group_id: "reading-1",
      material_id: "mat-workbook",
      title: "Study Session 1 / Reading 1",
      page_start: 13,
      page_end: 39,
      display_order: 0,
      section_count: 1,
      ready_count: 1,
      studied_count: 0
    },
    {
      group_id: "mat-workbook-formulas",
      material_id: "mat-workbook",
      title: "Formulas",
      page_start: 160,
      page_end: 160,
      display_order: 1,
      section_count: 1,
      ready_count: 1,
      studied_count: 0
    }
  ],
  sections: [workbookSection],
  total_sections: 1,
  offset: 0,
  limit: 60,
  has_more: false,
  ready_sections: 1,
  studied_sections: 0
};

const studyResponseWithoutFormulas: MaterialStudyResponse = {
  ...studyResponse,
  groups: studyResponse.groups.filter((group) => group.group_id !== "mat-workbook-formulas"),
  sections: [
    {
      ...workbookSection,
      formulas: []
    }
  ]
};

const formulaOnlyStudyResponse: MaterialStudyResponse = {
  ...studyResponse,
  sections: [
    {
      ...workbookSection,
      section_id: "section-formulas",
      parent_group_id: "mat-workbook-formulas",
      title: "Formulas",
      normalized_title: "Formulas"
    }
  ]
};

let activeStudyResponse = studyResponse;

vi.mock("next/navigation", () => ({
  usePathname: () => "/courses/course-demo/materials",
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn()
  }),
  useSearchParams: () => new URLSearchParams()
}));

vi.mock("@/lib/api", () => ({
  createModule: vi.fn(),
  deleteMaterial: vi.fn(),
  fetchCourseMaterials: vi.fn(async () => courseMaterials),
  fetchMaterialStudy: apiMocks.fetchMaterialStudy,
  fetchMaterialStudySection: vi.fn(async () => ({ section: workbookSection })),
  fetchQuizGenerationJob: vi.fn(),
  generateQuiz: vi.fn(),
  gradeQuiz: vi.fn(),
  markMaterialStudySection: vi.fn(async () => ({ section: workbookSection })),
  reprocessMaterial: vi.fn(async () => ({ material_id: "mat-workbook", status: "completed" })),
  retryMaterialProcessing: vi.fn(),
  trackActivityEvent: vi.fn(),
  uploadMaterial: vi.fn()
}));

vi.mock("@/components/shared/course-context", () => ({
  useCourseSelection: () => ({
    selectedModuleId: null,
    refresh: vi.fn(async () => undefined)
  })
}));

describe("CourseMaterialsWorkspace formula study session", () => {
  beforeEach(() => {
    activeStudyResponse = studyResponse;
    apiMocks.fetchMaterialStudy.mockReset();
    apiMocks.fetchMaterialStudy.mockImplementation(async (_materialId: string, options?: { groupId?: string | null }) => {
      if (options?.groupId === "mat-workbook-formulas") {
        return formulaOnlyStudyResponse;
      }
      return activeStudyResponse;
    });
  });

  afterEach(() => {
    cleanup();
  });

  it("shows a dedicated Formulas card and opens grouped formula study tools", async () => {
    window.localStorage.clear();
    const user = userEvent.setup();
    const { container } = render(<CourseMaterialsWorkspace courseId="course-demo" />);

    await user.click(await screen.findByRole("button", { name: /FRM 2025 Part 1 KAPLAN Book 1\.PDF/i }));

    const readingCard = await screen.findByRole("article", { name: /Study Session 1 \/ Reading 1/i });
    expect(within(readingCard).queryByRole("link", { name: "Study cards" })).not.toBeInTheDocument();

    const formulasCard = await screen.findByRole("article", { name: /Formulas study session/i });
    const gridCards = Array.from(container.querySelectorAll(".book-module-grid > article"));
    expect(screen.queryByRole("article", { name: /^Formulas study session$/ })).toBeInTheDocument();
    expect(gridCards.at(-1)).toHaveAttribute("aria-label", "Formulas study session");
    expect(gridCards).toHaveLength(2);
    expect(within(formulasCard).getByRole("heading", { name: "Formulas" })).toBeInTheDocument();
    expect(within(formulasCard).getByText(/Official formula sheet \/ extracted formulas/i)).toBeInTheDocument();
    expect(within(formulasCard).getByText(/page 160/i)).toBeInTheDocument();
    expect(within(formulasCard).getByText(/ready/i)).toBeInTheDocument();
    expect(within(formulasCard).getByRole("button", { name: /Study formulas/i })).toBeInTheDocument();
    expect(within(formulasCard).getByRole("button", { name: /Practice formulas/i })).toBeInTheDocument();
    expect(within(formulasCard).getByRole("button", { name: /Open source/i })).toBeInTheDocument();
    expect(within(formulasCard).getByRole("link", { name: /Study formula cards/i })).toHaveAttribute(
      "href",
      "/courses/course-demo/flashcards?materialId=mat-workbook&formula=1"
    );

    await user.click(within(readingCard).getByRole("button", { name: /Study Session 1 \/ Reading 1/i }));
    const sectionCardsLink = await screen.findByRole("link", { name: "Study cards" });
    expect(sectionCardsLink).toHaveAttribute(
      "href",
      "/courses/course-demo/flashcards?materialId=mat-workbook&sectionId=section-1"
    );

    await user.click(await screen.findByRole("button", { name: /Back to book/i }));

    const restoredFormulasCard = await screen.findByRole("article", { name: /Formulas study session/i });
    await user.click(within(restoredFormulasCard).getByRole("button", { name: /Study formulas/i }));

    expect(apiMocks.fetchMaterialStudy).toHaveBeenCalledWith(
      "mat-workbook",
      expect.objectContaining({ groupId: "mat-workbook-formulas" })
    );
    expect(await screen.findByRole("heading", { name: "Formulas" })).toBeInTheDocument();
    expect(screen.getByText(/Official formula sheet \/ extracted formulas/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Reading 1/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Expected loss/i })).toBeInTheDocument();
    expect(screen.getByText(/EL = EAD x PD x LGD/i)).toBeInTheDocument();
    expect(screen.getByText(/Probability of default/i)).toBeInTheDocument();
    expect(screen.getByAltText(/Expected loss source crop/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Create Flashcard/i }));
    const savedCards = JSON.parse(window.localStorage.getItem("exam-prep-flashcard-custom:course-demo") ?? "[]");
    expect(savedCards).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          flashcard_id: "formula-formula-expected-loss",
          formula_id: "formula-expected-loss",
          front: "What is the formula for Expected loss?",
          back_concise: "EL = EAD x PD x LGD",
          source_page: 160
        })
      ])
    );
    expect(screen.getByRole("button", { name: /Practice Calculation/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Open Source Page/i })).toBeInTheDocument();
  });

  it("keeps a final Formulas card visible when no formulas were detected yet", async () => {
    activeStudyResponse = studyResponseWithoutFormulas;
    const { container } = render(<CourseMaterialsWorkspace courseId="course-demo" />);

    await userEvent.click(await screen.findByRole("button", { name: /FRM 2025 Part 1 KAPLAN Book 1\.PDF/i }));

    const formulasCard = await screen.findByRole("article", { name: /Formulas study session/i });
    const gridCards = Array.from(container.querySelectorAll(".book-module-grid > article"));
    expect(gridCards.at(-1)).toHaveAttribute("aria-label", "Formulas study session");
    expect(within(formulasCard).getByText(/No formulas detected yet/i)).toBeInTheDocument();
    expect(within(formulasCard).getByRole("button", { name: /Study formulas/i })).toBeInTheDocument();
    expect(within(formulasCard).getByRole("button", { name: /Practice formulas/i })).toBeDisabled();
    expect(within(formulasCard).getByRole("button", { name: /Open source/i })).toBeDisabled();
  });
});
