import React from "react";
import type {
  MockExamHistoryItem,
  QuestionGradeResult,
  QuizAttemptSummary,
  QuizHistoryItem,
  SourceChunk
} from "@/lib/schemas";
import { sourceHrefFromCitation } from "@/lib/scope";

type MetricItem = {
  label: string;
  value: string;
  hint?: string;
};

type MasteryChartProps = {
  masteryByConcept: Record<string, number>;
  title?: string;
};

type HistoryAccordionProps = {
  quizzes: QuizHistoryItem[];
  mockExams: MockExamHistoryItem[];
  loading?: boolean;
  error?: string | null;
  title?: string;
  courseId?: string | null;
  focusedHistoryId?: string | null;
  onOpenAttempt?: (quizId: string) => void;
  onDeleteAttempt?: (quizId: string) => void;
};

type QuestionReviewCardProps = {
  result: QuestionGradeResult;
  reviewHref?: string;
  onReviewMaterial?: (() => void) | null;
  onPracticeConcept?: (() => void) | null;
  isPracticeStarting?: boolean;
  onDeleteAttempt?: (() => void) | null;
  compact?: boolean;
};

type WrongQuestionListProps = {
  results: QuestionGradeResult[];
  reviewHrefForResult?: (result: QuestionGradeResult) => string | undefined;
  onReviewMaterial?: (result: QuestionGradeResult) => void;
  onPracticeConcept?: (result: QuestionGradeResult) => void;
  startingPracticeQuestionId?: string | null;
};

type ReviewMaterialOptions = {
  returnTo?: string;
};

export function gradeBadgeLabel(result: QuestionGradeResult): string {
  return result.is_correct ? "Correct" : "Incorrect";
}

export function gradeBadgeClass(result: QuestionGradeResult): string {
  return result.is_correct ? "result-good" : "result-bad";
}

export function formatSourceLabel(citation?: SourceChunk | null): string {
  if (!citation) {
    return "Source unavailable";
  }
  const location = formatLocatorLabel(citation);
  return [truncateLabel(citation.file_name, 48), location ?? truncateLabel(cleanDisplayText(citation.section_title), 40)]
    .filter(Boolean)
    .join(" · ");
}

export function buildMaterialReviewHref(
  citation?: SourceChunk | null,
  options: ReviewMaterialOptions = {}
): string | undefined {
  if (!citation) {
    return undefined;
  }
  return sourceHrefFromCitation(citation, options.returnTo);
}

export function simplifyExplanation(result: QuestionGradeResult): string {
  const raw = cleanDisplayText(result.explanation);
  if (!raw) {
    return result.is_correct
      ? "Your answer matches the grounded material."
      : "The submitted answer does not match the grounded material.";
  }

  const withoutCitations = raw
    .replace(/citation:\s*[^.]+/gi, "")
    .replace(/submitted answer:?\s*"?[^."]+"?/gi, "")
    .replace(/correct answer:?\s*"?[^."]+"?/gi, "")
    .replace(/the submitted answer was incorrect\.?/gi, "")
    .replace(/the submission was incorrect\.?/gi, "")
    .replace(/the submission was correct\.?/gi, "")
    .replace(/review the citation for more detail\.?/gi, "")
    .replace(/\s+/g, " ")
    .replace(/^[,.;:\s]+/, "")
    .trim();

  return withoutCitations || raw;
}

export function learnerFacingExplanation(result: QuestionGradeResult): string {
  const simplified = simplifyExplanation(result)
    .replace(/the citation excerpt mentions/gi, "the source states")
    .replace(/because the citation excerpt/gi, "because the source")
    .replace(/the citation\s+"[^"]+"\s+supports/gi, "the source supports")
    .replace(/the cited concept/gi, "this concept")
    .replace(/the grounded concept/gi, "the core idea")
    .replace(/the grounded material/gi, "this section")
    .replace(/the remaining options are weaker distractors\.?/gi, "")
    .replace(/the other choices do not match the core idea as closely\.?/gi, "")
    .replace(/\s+/g, " ")
    .trim();

  if (result.is_correct) {
    return truncateLabel(
      simplified || "Your answer matches the main idea taught in this section.",
      180
    );
  }

  const correctAnswer = cleanDisplayText(result.correct_answer);
  const base =
    simplified ||
    "Your answer does not match the concept taught in this section. Review the core idea and try again.";

  if (base.toLowerCase().includes(correctAnswer.toLowerCase())) {
    return truncateLabel(base, 220);
  }

  return truncateLabel(
    `${base} The correct concept is ${correctAnswer}.`,
    220
  );
}

