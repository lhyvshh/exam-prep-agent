import React from "react";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CourseMaterialsWorkspace, StudySectionModal } from "@/components/courses/course-materials-workspace";
import type {
  CourseMaterialsResponse,
  MaterialRecord,
  MaterialStudyResponse,
  MaterialStudySection,
  QuizBundle,
  QuizGenerationJobResponse
} from "@/lib/schemas";

const navigationMock = vi.hoisted(() => ({
  search: "",
  replace: vi.fn(),
  push: vi.fn()
}));

const courseSelectionMock = vi.hoisted(() => ({
  selectedModuleId: null as string | null,
  refresh: vi.fn()
}));

const apiMocks = vi.hoisted(() => ({
  createModule: vi.fn(),
  deleteMaterial: vi.fn(),
  fetchCourseMaterials: vi.fn(),
  fetchMaterialStudy: vi.fn(),
  fetchMaterialStudySection: vi.fn(),
  fetchQuizGenerationJob: vi.fn(),
  generateQuiz: vi.fn(),
  gradeQuiz: vi.fn(),
  markMaterialStudySection: vi.fn(),
  reprocessMaterial: vi.fn(),
  retryMaterialProcessing: vi.fn(),
  trackActivityEvent: vi.fn(),
  uploadMaterial: vi.fn()
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/courses/course-demo/materials",
  useRouter: () => ({
    push: navigationMock.push,
    replace: navigationMock.replace
  }),
  useSearchParams: () => new URLSearchParams(navigationMock.search)
}));

vi.mock("@/components/shared/course-context", () => ({
  useCourseSelection: () => courseSelectionMock
}));

vi.mock("@/lib/api", () => apiMocks);

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  navigationMock.search = "";
  courseSelectionMock.selectedModuleId = null;
});

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

