"use client";

import React, { useEffect, useState } from "react";

import { fetchMockExamReview, fetchQuizReview } from "@/lib/api";

type HistoryRedirectProps = {
  recordId: string;
  type: "quiz" | "exam";
};

export function HistoryRedirect({ recordId, type }: HistoryRedirectProps): JSX.Element {
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function redirectToCourseHistory(): Promise<void> {
      try {
        if (type === "exam") {
          const response = await fetchMockExamReview(recordId);
          if (!cancelled) {
            window.location.replace(
              `/courses/${encodeURIComponent(response.exam.course_id)}/wrong-questions?historyExamId=${encodeURIComponent(recordId)}#quiz-exam-history`
            );
          }
          return;
        }

        const response = await fetchQuizReview(recordId);
        if (!cancelled) {
          window.location.replace(
            `/courses/${encodeURIComponent(response.quiz.course_id)}/wrong-questions?historyQuizId=${encodeURIComponent(recordId)}#quiz-exam-history`
          );
        }
      } catch (redirectError) {
        if (!cancelled) {
          setError(redirectError instanceof Error ? redirectError.message : "Unable to open this saved record.");
        }
      }
    }

    void redirectToCourseHistory();
    return () => {
      cancelled = true;
    };
  }, [recordId, type]);

  return (
    <main className="page-shell">
      <section className="card">
        <p className="eyebrow">History</p>
        <h1>Opening saved record</h1>
        {error ? (
          <div className="status-panel error-panel" aria-live="polite">
            <strong>Issue:</strong> {error}
          </div>
        ) : (
          <p className="subtle">Taking you to the course quiz/exam history.</p>
        )}
      </section>
    </main>
  );
}