export function cleanDisplayText(value: string): string {
  const cleaned = value
    .replace(/\s+/g, " ")
    .replace(/\s+\|\s+/g, " | ")
    .replace(/(?:^|\s)(page|pages|slide|slides)\s+\d+(?:-\d+)?/gi, (match) => match.toLowerCase())
    .trim();

  const pipeParts = cleaned
    .split("|")
    .map((part) => part.trim())
    .filter(Boolean);
  const dedupedPipeParts = pipeParts.filter(
    (part, index) =>
      index === pipeParts.findIndex((candidate) => candidate.toLowerCase() === part.toLowerCase())
  );
  const recombined = dedupedPipeParts.length > 0 ? dedupedPipeParts.join(" | ") : cleaned;
  return recombined.replace(/\b(.+?)\s+\1\b/gi, "$1").trim();
}

export function truncateLabel(value: string, maxLength: number = 72): string {
  const cleaned = cleanDisplayText(value);
  if (cleaned.length <= maxLength) {
    return cleaned;
  }
  return `${cleaned.slice(0, maxLength - 1).trimEnd()}…`;
}

export function MetricGrid({ items }: { items: MetricItem[] }): JSX.Element {
  return (
    <div className="metric-grid">
      {items.map((item) => (
        <article className="metric-card" key={item.label}>
          <p className="eyebrow">{item.label}</p>
          <h2>{item.value}</h2>
          {item.hint ? <p className="subtle">{item.hint}</p> : null}
        </article>
      ))}
    </div>
  );
}

