"use client";

import React from "react";
import type { ChangeEvent, FormEvent } from "react";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";

import {
  cancelQuizGenerationJob,
  fetchCourseMaterials,
  fetchQuizGenerationJob,
  generateQuiz,
  gradeQuiz,
  trackActivityEvent
} from "@/lib/api";
import type {
  CourseMaterialsResponse,
  QuestionType,
  QuizBundle,
  QuizGenerationJobResponse,
  QuizGenerationRequest,
  QuizGradeResponse,
  QuizSubmissionAnswer,
  SourceChunk
} from "@/lib/schemas";
import {
  cleanDisplayText,
  QuestionReviewCard,
  MasteryChart,
  MetricGrid,
  truncateLabel
} from "@/components/shared/data-widgets";
import { writeButlerPageContext } from "@/lib/butler-context";
import { ReviewSourceModal } from "@/components/shared/source-viewer";
import { useCourseSelection } from "@/components/shared/course-context";

const defaultRequest: QuizGenerationRequest = {
  course_id: "",
  module_id: null,
  query: "",
  question_count: 3,
  question_types: ["mcq"],
  retrieval_top_k: 6,
  selected_source_ids: [],
  client_request_id: null
};

const POLL_INTERVAL_MS = 1500;
const EMPTY_JOB_PROGRESS = {
  total_questions: 0,
  completed_questions: 0,
  fallback_questions: 0,
  current_question_index: 0
} satisfies QuizGenerationJobResponse["progress"];