const officialWorkbookSection: MaterialStudySection = {
  section_id: "section-1",
  material_id: "mat-workbook",
  parent_group_id: "reading-1",
  title: "Module 1.2: Types of Risk",
  normalized_title: "Module 1.2: Types of Risk",
  page_start: 21,
  page_end: 39,
  source_anchor: "FRM 2025 Part 1 KAPLAN Book 1.PDF | Module 1.2: Types of Risk",
  summary: "Generated summary should not be shown for official workbook sections.",
  key_points: ["Generated key concept should not render."],
  memorize_keywords: ["Generated keyword"],
  memorize_functions_or_formulas: ["Generated formula"],
  traps: ["Generated trap"],
  workbook_key_concepts: [
    "LO 1.a Risk is uncertainty surrounding outcomes.",
    "LO 1.b The risk management process has four components."
  ],
  workbook_module_quiz: [
    "MODULE QUIZ 1.2",
    "1. In considering the major classes of risks, which risk would best describe weak internal controls?",
    "A. Business risk.",
    "B. Legal and regulatory risk.",
    "C. Operational risk.",
    "D. Strategic risk."
  ],
  workbook_answer_key: [
    "Module Quiz 1.2",
    "1. C Operational risk includes failed internal processes and controls."
  ],
  original_book_content: {
    key_concepts: [
      {
        item_id: "section-1-key-concept-1",
        title: "LO 1.a",
        content: "LO 1.a\nRisk is uncertainty surrounding outcomes.",
        source_pages: [21],
        original_order: 1,
        content_origin: "original_book",
        source_block_ids: ["source-1"]
      }
    ],
    module_quiz: [
      {
        item_id: "section-1-module-quiz-1",
        title: "Original Module Quiz",
        content: [
          "MODULE QUIZ 1.2",
          "1. In considering the major classes of risks, which risk would best describe weak internal controls?",
          "A. Business risk.",
          "B. Legal and regulatory risk.",
          "C. Operational risk.",
          "D. Strategic risk."
        ].join("\n"),
        source_pages: [21],
        original_order: 1,
        content_origin: "original_book",
        source_block_ids: ["source-1"]
      }
    ],
    answers: [
      {
        item_id: "section-1-answer-1",
        title: "Question 1 answer",
        content: "1. C Operational risk includes failed internal processes and controls.",
        source_pages: [21],
        original_order: 1,
        content_origin: "original_book",
        source_block_ids: ["source-1"]
      }
    ]
  },
  learning_outcomes: [
    {
      outcome_id: "outcome-1",
      outcome_title: "LO 1.a",
      content_origin: "original_book",
      related_original_key_concept_ids: ["section-1-key-concept-1"],
      concepts: [],
      completion_status: "not_started",
      confidence_score: 0
    }
  ],
  concepts: [
    {
      concept_id: "concept-1",
      material_id: "mat-workbook",
      module_id: null,
      title: "Risk uncertainty",
      learning_outcome: "LO 1.a",
      related_original_key_concept_id: "section-1-key-concept-1",
      source_pages: [21],
      source_excerpt: "Risk is uncertainty surrounding outcomes.",
      simplified_explanation: "Risk is uncertainty surrounding outcomes.",
      key_terms: ["Risk", "Uncertainty"],
      formulas: [],
      exam_focus: "Study the original key concept first.",
      common_traps: [],
      difficulty_level: "medium",
      mastery_score: 0,
      content_origin: "ai_generated_from_original"
    }
  ],
  formulas: [
    {
      formula_id: "formula-expected-loss",
      course_id: "course-demo",
      material_id: "mat-workbook",
      module_id: null,
      concept_id: "concept-1",
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
      source_excerpt: "EL = EAD x PD x LGD",
      usage_note: "Use expected loss to calculate credit loss from exposure, probability, and severity.",
      example_if_available: null,
      content_origin: "original_book"
    }
  ],
  flashcards: [
    {
      flashcard_id: "flashcard-1",
      material_id: "mat-workbook",
      module_id: null,
      learning_outcome_id: "section-1-key-concept-1",
      concept_id: "concept-1",
      front: "What is risk?",
      back: "Risk is uncertainty surrounding outcomes.",
      card_type: "definition",
      source_page: 21,
      source_excerpt: "Risk is uncertainty surrounding outcomes.",
      difficulty: "medium",
      confidence_group: "new",
      interval_days: 0,
      ease_factor: 2.5,
      repetitions: 0,
      due_at: null,
      last_reviewed_at: null,
      archived: false,
      content_origin: "ai_generated_from_original",
      needs_more_source: true
    }
  ],
  due_flashcard_count: 1,
  mastery_percent: 0,
  weakest_concepts: ["Risk uncertainty"],
  difficulty: "medium",
  studied_status: "not_started",
  quiz_ready: true,
  display_order: 1,
  enrichment_status: "completed",
  source_ids: ["source-1"]
};

