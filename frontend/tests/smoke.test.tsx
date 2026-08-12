import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ConfigForm } from "@/components/config/config-form";
import { CourseSelectionProvider } from "@/components/shared/course-context";
import { DashboardShell } from "@/components/dashboard/dashboard-shell";
import { MockExamWorkspace } from "@/components/exams/mock-exam-workspace";
import { ExamReview } from "@/components/history/exam-review";
import { HistoryReview } from "@/components/history/history-review";
import { MaterialsWorkspace } from "@/components/materials/materials-workspace";
import { QuizWorkspace } from "@/components/quiz/quiz-workspace";
import { WrongQuestionReview } from "@/components/review/wrong-question-review";
import type {
  CourseMaterialsResponse,
  MaterialLibraryResponse,
  MaterialRecord,
  MaterialStudyResponse,
  MaterialSectionSummary,
  ModuleRecord,
  QuizSourceSummary
} from "@/lib/schemas";

const fetchMock = vi.fn();

vi.stubGlobal("fetch", fetchMock);

function mockJsonResponse(payload: unknown): { ok: true; json: () => Promise<unknown> } {
  return {
    ok: true,
    json: async () => payload
  };
}

function buildWorkflowResponse(
  courseId: string | null,
  moduleId: string | null = null,
  materialIds: string[] = [],
): Record<string, unknown> {
  return {
    workflow_id: "current",
    course_id: courseId,
    module_id: moduleId,
    graph_state: {
      course_id: courseId,
      module_id: moduleId,
      material_ids: materialIds,
      grounding_context: [],
      active_quiz: null,
      mastery_by_concept: {},
      wrong_concepts: [],
      execution_trace: []
    },
    material_count: materialIds.length,
    has_active_course: Boolean(courseId),
    available_course_ids: courseId ? [courseId] : []
  };
}

function buildCourseLibraryResponse(
  rootMaterials: MaterialRecord[] = [],
  modules: Array<{ module: ModuleRecord; materials: MaterialRecord[] }> = [],
): MaterialLibraryResponse {
  return {
    courses: [
      {
        course: {
          course_id: "course-demo",
          course_code: "101",
          display_name: "Demo Course",
          description: "A demo course"
        },
        usage: {
          material_count: rootMaterials.length + modules.flatMap((item) => item.materials).length,
          section_count: rootMaterials.reduce((total, material) => total + material.section_count, 0) +
            modules.flatMap((item) => item.materials).reduce((total, material) => total + material.section_count, 0),
          quiz_count: 0,
          attempt_count: 0,
          wrong_question_count: 0
        },
        root_materials: rootMaterials,
        modules: modules.map((item) => ({
          ...item,
          usage: {
            material_count: item.materials.length,
            section_count: item.materials.reduce((total, material) => total + material.section_count, 0),
            quiz_count: 0,
            attempt_count: 0,
            wrong_question_count: 0
          }
        }))
      }
    ]
  };
}

function buildMaterialsResponse(
  records: MaterialRecord[],
  sections: MaterialSectionSummary[],
  quizSources: QuizSourceSummary[],
): CourseMaterialsResponse {
  return {
    course_id: "course-demo",
    records,
    sections,
    quiz_sources: quizSources,
    default_source_ids: quizSources.flatMap((source) => source.source_ids),
    default_quiz_source_ids: quizSources.filter((source) => source.is_default).map((source) => source.quiz_source_id)
  };
}

async function renderWithCourseContext(element: JSX.Element): Promise<void> {
  render(<CourseSelectionProvider>{element}</CourseSelectionProvider>);
}

const baseRecord: MaterialRecord = {
  material_id: "mat-1",
  course_id: "course-demo",
  module_id: null,
  file_name: "notes.txt",
  display_name: "Demo Notes",
  file_path: "/tmp/notes.txt",
  uploaded_at: "2026-04-13T10:00:00Z",
  content_type: "text/plain",
  status: "completed",
  chunk_count: 1,
  section_count: 1,
  error_message: null
};

const baseSection: MaterialSectionSummary = {
  source_id: "mat-1-section-1",
  material_id: "mat-1",
  course_id: "course-demo",
  module_id: null,
  file_name: "notes.txt",
  content_type: "text/plain",
  section_title: "Gradient Descent Basics",
  section_kind: "instructional",
  content_label: "testable_content",
  priority_score: 0.9,
  is_default: true,
  citation_label: "notes.txt | Gradient Descent Basics",
  locator: {
    section_index: 1,
    page_number: 1,
    slide_number: null,
    paragraph_index: null,
    char_start: null,
    char_end: null
  }
};

