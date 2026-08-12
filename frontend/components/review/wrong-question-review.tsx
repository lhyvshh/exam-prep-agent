"use client";

import React from "react";
import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import { fetchCourseDashboard, generateQuiz, trackActivityEvent } from "@/lib/api";
import { useCourseSelection } from "@/components/shared/course-context";
import { ReviewSourceModal } from "@/components/shared/source-viewer";
import { scopeFromQuestionResult } from "@/lib/scope";
import type { CourseDashboardResponse, QuestionGradeResult, SourceChunk } from "@/lib/schemas";
import {
  HistoryAccordion,
  MetricGrid,
  WrongQuestionList
} from "@/components/shared/data-widgets";

export function WrongQuestionReview(): JSX.Element {
  const { selectedCourseId, selectedModuleId, selectedCourse, selectedModule } = useCourseSelection();
  const searchParams = useSearchParams();
  const focusedHistoryId = searchParams?.get("historyQuizId") ?? searchParams?.get("historyExamId");
  const [summary, setSummary] = useState<CourseDashboardResponse | null>(null);
  const [selectedConcepts, setSelectedConcepts] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isStartingPractice, setIsStartingPractice] = useState<string | null>(null);
  const [reviewSource, setReviewSource] = useState<SourceChunk | null>(null);

  useEffect(() => {
    void loadCurrentReview();
  }, [selectedCourseId, selectedModuleId]);

  useEffect(() => {
    const concept = searchParams?.get("concept");
    if (concept) {
      setSelectedConcepts([concept]);
    }
  }, [searchParams]);

  useEffect(() => {
    if (!focusedHistoryId || !summary) {
      return;
    }
    window.setTimeout(() => {
      document.getElementById(`history-${focusedHistoryId}`)?.scrollIntoView({ block: "center", behavior: "smooth" });
    }, 80);
  }, [focusedHistoryId, summary]);

  async function loadCurrentReview(): Promise<void> {
    if (!selectedCourseId) {
      setSummary(null);
      return;
    }

    setIsLoading(true);
    try {
      const dashboard = await fetchCourseDashboard(selectedCourseId, selectedModuleId);
      setSummary(dashboard);
      setSelectedConcepts(dashboard.wrong_concepts);
      setError(null);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to load wrong-question review."
      );
      setSummary(null);
    } finally {
      setIsLoading(false);
    }
  }

  function toggleConcept(concept: string): void {
    setSelectedConcepts((current) =>
      current.includes(concept) ? current.filter((item) => item !== concept) : [...current, concept]
    );
  }

  async function handlePracticeConcept(result: QuestionGradeResult): Promise<void> {
    if (!summary || !selectedCourseId || isStartingPractice) {
      return;
    }

    setIsStartingPractice(result.question_id);
    setError(null);
    try {
      const sourceIds = result.citations.map((citation) => citation.source_id).filter(Boolean);
      const scope = scopeFromQuestionResult(selectedCourseId, result, selectedModuleId);
      const response = await generateQuiz({
        course_id: selectedCourseId,
        module_id: selectedModuleId,
        query: `Practice: ${result.concept}`,
        question_count: 3,
        question_types: ["mcq"],
        retrieval_top_k: 6,
        selected_source_ids: sourceIds,
        scope,
        client_request_id: `practice-${result.question_id}-${Date.now()}`
      });
      void trackActivityEvent({
        course_id: selectedCourseId,
        module_id: selectedModuleId,
        material_id: result.citations[0]?.material_id ?? null,
        section_id: result.citations[0]?.source_id ?? null,
        quiz_id: focusedHistoryId,
        question_id: result.question_id,
        question_type: result.question_type,
        event_type: "practice_concept_clicked",
        metadata_json: {
          origin: "wrong_questions",
          concept: result.concept,
          practice_job_id: response.job_id
        }
      }).catch(() => undefined);
      window.location.href = `/courses/${encodeURIComponent(selectedCourseId)}/quiz?jobId=${encodeURIComponent(response.job_id)}`;
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to start concept practice."
      );
    } finally {
      setIsStartingPractice(null);
    }
  }

  const metrics = summary
    ? [
        { label: "Wrong concepts", value: String(summary.wrong_concepts.length) },
        { label: "Wrong questions", value: String(summary.wrong_questions.length) },
        {
          label: "Selected concepts",
          value: String(selectedConcepts.length)
        }
      ]
      : [
        { label: "Wrong concepts", value: "0" },
        { label: "Wrong questions", value: "0" },
        { label: "Selected concepts", value: "0" }
      ];

  return (
    <div className="stack">
      <section className="card">
        <h3>Review misses and practice concepts</h3>
        {!selectedCourseId ? (
          <p className="subtle">Choose a course or module in the shared selector to review wrong questions.</p>
        ) : (
          <p>
            Reviewing {selectedCourse?.display_name}
            {selectedModule ? ` · ${selectedModule.display_name}` : " · whole course"}.
          </p>
        )}

        {isLoading ? <p className="subtle">Loading the selected review context...</p> : null}

        {error ? (
          <div className="status-panel error-panel" aria-live="polite">
            <strong>Issue:</strong> {error}
          </div>
        ) : null}
      </section>

      <MetricGrid items={metrics} />

      {summary ? (
        <>
          <section className="card">
            <div className="section-header">
              <div>
                <h3>Concepts to practice</h3>
                <p className="subtle">Use Practice this concept on a missed question to start a focused 3-question quiz.</p>
              </div>
            </div>

            <div className="checkbox-row">
              {summary.wrong_concepts.length === 0 ? (
                <p className="subtle">No wrong concepts are available in this context yet.</p>
              ) : (
                summary.wrong_concepts.map((concept) => (
                  <label className="checkbox-chip" key={concept}>
                    <input
                      checked={selectedConcepts.includes(concept)}
                      onChange={() => toggleConcept(concept)}
                      type="checkbox"
                    />
                    <span>{concept}</span>
                  </label>
                ))
              )}
            </div>
          </section>

          <WrongQuestionList
            results={summary.wrong_questions}
            onReviewMaterial={(result) => {
              if (result.citations[0]) {
                void trackActivityEvent({
                  course_id: selectedCourseId,
                  module_id: selectedModuleId,
                  material_id: result.citations[0].material_id,
                  section_id: result.citations[0].source_id,
                  quiz_id: focusedHistoryId,
                  question_id: result.question_id,
                  question_type: result.question_type,
                  event_type: "review_material_clicked",
                  metadata_json: {
                    origin: "wrong_questions",
                    concept: result.concept,
                    page_number: result.citations[0].locator?.page_number ?? null
                  }
                }).catch(() => undefined);
                setReviewSource(result.citations[0]);
              }
            }}
            onPracticeConcept={(result) => {
              setSelectedConcepts([result.concept]);
              void handlePracticeConcept(result);
            }}
            startingPracticeQuestionId={isStartingPractice}
          />

          <HistoryAccordion
            courseId={selectedCourseId}
            focusedHistoryId={focusedHistoryId}
            title="Quiz/exam history"
            quizzes={summary.quizzes}
            mockExams={summary.mock_exams}
            loading={false}
          />
        </>
      ) : null}
      {reviewSource ? (
        <ReviewSourceModal
          citation={reviewSource}
          returnHref={
            selectedConcepts.length === 1
              ? `/courses/${encodeURIComponent(selectedCourseId ?? reviewSource.course_id)}/wrong-questions?concept=${encodeURIComponent(selectedConcepts[0])}`
              : `/courses/${encodeURIComponent(selectedCourseId ?? reviewSource.course_id)}/wrong-questions`
          }
          returnLabel="Back to misses"
          onClose={() => setReviewSource(null)}
        />
      ) : null}
    </div>
  );
}
