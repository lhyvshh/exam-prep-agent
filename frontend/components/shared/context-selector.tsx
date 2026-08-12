"use client";

import React from "react";

import { useCourseSelection } from "@/components/shared/course-context";

export function ContextSelector(): JSX.Element {
  const {
    courses,
    modules,
    selectedCourseId,
    selectedModuleId,
    selectedCourse,
    selectedModule,
    workflow,
    isLoading,
    error,
    setSelection
  } = useCourseSelection();

  return (
    <section className="context-panel">
      <div className="context-panel-header">
        <div>
          <strong>Active study context</strong>
          <p className="subtle">
            {selectedCourse
              ? `${selectedCourse.display_name}${selectedModule ? ` · ${selectedModule.display_name}` : " · whole course"}`
              : "Choose a course and optional module to scope materials, quizzes, and exams."}
          </p>
        </div>
      </div>

      <div className="two-column-grid">
        <label className="field">
          <span>Course</span>
          <select
            aria-label="Shared course selector"
            disabled={isLoading}
            value={selectedCourseId ?? ""}
            onChange={(event) => void setSelection(event.target.value || null, null)}
          >
            <option value="">Choose a course</option>
            {courses.map((course) => (
              <option key={course.course_id} value={course.course_id}>
                {course.course_code} · {course.display_name}
              </option>
            ))}
          </select>
        </label>

        <label className="field">
          <span>Module</span>
          <select
            aria-label="Shared module selector"
            disabled={isLoading || !selectedCourseId}
            value={selectedModuleId ?? ""}
            onChange={(event) => void setSelection(selectedCourseId, event.target.value || null)}
          >
            <option value="">Whole course</option>
            {modules.map((module) => (
              <option key={module.module_id} value={module.module_id}>
                {module.module_number} · {module.display_name}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error ? (
        <div className="status-panel error-panel" aria-live="polite">
          <strong>Issue:</strong> {error}
        </div>
      ) : null}

      {workflow?.graph_state.execution_trace.length ? (
        <div className="graph-trace" aria-label="Agent graph trace">
          {workflow.graph_state.execution_trace.map((record) => (
            <span className="graph-step" key={`${record.node_name}-${record.status}`}>
              <strong>{record.node_name.replace("_", " ")}</strong>
              <span>{record.status.replace("_", " ")}</span>
            </span>
          ))}
        </div>
      ) : null}
    </section>
  );
}