const baseQuizSource: QuizSourceSummary = {
  quiz_source_id: "mat-1-quiz-source-1",
  material_id: "mat-1",
  course_id: "course-demo",
  module_id: null,
  file_name: "notes.txt",
  title: "Gradient packet · pages 1-3",
  summary: "Gradient Descent Basics | Worked example | Learning rate notes",
  source_ids: ["mat-1-section-1"],
  section_count: 3,
  section_kind: "instructional",
  content_label: "testable_content",
  priority_score: 0.9,
  is_default: true,
  citation_label: "notes.txt | Gradient packet · pages 1-3",
  location_label: "pages 1-3",
  locator: {
    section_index: 1,
    page_number: 1,
    slide_number: null,
    paragraph_index: null,
    char_start: null,
    char_end: null
  }
};

const baseStudyResponse: MaterialStudyResponse = {
  record: {
    ...baseRecord,
    page_count: 3,
    processing_status: "ready",
    processing_progress: 100,
    outline_status: "completed",
    enrichment_status: "completed",
    last_processed_at: "2026-04-13T10:00:00Z",
    content_hash: "demo-hash"
  },
  groups: [
    {
      group_id: "mat-1-group-1",
      material_id: "mat-1",
      title: "Gradient Descent",
      page_start: 1,
      page_end: 3,
      display_order: 1,
      section_count: 1,
      ready_count: 1,
      studied_count: 0
    }
  ],
  sections: [
    {
      section_id: "mat-1-study-section-1",
      material_id: "mat-1",
      parent_group_id: "mat-1-group-1",
      title: "Gradient Descent Basics",
      normalized_title: "Gradient Descent Basics",
      page_start: 1,
      page_end: 3,
      source_anchor: "notes.txt | Gradient Descent Basics",
      summary: "Gradient descent updates model parameters by moving against the gradient. For exams, remember how the learning rate controls update size and convergence behavior.",
      key_points: [
        "The gradient points in the direction of steepest increase.",
        "The update step subtracts a scaled gradient from the current parameters."
      ],
      memorize_keywords: ["gradient", "learning rate", "convergence"],
      memorize_functions_or_formulas: ["theta_next = theta - alpha * gradient"],
      traps: ["Do not confuse the gradient direction with the descent update direction."],
      difficulty: "medium",
      studied_status: "not_started",
      quiz_ready: true,
      display_order: 1,
      enrichment_status: "completed",
      source_ids: ["mat-1-section-1"]
    }
  ],
  total_sections: 1,
  ready_sections: 1,
  studied_sections: 0,
  offset: 0,
  limit: 12,
  has_more: false
};

afterEach(() => {
  fetchMock.mockReset();
  window.localStorage.clear();
  cleanup();
});