describe("StudySectionModal workbook rendering", () => {
  it("shows only official workbook tabs instead of generated study fields", async () => {
    render(
      <StudySectionModal
        defaultPosition={{ x: 0, y: 0 }}
        isActive
        positionKey="test"
        state={{ material: workbookMaterial, section: officialWorkbookSection }}
        zIndex={80}
        onClose={vi.fn()}
        onFocus={vi.fn()}
        onMarkStudied={vi.fn()}
        onMinimize={vi.fn()}
        onOpenSource={vi.fn()}
        onQuiz={vi.fn()}
      />
    );

    expect(screen.queryByText(/Generated summary should not be shown/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Generated key concept should not render/i)).not.toBeInTheDocument();
    expect(screen.getAllByText(/Original from Book/i).length).toBeGreaterThan(0);
    expect(screen.getByRole("tab", { name: /Key Concepts/i })).toBeInTheDocument();
    expect(screen.getAllByText(/LO 1\.a/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Risk is uncertainty surrounding outcomes/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/AI-Generated Study Layer/i)).toBeInTheDocument();
    expect(screen.getByText(/What is risk\?/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Expected loss/i })).toBeInTheDocument();
    expect(screen.getByText(/EL = EAD x PD x LGD/i)).toBeInTheDocument();
    expect(screen.getByText(/Probability of default/i)).toBeInTheDocument();
    expect(screen.getAllByText(/page 160/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/Reading 1/i)).toBeInTheDocument();
    expect(screen.getByText(/Formula source page 160/i)).toBeInTheDocument();
    expect(screen.getByText(/High confidence/i)).toBeInTheDocument();
    expect(screen.getByAltText(/Expected loss source crop/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Practice Calculation/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Create Flashcard/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Open Source Page/i })).toBeInTheDocument();
    expect(screen.getByText(/Flashcard coverage by LO/i)).toBeInTheDocument();
    const coveragePanel = screen.getByLabelText(/Flashcard coverage by learning outcome/i);
    expect(within(coveragePanel).getByText(/LO 1\.a/i)).toBeInTheDocument();
    expect(within(coveragePanel).getByText(/1 \/ 10 cards/i)).toBeInTheDocument();
    expect(within(coveragePanel).getByText(/Needs more source/i)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("tab", { name: /Module Quiz/i }));

    expect(screen.getByText(/MODULE QUIZ 1\.2/i)).toBeInTheDocument();
    expect(screen.getByText(/which risk would best describe weak internal controls/i)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("tab", { name: /Answers/i }));

    expect(screen.getByText(/Operational risk includes failed internal processes/i)).toBeInTheDocument();
  });

  it("deduplicates flashcard coverage rows by learning outcome label", () => {
    render(
      <StudySectionModal
        defaultPosition={{ x: 0, y: 0 }}
        isActive
        positionKey="test"
        state={{
          material: workbookMaterial,
          section: {
            ...officialWorkbookSection,
            learning_outcomes: [
              ...(officialWorkbookSection.learning_outcomes ?? []),
              {
                outcome_id: "outcome-1-duplicate",
                outcome_title: "LO 1.a Risk uncertainty",
                content_origin: "original_book",
                related_original_key_concept_ids: ["section-1-key-concept-1"],
                concepts: [],
                completion_status: "not_started",
                confidence_score: 0
              }
            ]
          }
        }}
        zIndex={80}
        onClose={vi.fn()}
        onFocus={vi.fn()}
        onMarkStudied={vi.fn()}
        onMinimize={vi.fn()}
        onOpenSource={vi.fn()}
        onQuiz={vi.fn()}
      />
    );

    const coveragePanel = screen.getByLabelText(/Flashcard coverage by learning outcome/i);

    expect(within(coveragePanel).getAllByText(/^LO 1\.a$/i)).toHaveLength(1);
  });

  it("clears stale needs-source coverage badges once an LO reaches ten cards", () => {
    const tenCards = Array.from({ length: 10 }, (_, index) => ({
      ...officialWorkbookSection.flashcards![0],
      flashcard_id: `flashcard-balanced-${index + 1}`,
      front: `What is risk concept ${index + 1}?`,
      needs_more_source: index === 0
    }));

    render(
      <StudySectionModal
        defaultPosition={{ x: 0, y: 0 }}
        isActive
        positionKey="test"
        state={{
          material: workbookMaterial,
          section: {
            ...officialWorkbookSection,
            flashcards: tenCards
          }
        }}
        zIndex={80}
        onClose={vi.fn()}
        onFocus={vi.fn()}
        onMarkStudied={vi.fn()}
        onMinimize={vi.fn()}
        onOpenSource={vi.fn()}
        onQuiz={vi.fn()}
      />
    );

    const coveragePanel = screen.getByLabelText(/Flashcard coverage by learning outcome/i);

    expect(within(coveragePanel).getByText(/10 \/ 10 cards/i)).toBeInTheDocument();
    expect(within(coveragePanel).queryByText(/Needs more source/i)).not.toBeInTheDocument();
  });
});

