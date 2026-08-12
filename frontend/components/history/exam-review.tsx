"use client";

import React, { useEffect, useState } from "react";

import { fetchMockExamReview } from "@/lib/api";
import {
  cleanDisplayText,
  formatTimestamp,
  MetricGrid,
  QuestionReviewCard
} from "@/components/shared/data-widgets";
import { ReviewSourceModal } from "@/components/shared/source-viewer";
import type { MockExamReviewResponse, SourceChunk } from "@/lib/schemas";

type ExamReviewProps = {
  examId: string;
};

export function ExamReview({ examId }: ExamReviewProps): JSX.Element {
  const [review, setReview] = useState<MockExamReviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [reviewSource, setReviewSource] = useState<SourceChunk | null>(null);

  useEffect(() => {
    void loadReview();
  }, [examId]);

  async function loadReview(): Promise<void> {
    setIsLoading(true);
    try {
      const response = await fetchMockExamReview(examId);
      setReview(response);
      setError(null);
    } catch (requestError) {
      setReview(null);
      setError(requestError instanceof Error ? requestError.message : "Unable to load saved exam.");
    } finally {
      setIsLoading(false);
    }
  }

  const completedAt = review?.grade_result?.completed_at ?? review?.exam.created_at ?? null;
  const questionCount = review?.exam.questions.length ?? 0;
  const scopeLabel = review
    ? buildExamScopeLabel(review.exam.module_ids, review.exam.module_id)
    : null;

  return (
    <div className="stack">
      <section className="card">
        <div className="section-header">
          <div>
            <span className="timeline-kind">Mock exam</span>
            <h3>{review ? cleanDisplayText(review.exam.blueprint.title) : "Saved exam review"}</h3>
            {review ? (
              <p className="subtle">
                {completedAt ? formatTimestamp(completedAt) : "Time unavailable"} · {questionCount} questions
                {scopeLabel ? ` · ${scopeLabel}` : ""}
              </p>
            ) : null}
          </div>
        </div>
        {isLoading ? <p className="subtle">Loading saved exam...</p> : null}
        {error ? (
          <div className="status-panel error-panel" aria-live="polite">
            <strong>Issue:</strong> {error}
          </div>
        ) : null}
      </section>

      {review ? (
        <>
          <MetricGrid
            items={[
              {
                label: "Score",
                value: review.grade_result ? `${review.grade_result.overall_score}%` : "Ungraded"
              },
              { label: "Questions", value: String(questionCount) },
              { label: "Saved", value: completedAt ? formatTimestamp(completedAt) : "Time unavailable" }
            ]}
          />

          <section className="card">
            <h3>Question review</h3>
            {review.grade_result ? (
              <div className="stacked-list">
                {review.grade_result.results.map((result) => (
                  <QuestionReviewCard
                    key={result.question_id}
                    result={result}
                    onReviewMaterial={result.citations[0] ? () => setReviewSource(result.citations[0]) : null}
                  />
                ))}
              </div>
            ) : (
              <p className="subtle">This exam has been generated but not graded yet.</p>
            )}
          </section>
        </>
      ) : null}
      {reviewSource ? (
        <ReviewSourceModal
          citation={reviewSource}
          returnHref={`/history/exam/${encodeURIComponent(examId)}`}
          returnLabel="Back to exam review"
          onClose={() => setReviewSource(null)}
        />
      ) : null}
    </div>
  );
}

function buildExamScopeLabel(
  moduleIds: string[] | undefined,
  moduleId: string | null | undefined
): string | null {
  const normalized = Array.from(new Set(moduleIds ?? (moduleId ? [moduleId] : [])));
  if (!normalized.length) {
    return "whole course";
  }
  if (normalized.length === 1) {
    return "1 module";
  }
  return `${normalized.length} modules`;
}
