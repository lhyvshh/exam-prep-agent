import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  AttemptHistory,
  buildMaterialReviewHref,
  MasteryChart,
  WrongQuestionList
} from "@/components/shared/data-widgets";
import { scopeFromQuestionResult } from "@/lib/scope";
import type { QuestionGradeResult } from "@/lib/schemas";

afterEach(() => {
  cleanup();
});

describe("MasteryChart", () => {
  it("renders concept mastery values", () => {
    render(
      <MasteryChart
        masteryByConcept={{
          "Gradient Descent": 0.75,
          "Learning Rate": 0.5
        }}
      />
    );

    expect(screen.getByText("Gradient Descent")).toBeInTheDocument();
    expect(screen.getByText("75%")).toBeInTheDocument();
    expect(screen.getByText("Learning Rate")).toBeInTheDocument();
  });
});

describe("AttemptHistory", () => {
  it("renders quiz and exam entries with timestamps and review links", () => {
    render(
      <AttemptHistory
        quizzes={[
          {
            quiz_id: "quiz-1",
            query: "gradient descent",
            question_count: 2,
            overall_score: 50,
            wrong_question_count: 1,
            created_at: "2026-04-20T10:00:00Z",
            attempts: [
              {
                quiz_id: "quiz-1",
                created_at: "2026-04-20T10:00:00Z",
                question_count: 2,
                overall_score: 50,
                wrong_question_count: 1,
                module_id: null
              }
            ]
          }
        ]}
        mockExams={[
          {
            exam_id: "exam-1",
            title: "Midterm Mock",
            question_count: 3,
            target_difficulty: 0.6,
            created_at: "2026-04-19T10:00:00Z"
          }
        ]}
      />
    );

    expect(screen.getByText("Midterm Mock")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Midterm Mock" })).toHaveAttribute(
      "href",
      "/history/exam/exam-1"
    );
    expect(screen.getByText("gradient descent")).toBeInTheDocument();
    expect(screen.getByText("Latest attempt")).toBeInTheDocument();
    expect(screen.getAllByText(/4\/20\/2026/i).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: /Quiz gradient descent/i })).toHaveAttribute(
      "href",
      "/history/quiz-1"
    );
  });

  it("opens saved attempts directly from course-scoped history entries", () => {
    render(
      <AttemptHistory
        courseId="course-demo"
        quizzes={[
          {
            quiz_id: "quiz-1",
            query: "gradient descent",
            question_count: 2,
            overall_score: 50,
            wrong_question_count: 1,
            created_at: "2026-04-20T10:00:00Z",
            attempts: [
              {
                quiz_id: "quiz-attempt-2",
                created_at: "2026-04-21T10:00:00Z",
                question_count: 2,
                overall_score: 75,
                wrong_question_count: 0,
                module_id: null
              }
            ]
          }
        ]}
        mockExams={[
          {
            exam_id: "exam-1",
            title: "Midterm Mock",
            question_count: 3,
            target_difficulty: 0.6,
            created_at: "2026-04-19T10:00:00Z"
          }
        ]}
      />
    );

    expect(screen.getByRole("link", { name: /Quiz gradient descent/i })).toHaveAttribute(
      "href",
      "/history/quiz-1"
    );
    expect(screen.getByRole("link", { name: "Latest attempt" })).toHaveAttribute(
      "href",
      "/history/quiz-attempt-2"
    );
    expect(screen.getByRole("link", { name: "Midterm Mock" })).toHaveAttribute(
      "href",
      "/history/exam/exam-1"
    );
  });

  it("opens an attempt review from the accordion action", async () => {
    const onOpenAttempt = vi.fn();

    render(
      <AttemptHistory
        quizzes={[
          {
            quiz_id: "quiz-1",
            query: "gradient descent",
            question_count: 2,
            overall_score: 50,
            wrong_question_count: 1,
            created_at: "2026-04-20T10:00:00Z",
            attempts: [
              {
                quiz_id: "quiz-1",
                created_at: "2026-04-20T10:00:00Z",
                question_count: 2,
                overall_score: 50,
                wrong_question_count: 1,
                module_id: null
              }
            ]
          }
        ]}
        mockExams={[]}
        onOpenAttempt={onOpenAttempt}
      />
    );

    await userEvent.click(screen.getByRole("button", { name: "Review" }));

    expect(onOpenAttempt).toHaveBeenCalledWith("quiz-1");
  });
});

describe("WrongQuestionList", () => {
  it("renders wrong-question explanations and citations", () => {
    const result: QuestionGradeResult = {
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
      citations: [
        {
          chunk_id: "chunk-1",
          source_id: "source-1",
          material_id: "mat-1",
          course_id: "course-1",
          module_id: "module-1",
          file_name: "notes.txt",
          content_type: "text/plain",
          section_title: "Gradient Descent",
          text: "Gradient descent updates parameters.",
          section_kind: "instructional",
          content_label: "testable_content",
          priority_score: 0.9,
          is_default: true,
          locator: {
            section_index: 1,
            page_number: 2,
            slide_number: null,
            paragraph_index: null,
            char_start: 0,
            char_end: 32
          },
          citation_label: "notes.txt | Gradient Descent"
        }
      ]
    };

    render(
      <WrongQuestionList
        results={[result]}
        reviewHrefForResult={(result) => buildMaterialReviewHref(result.citations[0], { returnTo: "/quiz" })}
      />
    );

    expect(screen.getByText("Expected answer grounded in notes.")).toBeInTheDocument();
    expect(screen.getByText("notes.txt · page 2")).toBeInTheDocument();
    expect(screen.getByText(/Your answer:/i)).not.toBeVisible();
    expect(screen.getByText("Show details")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Review material" })).toHaveAttribute(
      "href",
      expect.stringContaining("/courses/course-1/materials")
    );
    expect(screen.getByRole("link", { name: "Review material" })).toHaveAttribute(
      "href",
      expect.stringContaining("materialId=mat-1")
    );
    expect(screen.getByRole("link", { name: "Review material" })).toHaveAttribute(
      "href",
      expect.stringContaining("sourceId=source-1")
    );
    expect(screen.getByRole("link", { name: "Review material" })).toHaveAttribute(
      "href",
      expect.stringContaining("study=1")
    );
    expect(screen.getByRole("link", { name: "Review material" })).toHaveAttribute(
      "href",
      expect.stringContaining("source=1")
    );
    expect(screen.getByRole("link", { name: "Review material" })).toHaveAttribute(
      "href",
      expect.stringContaining("page=2")
    );

    expect(scopeFromQuestionResult("course-1", result)).toEqual({
      course_id: "course-1",
      module_ids: ["module-1"],
      material_ids: ["mat-1"],
      section_ids: ["source-1"],
      source_type: "study_material"
    });
  });

  it("does not use raw question ids as learner-facing review titles", () => {
    const result: QuestionGradeResult = {
      question_id: "687a67445a514955989f485c54ea5dce-question-2",
      question_type: "mcq",
      concept: "",
      is_correct: false,
      grading_label: "incorrect",
      score: 0,
      submitted_option_id: "B",
      submitted_answer: "B",
      correct_option_id: "A",
      correct_answer: "A",
      explanation: "Risk appetite is the amount of risk a firm is willing to accept.",
      citations: []
    };

    render(<WrongQuestionList results={[result]} />);

    expect(screen.getByText("Question review")).toBeInTheDocument();
    expect(screen.queryByText(/687a67445a514955989f485c54ea5dce/i)).not.toBeInTheDocument();
  });
});