export function QuizWorkspace(): JSX.Element {
  const searchParams = useSearchParams();
  const {
    selectedCourseId,
    selectedModuleId,
    selectedCourse,
    selectedModule
  } = useCourseSelection();
  const [requestState, setRequestState] = useState<QuizGenerationRequest>(defaultRequest);
  const [courseMaterials, setCourseMaterials] = useState<CourseMaterialsResponse | null>(null);
  const [selectedQuizSourceIds, setSelectedQuizSourceIds] = useState<string[]>([]);
  const [quiz, setQuiz] = useState<QuizBundle | null>(null);
  const [activeJob, setActiveJob] = useState<QuizGenerationJobResponse | null>(null);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [gradeResult, setGradeResult] = useState<QuizGradeResponse | null>(null);
  const [answers, setAnswers] = useState<Record<string, QuizSubmissionAnswer>>({});
  const [isGenerating, setIsGenerating] = useState<boolean>(false);
  const [isGrading, setIsGrading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [reviewSource, setReviewSource] = useState<SourceChunk | null>(null);
  const pollTimerRef = useRef<number | null>(null);
  const submitInFlightRef = useRef<boolean>(false);
  const resumedJobIdRef = useRef<string | null>(null);
  const answeredEventRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    void loadContextMaterials();
    return () => {
      clearPollTimer();
    };
  }, [selectedCourseId, selectedModuleId]);

  useEffect(() => {
    const reviewQuizId = searchParams?.get("reviewQuizId");
    if (!reviewQuizId) {
      return;
    }
    window.location.replace(`/history/${encodeURIComponent(reviewQuizId)}`);
  }, [searchParams]);

  useEffect(() => {
    const jobId = searchParams?.get("jobId");
    if (!jobId || resumedJobIdRef.current === jobId) {
      return;
    }
    resumedJobIdRef.current = jobId;
    startPolling(jobId);
  }, [searchParams]);

  useEffect(() => {
    if (!quiz || !gradeResult || gradeResult.results.length === 0) {
      return;
    }
    const result = gradeResult.results.find((item) => !item.is_correct) ?? gradeResult.results[0];
    const questionIndex = quiz.questions.findIndex((item) => item.question_id === result.question_id);
    const question = quiz.questions[questionIndex];
    if (!question) {
      return;
    }
    const citations = result.citations.length > 0 ? result.citations : question.citations;
    const selectedOptionId = result.submitted_option_id ?? answers[question.question_id]?.selected_option_id ?? null;
    writeButlerPageContext({
      page_type: "quiz_review",
      route: typeof window === "undefined" ? "" : `${window.location.pathname}${window.location.search}`,
      title: "Quiz review",
      visible_text: [
        `Question ${questionIndex + 1}: ${cleanDisplayText(question.prompt)}`,
        `Submitted answer: ${result.submitted_answer || selectedOptionId || "not answered"}`,
        `Correct answer: ${result.correct_answer}`,
        `Explanation: ${result.explanation}`
      ].join(" "),
      source_ids: uniqueStrings(citations.map((citation) => citation.source_id)),
      material_ids: uniqueStrings(citations.map((citation) => citation.material_id)),
      section_ids: uniqueStrings(citations.map((citation) => citation.source_id)),
      question: {
        question_number: questionIndex + 1,
        question_id: question.question_id,
        prompt: cleanDisplayText(question.prompt),
        selected_option_id: selectedOptionId,
        correct_option_id: result.correct_option_id ?? null,
        correct_answer: result.correct_answer,
        explanation: result.explanation,
        concept: result.concept,
        source_page: question.source_page ?? citations[0]?.locator.page_number ?? null,
        options: question.options.map((option) => ({
          option_id: option.option_id,
          text: cleanDisplayText(option.text)
        }))
      }
    });
  }, [answers, gradeResult, quiz]);

  async function loadContextMaterials(): Promise<void> {
    clearPollTimer();
    setActiveJob(null);
    setActiveJobId(null);
    setQuiz(null);
    setGradeResult(null);
    setAnswers({});

    if (searchParams?.get("reviewQuizId")) {
      setCourseMaterials(null);
      setSelectedQuizSourceIds([]);
      clearStoredJobId(null, null);
      return;
    }

    if (!selectedCourseId) {
      setCourseMaterials(null);
      setRequestState(defaultRequest);
      setSelectedQuizSourceIds([]);
      clearStoredJobId(null, null);
      return;
    }

    try {
      const materials = await fetchCourseMaterials(selectedCourseId, selectedModuleId);
      setCourseMaterials(materials);
      const selectedSourceIds =
        materials.default_quiz_source_ids.length > 0
          ? materials.default_quiz_source_ids
          : materials.quiz_sources.slice(0, 3).map((source) => source.quiz_source_id);
      setSelectedQuizSourceIds(selectedSourceIds);
      setRequestState({
        course_id: selectedCourseId,
        module_id: selectedModuleId,
        query:
          materials.quiz_sources[0]?.summary ??
          materials.quiz_sources[0]?.title ??
          selectedModule?.display_name ??
          selectedCourse?.display_name ??
          "",
        question_count: 3,
        question_types: ["mcq"],
        retrieval_top_k: 6,
        selected_source_ids: resolveSelectedSourceIds(materials, selectedSourceIds),
        scope: {
          course_id: selectedCourseId,
          module_ids: selectedModuleId ? [selectedModuleId] : [],
          material_ids: materials.records.map((record) => record.material_id),
          section_ids: resolveSelectedSourceIds(materials, selectedSourceIds),
          source_type: "study_material"
        },
        client_request_id: null
      });
      setError(null);

      const storedJobId = readStoredJobId(selectedCourseId, selectedModuleId);
      if (storedJobId && resumedJobIdRef.current !== storedJobId) {
        resumedJobIdRef.current = storedJobId;
        startPolling(storedJobId);
      }
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Unable to load current materials.");
      setCourseMaterials(null);
    }
  }

  function clearPollTimer(): void {
    if (pollTimerRef.current !== null) {
      window.clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }

  function updateAnswer(
    questionId: string,
    field: "selected_option_id" | "answer_text",
    value: string
  ): void {
    setAnswers((current) => ({
      ...current,
      [questionId]: {
        ...current[questionId],
        question_id: questionId,
        [field]: value
      }
    }));
    if (!answeredEventRef.current.has(questionId)) {
      answeredEventRef.current.add(questionId);
      const question = quiz?.questions.find((item) => item.question_id === questionId);
      const citation = question?.citations[0];
      void trackActivityEvent({
        course_id: selectedCourseId,
        module_id: selectedModuleId,
        material_id: citation?.material_id ?? null,
        section_id: citation?.source_id ?? null,
        quiz_id: quiz?.quiz_id ?? null,
        question_id: questionId,
        question_type: question?.question_type ?? null,
        difficulty: question?.difficulty ?? null,
        event_type: "question_answered",
        metadata_json: {
          origin: "quiz_workspace",
          answer_field: field
        }
      }).catch(() => undefined);
    }
  }

  function toggleQuestionType(type: "mcq"): void {
    setRequestState((current) => {
      const nextTypes = current.question_types.includes(type)
        ? current.question_types.filter((item) => item !== type)
        : [...current.question_types, type];
      return {
        ...current,
        question_types: nextTypes.length > 0 ? nextTypes : [type]
      };
    });
  }

  function toggleSourceSelection(quizSourceId: string): void {
    setSelectedQuizSourceIds((current) =>
      current.includes(quizSourceId)
        ? current.filter((item) => item !== quizSourceId)
        : [...current, quizSourceId]
    );
  }

  async function handleGenerate(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!selectedCourseId || submitInFlightRef.current || isGenerating) {
      return;
    }

    submitInFlightRef.current = true;
    setError(null);
    setGradeResult(null);

    try {
      const clientRequestId = createClientRequestId();
      const selectedSourceIds = resolveSelectedSourceIds(courseMaterials, selectedQuizSourceIds);
      const materialIds = courseMaterials?.records.map((record) => record.material_id) ?? [];
      const response = await generateQuiz({
        ...requestState,
        course_id: selectedCourseId,
        module_id: selectedModuleId,
        selected_source_ids: selectedSourceIds,
        scope: {
          course_id: selectedCourseId,
          module_ids: selectedModuleId ? [selectedModuleId] : [],
          material_ids: materialIds,
          section_ids: selectedSourceIds,
          source_type: "study_material"
        },
        client_request_id: clientRequestId
      });
      void trackActivityEvent({
        course_id: selectedCourseId,
        module_id: selectedModuleId,
        event_type: "quiz_started",
        metadata_json: {
          origin: "quiz_workspace",
          job_id: response.job_id,
          selected_source_ids: selectedSourceIds
        }
      }).catch(() => undefined);
      writeStoredJobId(selectedCourseId, selectedModuleId, response.job_id);
      startPolling(response.job_id);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to start quiz generation.");
      setIsGenerating(false);
    } finally {
      submitInFlightRef.current = false;
    }
  }

  async function handleCancel(): Promise<void> {
    if (!activeJobId) {
      return;
    }

    try {
      await cancelQuizGenerationJob(activeJobId);
      setIsGenerating(false);
      clearPollTimer();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to cancel generation.");
    }
  }

  async function handleGrade(): Promise<void> {
    if (!quiz || !activeJob || !isJobReadyForReview(activeJob.status)) {
      return;
    }
    setIsGrading(true);
    setError(null);

    try {
      const orderedAnswers = quiz.questions.map((question) => answers[question.question_id] ?? {
        question_id: question.question_id,
        selected_option_id: null,
        answer_text: ""
      });
      const response = await gradeQuiz(quiz.quiz_id, orderedAnswers);
      setGradeResult(response);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to grade quiz.");
    } finally {
      setIsGrading(false);
    }
  }

  async function handlePracticeConcept(result: QuizGradeResponse["results"][number]): Promise<void> {
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
        scope: {
          course_id: selectedCourseId,
          module_ids: selectedModuleId ? [selectedModuleId] : [],
          material_ids: Array.from(new Set(result.citations.map((citation) => citation.material_id))),
          section_ids: result.citations.map((citation) => citation.source_id),
          source_type: "study_material"
        },
        client_request_id: `practice-${result.question_id}-${Date.now()}`
      });
      void trackActivityEvent({
        course_id: selectedCourseId,
        module_id: selectedModuleId,
        quiz_id: quiz?.quiz_id ?? null,
        question_id: result.question_id,
        question_type: result.question_type,
        event_type: "practice_concept_clicked",
        metadata_json: {
          origin: "quiz_workspace_review",
          concept: result.concept,
          practice_job_id: response.job_id
        }
      }).catch(() => undefined);
      window.location.href = `/courses/${encodeURIComponent(selectedCourseId)}/quiz?jobId=${encodeURIComponent(response.job_id)}`;
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to start concept practice.");
    }
  }

  function startPolling(jobId: string): void {
    clearPollTimer();
    setIsGenerating(true);
    setActiveJobId(jobId);
    void pollJob(jobId);
  }

  async function pollJob(jobId: string): Promise<void> {
    try {
      const job = await fetchQuizGenerationJob(jobId);
      setActiveJob(job);
      if (job.quiz) {
        setQuiz(job.quiz);
      }

      if (job.status === "queued" || job.status === "running") {
        setIsGenerating(true);
        pollTimerRef.current = window.setTimeout(() => {
          void pollJob(jobId);
        }, POLL_INTERVAL_MS);
        return;
      }

      setIsGenerating(false);
      clearPollTimer();
      if (selectedCourseId) {
        clearStoredJobId(selectedCourseId, selectedModuleId);
      }
      if (job.status === "failed" || job.status === "cancelled") {
        setError(job.error_summary ?? `Quiz generation ${job.status}.`);
      } else if (job.status === "partial" && job.error_summary) {
        setError(job.error_summary);
      }
    } catch (requestError) {
      setIsGenerating(false);
      clearPollTimer();
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to check quiz generation progress."
      );
    }
  }

  const activeJobProgress = activeJob?.progress ?? EMPTY_JOB_PROGRESS;
  const metrics = quiz
    ? [
        { label: "Questions", value: String(quiz.questions.length) },
        { label: "Source", value: selectedModule?.display_name ?? selectedCourse?.display_name ?? quiz.course_id },
        {
          label: "Score",
          value: gradeResult ? `${gradeResult.overall_score}%` : "Pending"
        }
      ]
    : [
        { label: "Questions", value: activeJob ? String(activeJobProgress.completed_questions) : "0" },
        { label: "Source", value: selectedModule?.display_name ?? selectedCourse?.display_name ?? "No context" },
        { label: "Score", value: "Pending" }
      ];

  return (
    <div className="stack">
      <section className="card">
        <div className="section-header">
          <div>
            <h3>Generate a grounded quiz</h3>
            {!selectedCourseId ? (
              <p className="subtle">Choose a course or module in the shared selector to generate a quiz.</p>
            ) : (
              <p>
                Building from {selectedCourse?.display_name}
                {selectedModule ? ` · ${selectedModule.display_name}` : " · whole course"}.
              </p>
            )}
          </div>
        </div>

        <form className="config-form" onSubmit={handleGenerate}>
            <div className="two-column-grid">
              <label className="field">
                <span>Question count</span>
                <input
                  aria-label="Question count"
                  type="number"
                  min={1}
                  max={10}
                  value={requestState.question_count}
                  onChange={(event) =>
                    setRequestState((current) => ({
                      ...current,
                      question_count: Number(event.target.value)
                    }))
                  }
                />
              </label>
              <label className="field">
                <span>Retrieval top K</span>
                <input
                  aria-label="Retrieval top K"
                  type="number"
                  min={1}
                  max={20}
                  value={requestState.retrieval_top_k}
                  onChange={(event) =>
                    setRequestState((current) => ({
                      ...current,
                      retrieval_top_k: Number(event.target.value)
                    }))
                  }
                />
              </label>
            </div>

            <label className="field">
              <span>Grounding query</span>
              <input
                aria-label="Grounding query"
                type="text"
                value={requestState.query}
                onChange={(event) =>
                  setRequestState((current) => ({ ...current, query: event.target.value }))
                }
              />
            </label>

            <div className="field">
              <span>Question types</span>
              <div className="chip-toggle-row" role="group" aria-label="Question types">
                {(["mcq"] as const).map((type) => {
                  const selected = requestState.question_types.includes(type);
                  return (
                    <button
                      aria-pressed={selected}
                      className={`chip-toggle${selected ? " chip-toggle-active" : ""}`}
                      key={type}
                      onClick={() => toggleQuestionType(type)}
                      type="button"
                    >
                      MCQ
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="pill-row">
              <button className="primary-button" disabled={isGenerating || !selectedCourseId} type="submit">
                {isGenerating ? "Generating..." : "Generate quiz"}
              </button>
              {isGenerating && activeJobId ? (
                <button className="secondary-button" onClick={() => void handleCancel()} type="button">
                  Cancel
                </button>
              ) : null}
            </div>
        </form>

        {courseMaterials && courseMaterials.quiz_sources.length > 0 ? (
          <div className="stack">
            <div className="quiz-source-chip-row">
              {courseMaterials.quiz_sources.slice(0, 6).map((source) => (
                <span
                  className="quiz-source-chip"
                  key={source.quiz_source_id}
                  title={`${source.file_name} · ${source.summary}`}
                >
                  {truncateLabel(cleanDisplayText(source.title), 36)}
                </span>
              ))}
            </div>

            <div className="stack">
              <div>
                <strong>Quiz source sections</strong>
                <p className="subtle">
                  Choose cleaned teaching sections from the active course or module. Administrative-only
                  content is excluded automatically.
                </p>
              </div>
              <div className="quiz-source-list">
                {courseMaterials.quiz_sources.map((source) => (
                  <label className="quiz-source-card" key={source.quiz_source_id}>
                    <input
                      checked={selectedQuizSourceIds.includes(source.quiz_source_id)}
                      onChange={() => toggleSourceSelection(source.quiz_source_id)}
                      type="checkbox"
                    />
                    <div className="quiz-source-details">
                      <div className="quiz-source-header">
                        <strong>{truncateLabel(cleanDisplayText(source.title), 56)}</strong>
                        <span className="subtle">
                          {source.section_count} section{source.section_count === 1 ? "" : "s"} ·{" "}
                          {source.location_label}
                        </span>
                      </div>
                      <p className="quiz-source-summary">{truncateLabel(cleanDisplayText(source.summary), 120)}</p>
                      <p className="subtle">
                        {source.file_name} · {source.content_label.replaceAll("_", " ")}
                        {source.is_default ? " · recommended" : ""}
                      </p>
                    </div>
                  </label>
                ))}
              </div>
            </div>
          </div>
        ) : null}

        {activeJob ? (
          <div className="status-panel" aria-live="polite">
            <strong>Quiz job:</strong> {activeJob.status}
            <p className="subtle">
              {renderProgressLabel(activeJob)}
            </p>
            <p className="subtle">
              {activeJobProgress.completed_questions} / {activeJobProgress.total_questions} ready
              {activeJobProgress.fallback_questions > 0
                ? ` · ${activeJobProgress.fallback_questions} fallback`
                : ""}
            </p>
          </div>
        ) : null}

        {error ? (
          <div className="status-panel error-panel" aria-live="polite">
            <strong>Issue:</strong> {error}
          </div>
        ) : null}
      </section>

      <MetricGrid items={metrics} />

      {quiz ? (
        <section className="card">
          <div className="section-header">
            <div>
              <h3>{activeJob && !isJobReadyForReview(activeJob.status) ? "Quiz progress" : "Answer the quiz"}</h3>
              <p className="subtle">
                Source: {selectedCourse?.display_name}
                {selectedModule ? ` · ${selectedModule.display_name}` : " · whole course"}
              </p>
            </div>
            <button
              className="primary-button"
              disabled={isGrading || !activeJob || !isJobReadyForReview(activeJob.status)}
              onClick={() => void handleGrade()}
              type="button"
            >
              {isGrading ? "Grading..." : "Grade submission"}
            </button>
          </div>

          <div className="question-list">
            {quiz.questions.map((question, index) => {
              const partialResult = activeJob?.partial_results.find(
                (result) => result.question_id === question.question_id
              );
              return (
                <article className="question-card" key={question.question_id}>
                  <div className="preview-header">
                    <strong>
                      Question {index + 1}: {cleanDisplayText(question.concept)}
                    </strong>
                    <span className="subtle">
                      {question.question_type} · difficulty {question.difficulty}
                      {partialResult ? ` · ${partialResult.generation_mode}` : ""}
                    </span>
                  </div>
                  {question.quality_validation && shouldShowQualityBadge(question.quality_validation) ? (
                    <span
                      className={qualityBadgeClass(question.quality_validation.accepted_for_delivery)}
                      title={question.quality_validation.notes.join(" ")}
                    >
                      {qualityBadgeLabel(question.quality_validation)}
                    </span>
                  ) : null}
                  <p>{cleanDisplayText(question.prompt)}</p>

                  {question.question_type === "mcq" ? (
                    <div className="option-list">
                      {question.options.map((option) => (
                        <label className="option-card" key={option.option_id}>
                          <input
                            checked={answers[question.question_id]?.selected_option_id === option.option_id}
                            disabled={!activeJob || !isJobReadyForReview(activeJob.status)}
                            name={question.question_id}
                            onChange={(event: ChangeEvent<HTMLInputElement>) =>
                              updateAnswer(question.question_id, "selected_option_id", event.target.value)
                            }
                            type="radio"
                            value={option.option_id}
                          />
                          <span>
                            <strong>{option.option_id}.</strong> {cleanDisplayText(option.text)}
                          </span>
                        </label>
                      ))}
                    </div>
                  ) : (
                    <label className="field">
                      <span>Your answer</span>
                      <textarea
                        aria-label={`Answer for question ${index + 1}`}
                        className="text-area"
                        disabled={!activeJob || !isJobReadyForReview(activeJob.status)}
                        rows={4}
                        value={answers[question.question_id]?.answer_text ?? ""}
                        onChange={(event) =>
                          updateAnswer(question.question_id, "answer_text", event.target.value)
                        }
                      />
                    </label>
                  )}

                  <div className="quiz-source-chip-row">
                    {question.citations.map((citation) => (
                      <button
                        className="quiz-source-chip"
                        key={citation.chunk_id}
                        onClick={() => setReviewSource(citation)}
                        title={citation.citation_label}
                        type="button"
                      >
                        {cleanDisplayText(citation.section_title)}
                      </button>
                    ))}
                  </div>
                </article>
              );
            })}
          </div>
        </section>
      ) : null}

      {gradeResult ? (
        <div className="dashboard-grid">
          <MasteryChart masteryByConcept={gradeResult.mastery_by_concept} title="Updated mastery" />

          <section className="card">
            <h3>Grading feedback</h3>
            <div className="stacked-list">
              {gradeResult.results.map((result) => (
                <QuestionReviewCard
                  compact
                  key={result.question_id}
                  result={result}
                  onReviewMaterial={result.citations[0] ? () => setReviewSource(result.citations[0]) : null}
                  onPracticeConcept={() => void handlePracticeConcept(result)}
                />
              ))}
            </div>
          </section>
        </div>
      ) : null}
      {reviewSource ? (
        <ReviewSourceModal
          citation={reviewSource}
          returnHref="/quiz"
          returnLabel="Back to quiz"
          onClose={() => setReviewSource(null)}
        />
      ) : null}
    </div>
  );
}

function resolveSelectedSourceIds(
  materials: CourseMaterialsResponse | null,
  selectedQuizSourceIds: string[]
): string[] {
  if (!materials) {
    return [];
  }

  const selectedSourceIds = new Set<string>();
  for (const source of materials.quiz_sources) {
    if (!selectedQuizSourceIds.includes(source.quiz_source_id)) {
      continue;
    }
    for (const sourceId of source.source_ids) {
      selectedSourceIds.add(sourceId);
    }
  }
  return [...selectedSourceIds];
}

function uniqueStrings(values: string[]): string[] {
  return Array.from(new Set(values.filter(Boolean)));
}

function buildStorageKey(courseId: string | null, moduleId?: string | null): string | null {
  if (!courseId) {
    return null;
  }
  return `quiz-job:${courseId}:${moduleId ?? "all"}`;
}

function readStoredJobId(courseId: string | null, moduleId?: string | null): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  const storageKey = buildStorageKey(courseId, moduleId);
  if (!storageKey) {
    return null;
  }
  return window.localStorage.getItem(storageKey);
}

function writeStoredJobId(courseId: string | null, moduleId: string | null | undefined, jobId: string): void {
  if (typeof window === "undefined") {
    return;
  }
  const storageKey = buildStorageKey(courseId, moduleId);
  if (!storageKey) {
    return;
  }
  window.localStorage.setItem(storageKey, jobId);
}

function clearStoredJobId(courseId: string | null, moduleId?: string | null): void {
  if (typeof window === "undefined") {
    return;
  }
  const storageKey = buildStorageKey(courseId, moduleId);
  if (!storageKey) {
    return;
  }
  window.localStorage.removeItem(storageKey);
}

function renderProgressLabel(job: QuizGenerationJobResponse): string {
  if (job.status === "queued") {
    return "Queued";
  }
  if (job.status === "running") {
    return `Generating question ${Math.max(job.progress.current_question_index, 1)} of ${job.progress.total_questions}`;
  }
  if (job.status === "partial") {
    return "Completed with fallback coverage";
  }
  if (job.status === "completed") {
    return "Completed";
  }
  if (job.status === "cancelled") {
    return "Cancelled";
  }
  return "Failed";
}

function isJobReadyForReview(status: QuizGenerationJobResponse["status"]): boolean {
  return status === "completed" || status === "partial";
}

function createClientRequestId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `quiz-${Date.now()}`;
}

function qualityBadgeClass(accepted: boolean): string {
  return `question-quality-badge ${accepted ? "question-quality-badge-passed" : "question-quality-badge-review"}`;
}

function qualityBadgeLabel(validation: { accepted_for_delivery: boolean; notes: string[] }): string {
  const regenerated = validation.notes.some((note) => note.toLowerCase().includes("regenerated"));
  if (regenerated) {
    return "Regenerated";
  }
  if (validation.accepted_for_delivery) {
    return "Quality checked";
  }
  return "Quality review";
}

function shouldShowQualityBadge(validation: { accepted_for_delivery: boolean; notes: string[] }): boolean {
  return validation.accepted_for_delivery || validation.notes.some((note) => note.toLowerCase().includes("regenerated"));
}
