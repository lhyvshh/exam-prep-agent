"use client";

import React, { ReactNode, useEffect } from "react";

import { AgentCoachPanel } from "@/components/agents/agent-coach-panel";
import { findLibraryCourse, useCourseSelection } from "@/components/shared/course-context";

type CourseTabSlug = "packages" | "overview" | "materials" | "flashcards" | "study" | "quiz" | "wrong-questions";

const courseTabs: Array<{ slug: CourseTabSlug; label: string }> = [
  { slug: "packages", label: "Offline Package" },
  { slug: "overview", label: "Overview" },
  { slug: "materials", label: "Book Library" },
  { slug: "wrong-questions", label: "Wrong Questions" }
];

export function CourseWorkspaceFrame({
  courseId,
  activeTab,
  children
}: {
  courseId: string;
  activeTab: CourseTabSlug;
  children: ReactNode;
}): JSX.Element {
  const {
    library,
    selectedCourseId,
    selectedModuleId,
    selectedCourse,
    setSelection,
    isLoading,
    error
  } = useCourseSelection();
  const courseItem = findLibraryCourse(library, courseId);
  const isRouteContextReady = selectedCourseId === courseId;

  useEffect(() => {
    if (courseId && selectedCourseId !== courseId) {
      void setSelection(courseId, null);
    }
  }, [courseId, selectedCourseId]);

  const courseLabel = selectedCourse?.display_name ?? courseItem?.course.display_name ?? "Course workspace";
  const courseCode = selectedCourse?.course_code ?? courseItem?.course.course_code ?? "Course";

  return (
    <main
      className={`course-workspace-shell${activeTab === "packages" ? " course-workspace-packages" : ""}`}
      id="main-content"
    >
      <header className="course-workspace-header course-workspace-header-compact">
        <div className="course-header-main">
          <div className="course-title-block">
            <div className="workspace-breadcrumb-line" aria-label="Course breadcrumb">
              <a className="breadcrumb-link" href="/courses">Courses</a>
              <span>/</span>
              <span>{courseCode}</span>
            </div>
            <h1>{courseLabel}</h1>
          </div>
        </div>

        <nav className="course-tab-row" aria-label="Course workspace tabs">
          {courseTabs.map((tab) => (
            <a
              className={`course-tab-link${tab.slug === activeTab ? " course-tab-active" : ""}`}
              href={`/courses/${encodeURIComponent(courseId)}/${tab.slug}`}
              key={tab.slug}
              aria-current={tab.slug === activeTab ? "page" : undefined}
            >
              {tab.label}
            </a>
          ))}
        </nav>
      </header>

      {isLoading || !isRouteContextReady ? <p className="subtle">Loading course workspace...</p> : null}
      {error ? (
        <div className="status-panel error-panel" aria-live="polite">
          <strong>Issue:</strong> {error}
        </div>
      ) : null}

      {isRouteContextReady ? (
        <AgentCoachPanel courseId={courseId} moduleId={selectedModuleId} />
      ) : null}

      <div className="course-workspace-body">
        {isRouteContextReady ? children : null}
      </div>
    </main>
  );
}
