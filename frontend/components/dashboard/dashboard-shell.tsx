"use client";

import React from "react";
import { useEffect, useState } from "react";

import { deleteMaterial, deleteQuizAttempt, fetchCourseDashboard, generateQuiz } from "@/lib/api";
import { useCourseSelection } from "@/components/shared/course-context";
import {
  HistoryAccordion,
  MasteryChart,
  MetricGrid,
  WrongQuestionList
} from "@/components/shared/data-widgets";
import { ReviewSourceModal } from "@/components/shared/source-viewer";
import type { CourseDashboardResponse, SourceChunk } from "@/lib/schemas";

export function DashboardShell(): JSX.Element {
  const {
    selectedCourseId,
    selectedModuleId,
    selectedCourse,
    selectedModule,
    refresh
  } = useCourseSelection();
  const [summary, setSummary] = useState<CourseDashboardResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [reviewSource, setReviewSource] = useState<SourceChunk | null>(null);

  useEffect(() => {
    void loadDashboard();
  }, [selectedCourseId, selectedModuleId]);

  async function loadDashboard(): Promise<void> {
    if (!selectedCourseId) {
      setSummary(null);
      return;
    }

    setIsLoading(true);
    try {
      const dashboard = await fetchCourseDashboard(selectedCourseId, selectedModuleId);
      setSummary(dashboard);
      setError(null);
    } catch (dashboardError) {
      setError(
        dashboardError instanceof Error ? dashboardError.message : "Unable to load dashboard."
      );
      setSummary(null);
    } finally {
      setIsLoading(false);
    }
  }

  async function handleDelete(materialId: string): Promise<void> {
    const confirmed = window.confirm("Delete this uploaded file and its parsed material?");
    if (!confirmed) {
      return;
    }
    try {
      await deleteMaterial(materialId);
      await refresh();
      await loadDashboard();
    } catch (dashboardError) {
      setError(
        dashboardError instanceof Error ? dashboardError.message : "Unable to delete material."
      );
    }
  }

  async function handleDeleteAttempt(quizId: string): Promise<void> {
    const confirmed = window.confirm("Delete this saved quiz attempt?");
    if (!confirmed) {
      return;
    }
    try {
      await deleteQuizAttempt(quizId);
      await loadDashboard();
    } catch (dashboardError) {
      setError(
        dashboardError instanceof Error ? dashboardError.message : "Unable to delete quiz attempt."
      );
    }
  }

  function openAttemptReview(quizId: string): void {
    window.location.href = `/history/${encodeURIComponent(quizId)}`;
  }

  async function handlePracticeConcept(result: CourseDashboardResponse["wrong_questions"][number]): Promise<void> {
    if (!selectedCourseId) {
      return;
    }
    try {
      const response = await generateQuiz({
        course_id: selectedCourseId,
        module_id: selectedModuleId,
        query: `Practice: ${result.concept}`,
        question_count: 3,
        question_types: ["mcq"],
        retrieval_top_k: 6,
        selected_source_ids: result.citations.map((citation) => citation.source_id),
        client_request_id: `practice-${result.question_id}-${Date.now()}`
      });
      window.location.href = `/courses/${encodeURIComponent(selectedCourseId)}/quiz?jobId=${encodeURIComponent(response.job_id)}`;
    } catch (practiceError) {
      setError(practiceError instanceof Error ? practiceError.message : "Unable to start concept practice.");
    }
  }

  const metrics = summary
    ? [
        { label: "Materials", value: String(summary.material_count) },
        { label: "Mastery", value: `${summary.mastery_percent}%` },
        { label: "Wrong questions", value: String(summary.wrong_questions.length) },
        { label: "Mock exams", value: String(summary.mock_exams.length) }
      ]
    : [
        { label: "Materials", value: "0" },
        { label: "Mastery", value: "0%" },
        { label: "Wrong questions", value: "0" },
        { label: "Mock exams", value: "0" }
      ];

  return (
    <div className="stack">
      <section className="card">
        <h3>Course dashboard</h3>
        {!selectedCourseId ? (
          <p className="subtle">Choose a course or module in the shared selector to load its dashboard.</p>
        ) : (
          <p>
            Viewing {selectedCourse?.display_name ?? "selected course"}
            {selectedModule ? ` · ${selectedModule.display_name}` : " · whole course"}.
          </p>
        )}

        {isLoading ? <p className="subtle">Loading the selected dashboard...</p> : null}

        {error ? (
          <div className="status-panel error-panel" aria-live="polite">
            <strong>Issue:</strong> {error}
          </div>
        ) : null}
      </section>

      <MetricGrid items={metrics} />

      {summary ? (
        <>
          <section className="card next-action-panel">
            <div className="section-header">
              <div>
                <h3>Next best actions</h3>
                <p className="subtle">Use these shortcuts to keep studying without hunting through pages.</p>
              </div>
            </div>
            <div className="next-action-grid">
              <a className="next-action-card" href={`/courses/${encodeURIComponent(selectedCourseId ?? "")}/materials`}>
                <strong>Study from books</strong>
                <span>Open the current course library and continue section review.</span>
              </a>
              <a className="next-action-card" href={`/courses/${encodeURIComponent(selectedCourseId ?? "")}/wrong-questions`}>
                <strong>Review misses</strong>
                <span>{summary.wrong_questions.length} question{summary.wrong_questions.length === 1 ? "" : "s"} need attention.</span>
              </a>
              <a className="next-action-card" href={`/courses?mockExamCourseId=${encodeURIComponent(selectedCourseId ?? "")}`}>
                <strong>Build mock exam</strong>
                <span>Use module weights and past exam style for targeted practice.</span>
              </a>
            </div>
          </section>

          <div className="dashboard-grid">
            <MasteryChart masteryByConcept={summary.mastery_by_concept} />
            <section className="card">
              <h3>Weak concepts</h3>
              {summary.wrong_concepts.length === 0 ? (
                <p className="subtle">No wrong concepts recorded in this context yet.</p>
              ) : (
                <div className="pill-row">
                  {summary.wrong_concepts.slice(0, 8).map((concept) => (
                    <span className="pill" key={concept}>
                      {concept}
                    </span>
                  ))}
                </div>
              )}
            </section>
          </div>

          <details className="card collapsible-card">
            <summary>
              <span>
                <strong>Materials in context</strong>
                <small>{summary.materials.length} uploaded item{summary.materials.length === 1 ? "" : "s"}</small>
              </span>
            </summary>
            <div className="stacked-list">
              {summary.materials.length === 0 ? (
                <p className="subtle">No materials uploaded in this context yet.</p>
              ) : (
                summary.materials.map((material) => (
                  <article className="preview-item" key={material.material_id}>
                    <div className="preview-header">
                      <div>
                        <strong>{material.display_name || material.file_name}</strong>
                        <p className="subtle">
                          {material.status} · {material.section_count} sections · {material.chunk_count} chunks
                        </p>
                      </div>
                      <button
                        className="secondary-button"
                        onClick={() => void handleDelete(material.material_id)}
                        type="button"
                      >
                        Delete
                      </button>
                    </div>
                  </article>
                ))
              )}
            </div>
          </details>

          <HistoryAccordion
            courseId={selectedCourseId}
            mockExams={summary.mock_exams}
            quizzes={summary.quizzes}
            loading={isLoading}
            error={error}
            onOpenAttempt={openAttemptReview}
            onDeleteAttempt={(quizId) => void handleDeleteAttempt(quizId)}
          />

          <WrongQuestionList
            results={summary.wrong_questions}
            onReviewMaterial={(result) => {
              if (result.citations[0]) {
                setReviewSource(result.citations[0]);
              }
            }}
            onPracticeConcept={(result) => {
              void handlePracticeConcept(result);
            }}
          />
        </>
      ) : null}
      {reviewSource ? (
        <ReviewSourceModal
          citation={reviewSource}
          returnHref="/dashboard"
          returnLabel="Back to dashboard"
          onClose={() => setReviewSource(null)}
        />
      ) : null}
    </div>
  );
}