describe("ConfigForm", () => {
  it("renders and validates demo-mode configuration", async () => {
    fetchMock
      .mockResolvedValueOnce(
        mockJsonResponse({
          config: {
            provider: "openai",
            model: "gpt-4.1-mini",
            api_key: null,
            demo_mode: true
          },
          source: "settings_default"
        })
      )
      .mockResolvedValueOnce(
        mockJsonResponse({
          ok: false,
          status: "missing_config",
          config_present: false
        })
      )
      .mockResolvedValueOnce(
        mockJsonResponse({
          is_valid: true,
          status: "demo_ready",
          message: "Demo mode is enabled. The system can proceed without a live API key.",
          config: {
            provider: "openai",
            model: "gpt-4.1-mini",
            api_key: null,
            demo_mode: true
          },
          can_proceed: true
        })
      )
      .mockResolvedValueOnce(
        mockJsonResponse({
          ok: true,
          status: "demo_mode",
          config_present: true
        })
      );

    render(<ConfigForm />);

    expect(await screen.findByLabelText("Provider")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Validate configuration" }));

    expect(await screen.findByText(/Demo mode is enabled/i)).toBeInTheDocument();
    expect(await screen.findByText(/Runtime/i)).toBeInTheDocument();
  });

  it("shows separate model setup profiles for practice generation, Butler, and parser agents", async () => {
    fetchMock
      .mockResolvedValueOnce(
        mockJsonResponse({
          config: {
            provider: "openai",
            model: "gpt-5.4-mini",
            api_key: null,
            demo_mode: true
          },
          butler_config: {
            provider: "openai",
            model: "gpt-5.4",
            api_key: null,
            demo_mode: true
          },
          parser_config: {
            provider: "openai",
            model: "gpt-5.4-parser",
            api_key: null,
            demo_mode: true
          },
          source: "settings_default"
        })
      )
      .mockResolvedValueOnce(
        mockJsonResponse({
          ok: true,
          status: "demo_mode",
          config_present: true
        })
      );

    render(<ConfigForm />);

    expect(await screen.findByRole("button", { name: "Practice generator" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Set up model for Butler" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Set up model for parser agents" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Set up model for Butler" }));

    expect(screen.getByDisplayValue("gpt-5.4")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Set up model for parser agents" }));

    expect(screen.getByDisplayValue("gpt-5.4-parser")).toBeInTheDocument();
  });

  it("ignores duplicate validate clicks while a request is in flight", async () => {
    let resolveValidation: (value: unknown) => void = () => {
      throw new Error("Validation resolver was not initialized.");
    };
    const pendingValidation = new Promise<unknown>((resolve) => {
      resolveValidation = resolve;
    });

    fetchMock
      .mockResolvedValueOnce(
        mockJsonResponse({
          config: {
            provider: "nvidia",
            model: "meta/llama-3.1-8b-instruct",
            api_key: "nvapi-test-key",
            demo_mode: false
          },
          source: "sqlite_store"
        })
      )
      .mockResolvedValueOnce(
        mockJsonResponse({
          ok: true,
          status: "ready",
          config_present: true
        })
      )
      .mockImplementationOnce(async () => pendingValidation)
      .mockResolvedValueOnce(
        mockJsonResponse({
          ok: true,
          status: "ready",
          config_present: true
        })
      );

    render(<ConfigForm />);

    const button = (await screen.findAllByRole("button", { name: "Validate configuration" }))[0];
    await userEvent.click(button);
    await userEvent.click(button);

    expect(fetchMock).toHaveBeenCalledTimes(3);

    resolveValidation({
      ok: true,
      json: async () => ({
        is_valid: true,
        status: "valid",
        message: "Live provider validation succeeded.",
        config: {
          provider: "nvidia",
          model: "meta/llama-3.1-8b-instruct",
          api_key: "nvapi-test-key",
          demo_mode: false
        },
        can_proceed: true
      })
    });

    expect(await screen.findByText(/Live provider validation succeeded/i)).toBeInTheDocument();
  });
});

describe("MaterialsWorkspace", () => {
  it("uploads a file and renders a section study workspace", async () => {
    const emptyMaterials = buildMaterialsResponse([], [], []);
    const populatedMaterials = buildMaterialsResponse([baseRecord], [baseSection], [baseQuizSource]);

    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      const method = init?.method ?? "GET";

      if (url.endsWith("/api/v1/workflow/current")) {
        return mockJsonResponse(
          method === "POST"
            ? buildWorkflowResponse("course-demo", null, ["mat-1"])
            : buildWorkflowResponse("course-demo")
        );
      }

      if (url.endsWith("/api/v1/courses/library")) {
        return mockJsonResponse(
          fetchMock.mock.calls.some((call) => String(call[0]).endsWith("/api/v1/materials/upload"))
            ? buildCourseLibraryResponse([baseRecord])
            : buildCourseLibraryResponse()
        );
      }

      if (url.includes("/api/v1/materials/course/course-demo")) {
        return mockJsonResponse(
          fetchMock.mock.calls.some((call) => String(call[0]).endsWith("/api/v1/materials/upload"))
            ? populatedMaterials
            : emptyMaterials
        );
      }

      if (url.endsWith("/api/v1/materials/upload")) {
        return mockJsonResponse({
          record: baseRecord
        });
      }

      if (url.endsWith("/api/v1/materials/mat-1/study/sections/mat-1-study-section-1/quiz")) {
        return mockJsonResponse({
          job_id: "job-section-1",
          status: "queued",
          dedupe_key: "section-dedupe",
          created_at: "2026-04-20T10:00:00Z",
          updated_at: "2026-04-20T10:00:00Z"
        });
      }

      if (url.includes("/api/v1/materials/mat-1/study")) {
        return mockJsonResponse(baseStudyResponse);
      }

      return mockJsonResponse({});
    });

    await renderWithCourseContext(<MaterialsWorkspace />);

    const file = new File(["# Topic\nAlpha beta gamma"], "notes.txt", {
      type: "text/plain"
    });

    await userEvent.upload(screen.getByLabelText("Document file"), file);
    await userEvent.click(screen.getByRole("button", { name: "Upload material" }));

    expect(await screen.findByText("Gradient Descent Basics")).toBeInTheDocument();
    expect(await screen.findByText(/Gradient descent updates model parameters/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Study section" }));
    expect(await screen.findByText("Quoted page")).toBeInTheDocument();
    expect(screen.getByAltText("Gradient Descent Basics quoted page")).toHaveAttribute(
      "src",
      "/api/v1/materials/mat-1/pages/1/image?width=900"
    );
    await userEvent.click(screen.getByRole("button", { name: "Quiz this section" }));
    expect(
      fetchMock.mock.calls.some((call) =>
        String(call[0]).endsWith("/api/v1/materials/mat-1/study/sections/mat-1-study-section-1/quiz")
      )
    ).toBe(true);
    expect(fetchMock.mock.calls.some((call) => call[0] === "/api/v1/materials/upload")).toBe(true);
  });

  it("allows reprocessing a material that is stuck before completion", async () => {
    const extractingRecord: MaterialRecord = {
      ...baseRecord,
      status: "processing",
      section_count: 0,
      chunk_count: 0
    };
    const extractingStudyResponse: MaterialStudyResponse = {
      ...baseStudyResponse,
      record: {
        ...baseStudyResponse.record,
        ...extractingRecord,
        processing_status: "extracting",
        processing_progress: 20,
        outline_status: "pending",
        enrichment_status: "pending"
      },
      groups: [],
      sections: [],
      total_sections: 0,
      ready_sections: 0
    };

    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      const method = init?.method ?? "GET";

      if (url.endsWith("/api/v1/workflow/current")) {
        return mockJsonResponse(buildWorkflowResponse("course-demo", null, ["mat-1"]));
      }
      if (url.endsWith("/api/v1/courses/library")) {
        return mockJsonResponse(buildCourseLibraryResponse([extractingRecord]));
      }
      if (url.includes("/api/v1/materials/course/course-demo")) {
        return mockJsonResponse(buildMaterialsResponse([extractingRecord], [], []));
      }
      if (url.includes("/api/v1/materials/mat-1/study")) {
        return mockJsonResponse(extractingStudyResponse);
      }
      if (url.endsWith("/api/v1/materials/mat-1/reprocess") && method === "POST") {
        return mockJsonResponse({ record: extractingStudyResponse.record });
      }
      if (url.endsWith("/api/v1/materials/mat-1/status")) {
        return mockJsonResponse({ record: extractingStudyResponse.record });
      }

      return mockJsonResponse({});
    });

    await renderWithCourseContext(<MaterialsWorkspace />);

    const reprocessButton = await screen.findByRole("button", { name: "Reprocess" });
    expect(reprocessButton).toBeEnabled();

    await userEvent.click(reprocessButton);

    expect(
      fetchMock.mock.calls.some((call) => String(call[0]).endsWith("/api/v1/materials/mat-1/reprocess"))
    ).toBe(true);
  });
});

describe("DashboardShell", () => {
  it("loads and renders a course dashboard summary", async () => {
    fetchMock
      .mockResolvedValueOnce(mockJsonResponse(buildWorkflowResponse("course-demo", null, ["mat-1"])))
      .mockResolvedValueOnce(mockJsonResponse(buildCourseLibraryResponse([baseRecord])))
      .mockResolvedValueOnce(
        mockJsonResponse({
          course_id: "course-demo",
          module_id: null,
          material_count: 1,
          section_count: 2,
          chunk_count: 4,
          mastery_percent: 75,
          mastery_by_concept: {
            "Gradient Descent": 0.75
          },
          wrong_concepts: ["Gradient Descent"],
          materials: [baseRecord],
          quizzes: [
            {
              quiz_id: "quiz-1",
              course_id: "course-demo",
              module_id: null,
              query: "gradient descent",
              question_count: 2,
              overall_score: 50,
              wrong_question_count: 1,
              created_at: "2026-04-18T10:00:00Z",
              attempts: [
                {
                  quiz_id: "quiz-1",
                  created_at: "2026-04-18T10:00:00Z",
                  question_count: 2,
                  overall_score: 50,
                  wrong_question_count: 1,
                  module_id: null
                }
              ]
            }
          ],
          mock_exams: [
            {
              exam_id: "exam-1",
              course_id: "course-demo",
              module_id: null,
              title: "Midterm Mock",
              question_count: 3,
              target_difficulty: 0.6
            }
          ],
          remediation_history: [
            {
              remediation_id: "rem-1",
              course_id: "course-demo",
              module_id: null,
              concept: "Gradient Descent",
              generated_question_ids: ["q1", "q2", "q3"],
              prompt_signatures: ["sig-1"],
              original_question_ids: ["orig-1"]
            }
          ],
          wrong_questions: [
            {
              question_id: "q1",
              question_type: "mcq",
              concept: "Gradient Descent",
              is_correct: false,
              grading_label: "incorrect",
              score: 0,
              submitted_option_id: "B",
              submitted_answer: "B",
              correct_option_id: "A",
              correct_answer: "A",
              explanation: "Expected answer grounded in notes.",
              citations: []
            }
          ]
        })
      );

    await renderWithCourseContext(<DashboardShell />);

    expect(await screen.findByText("Midterm Mock")).toBeInTheDocument();
    expect((await screen.findAllByText("Gradient Descent")).length).toBeGreaterThan(0);
    expect(await screen.findByText("Expected answer grounded in notes.")).toBeInTheDocument();
  });
});

describe("QuizWorkspace", () => {
  it("shows the MCQ-only question-type control accessibly", async () => {
    fetchMock
      .mockResolvedValueOnce(mockJsonResponse(buildWorkflowResponse("course-demo", null, ["mat-1"])))
      .mockResolvedValueOnce(mockJsonResponse(buildCourseLibraryResponse([baseRecord])))
      .mockResolvedValueOnce(mockJsonResponse(buildMaterialsResponse([baseRecord], [baseSection], [baseQuizSource])));

    await renderWithCourseContext(<QuizWorkspace />);

    const mcqChip = await screen.findByRole("button", { name: "MCQ" });

    expect(mcqChip).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByRole("button", { name: "Short answer" })).not.toBeInTheDocument();
  });

  it("generates and grades a quiz", async () => {
    fetchMock
      .mockResolvedValueOnce(mockJsonResponse(buildWorkflowResponse("course-demo", null, ["mat-1"])))
      .mockResolvedValueOnce(mockJsonResponse(buildCourseLibraryResponse([baseRecord])))
      .mockResolvedValueOnce(mockJsonResponse(buildMaterialsResponse([baseRecord], [baseSection], [baseQuizSource])))
      .mockResolvedValueOnce(
        mockJsonResponse({
          job_id: "job-1",
          status: "queued",
          created_at: "2026-04-18T10:00:00Z",
          dedupe_key: "dedupe-1"
        })
      )
      .mockResolvedValueOnce(
        mockJsonResponse({
          job_id: "job-1",
          dedupe_key: "dedupe-1",
          status: "completed",
          provider: "nvidia",
          model: "meta/llama-3.1-70b-instruct",
          request_payload: {
            course_id: "course-demo",
            module_id: null,
            query: "gradient descent",
            question_count: 3,
            question_types: ["mcq", "short_answer"],
            retrieval_top_k: 6,
            selected_source_ids: ["mat-1-section-1"],
            client_request_id: "req-1"
          },
          progress: {
            total_questions: 1,
            completed_questions: 1,
            fallback_questions: 0,
            current_question_index: 1
          },
          quiz: {
            quiz_id: "quiz-1",
            course_id: "course-demo",
            module_id: null,
            query: "gradient descent",
            questions: [
              {
                question_id: "q1",
                question_type: "mcq",
                concept: "Gradient Descent",
                section_title: "Gradient Descent Basics",
                difficulty: 0.6,
                prompt: "Which statement is supported?",
                options: [
                  { option_id: "A", text: "Correct answer" },
                  { option_id: "B", text: "Distractor 1" },
                  { option_id: "C", text: "Distractor 2" },
                  { option_id: "D", text: "Distractor 3" }
                ],
                citations: [],
                rationale: "Grounded.",
                quality_validation: {
                  score: 0.9,
                  confidence: 0.8,
                  label: "high_quality",
                  accepted_for_delivery: true,
                  model_version: "v1",
                  model_source: "heuristic_fallback",
                  notes: []
                }
              }
            ]
          },
          partial_results: [
            {
              job_id: "job-1",
              question_id: "q1",
              ordinal: 1,
              source_id: "mat-1-section-1",
              section_title: "Gradient Descent Basics",
              generation_mode: "live",
              question: {
                question_id: "q1",
                question_type: "mcq",
                concept: "Gradient Descent",
                section_title: "Gradient Descent Basics",
                difficulty: 0.6,
                prompt: "Which statement is supported?",
                options: [
                  { option_id: "A", text: "Correct answer" },
                  { option_id: "B", text: "Distractor 1" },
                  { option_id: "C", text: "Distractor 2" },
                  { option_id: "D", text: "Distractor 3" }
                ],
                citations: [],
                rationale: "Grounded.",
                quality_validation: {
                  score: 0.9,
                  confidence: 0.8,
                  label: "high_quality",
                  accepted_for_delivery: true,
                  model_version: "v1",
                  model_source: "heuristic_fallback",
                  notes: []
                }
              },
              answer_key: {
                question_id: "q1",
                question_type: "mcq",
                concept: "Gradient Descent",
                correct_answer: "Correct answer",
                correct_option_id: "A",
                expected_keywords: ["correct", "answer"],
                difficulty: 0.6,
                citations: []
              },
              created_at: "2026-04-18T10:00:01Z"
            }
          ],
          error_summary: null,
          created_at: "2026-04-18T10:00:00Z",
          started_at: "2026-04-18T10:00:00Z",
          completed_at: "2026-04-18T10:00:01Z",
          last_heartbeat_at: "2026-04-18T10:00:01Z"
        })
      )
      .mockResolvedValueOnce(
        mockJsonResponse({
          quiz_id: "quiz-1",
          course_id: "course-demo",
          module_id: null,
          overall_score: 100,
          mastery_by_concept: {
            "Gradient Descent": 1
          },
          wrong_concepts: [],
          results: [
            {
              question_id: "q1",
              question_type: "mcq",
              concept: "Gradient Descent",
              is_correct: true,
              grading_label: "correct",
              score: 1,
              submitted_option_id: "A",
              submitted_answer: "Correct answer",
              correct_option_id: "A",
              correct_answer: "Correct answer",
              explanation: "Correct answer grounded in notes.",
              citations: []
            }
          ]
        })
      );

    await renderWithCourseContext(<QuizWorkspace />);

    await userEvent.click((await screen.findAllByRole("button", { name: "Generate quiz" }))[0]);
    expect((await screen.findAllByText("Gradient packet · pages 1-3")).length).toBeGreaterThan(0);
    await screen.findByText("Which statement is supported?");
    const quizGenerateCall = fetchMock.mock.calls.find((call) => call[0] === "/api/v1/quiz/generate");
    expect(quizGenerateCall?.[1]).toEqual(
      expect.objectContaining({
        method: "POST",
        body: expect.stringContaining("\"selected_source_ids\":[\"mat-1-section-1\"]")
      })
    );
    await userEvent.click(screen.getByLabelText(/A. Correct answer/i));
    await userEvent.click(screen.getByRole("button", { name: "Grade submission" }));

    expect(await screen.findByText("Correct answer grounded in notes.")).toBeInTheDocument();
  });

  it("shows an incorrect badge when the canonical grading result is incorrect", async () => {
    fetchMock
      .mockResolvedValueOnce(mockJsonResponse(buildWorkflowResponse("course-demo", null, ["mat-1"])))
      .mockResolvedValueOnce(mockJsonResponse(buildCourseLibraryResponse([baseRecord])))
      .mockResolvedValueOnce(mockJsonResponse(buildMaterialsResponse([baseRecord], [baseSection], [baseQuizSource])))
      .mockResolvedValueOnce(
        mockJsonResponse({
          job_id: "job-2",
          status: "queued",
          created_at: "2026-04-18T10:05:00Z",
          dedupe_key: "dedupe-2"
        })
      )
      .mockResolvedValueOnce(
        mockJsonResponse({
          job_id: "job-2",
          dedupe_key: "dedupe-2",
          status: "completed",
          provider: "nvidia",
          model: "meta/llama-3.1-70b-instruct",
          request_payload: {
            course_id: "course-demo",
            module_id: null,
            query: "python basics",
            question_count: 3,
            question_types: ["mcq", "short_answer"],
            retrieval_top_k: 6,
            selected_source_ids: ["mat-1-section-1"],
            client_request_id: "req-2"
          },
          progress: {
            total_questions: 1,
            completed_questions: 1,
            fallback_questions: 0,
            current_question_index: 1
          },
          quiz: {
            quiz_id: "quiz-1",
            course_id: "course-demo",
            module_id: null,
            query: "python basics",
            questions: [
              {
                question_id: "q1",
                question_type: "mcq",
                concept: "Introduction to Python",
                section_title: "Introduction to Python",
                difficulty: 0.5,
                prompt: "Which answer matches the notes?",
                options: [
                  { option_id: "A", text: "Introduction to Python" },
                  { option_id: "B", text: "Office hours schedule" },
                  { option_id: "C", text: "Attendance policy" },
                  { option_id: "D", text: "Contact details" }
                ],
                citations: [],
                rationale: "Grounded.",
                quality_validation: null
              }
            ]
          },
          partial_results: [],
          error_summary: null,
          created_at: "2026-04-18T10:05:00Z",
          started_at: "2026-04-18T10:05:00Z",
          completed_at: "2026-04-18T10:05:01Z",
          last_heartbeat_at: "2026-04-18T10:05:01Z"
        })
      )
      .mockResolvedValueOnce(
        mockJsonResponse({
          quiz_id: "quiz-1",
          course_id: "course-demo",
          module_id: null,
          overall_score: 0,
          mastery_by_concept: {},
          wrong_concepts: ["Introduction to Python"],
          results: [
            {
              question_id: "q1",
              question_type: "mcq",
              concept: "Introduction to Python",
              is_correct: false,
              grading_label: "incorrect",
              score: 0,
              submitted_option_id: "B",
              submitted_answer: "Office hours schedule",
              correct_option_id: "A",
              correct_answer: "Introduction to Python",
              explanation:
                "The submission was incorrect. The correct answer is Introduction to Python.",
              citations: []
            }
          ]
        })
      );

    await renderWithCourseContext(<QuizWorkspace />);

    await userEvent.click((await screen.findAllByRole("button", { name: "Generate quiz" }))[0]);
    await screen.findByText("Which answer matches the notes?");
    await userEvent.click(screen.getByLabelText(/B. Office hours schedule/i));
    await userEvent.click(screen.getByRole("button", { name: "Grade submission" }));

    expect((await screen.findAllByText("Incorrect")).length).toBeGreaterThan(0);
    expect(screen.queryByText("Needs review")).not.toBeInTheDocument();
  });

  it("resumes polling from a stored job id after remount", async () => {
    window.localStorage.setItem("quiz-job:course-demo:all", "job-resume");

    fetchMock
      .mockResolvedValueOnce(mockJsonResponse(buildWorkflowResponse("course-demo", null, ["mat-1"])))
      .mockResolvedValueOnce(mockJsonResponse(buildCourseLibraryResponse([baseRecord])))
      .mockResolvedValueOnce(mockJsonResponse(buildMaterialsResponse([baseRecord], [baseSection], [baseQuizSource])))
      .mockResolvedValueOnce(
        mockJsonResponse({
          job_id: "job-resume",
          dedupe_key: "dedupe-resume",
          status: "running",
          provider: "nvidia",
          model: "meta/llama-3.1-70b-instruct",
          request_payload: {
            course_id: "course-demo",
            module_id: null,
            query: "gradient descent",
            question_count: 3,
            question_types: ["mcq", "short_answer"],
            retrieval_top_k: 6,
            selected_source_ids: ["mat-1-section-1"],
            client_request_id: "req-resume"
          },
          progress: {
            total_questions: 3,
            completed_questions: 1,
            fallback_questions: 0,
            current_question_index: 2
          },
          quiz: {
            quiz_id: "job-resume",
            course_id: "course-demo",
            module_id: null,
            query: "gradient descent",
            questions: []
          },
          partial_results: [],
          error_summary: null,
          created_at: "2026-04-18T10:10:00Z",
          started_at: "2026-04-18T10:10:00Z",
          completed_at: null,
          last_heartbeat_at: "2026-04-18T10:10:05Z"
        })
      );

    await renderWithCourseContext(<QuizWorkspace />);

    expect(await screen.findByText(/Generating question 2 of 3/i)).toBeInTheDocument();
  });

  it("shows a friendly error when the generate request fails", async () => {
    fetchMock
      .mockResolvedValueOnce(mockJsonResponse(buildWorkflowResponse("course-demo", null, ["mat-1"])))
      .mockResolvedValueOnce(mockJsonResponse(buildCourseLibraryResponse([baseRecord])))
      .mockResolvedValueOnce(mockJsonResponse(buildMaterialsResponse([baseRecord], [baseSection], [baseQuizSource])))
      .mockRejectedValueOnce(new TypeError("socket hang up"));

    await renderWithCourseContext(<QuizWorkspace />);

    await userEvent.click((await screen.findAllByRole("button", { name: "Generate quiz" }))[0]);

    expect(
      await screen.findByText(/The local backend is unavailable/i)
    ).toBeInTheDocument();
  });
});

describe("MockExamWorkspace", () => {
  it("generates a mock exam", async () => {
    fetchMock
      .mockResolvedValueOnce(mockJsonResponse(buildWorkflowResponse("course-demo", null, ["mat-1"])))
      .mockResolvedValueOnce(mockJsonResponse(buildCourseLibraryResponse([baseRecord])))
      .mockResolvedValueOnce(mockJsonResponse({ sources: [] }))
      .mockResolvedValueOnce(mockJsonResponse(buildMaterialsResponse([baseRecord], [baseSection], [baseQuizSource])))
      .mockResolvedValueOnce(
        mockJsonResponse({
          record: baseRecord,
          sections: [],
          chunks: []
        })
      )
      .mockResolvedValueOnce(
        mockJsonResponse({
          exam: {
            exam_id: "exam-1",
            course_id: "course-demo",
            module_id: null,
            blueprint: {
              title: "Midterm Mock",
              instructions: "Answer all questions",
              topic_coverage: [
                {
                  topic: "Gradient Descent",
                  question_count: 1,
                  question_types: ["mcq"]
                }
              ],
              target_difficulty: 0.6,
              style_example: "Answer clearly."
            },
            questions: [
              {
                question_id: "q1",
                question_type: "mcq",
                concept: "Gradient Descent",
                section_title: "Gradient Descent Basics",
                difficulty: 0.6,
                prompt: "Which statement best matches the topic?",
                options: [
                  { option_id: "A", text: "Correct answer" },
                  { option_id: "B", text: "Distractor 1" },
                  { option_id: "C", text: "Distractor 2" },
                  { option_id: "D", text: "Distractor 3" }
                ],
                citations: [],
                rationale: "Grounded.",
                quality_validation: null
              }
            ]
          }
        })
      );

    await renderWithCourseContext(<MockExamWorkspace />);
    await userEvent.click(screen.getByRole("button", { name: "Generate mock exam" }));

    expect(await screen.findByText("Which statement best matches the topic?")).toBeInTheDocument();
  });
});

describe("HistoryReview", () => {
  it("opens a saved attempt without the live quiz runner", async () => {
    fetchMock.mockResolvedValueOnce(
      mockJsonResponse({
        quiz: {
          quiz_id: "quiz-1",
          course_id: "course-demo",
          module_id: null,
          query: "gradient descent",
          created_at: "2026-04-21T17:05:30Z",
          questions: [
            {
              question_id: "q1",
              question_type: "mcq",
              concept: "Gradient Descent",
              section_title: "Gradient Descent Basics",
              difficulty: 0.6,
              prompt: "Which statement is supported?",
              options: [],
              citations: [],
              rationale: "Grounded.",
              quality_validation: null
            }
          ]
        },
        results: [
          {
            question_id: "q1",
            question_type: "mcq",
            concept: "Gradient Descent",
            is_correct: true,
            grading_label: "correct",
            score: 1,
            submitted_option_id: "A",
            submitted_answer: "Correct answer",
            correct_option_id: "A",
            correct_answer: "Correct answer",
            explanation: "Correct. The answer matches the core idea.",
            citations: []
          }
        ]
      })
    );

    render(<HistoryReview recordId="quiz-1" />);

    expect(await screen.findByText("Saved attempt review")).toBeInTheDocument();
    expect(await screen.findByText("gradient descent")).toBeInTheDocument();
    expect(await screen.findByText(/Completed/i)).toBeInTheDocument();
    expect(fetchMock.mock.calls.some((call) => call[0] === "/api/v1/quiz/quiz-1/review")).toBe(true);
    expect(screen.queryByText("Answer the quiz")).not.toBeInTheDocument();
  });
});

describe("ExamReview", () => {
  it("loads saved exam review without entering a live runner", async () => {
    fetchMock.mockResolvedValueOnce(
      mockJsonResponse({
        exam: {
          exam_id: "exam-1",
          course_id: "course-demo",
          module_id: null,
          created_at: "2026-04-20T10:00:00Z",
          blueprint: {
            title: "Midterm Mock",
            instructions: "Answer all questions.",
            topic_coverage: [],
            target_difficulty: 0.6,
            style_example: "Short answers."
          },
          questions: []
        },
        grade_result: {
          exam_id: "exam-1",
          course_id: "course-demo",
          module_id: null,
          completed_at: "2026-04-20T10:30:00Z",
          overall_score: 100,
          analytics_by_concept: [],
          results: []
        }
      })
    );

    render(<ExamReview examId="exam-1" />);

    expect(await screen.findByText("Midterm Mock")).toBeInTheDocument();
    expect(await screen.findByText("100%")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some((call) => call[0] === "/api/v1/exams/exam-1/review")).toBe(true);
    expect(screen.queryByText("Generate a mock exam")).not.toBeInTheDocument();
  });
});

describe("WrongQuestionReview", () => {
  it("loads wrong questions and concept practice controls", async () => {
    fetchMock
      .mockResolvedValueOnce(mockJsonResponse(buildWorkflowResponse("course-demo", null, ["mat-1"])))
      .mockResolvedValueOnce(mockJsonResponse(buildCourseLibraryResponse([baseRecord])))
      .mockResolvedValueOnce(
        mockJsonResponse({
          course_id: "course-demo",
          module_id: null,
          material_count: 1,
          section_count: 2,
          chunk_count: 4,
          mastery_percent: 60,
          mastery_by_concept: {
            "Gradient Descent": 0.6
          },
          wrong_concepts: ["Gradient Descent"],
          materials: [],
          quizzes: [],
          mock_exams: [],
          remediation_history: [],
          wrong_questions: [
            {
              question_id: "q1",
              question_type: "mcq",
              concept: "Gradient Descent",
              is_correct: false,
              grading_label: "incorrect",
              score: 0,
              submitted_option_id: "B",
              submitted_answer: "B",
              correct_option_id: "A",
              correct_answer: "A",
              explanation: "Expected answer grounded in notes.",
              citations: []
            }
          ]
        })
      );

    await renderWithCourseContext(<WrongQuestionReview />);

    expect((await screen.findAllByText("Expected answer grounded in notes.")).length).toBeGreaterThan(0);
    expect(await screen.findByText("Concepts to practice")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Practice this concept" })).toBeInTheDocument();
  });
});
