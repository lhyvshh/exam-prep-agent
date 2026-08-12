"use client";

import React, { useEffect, useMemo, useState } from "react";

import { fetchCourseDashboard } from "@/lib/api";
import { useCourseSelection } from "@/components/shared/course-context";
import { cleanDisplayText, formatTimestamp } from "@/components/shared/data-widgets";
import { readCourseResume, type CourseResumeLink, type CourseResumeState } from "@/lib/course-resume";
import type { CourseDashboardResponse, MaterialRecord, QuizHistoryItem } from "@/lib/schemas";

type OverviewShortcut = {
  eyebrow: string;
  title: string;
  description: string;
  href: string;
  actionLabel: string;
};

export function CourseOverview({ courseId }: { courseId: string }): JSX.Element {
  const { selectedModuleId, selectedCourse } = useCourseSelection();
  const [dashboard, setDashboard] = useState<CourseDashboardResponse | null>(null);
  const [resume, setResume] = useState<CourseResumeState>({});
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void loadDashboard();
  }, [courseId, selectedModuleId]);

  useEffect(() => {
    setResume(readCourseResume(courseId));
  }, [courseId, dashboard]);

  async function loadDashboard(): Promise<void> {
    setIsLoading(true);
    try {
      setDashboard(await fetchCourseDashboard(courseId, selectedModuleId));
      setError(null);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Unable to load course overview.");
      setDashboard(null);
    } finally {
      setIsLoading(false);
    }
  }

  const shortcuts = useMemo(
    () => buildOverviewShortcuts(courseId, dashboard, resume),
    [courseId, dashboard, resume]
  );

  return (
    <div className="stack">
      <section className="card overview-hero-card">
        <div>
          <h2>{selectedCourse?.display_name ?? "Course overview"}</h2>
          <p>Resume the material, card, or quiz you touched most recently.</p>
        </div>
        <div className="action-row">
          <a className="primary-button" href={`/courses/${encodeURIComponent(courseId)}/materials`}>Open book library</a>
          <a className="secondary-button" href={`/courses/${encodeURIComponent(courseId)}/wrong-questions`}>Quiz history</a>
          <a className="secondary-button" href={`/courses?mockExamCourseId=${encodeURIComponent(courseId)}`}>Mock exam</a>
        </div>
      </section>

      {isLoading ? <p className="subtle">Loading overview...</p> : null}
      {error ? (
        <div className="status-panel error-panel" aria-live="polite">
          <strong>Issue:</strong> {error}
        </div>
      ) : null}

      <section aria-label="Resume shortcuts" className="card overview-resume-panel">
        <div className="overview-resume-header">
          <div>
            <p className="eyebrow">Continue</p>
            <h3>Pick up where you left off</h3>
          </div>
        </div>
        <div className="overview-resume-grid">
          {shortcuts.map((shortcut) => (
            <article className="overview-resume-card" key={shortcut.eyebrow}>
              <p className="eyebrow">{shortcut.eyebrow}</p>
              <strong>{shortcut.title}</strong>
              <p className="subtle">{shortcut.description}</p>
              <a className="secondary-button" href={shortcut.href}>
                {shortcut.actionLabel}
              </a>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}

function buildOverviewShortcuts(
  courseId: string,
  dashboard: CourseDashboardResponse | null,
  resume: CourseResumeState
): OverviewShortcut[] {
  const latestQuiz = dashboard?.quizzes[0] ?? null;
  return [
    buildModuleShortcut(courseId, resume.lastModule, dashboard?.materials[0] ?? null),
    buildStudyCardShortcut(courseId, resume.lastStudyCard),
    buildQuizShortcut(courseId, latestQuiz)
  ];
}

function buildModuleShortcut(
  courseId: string,
  savedLink: CourseResumeLink | undefined,
  fallbackMaterial: MaterialRecord | null
): OverviewShortcut {
  if (savedLink) {
    return {
      eyebrow: "Last opened module",
      title: savedLink.title,
      description: savedLink.meta ?? "Return to the module you last opened.",
      href: savedLink.href,
      actionLabel: "Open module"
    };
  }

  return {
    eyebrow: "Last opened module",
    title: fallbackMaterial?.display_name || fallbackMaterial?.file_name || "Book library",
    description: fallbackMaterial ? "Open the latest available material." : "Choose a material to start studying.",
    href: fallbackMaterial
      ? `/courses/${encodeURIComponent(courseId)}/materials?materialId=${encodeURIComponent(fallbackMaterial.material_id)}`
      : `/courses/${encodeURIComponent(courseId)}/materials`,
    actionLabel: "Open module"
  };
}

function buildStudyCardShortcut(courseId: string, savedLink: CourseResumeLink | undefined): OverviewShortcut {
  if (savedLink) {
    return {
      eyebrow: "Last opened study card",
      title: savedLink.title,
      description: savedLink.meta ?? "Continue the card deck from your last position.",
      href: savedLink.href,
      actionLabel: "Open card"
    };
  }

  return {
    eyebrow: "Last opened study card",
    title: "Study cards",
    description: "Open your card deck after studying a module.",
    href: `/courses/${encodeURIComponent(courseId)}/flashcards`,
    actionLabel: "Open card"
  };
}

function buildQuizShortcut(courseId: string, latestQuiz: QuizHistoryItem | null): OverviewShortcut {
  if (!latestQuiz) {
    return {
      eyebrow: "Quizzes",
      title: "Quiz history",
      description: "Open saved quiz attempts and explanations.",
      href: `/courses/${encodeURIComponent(courseId)}/wrong-questions`,
      actionLabel: "Open quiz history"
    };
  }

  return {
    eyebrow: "Quizzes",
    title: cleanDisplayText(latestQuiz.query),
    description: formatQuizMeta(latestQuiz),
    href: `/history/${encodeURIComponent(latestQuiz.quiz_id)}`,
    actionLabel: "Review quiz"
  };
}

function formatQuizMeta(quiz: QuizHistoryItem): string {
  const score = quiz.overall_score !== null ? ` · ${quiz.overall_score}%` : "";
  const saved = quiz.created_at ? ` · ${formatTimestamp(quiz.created_at)}` : "";
  return `${quiz.question_count} questions${score}${saved}`;
}
