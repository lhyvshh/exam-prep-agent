"use client";

import React, { useEffect, useState } from "react";

import { fetchQuizReview, generateQuiz, trackActivityEvent } from "@/lib/api";
import {
  formatTimestamp,
  MetricGrid,
  QuestionReviewCard,
  cleanDisplayText
} from "@/components/shared/data-widgets";
import { ReviewSourceModal } from "@/components/shared/source-viewer";
import { scopeFromQuestionResult } from "@/lib/scope";
import type { QuestionGradeResult, QuizReviewResponse, SourceChunk } from "@/lib/schemas";

type HistoryReviewProps = {
  recordId: string;
};

export function HistoryReview({ recordId }: HistoryReviewProps): JSX.Element {
  const [review, setReview] = useState<QuizReviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isStartingPractice, setIsStartingPractice] = useState<string | null>(null);
  const [reviewSource, setReviewSource] = useState<SourceChunk | null>(null);

  useEffect(() => {
    void loadReview();
  }, [recordId]);

  async function loadReview(): Promise<void> {
    setIsLoading(true);
    try {
      const response = await fetchQuizReview(recordId);
      setReview(response);
      setError(null);
    } catch (requestError) {
      setReview(null);
      setError(requestError instanceof Error ? requestError.message : "Unable to load saved attempt.");
    } finally {
      setIsLoading(false);
    }
  }

  async function handlePracticeConcept(result: QuestionGradeResult): Promise<void> {
    if (!review || isStartingPractice) {
      return;
    }
    setIsStartingPractice(result.question_id);
    try {
      const response = await generateQuiz({
        course_id: review.quiz.course_id,
        module_id: review.quiz.module_id ?? null,
        query: `Practice: ${result.concept}`,
        question_count: 3,
        question_types: ["mcq"],
        retrieval_top_k: 6,
        selected_source_ids: result.citations.map((citation) => citation.source_id),
        scope: scopeFromQuestionResult(review.quiz.course_id, result, review.quiz.module_id ?? null),
        client_request_id: `practice-${result.question_id}-${Date.now()}`
      });
      void trackActivityEvent({
        course_id: review.quiz.course_id,
        module_id: review.quiz.module_id ?? null,
        material_id: result.citations[0]?.material_id ?? null,
        section_id: result.citations[0]?.source_id ?? null,
        quiz_id: review.quiz.quiz_id,
        question_id: result.question_id,
        question_type: result.question_type,
        event_type: "practice_concept_clicked",
        metadata_json: {
          origin: "history_review",
          concept: result.concept,
          practice_job_id: response.job_id
        }
      }).catch(() => undefined);
      window.location.href = `/courses/${encodeURIComponent(review.quiz.course_id)}/quiz?jobId=${encodeURIComponent(response.job_id)}`;
    } catch (practiceError) {
      setError(practiceError instanceof Error ? practiceError.message : "Unable to start concept practice.");
      setIsStartingPractice(null);
    }
  }

  const score = review?.results.length
    ? Math.round((review.results.reduce((total, result) => total + result.score, 0) / review.results.length) * 100)
    : 0;
  const savedAt = review?.quiz.created_at ?? null;
  const recordType = review?.quiz.query.toLowerCase().startsWith("practice:")
    ? "Concept practice"
    : "Quiz";

  return (
    <div className="stack">
      <section className="card">
        <div className="section-header">
          <div>
            <span className="timeline-kind">{recordType}</span>
            <h3>{review ? cleanDisplayText(review.quiz.query.replace(/^Practice:\s*/i, "")) : "Saved attempt review"}</h3>
            {review ? (
              <p className="subtle">
                Completed {savedAt ? formatTimestamp(savedAt) : "time unavailable"} · {review.quiz.questions.length} questions
              </p>
            ) : null}
          </div>
        </div>
        {isLoading ? <p className="subtle">Loading saved attempt...</p> : null}
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
              { label: "Score", value: `${score}%` },
              { label: "Questions", value: String(review.quiz.questions.length) },
              { label: "Saved", value: savedAt ? formatTimestamp(savedAt) : "Time unavailable" }
            ]}
          />

          <section className="card">
            <h3>Question review</h3>
            <div className="stacked-list">
              {review.results.map((result) => (
                <QuestionReviewCard
                  key={result.question_id}
                  result={result}
                  onReviewMaterial={result.citations[0] ? () => {
                    void trackActivityEvent({
                      course_id: review.quiz.course_id,
                      module_id: review.quiz.module_id ?? null,
                      material_id: result.citations[0].material_id,
                      section_id: result.citations[0].source_id,
                      quiz_id: review.quiz.quiz_id,
                      question_id: result.question_id,
                      question_type: result.question_type,
                      event_type: "review_material_clicked",
                      metadata_json: {
                        origin: "history_review",
                        concept: result.concept,
                        page_number: result.citations[0].locator?.page_number ?? null
                      }
                    }).catch(() => undefined);
                    setReviewSource(result.citations[0]);
                  } : null}
                  onPracticeConcept={() => void handlePracticeConcept(result)}
                  isPracticeStarting={isStartingPractice === result.question_id}
                />
              ))}
            </div>
          </section>
        </>
      ) : null}
      {reviewSource ? (
        <ReviewSourceModal
          citation={reviewSource}
          returnHref={`/history/${encodeURIComponent(recordId)}`}
          returnLabel="Back to review"
          onClose={() => setReviewSource(null)}
        />
      ) : null}
    </div>
  );
}