describe("CourseMaterialsWorkspace floating quiz window", () => {
  it("keeps the generated quiz visible after minimizing and restoring the quiz window", async () => {
    navigationMock.search = "materialId=mat-workbook&groupId=all-sections";
    const user = userEvent.setup();
    const materialsResponse: CourseMaterialsResponse = {
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
          group_id: "all-sections",
          material_id: workbookMaterial.material_id,
          title: "All study sections",
          page_start: 21,
          page_end: 39,
          display_order: 1,
          section_count: 1,
          ready_count: 1,
          studied_count: 0
        }
      ],
      sections: [officialWorkbookSection],
      total_sections: 1,
      ready_sections: 1,
      studied_sections: 0,
      offset: 0,
      limit: 30,
      has_more: false
    };
    const quiz: QuizBundle = {
      quiz_id: "quiz-demo",
      course_id: "course-demo",
      module_id: null,
      query: "Section practice: Module 1.2: Types of Risk",
      created_at: "2026-06-25T13:00:00Z",
      record_type: "quiz",
      questions: [
        {
          question_id: "quiz-demo-q1",
          question_type: "mcq",
          concept: "Operational risk",
          section_title: "Module 1.2: Types of Risk",
          difficulty: 0.6,
          prompt: "Which situation best illustrates operational risk?",
          options: [
            { option_id: "A", text: "A failed internal control process" },
            { option_id: "B", text: "A decline in market interest rates" },
            { option_id: "C", text: "A planned strategic acquisition" },
            { option_id: "D", text: "A new competitor entering the market" }
          ],
          citations: [],
          rationale: "Operational risk includes failed internal processes.",
          quality_validation: {
            score: 0.91,
            confidence: 0.82,
            label: "high_quality",
            accepted_for_delivery: true,
            model_version: "question-quality-test",
            model_source: "pytorch_checkpoint",
            notes: ["Question structure and grounding signals look strong."]
          }
        }
      ]
    };
    const completedJob: QuizGenerationJobResponse = {
      job_id: "job-demo",
      dedupe_key: "dedupe-demo",
      status: "completed",
      provider: "openai",
      model: "gpt-5.4-mini",
      request_payload: {
        course_id: "course-demo",
        module_id: null,
        query: "Section practice: Module 1.2: Types of Risk",
        question_count: 1,
        question_types: ["mcq"],
        retrieval_top_k: 6,
        selected_source_ids: ["source-1"],
        scope: {
          course_id: "course-demo",
          module_ids: [],
          material_ids: ["mat-workbook"],
          section_ids: ["section-1"],
          source_type: "study_material"
        },
        client_request_id: "section-modal-section-1-1"
      },
      progress: {
        total_questions: 1,
        completed_questions: 1,
        fallback_questions: 0,
        current_question_index: 1
      },
      partial_results: [],
      quiz,
      error_summary: null,
      created_at: "2026-06-25T13:00:00Z",
      started_at: "2026-06-25T13:00:00Z",
      completed_at: "2026-06-25T13:00:01Z",
      last_heartbeat_at: "2026-06-25T13:00:01Z"
    };

    apiMocks.fetchCourseMaterials.mockResolvedValue(materialsResponse);
    apiMocks.fetchMaterialStudy.mockResolvedValue(studyResponse);
    apiMocks.trackActivityEvent.mockResolvedValue(undefined);
    apiMocks.generateQuiz.mockResolvedValue({
      job_id: "job-demo",
      status: "queued",
      created_at: "2026-06-25T13:00:00Z",
      dedupe_key: "dedupe-demo"
    });
    apiMocks.fetchQuizGenerationJob.mockResolvedValue(completedJob);

    render(<CourseMaterialsWorkspace courseId="course-demo" />);

    await user.click(await screen.findByRole("button", { name: /Quiz this section/i }));
    await user.click(screen.getByRole("button", { name: /Generate quiz/i }));

    expect(await screen.findByText(/Which situation best illustrates operational risk/i)).toBeInTheDocument();
    expect(screen.getByText("Quality checked")).toBeInTheDocument();
    expect(screen.queryByText(/PyTorch quality/i)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Minimize/i }));
    expect(screen.getByRole("navigation", { name: /Minimized study windows/i })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Module 1\.2: Types of Risk/i }));

    await waitFor(() => {
      expect(screen.getByText(/Which situation best illustrates operational risk/i)).toBeVisible();
    });
    expect(screen.queryByText(/Ready to generate/i)).not.toBeInTheDocument();
  });
});
