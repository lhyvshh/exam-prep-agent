import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AgentCoachPanel } from "@/components/agents/agent-coach-panel";
import {
  chatWithAgent,
  fetchAgentMemory,
  fetchAgentRecommendations,
  fetchSmartAgentStudyPlan,
  runAgentCheck
} from "@/lib/api";

vi.mock("@/lib/api", () => ({
  chatWithAgent: vi.fn(async () => ({
    course_id: "course-demo",
    message: "Beta measures how sensitive the asset is to broad market movement.",
    response_mode: "live_llm",
    actions: [],
    memory: {
      course_id: "course-demo",
      preferred_study_style: "balanced",
      preferred_quiz_format: "mcq",
      default_question_count: 3,
      focus_areas: [],
      encouragement_style: "steady",
      progress_notes: []
    },
    recommendations: [],
    active_agent_profile: {
      agent_name: "study_coach_agent",
      display_name: "Exam Butler",
      role: "Teaching assistant",
      personality: "Concise",
      skills: [],
      operating_rules: [],
      sample_line: null
    },
    agent_profiles: []
  })),
  dismissAgentRecommendation: vi.fn(),
  fetchAgentMemory: vi.fn(async () => ({
    course_id: "course-demo",
    preferred_study_style: "balanced",
    preferred_quiz_format: "mixed",
    default_question_count: 3,
    focus_areas: [],
    encouragement_style: "steady",
    progress_notes: []
  })),
  fetchAgentRecommendations: vi.fn(async () => ({
    course_id: "course-demo",
    recommendations: [],
    agent_profiles: [
      {
        agent_name: "study_coach_agent",
        display_name: "Exam Butler",
        role: "Interacts with the student and recommends the next best action.",
        personality: "Cheerful and grounded.",
        skills: ["progress interpretation", "weak concept triage"],
        operating_rules: ["Use real study data."],
        sample_line: "You’re 2 focused steps away from a stronger score."
      },
      {
        agent_name: "quality_agent",
        display_name: "Quality Agent",
        role: "Checks grounding and quality.",
        personality: "Reliability-first.",
        skills: ["PyTorch quality gating"],
        operating_rules: ["Reject unsupported output."],
        sample_line: "Quality check passed."
      }
    ],
    latest_run: {
      run_id: "run-1",
      intent: "progress_check",
      course_id: "course-demo",
      scope: {
        course_id: "course-demo",
        module_ids: [],
        material_ids: [],
        section_ids: [],
        source_type: "study_material"
      },
      node_statuses: [],
      agent_messages: [],
      recommendations: [],
      quality_summary: null,
      agent_profiles: [
        {
          agent_name: "study_coach_agent",
          display_name: "Exam Butler",
          role: "Interacts with the student and recommends the next best action.",
          personality: "Cheerful and grounded.",
          skills: ["progress interpretation", "weak concept triage"],
          operating_rules: ["Use real study data."],
          sample_line: "You’re 2 focused steps away from a stronger score."
        }
      ],
      created_at: "2026-04-30T12:00:00Z"
    }
  })),
  fetchSmartAgentStudyPlan: vi.fn(async () => ({
    summary: "Your weakest area is Third Normal Form, especially scenario questions.",
    readinessScore: 64,
    recommendedNextAction: "Review Third Normal Form, then practice scenario questions.",
    topWeakModules: [
      {
        id: "module-1",
        name: "Normalization",
        accuracy: 0.4,
        attempts: 5,
        recentTrend: "Needs attention",
        priorityScore: 88
      }
    ],
    topWeakConcepts: [
      {
        id: "concept-1",
        name: "Third Normal Form",
        accuracy: 0.4,
        attempts: 5,
        recentTrend: "Needs attention",
        priorityScore: 91
      }
    ],
    weakestQuestionTypes: [
      {
        id: "scenario",
        name: "scenario",
        accuracy: 0,
        attempts: 3,
        recentTrend: "Needs attention",
        priorityScore: 72
      }
    ],
    recommendations: [
      {
        title: "Review Third Normal Form",
        reason: "You missed 3 of 5 related attempts.",
        actionType: "review_material",
        buttonText: "Review Material",
        targetUrl: "/courses/course-demo/materials?materialId=mat-1&sectionId=section-1&sourceId=section-1&source=1&page=47",
        targetMaterialId: "mat-1",
        targetSectionId: "section-1",
        targetConceptId: "concept-1",
        targetModuleId: "module-1",
        sourcePage: 47,
        questionType: "scenario",
        priorityScore: 91,
        weakAreaName: "Third Normal Form",
        accuracy: 0.4,
        attempts: 5,
        recentTrend: "Needs attention",
        whyItMatters: "Low accuracy on Third Normal Form, 3 recent misses.",
        recommendedAction: "Review material first, then practice scenario questions.",
        buttons: [
          {
            label: "Review Material",
            actionType: "review_material",
            targetUrl: "/courses/course-demo/materials?materialId=mat-1&sectionId=section-1&sourceId=section-1&source=1&page=47"
          },
          {
            label: "Practice Third Normal Form Scenarios",
            actionType: "practice_concept",
            targetUrl: "/courses/course-demo/materials?materialId=mat-1&sectionId=section-1&sourceId=section-1&study=1&quiz=1&questionType=scenario"
          },
          {
            label: "Generate Quiz",
            actionType: "generate_quiz",
            targetUrl: "/courses/course-demo/materials?materialId=mat-1&sectionId=section-1&sourceId=section-1&study=1&quiz=1"
          },
          {
            label: "Retake Missed Questions",
            actionType: "retake_missed_questions",
            targetUrl: "/courses/course-demo/wrong-questions?concept=concept-1"
          },
          {
            label: "View Source PDF Page",
            actionType: "view_source_pdf_page",
            targetUrl: "/courses/course-demo/materials?materialId=mat-1&sectionId=section-1&sourceId=section-1&source=1&page=47"
          },
          {
            label: "Study Similar Questions",
            actionType: "study_similar_questions",
            targetUrl: "/courses/course-demo/materials?materialId=mat-1&sectionId=section-1&sourceId=section-1&study=1&quiz=1&questionType=scenario"
          }
        ]
      }
    ]
  })),
  runAgentCheck: vi.fn(async () => ({
    run_id: "run-2",
    intent: "progress_check",
    course_id: "course-demo",
    scope: {
      course_id: "course-demo",
      module_ids: [],
      material_ids: [],
      section_ids: [],
      source_type: "study_material"
    },
    node_statuses: [],
    agent_messages: [],
    recommendations: [],
    quality_summary: null,
    agent_profiles: [],
    created_at: "2026-04-30T12:05:00Z"
  })),
  saveAgentMemory: vi.fn(),
  trackActivityEvent: vi.fn(async () => undefined)
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("AgentCoachPanel", () => {
  it("opens as a lightweight TA without loading progress dashboards", async () => {
    const user = userEvent.setup();
    render(<AgentCoachPanel courseId="course-demo" />);

    expect(screen.getByRole("button", { name: /Exam Butler/i })).toBeInTheDocument();
    expect(fetchAgentRecommendations).not.toHaveBeenCalled();
    expect(fetchAgentMemory).not.toHaveBeenCalled();
    expect(fetchSmartAgentStudyPlan).not.toHaveBeenCalled();
    expect(runAgentCheck).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: /Exam Butler/i }));

    expect((await screen.findAllByText("Exam Butler")).length).toBeGreaterThan(0);
    expect(fetchAgentRecommendations).not.toHaveBeenCalled();
    expect(fetchAgentMemory).not.toHaveBeenCalled();
    expect(fetchSmartAgentStudyPlan).not.toHaveBeenCalled();
    expect(runAgentCheck).not.toHaveBeenCalled();
  });

  it("answers questions as a chat-first TA without static agent panels", async () => {
    const user = userEvent.setup();
    render(<AgentCoachPanel courseId="course-demo" />);

    await user.click(screen.getByRole("button", { name: /Exam Butler/i }));
    expect((await screen.findAllByText("Exam Butler")).length).toBeGreaterThan(0);
    expect(screen.getByText("Ask about this page, a missed question, or a specific topic.")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Message Exam Butler"), "Explain CAPM beta");
    await user.click(screen.getByRole("button", { name: "Send" }));

    expect(chatWithAgent).toHaveBeenCalledWith(
      "course-demo",
      "Explain CAPM beta",
      expect.any(Object),
      expect.anything()
    );
    expect(await screen.findByText(/Beta measures how sensitive/i)).toBeInTheDocument();
    expect(screen.queryByText("Third Normal Form")).not.toBeInTheDocument();
    expect(screen.queryByText("Agent skills")).not.toBeInTheDocument();
    expect(screen.queryByText("Memory folder")).not.toBeInTheDocument();
  });

  it("runs progress checks only when explicitly requested", async () => {
    const user = userEvent.setup();
    render(<AgentCoachPanel courseId="course-demo" />);

    await user.click(screen.getByRole("button", { name: /Exam Butler/i }));
    await user.click(screen.getByRole("button", { name: "Run progress check" }));

    expect(runAgentCheck).toHaveBeenCalledTimes(1);
    expect(await screen.findByText(/Checked progress/i)).toBeInTheDocument();
  });

  it("does not expose raw source ids in butler copy", async () => {
    const user = userEvent.setup();
    render(<AgentCoachPanel courseId="course-demo" />);

    await user.click(screen.getByRole("button", { name: /Exam Butler/i }));
    expect((await screen.findAllByText("Exam Butler")).length).toBeGreaterThan(0);

    expect(screen.queryByText(/687a67445a514955989f485c54ea5dce-section-2/i)).not.toBeInTheDocument();
  });
});