export function MasteryChart({
  masteryByConcept,
  title = "Mastery by concept"
}: MasteryChartProps): JSX.Element {
  const entries = Object.entries(masteryByConcept)
    .sort(([, left], [, right]) => right - left)
    .slice(0, 8);

  return (
    <section className="card">
      <h3>{title}</h3>
      {entries.length === 0 ? (
        <p className="subtle">No graded concepts yet.</p>
      ) : (
        <div className="chart-list">
          {entries.map(([concept, score]) => (
            <div className="chart-row" key={concept}>
              <div className="chart-label-row">
                <strong>{truncateLabel(concept, 48)}</strong>
                <span className="subtle">{Math.round(score * 100)}%</span>
              </div>
              <div className="chart-track" aria-hidden="true">
                <div
                  className="chart-bar"
                  style={{ width: `${Math.max(8, Math.round(score * 100))}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

export const AttemptHistory = HistoryAccordion;

export function HistoryAccordion({
  quizzes,
  mockExams,
  loading = false,
  error = null,
  title = "Study history",
  courseId = null,
  focusedHistoryId = null,
  onOpenAttempt,
  onDeleteAttempt
}: HistoryAccordionProps): JSX.Element {
  return (
    <details className="card collapsible-card" id="quiz-exam-history" open={Boolean(focusedHistoryId)}>
      <summary>
        <span>
          <strong>{title}</strong>
          <small>{quizzes.length + mockExams.length} saved items</small>
        </span>
      </summary>

      {loading ? <p className="subtle">Loading recent study history...</p> : null}
      {error ? <p className="subtle">{error}</p> : null}

      {!loading && quizzes.length === 0 && mockExams.length === 0 ? (
        <p className="subtle">No quiz, exam, or concept-practice attempts yet.</p>
      ) : (
        <div className="history-accordion">
          {quizzes.map((quiz) => (
            <article
              className={`history-item${focusedHistoryId === quiz.quiz_id ? " history-item-focused" : ""}`}
              id={`history-${quiz.quiz_id}`}
              key={quiz.quiz_id}
            >
              <a className="history-summary" href={buildHistoryHref(courseId, "quiz", quiz.quiz_id)}>
                <div className="history-summary-text">
                  <span className="timeline-kind">{historyKindLabel(quiz.query, quiz.record_type)}</span>
                  <strong>{truncateLabel(cleanDisplayText(quiz.query), 60)}</strong>
                  <p className="subtle">
                    {quiz.question_count} questions
                    {quiz.overall_score !== null ? ` · ${quiz.overall_score}%` : ""}
                    {quiz.created_at ? ` · ${formatTimestamp(quiz.created_at)}` : " · time unavailable"}
                  </p>
                </div>
              </a>
              <div className="history-body">
                {(quiz.attempts ?? [
                  {
                    quiz_id: quiz.quiz_id,
                    created_at: quiz.created_at ?? null,
                    question_count: quiz.question_count,
                    overall_score: quiz.overall_score,
                    wrong_question_count: quiz.wrong_question_count,
                    module_id: quiz.module_id ?? null
                  }
                ]).length === 0 ? (
                  <p className="subtle">No attempts stored for this quiz yet.</p>
                ) : (
                  <div className="stacked-list">
                    {(quiz.attempts ?? [
                      {
                        quiz_id: quiz.quiz_id,
                        created_at: quiz.created_at ?? null,
                        question_count: quiz.question_count,
                        overall_score: quiz.overall_score,
                        wrong_question_count: quiz.wrong_question_count,
                        module_id: quiz.module_id ?? null
                      }
                    ]).map((attempt, index) => (
                      <article className="timeline-item" key={attempt.quiz_id}>
                        <div className="preview-header">
                          <div>
                            <strong>
                              <a href={buildHistoryHref(courseId, "quiz", attempt.quiz_id)}>
                                {index === 0 ? "Latest attempt" : `Attempt ${index + 1}`}
                              </a>
                            </strong>
                            <p className="subtle">
                              {attempt.question_count} questions
                              {attempt.overall_score !== null ? ` · ${attempt.overall_score}%` : ""}
                              {attempt.created_at ? ` · ${formatTimestamp(attempt.created_at)}` : " · time unavailable"}
                            </p>
                          </div>
                          <div className="action-row">
                            {onOpenAttempt ? (
                              <button
                                className="secondary-button"
                                onClick={() => onOpenAttempt(attempt.quiz_id)}
                                type="button"
                              >
                                Review
                              </button>
                            ) : null}
                            {onDeleteAttempt ? (
                              <button
                                className="secondary-button"
                                onClick={() => onDeleteAttempt(attempt.quiz_id)}
                                type="button"
                              >
                                Delete
                              </button>
                            ) : null}
                          </div>
                        </div>
                      </article>
                    ))}
                  </div>
                )}
              </div>
            </article>
          ))}

          {mockExams.map((exam) => (
            <article
              className={`timeline-item${focusedHistoryId === exam.exam_id ? " history-item-focused" : ""}`}
              id={`history-${exam.exam_id}`}
              key={exam.exam_id}
            >
              <span className="timeline-kind">Mock exam</span>
              <strong>
                <a href={buildHistoryHref(courseId, "exam", exam.exam_id)}>
                  {truncateLabel(exam.title, 60)}
                </a>
              </strong>
              <p className="subtle">
                {exam.question_count} questions
                {exam.score_percent !== null && exam.score_percent !== undefined ? ` · ${exam.score_percent}%` : ""}
                {exam.completed_at
                  ? ` · ${formatTimestamp(exam.completed_at)}`
                  : exam.created_at
                  ? ` · ${formatTimestamp(exam.created_at)}`
                  : " · time unavailable"}
              </p>
            </article>
          ))}

        </div>
      )}
    </details>
  );
}

export function QuestionReviewCard({
  result,
  reviewHref,
  onReviewMaterial = null,
  onPracticeConcept = null,
  isPracticeStarting = false,
  onDeleteAttempt = null,
  compact = false
}: QuestionReviewCardProps): JSX.Element {
  const source = result.citations[0] ?? null;
  const explanation = learnerFacingExplanation(result);
  const reviewTitle = cleanDisplayText(result.concept || "Question review");

  return (
    <article className={`preview-item review-card${compact ? " review-card-compact" : ""}`}>
      <div className="preview-header">
        <div>
          <strong>{truncateLabel(reviewTitle, 56)}</strong>
        </div>
        <span className={`result-badge ${gradeBadgeClass(result)}`}>{gradeBadgeLabel(result)}</span>
      </div>

      <div className="review-stack">
        <div>
          <p className="review-label">Explanation</p>
          <p className="review-copy">{explanation}</p>
        </div>
        <div>
          <p className="review-label">Correct answer</p>
          <p className="review-copy">{cleanDisplayText(result.correct_answer)}</p>
        </div>
        <div>
          <p className="review-label">Source</p>
          <p className="review-copy" title={source?.citation_label}>
            {formatSourceLabel(source)}
          </p>
        </div>
      </div>

      <div className="action-row">
        {onReviewMaterial ? (
          <button className="secondary-button" onClick={onReviewMaterial} type="button">
            Review material
          </button>
        ) : reviewHref ? (
          <a className="secondary-button" href={reviewHref}>
            Review material
          </a>
        ) : null}
        {onPracticeConcept ? (
          <button className="secondary-button" disabled={isPracticeStarting} onClick={onPracticeConcept} type="button">
            {isPracticeStarting ? "Starting..." : "Practice this concept"}
          </button>
        ) : null}
        {onDeleteAttempt ? (
          <button className="secondary-button" onClick={onDeleteAttempt} type="button">
            Delete attempt
          </button>
        ) : null}
      </div>

      {source || result.submitted_answer ? (
        <details className="review-details">
          <summary>Show details</summary>
          <div className="review-details-body">
            {result.submitted_answer ? (
              <p>
                <strong>Your answer:</strong> {cleanDisplayText(result.submitted_answer || "No answer provided")}
              </p>
            ) : null}
            {source ? (
              <>
                <p>
                  <strong>Full citation:</strong> {source.citation_label}
                </p>
              </>
            ) : null}
          </div>
        </details>
      ) : null}
    </article>
  );
}

export function WrongQuestionList({
  results,
  reviewHrefForResult,
  onReviewMaterial,
  onPracticeConcept,
  startingPracticeQuestionId = null
}: WrongQuestionListProps): JSX.Element {
  const groupedResults = results.reduce<Record<string, QuestionGradeResult[]>>((groups, result) => {
    const groupKey = cleanDisplayText(result.concept || "Unlabeled concept");
    groups[groupKey] = [...(groups[groupKey] ?? []), result];
    return groups;
  }, {});

  return (
    <section className="card">
      <h3>Wrong-question review</h3>
      {results.length === 0 ? (
        <p className="subtle">No missed questions recorded yet.</p>
      ) : (
        <div className="wrong-question-accordion">
          {Object.entries(groupedResults).map(([concept, conceptResults]) => (
            <details className="wrong-question-group" key={concept}>
              <summary>
                <span>
                  <strong>{truncateLabel(concept, 48)}</strong>
                  <small>{conceptResults.length} missed question{conceptResults.length === 1 ? "" : "s"}</small>
                </span>
              </summary>
              <div className="stacked-list">
                {conceptResults.map((result) => (
                  <QuestionReviewCard
                    compact
                    key={result.question_id}
                    result={result}
                    reviewHref={reviewHrefForResult?.(result)}
                    onReviewMaterial={onReviewMaterial ? () => onReviewMaterial(result) : null}
                    onPracticeConcept={onPracticeConcept ? () => onPracticeConcept(result) : null}
                    isPracticeStarting={startingPracticeQuestionId === result.question_id}
                  />
                ))}
              </div>
            </details>
          ))}
        </div>
      )}
    </section>
  );
}

function formatLocatorLabel(citation: SourceChunk): string | null {
  if (citation.locator.page_number) {
    return `page ${citation.locator.page_number}`;
  }
  if (citation.locator.slide_number) {
    return `slide ${citation.locator.slide_number}`;
  }
  return null;
}

function formatRelativeTimestamp(value: string): string {
  return formatTimestamp(value);
}

export function formatTimestamp(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "Saved earlier";
  }
  return parsed.toLocaleString();
}

function historyKindLabel(query: string, recordType?: string): string {
  return recordType === "concept_practice" || query.toLowerCase().startsWith("practice:")
    ? "Concept practice"
    : "Quiz";
}

function buildHistoryHref(_courseId: string | null | undefined, type: "quiz" | "exam", recordId: string): string {
  return type === "exam"
    ? `/history/exam/${encodeURIComponent(recordId)}`
    : `/history/${encodeURIComponent(recordId)}`;
}
