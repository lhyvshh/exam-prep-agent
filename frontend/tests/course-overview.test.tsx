import React from "react";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CourseOverview } from "@/components/courses/course-overview";
import { fetchCourseDashboard } from "@/lib/api";
import type { CourseDashboardResponse } from "@/lib/schemas";

const dashboardResponse: CourseDashboardResponse = {
  course_id: "course-demo",
  module_id: null,
  material_count: 1,
  section_count: 3,
  chunk_count: 12,
  mastery_percent: 50,
  mastery_by_concept: {
    "Risk management": 0.67
  },
  wrong_concepts: [],
  materials: [
    {
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
      chunk_count: 12,
      section_count: 3,
      error_message: null
    }
  ],
  quizzes: [
    {
      quiz_id: "quiz-1",
      module_id: null,
      record_type: "quiz",
      query: "Section practice: Module 2.1: Corporate Risk Management",
      question_count: 3,
      overall_score: 67,
      wrong_question_count: 1,
      created_at: "2026-06-24T22:15:00Z",
      attempts: [
        {
          quiz_id: "quiz-1",
          created_at: "2026-06-24T22:15:00Z",
          question_count: 3,
          overall_score: 67,
          wrong_question_count: 1,
          module_id: null
        }
      ]
    }
  ],
  mock_exams: [],
  remediation_history: [],
  wrong_questions: [],
  exam_readiness_score: 27,
  weak_modules: [],
  weak_concepts_ranked: [],
  weak_question_types: [],
  study_recommendations: []
};

vi.mock("@/lib/api", () => ({
  fetchCourseDashboard: vi.fn(async () => dashboardResponse)
}));

vi.mock("@/components/shared/course-context", () => ({
  useCourseSelection: () => ({
    selectedModuleId: null,
    selectedCourse: {
      course_id: "course-demo",
      course_code: "FRM",
      display_name: "FRM",
      description: null
    }
  })
}));

afterEach(() => {
  cleanup();
  window.localStorage.clear();
  vi.clearAllMocks();
});

describe("CourseOverview", () => {
  it("shows resume shortcuts instead of dashboard analytics panels", async () => {
    window.localStorage.setItem(
      "exam-prep-course-resume:course-demo",
      JSON.stringify({
        lastModule: {
          title: "Module 6.1: Multifactor Model Assumptions and Inputs",
          href: "/courses/course-demo/materials?materialId=mat-workbook&groupId=reading-6&sectionId=section-6&study=1",
          meta: "FRM 2025 Part 1 KAPLAN Book 1.PDF",
          updatedAt: "2026-06-24T23:10:00Z"
        },
        lastStudyCard: {
          title: "What is the capital asset pricing model (CAPM)?",
          href: "/courses/course-demo/flashcards?materialId=mat-workbook&sectionId=section-6&cardId=card-capm",
          meta: "Card 4 of 30",
          updatedAt: "2026-06-24T23:12:00Z"
        }
      })
    );

    render(<CourseOverview courseId="course-demo" />);

    await waitFor(() => expect(fetchCourseDashboard).toHaveBeenCalledWith("course-demo", null));

    const resumePanel = screen.getByRole("region", { name: "Resume shortcuts" });
    expect(within(resumePanel).getByText("Module 6.1: Multifactor Model Assumptions and Inputs")).toBeInTheDocument();
    expect(within(resumePanel).getByText("What is the capital asset pricing model (CAPM)?")).toBeInTheDocument();
    expect(within(resumePanel).getByText("Section practice: Module 2.1: Corporate Risk Management")).toBeInTheDocument();

    expect(within(resumePanel).getByRole("link", { name: "Open module" })).toHaveAttribute(
      "href",
      "/courses/course-demo/materials?materialId=mat-workbook&groupId=reading-6&sectionId=section-6&study=1"
    );
    expect(within(resumePanel).getByRole("link", { name: "Open card" })).toHaveAttribute(
      "href",
      "/courses/course-demo/flashcards?materialId=mat-workbook&sectionId=section-6&cardId=card-capm"
    );
    expect(within(resumePanel).getByRole("link", { name: "Review quiz" })).toHaveAttribute("href", "/history/quiz-1");

    expect(screen.queryByText("Study recommendations")).not.toBeInTheDocument();
    expect(screen.queryByText("Study history")).not.toBeInTheDocument();
    expect(screen.queryByText("Mastery by concept")).not.toBeInTheDocument();
    expect(screen.queryByText("Readiness")).not.toBeInTheDocument();
  });
});
