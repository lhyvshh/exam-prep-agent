"use client";

import React from "react";
import type { ChangeEvent, FormEvent } from "react";
import { useEffect, useRef, useState } from "react";

import {
  fetchCourseMaterials,
  fetchMockExamSources,
  fetchMaterialPreview,
  generateMockExam,
  gradeMockExam,
  trackActivityEvent,
  uploadMockExamSource
} from "@/lib/api";
import { ReviewSourceModal } from "@/components/shared/source-viewer";
import { useCourseSelection } from "@/components/shared/course-context";
import type {
  ExamBlueprint,
  ExamTopicCoverage,
  MockExamBundle,
  MockExamGradeResponse,
  MockExamSourceBank,
  MockExamSourceBankSummary,
  ModuleRecord,
  QuizSubmissionAnswer,
  SourceChunk,
  SourceSection
} from "@/lib/schemas";
import { cleanDisplayText, gradeBadgeClass, gradeBadgeLabel, MetricGrid } from "@/components/shared/data-widgets";

const defaultTopic: ExamTopicCoverage = {
  topic: "Gradient Descent",
  question_count: 2,
  question_types: ["mcq"]
};

const defaultBlueprint: ExamBlueprint = {
  title: "Midterm Mock",
  instructions: "Answer all questions using grounded material from the selected context.",
  topic_coverage: [],
  target_difficulty: 0.6,
  style_example: "Answer clearly and tie each response back to the cited study material."
};

type ExamWeightingItem = {
  book: string;
  topicArea: string;
  examWeight: string;
  examQuestions: string;
  materialName: string;
};

export function MockExamWorkspace(): JSX.Element {
  const { selectedCourseId, selectedModuleId, selectedCourse, selectedModule, modules } = useCourseSelection();
  const [blueprint, setBlueprint] = useState<ExamBlueprint>(defaultBlueprint);
  const [retrievalTopK, setRetrievalTopK] = useState<number>(8);
  const [scope, setScope] = useState<"course" | "modules">(selectedModuleId ? "modules" : "course");
  const [selectedModuleIds, setSelectedModuleIds] = useState<string[]>(selectedModuleId ? [selectedModuleId] : []);
  const [questionsPerTopic, setQuestionsPerTopic] = useState<number>(2);
  const [customTopic, setCustomTopic] = useState<string>("");
  const [suggestedTopics, setSuggestedTopics] = useState<string[]>([]);
  const [bookWeighting, setBookWeighting] = useState<ExamWeightingItem[]>([]);
  const [moduleWeights, setModuleWeights] = useState<Record<string, number>>({});
  const [styleExamFile, setStyleExamFile] = useState<File | null>(null);
  const [styleExamName, setStyleExamName] = useState<string | null>(null);
  const [isUploadingStyleExam, setIsUploadingStyleExam] = useState<boolean>(false);
  const [enableSourceOcr, setEnableSourceOcr] = useState<boolean>(false);
  const [sourceBanks, setSourceBanks] = useState<MockExamSourceBankSummary[]>([]);
  const [selectedSourceExamId, setSelectedSourceExamId] = useState<string | null>(null);
  const [timed, setTimed] = useState<boolean>(false);
  const [studiedOnly, setStudiedOnly] = useState<boolean>(false);
  const [exam, setExam] = useState<MockExamBundle | null>(null);
  const [answers, setAnswers] = useState<Record<string, QuizSubmissionAnswer>>({});
  const [gradeResult, setGradeResult] = useState<MockExamGradeResponse | null>(null);
  const [isGenerating, setIsGenerating] = useState<boolean>(false);
  const [isGrading, setIsGrading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [reviewSource, setReviewSource] = useState<SourceChunk | null>(null);
  const answeredEventRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    setScope(selectedModuleId ? "modules" : "course");
    setSelectedModuleIds(selectedModuleId ? [selectedModuleId] : []);
  }, [selectedCourseId, selectedModuleId]);

  useEffect(() => {
    let cancelled = false;
    async function loadSourceBanks(): Promise<void> {
      if (!selectedCourseId) {
        setSourceBanks([]);
        setSelectedSourceExamId(null);
        return;
      }
      try {
        const response = await fetchMockExamSources(selectedCourseId);
        if (cancelled) {
          return;
        }
        const sources = Array.isArray(response.sources) ? response.sources : [];
        setSourceBanks(sources);
        setSelectedSourceExamId((current) => {
          if (current && sources.some((bank) => bank.exams.some((exam) => exam.source_exam_id === current))) {
            return current;
          }
          return sources[0]?.exams[0]?.source_exam_id ?? null;
        });
      } catch {
        if (!cancelled) {
          setSourceBanks([]);
          setSelectedSourceExamId(null);
        }
      }
    }
    void loadSourceBanks();
    return () => {
      cancelled = true;
    };
  }, [selectedCourseId]);

  useEffect(() => {
    const activeModuleIds = getActiveModuleIds(scope, modules, selectedModuleIds);
    setModuleWeights((current) => distributeModuleWeights(activeModuleIds, current));
  }, [scope, modules, selectedModuleIds]);

  useEffect(() => {
    const weightedTopics = bookWeighting.map((item) => item.topicArea);
    const nextTopics = Array.from(new Set([
      ...weightedTopics,
      ...buildSuggestedTopics(selectedCourse?.display_name, selectedModule?.display_name)
    ])).slice(0, 6);
    setSuggestedTopics(nextTopics);
    setBlueprint((current) => {
      if (current.topic_coverage.length > 0 || nextTopics.length === 0) {
        return current;
      }
      return {
        ...current,
        topic_coverage: [
          {
            topic: nextTopics[0],
            question_count: questionsPerTopic,
            question_types: ["mcq"]
          }
        ]
      };
    });
  }, [selectedCourseId, selectedModuleId, selectedCourse?.display_name, selectedModule?.display_name, bookWeighting]);

  useEffect(() => {
    let cancelled = false;
    async function loadBookWeighting(): Promise<void> {
      if (!selectedCourseId) {
        setBookWeighting([]);
        return;
      }
      try {
        const response = await fetchCourseMaterials(selectedCourseId);
        const previews = await Promise.all(
          response.records.slice(0, 8).map(async (material) => {
            try {
              return await fetchMaterialPreview(material.material_id, 1);
            } catch {
              return null;
            }
          })
        );
        if (cancelled) {
          return;
        }
        const rows = previews
          .flatMap((preview) => preview
            ? extractBookExamWeightings(preview.sections, preview.record.display_name ?? preview.record.file_name)
            : []);
        setBookWeighting(uniqueBookWeightings(rows));
      } catch {
        if (!cancelled) {
          setBookWeighting([]);
        }
      }
    }
    void loadBookWeighting();
    return () => {
      cancelled = true;
    };
  }, [selectedCourseId]);

  useEffect(() => {
    setBlueprint((current) => ({
      ...current,
      topic_coverage: current.topic_coverage.map((topic) => ({
        ...topic,
        question_count: questionsPerTopic
      }))
    }));
  }, [questionsPerTopic]);

  function toggleTopicQuestionType(type: "mcq"): void {
    setBlueprint((current) => ({
      ...current,
      topic_coverage: current.topic_coverage.map((topic) => {
        const nextTypes = topic.question_types.includes(type)
          ? topic.question_types.filter((item) => item !== type)
          : [...topic.question_types, type];
        return {
          ...topic,
          question_types: nextTypes.length > 0 ? nextTypes : [type]
        };
      })
    }));
  }

  function addTopic(topicName: string): void {
    const normalizedTopic = topicName.trim();
    if (!normalizedTopic) {
      return;
    }
    setBlueprint((current) => {
      if (current.topic_coverage.some((topic) => topic.topic.toLowerCase() === normalizedTopic.toLowerCase())) {
        return current;
      }
      return {
        ...current,
        topic_coverage: [
          ...current.topic_coverage,
          {
            topic: normalizedTopic,
            question_count: questionsPerTopic,
            question_types: current.topic_coverage[0]?.question_types ?? ["mcq"]
          }
        ]
      };
    });
  }

  function removeTopic(topicName: string): void {
    setBlueprint((current) => ({
      ...current,
      topic_coverage: current.topic_coverage.filter((topic) => topic.topic !== topicName)
    }));
  }

  function updateModuleWeight(moduleId: string, weight: number): void {
    setModuleWeights((current) => ({
      ...current,
      [moduleId]: Math.max(0, Math.min(100, Number.isFinite(weight) ? weight : 0))
    }));
  }

  function normalizeModuleWeights(): void {
    setModuleWeights((current) => normalizeModuleWeightsToHundred(activeModuleIds, current));
  }

  function resetEvenModuleWeights(): void {
    setModuleWeights(distributeModuleWeights(activeModuleIds, {}));
  }

  async function handleStyleExamUpload(): Promise<void> {
    if (!selectedCourseId || !styleExamFile) {
      setError("Choose a real exam file before uploading a source exam.");
      return;
    }
    setIsUploadingStyleExam(true);
    setError(null);
    try {
      const response = await uploadMockExamSource(selectedCourseId, styleExamFile, enableSourceOcr);
      const summaries = [sourceBankToSummary(response.bank), ...sourceBanks].filter(
        (bank, index, banks) => banks.findIndex((item) => item.bank_id === bank.bank_id) === index
      );
      setSourceBanks(summaries);
      setSelectedSourceExamId(response.bank.exams[0]?.source_exam_id ?? null);
      setStyleExamName(response.bank.file_name);
      setStyleExamFile(null);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to ingest source exam.");
    } finally {
      setIsUploadingStyleExam(false);
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
      const question = exam?.questions.find((item) => item.question_id === questionId);
      const citation = question?.citations[0];
      void trackActivityEvent({
        course_id: selectedCourseId,
        module_id: selectedModuleId,
        material_id: citation?.material_id ?? null,
        section_id: citation?.source_id ?? null,
        quiz_id: exam?.exam_id ?? null,
        question_id: questionId,
        question_type: question?.question_type ?? null,
        difficulty: question?.difficulty ?? null,
        event_type: "question_answered",
        metadata_json: {
          origin: "mock_exam_workspace",
          answer_field: field
        }
      }).catch(() => undefined);
    }
  }

  async function handleGenerate(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!selectedCourseId) {
      setError("Choose a course or module before generating an exam.");
      return;
    }
    if (scope === "modules" && selectedModuleIds.length === 0) {
      setError("Select at least one module before generating a module-scoped mock exam.");
      return;
    }
    if (!selectedSourceExamId && blueprint.topic_coverage.length === 0) {
      setError("Add at least one topic before generating a mock exam.");
      return;
    }

    setIsGenerating(true);
    setError(null);

    try {
      const normalizedModuleIds = scope === "modules"
        ? Array.from(new Set(selectedModuleIds))
        : [];
      const response = await generateMockExam({
        course_id: selectedCourseId,
        module_id: normalizedModuleIds.length === 1 ? normalizedModuleIds[0] : null,
        module_ids: normalizedModuleIds,
        scope: {
          course_id: selectedCourseId,
          module_ids: normalizedModuleIds,
          material_ids: [],
          section_ids: [],
          source_type: selectedSourceExamId ? "practice_exam" : "study_material"
        },
        source_exam_id: selectedSourceExamId,
        blueprint: normalizeBlueprint(
          blueprint,
          selectedCourse?.display_name,
          selectedModule?.display_name,
          timed,
          studiedOnly,
          moduleWeights,
          modules,
          selectedSourceExamId ? selectedSourceLabel(sourceBanks, selectedSourceExamId) : styleExamName,
          bookWeighting
        ),
        retrieval_top_k: retrievalTopK
      });
      setExam(response.exam);
      setGradeResult(null);
      setAnswers({});
      answeredEventRef.current.clear();
      void trackActivityEvent({
        course_id: selectedCourseId,
        module_id: normalizedModuleIds.length === 1 ? normalizedModuleIds[0] : selectedModuleId,
        quiz_id: response.exam.exam_id,
        event_type: "quiz_started",
        metadata_json: {
          origin: "mock_exam_workspace",
          exam_id: response.exam.exam_id,
          module_ids: normalizedModuleIds,
          topic_count: response.exam.blueprint.topic_coverage.length
        }
      }).catch(() => undefined);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to generate exam.");
      setExam(null);
    } finally {
      setIsGenerating(false);
    }
  }

  async function handleGrade(): Promise<void> {
    if (!exam) {
      return;
    }

    setIsGrading(true);
    setError(null);
    try {
      const orderedAnswers = exam.questions.map((question) => answers[question.question_id] ?? {
        question_id: question.question_id,
        selected_option_id: null,
        answer_text: ""
      });
      const response = await gradeMockExam(exam.exam_id, orderedAnswers);
      setGradeResult(response);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to grade exam.");
    } finally {
      setIsGrading(false);
    }
  }

  const metrics = exam
    ? [
        { label: "Exam", value: exam.blueprint.title },
        { label: "Questions", value: String(exam.questions.length) },
        { label: "Score", value: gradeResult ? `${gradeResult.overall_score}%` : "Pending" }
      ]
    : [
        { label: "Exam", value: "Not generated" },
        { label: "Questions", value: "0" },
        { label: "Score", value: "Pending" }
      ];
  const activeModuleIds = getActiveModuleIds(scope, modules, selectedModuleIds);
  const activeModules = activeModuleIds
    .map((moduleId) => modules.find((module) => module.module_id === moduleId))
    .filter((module): module is ModuleRecord => Boolean(module));
  const totalModuleWeight = activeModules.reduce((sum, module) => sum + (moduleWeights[module.module_id] ?? 0), 0);

  return (
    <div className="stack">
      <section className="card exam-builder-card">
        <h3>Mock exam builder</h3>
        {!selectedCourseId ? (
          <p className="subtle">Open a course to build an exam.</p>
        ) : (
          <p>
            Build a realistic mock for {selectedCourse?.display_name}. Tune module coverage and optionally upload a past exam for style.
          </p>
        )}
        <form className="config-form" onSubmit={handleGenerate}>
          <div className="exam-builder-steps" aria-label="Mock exam setup steps">
            <span>1 Scope</span>
            <span>2 Weights</span>
            <span>3 Style</span>
            <span>4 Settings</span>
            <span>5 Generate</span>
          </div>

          <section className="exam-builder-section">
            <div className="section-header">
              <div>
                <h4>Scope</h4>
                <p className="subtle">Choose the course coverage for this mock.</p>
              </div>
            </div>
            <div className="scope-card-row">
            <button
              aria-pressed={scope === "course"}
              className={`scope-card${scope === "course" ? " scope-card-active" : ""}`}
              onClick={() => setScope("course")}
              type="button"
            >
              <strong>Whole course</strong>
              <span>Use all uploaded materials in this course.</span>
            </button>
            <button
              aria-pressed={scope === "modules"}
              className={`scope-card${scope === "modules" ? " scope-card-active" : ""}`}
              onClick={() => setScope("modules")}
              type="button"
            >
              <strong>Selected modules</strong>
              <span>Focus the exam on specific modules.</span>
            </button>
            </div>

            {scope === "modules" ? (
              <div className="checkbox-row">
                {modules.length === 0 ? <p className="subtle">No modules yet.</p> : null}
                {modules.map((module) => (
                  <label className="checkbox-chip" key={module.module_id}>
                    <input
                      checked={selectedModuleIds.includes(module.module_id)}
                      onChange={() =>
                        setSelectedModuleIds((current) =>
                          current.includes(module.module_id)
                            ? current.filter((item) => item !== module.module_id)
                            : [...current, module.module_id]
                        )
                      }
                      type="checkbox"
                    />
                    <span>{module.module_number} · {module.display_name}</span>
                  </label>
                ))}
              </div>
            ) : null}
          </section>

          {bookWeighting.length > 0 ? (
            <section className="card compact-card exam-book-weighting-panel">
              <div className="section-header">
                <div>
                  <h4>Book-provided exam weighting</h4>
                  <p className="subtle">The mock exam agent will follow this weighting from the uploaded book.</p>
                </div>
                <span className="studied-tag">source-linked</span>
              </div>
              <div className="exam-weighting-grid">
                {bookWeighting.map((item) => (
                  <div className="exam-weighting-row" key={`${item.book}-${item.topicArea}`}>
                    <span className="exam-weighting-book">{item.book}</span>
                    <strong>{item.topicArea}</strong>
                    <span className="exam-weighting-weight">{item.examWeight}</span>
                    <span className="subtle">{item.examQuestions} questions</span>
                  </div>
                ))}
              </div>
            </section>
          ) : null}

          {modules.length > 0 ? (
            <section className="card compact-card exam-module-weight-panel">
              <div className="section-header">
                <div>
                  <h4>Module coverage</h4>
                  <p className="subtle">Adjust the target mix for this course. The generator will use these percentages as guidance.</p>
                </div>
                <span className={`weight-total-badge${Math.round(totalModuleWeight) === 100 ? " weight-total-good" : ""}`}>
                  {Math.round(totalModuleWeight)}%
                </span>
              </div>
              <div className="action-row">
                <button className="secondary-button" disabled={activeModules.length === 0} onClick={normalizeModuleWeights} type="button">
                  Normalize to 100%
                </button>
                <button className="secondary-button" disabled={activeModules.length === 0} onClick={resetEvenModuleWeights} type="button">
                  Even split
                </button>
              </div>
              <div className="module-weight-list">
                {activeModules.length === 0 ? (
                  <p className="subtle">Select modules above to customize their coverage.</p>
                ) : (
                  activeModules.map((module) => (
                    <label className="module-weight-row" key={module.module_id}>
                      <span>
                        <strong>{module.module_number} · {module.display_name}</strong>
                        <small>{scope === "course" ? "Included in whole course" : "Selected module"}</small>
                      </span>
                      <input
                        aria-label={`Coverage percentage for ${module.display_name}`}
                        max={100}
                        min={0}
                        type="range"
                        value={moduleWeights[module.module_id] ?? 0}
                        onChange={(event) => updateModuleWeight(module.module_id, Number(event.target.value))}
                      />
                      <input
                        aria-label={`Manual coverage percentage for ${module.display_name}`}
                        className="module-weight-number"
                        max={100}
                        min={0}
                        type="number"
                        value={Math.round(moduleWeights[module.module_id] ?? 0)}
                        onChange={(event) => updateModuleWeight(module.module_id, Number(event.target.value))}
                      />
                    </label>
                  ))
                )}
              </div>
              {activeModules.length > 0 && Math.round(totalModuleWeight) !== 100 ? (
                <p className="subtle">Tip: aim for 100%. The app will still generate and treat the numbers as relative weights.</p>
              ) : null}
            </section>
          ) : null}

          <section className="card compact-card exam-style-upload-panel">
            <div className="section-header">
              <div>
                <h4>FRM exam source</h4>
                <p className="subtle">Upload practice exams and generate one-to-one mocks from the parsed exam map.</p>
              </div>
              {selectedSourceExamId ? <span className="studied-tag">source mapped</span> : null}
            </div>
            <div className="exam-style-status-strip">
              <span className={selectedSourceExamId ? "status-dot status-dot-good" : "status-dot"} />
              <p className="subtle">
                {selectedSourceExamId
                  ? "The generator will mirror the selected exam question-for-question."
                  : "Upload the FRM exams PDF or a searchable TXT export to enable full mock exams."}
              </p>
            </div>
            <div className="real-exam-upload-row">
              <input
                aria-label="Upload FRM exam source"
                accept=".pdf,.txt"
                type="file"
                onChange={(event) => setStyleExamFile(event.target.files?.[0] ?? null)}
              />
              <button
                className="secondary-button"
                disabled={!styleExamFile || isUploadingStyleExam || !selectedCourseId}
                onClick={() => void handleStyleExamUpload()}
                type="button"
              >
                {isUploadingStyleExam ? "Ingesting..." : "Upload source exam"}
              </button>
            </div>
            <label className="checkbox-chip">
              <input checked={enableSourceOcr} onChange={(event) => setEnableSourceOcr(event.target.checked)} type="checkbox" />
              <span>Use OCR for scanned PDFs</span>
            </label>
            {sourceBanks.length > 0 ? (
              <label className="field">
                <span>Generated exam should mirror</span>
                <select
                  aria-label="Source exam"
                  value={selectedSourceExamId ?? ""}
                  onChange={(event) => setSelectedSourceExamId(event.target.value || null)}
                >
                  {sourceBanks.flatMap((bank) =>
                    bank.exams.map((exam) => (
                      <option key={exam.source_exam_id} value={exam.source_exam_id}>
                        {bank.file_name} · {exam.title} · {exam.question_count} questions
                      </option>
                    ))
                  )}
                </select>
              </label>
            ) : null}
            {styleExamName ? <p className="subtle">Latest source: {styleExamName}</p> : null}
          </section>

          <section className="exam-builder-section">
            <div className="section-header">
              <div>
                <h4>Settings</h4>
                <p className="subtle">Keep defaults or tune difficulty, timing, and format.</p>
              </div>
            </div>
            <label className="field">
              <span>Title</span>
              <input
                aria-label="Exam title"
                type="text"
                value={blueprint.title}
                onChange={(event) =>
                  setBlueprint((current) => ({ ...current, title: event.target.value }))
                }
              />
            </label>

            <label className="field">
              <span>Target difficulty</span>
              <input
                aria-label="Target difficulty"
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={blueprint.target_difficulty}
                onChange={(event) =>
                  setBlueprint((current) => ({
                    ...current,
                    target_difficulty: Number(event.target.value)
                  }))
                }
              />
              <span className="subtle">{blueprint.target_difficulty.toFixed(2)}</span>
            </label>

            <div className="two-column-grid">
              <label className="checkbox-chip">
                <input checked={timed} onChange={(event) => setTimed(event.target.checked)} type="checkbox" />
                <span>Timed exam</span>
              </label>
              <label className="checkbox-chip">
                <input checked={studiedOnly} onChange={(event) => setStudiedOnly(event.target.checked)} type="checkbox" />
                <span>Studied sections only</span>
              </label>
            </div>
          </section>

          <section className="card compact-card exam-topic-panel">
            <div className="section-header">
              <div>
                <h4>Topics for this mock</h4>
                <p className="subtle">Keep it simple: add the concepts you want covered.</p>
              </div>
            </div>
            <div className="exam-topic-shortlist">
              {suggestedTopics.length === 0 ? <p className="subtle">No suggested topics yet. Add one manually below.</p> : null}
              {suggestedTopics.map((topic) => {
                const selected = blueprint.topic_coverage.some((item) => item.topic.toLowerCase() === topic.toLowerCase());
                return (
                  <button
                    aria-pressed={selected}
                    className={`topic-shortlist-item${selected ? " topic-shortlist-item-active" : ""}`}
                    key={topic}
                    onClick={() => (selected ? removeTopic(topic) : addTopic(topic))}
                    type="button"
                  >
                    <span>{topic}</span>
                    <strong>{selected ? "Added" : "Add"}</strong>
                  </button>
                );
              })}
            </div>

            <div className="two-column-grid">
              <label className="field">
                <span>Add a custom topic</span>
                <input
                  aria-label="Custom topic"
                  placeholder="Neural networks"
                  type="text"
                  value={customTopic}
                  onChange={(event) => setCustomTopic(event.target.value)}
                />
              </label>
              <div className="action-row align-end">
                <button
                  className="secondary-button"
                  onClick={() => {
                    addTopic(customTopic);
                    setCustomTopic("");
                  }}
                  type="button"
                >
                  Add topic
                </button>
              </div>
            </div>

            <div className="exam-selected-topic-row">
              {blueprint.topic_coverage.length === 0 ? (
                <p className="subtle">No topics selected yet.</p>
              ) : (
                blueprint.topic_coverage.map((topic) => (
                  <span className="selected-topic-chip" key={topic.topic}>
                    {topic.topic}
                    <button
                      aria-label={`Remove ${topic.topic}`}
                      className="chip-dismiss"
                      onClick={() => removeTopic(topic.topic)}
                      type="button"
                    >
                      Remove
                    </button>
                  </span>
                ))
              )}
            </div>
          </section>

          <div className="two-column-grid">
            <label className="field compact-number-field">
              <span>Questions per topic</span>
              <input
                aria-label="Questions per topic"
                type="number"
                min={1}
                max={10}
                value={questionsPerTopic}
                onChange={(event) => setQuestionsPerTopic(Number(event.target.value))}
              />
            </label>
            <div className="field">
              <span>Question format</span>
              <div className="chip-toggle-row" role="group" aria-label="Question types for mock exam">
                {(["mcq"] as const).map((type) => {
                  const selected = blueprint.topic_coverage[0]?.question_types.includes(type) ?? defaultTopic.question_types.includes(type);
                  return (
                    <button
                      aria-pressed={selected}
                      className={`chip-toggle${selected ? " chip-toggle-active" : ""}`}
                      key={type}
                      onClick={() => toggleTopicQuestionType(type)}
                      type="button"
                    >
                      MCQ
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          <div className="action-row">
            <button className="primary-button" disabled={isGenerating || !selectedCourseId} type="submit">
              {isGenerating ? "Generating..." : "Generate mock exam"}
            </button>
            <label className="field compact-number-field">
              <span>Retrieval depth</span>
              <input
                aria-label="Exam retrieval depth"
                type="number"
                min={1}
                max={20}
                value={retrievalTopK}
                onChange={(event) => setRetrievalTopK(Number(event.target.value))}
              />
            </label>
          </div>
        </form>

        {error ? (
          <div className="status-panel error-panel" aria-live="polite">
            <strong>Issue:</strong> {error}
          </div>
        ) : null}
      </section>

      <MetricGrid items={metrics} />

      {exam ? (
        <section className="card">
          <div className="section-header">
            <div>
              <h3>{exam.blueprint.title}</h3>
              <p className="subtle">
                Source: {deriveExamScopeLabel(exam, selectedCourse?.display_name, modules)}
              </p>
            </div>
            <button className="primary-button" disabled={isGrading} onClick={() => void handleGrade()} type="button">
              {isGrading ? "Scoring..." : "Grade exam"}
            </button>
          </div>

          <div className="question-list">
            {exam.questions.map((question, index) => (
              <article className="question-card" key={question.question_id}>
                <div className="preview-header">
                  <strong>
                    Question {index + 1}: {question.concept}
                  </strong>
                  <span className="subtle">
                    {question.question_type} · difficulty {question.difficulty}
                  </span>
                </div>
                {question.quality_validation ? (
                  <span className={qualityBadgeClass(question.quality_validation.accepted_for_delivery)}>
                    PyTorch quality check: {question.quality_validation.accepted_for_delivery ? "passed" : "review"}
                  </span>
                ) : null}
                <p>{question.prompt}</p>

                {question.question_type === "mcq" ? (
                  <div className="option-list">
                    {question.options.map((option) => (
                      <label className="option-card" key={option.option_id}>
                        <input
                          checked={answers[question.question_id]?.selected_option_id === option.option_id}
                          name={question.question_id}
                          onChange={(event: ChangeEvent<HTMLInputElement>) =>
                            updateAnswer(question.question_id, "selected_option_id", event.target.value)
                          }
                          type="radio"
                          value={option.option_id}
                        />
                        <span>
                          <strong>{option.option_id}.</strong> {option.text}
                        </span>
                      </label>
                    ))}
                  </div>
                ) : (
                  <label className="field">
                    <span>Your answer</span>
                    <textarea
                      aria-label={`Mock exam answer for question ${index + 1}`}
                      className="text-area"
                      rows={4}
                      value={answers[question.question_id]?.answer_text ?? ""}
                      onChange={(event) =>
                        updateAnswer(question.question_id, "answer_text", event.target.value)
                      }
                    />
                  </label>
                )}
                {question.citations.length > 0 ? (
                  <div className="quiz-source-chip-row">
                    {question.citations.map((citation) => (
                      <button
                        className="quiz-source-chip"
                        key={citation.chunk_id}
                        onClick={() => {
                          void trackActivityEvent({
                            course_id: selectedCourseId,
                            module_id: selectedModuleId,
                            material_id: citation.material_id,
                            section_id: citation.source_id,
                            quiz_id: exam?.exam_id ?? null,
                            question_id: question.question_id,
                            question_type: question.question_type,
                            difficulty: question.difficulty,
                            event_type: "pdf_source_clicked",
                            metadata_json: {
                              origin: "mock_exam_question",
                              page_number: citation.locator?.page_number ?? null
                            }
                          }).catch(() => undefined);
                          setReviewSource(citation);
                        }}
                        title={citation.citation_label}
                        type="button"
                      >
                        View source
                      </button>
                    ))}
                  </div>
                ) : null}
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {gradeResult ? (
        <section className="card">
          <h3>Exam grading feedback</h3>
          <div className="stacked-list">
            {gradeResult.results.map((result) => (
              <article className="preview-item" key={result.question_id}>
                <div className="preview-header">
                  <strong>{cleanDisplayText(result.concept || "Question review")}</strong>
                  <span className={`result-badge ${gradeBadgeClass(result)}`}>
                    {gradeBadgeLabel(result)}
                  </span>
                </div>
                <p className="subtle">
                  Submitted: {result.submitted_answer || "No answer provided"} · Correct answer:{" "}
                  {result.correct_answer}
                </p>
                <p>{result.explanation}</p>
                {result.citations[0] ? (
                  <div className="action-row">
                    <button
                      className="secondary-button"
                      onClick={() => {
                        void trackActivityEvent({
                          course_id: selectedCourseId,
                          module_id: selectedModuleId,
                          material_id: result.citations[0].material_id,
                          section_id: result.citations[0].source_id,
                          quiz_id: exam?.exam_id ?? null,
                          question_id: result.question_id,
                          question_type: result.question_type,
                          event_type: "review_material_clicked",
                          metadata_json: {
                            origin: "mock_exam_feedback",
                            concept: result.concept,
                            page_number: result.citations[0].locator?.page_number ?? null
                          }
                        }).catch(() => undefined);
                        setReviewSource(result.citations[0]);
                      }}
                      type="button"
                    >
                      Review material
                    </button>
                  </div>
                ) : null}
              </article>
            ))}
          </div>
        </section>
      ) : null}
      {reviewSource ? (
        <ReviewSourceModal
          citation={reviewSource}
          returnHref={selectedCourseId ? `/courses?mockExamCourseId=${encodeURIComponent(selectedCourseId)}` : "/courses"}
          returnLabel="Back to mock exam"
          onClose={() => setReviewSource(null)}
        />
      ) : null}
    </div>
  );
}

function normalizeBlueprint(
  blueprint: ExamBlueprint,
  courseName?: string,
  moduleName?: string,
  timed?: boolean,
  studiedOnly?: boolean,
  moduleWeights: Record<string, number> = {},
  modules: ModuleRecord[] = [],
  styleExamName?: string | null,
  bookWeighting: ExamWeightingItem[] = []
): ExamBlueprint {
  const moduleWeightInstruction = buildModuleWeightInstruction(moduleWeights, modules);
  const bookWeightingInstruction = buildBookWeightingInstruction(bookWeighting);
  return {
    ...blueprint,
    title: blueprint.title.trim() || `${courseName ?? "Course"} Mock Exam`,
    instructions: [
      "Answer all questions using the selected course materials.",
      timed ? "Treat this as a timed practice run." : "Untimed practice is allowed.",
      studiedOnly ? "Prioritize sections already marked studied." : "Cover the selected scope broadly.",
      moduleWeightInstruction,
      bookWeightingInstruction,
      styleExamName ? `Mirror the style, pacing, and wording patterns of the uploaded real exam reference: ${styleExamName}.` : ""
    ].join(" "),
    style_example: [
      `Use concise exam-prep explanations grounded in ${moduleName ?? courseName ?? "the course material"}.`,
      styleExamName ? `Style reference uploaded: ${styleExamName}.` : ""
    ].filter(Boolean).join(" "),
    topic_coverage: blueprint.topic_coverage.map((topic) => ({
      ...topic,
      topic: topic.topic.trim() || moduleName || courseName || "Core course concepts",
      question_count: Math.max(1, topic.question_count)
    }))
  };
}

function buildBookWeightingInstruction(bookWeighting: ExamWeightingItem[]): string {
  if (!bookWeighting.length) {
    return "";
  }
  return `Follow the book-provided exam weighting: ${bookWeighting
    .map((item) => `${item.topicArea} ${item.examWeight} (${item.examQuestions} questions)`)
    .join("; ")}.`;
}

function getActiveModuleIds(
  scope: "course" | "modules",
  modules: ModuleRecord[],
  selectedModuleIds: string[]
): string[] {
  if (scope === "course") {
    return modules.map((module) => module.module_id);
  }
  return selectedModuleIds.filter((moduleId) => modules.some((module) => module.module_id === moduleId));
}

function distributeModuleWeights(moduleIds: string[], current: Record<string, number>): Record<string, number> {
  if (!moduleIds.length) {
    return {};
  }
  const next: Record<string, number> = {};
  const knownTotal = moduleIds.reduce((sum, moduleId) => sum + (current[moduleId] ?? 0), 0);
  if (knownTotal > 0) {
    moduleIds.forEach((moduleId) => {
      next[moduleId] = current[moduleId] ?? 0;
    });
    return next;
  }
  const base = Math.floor(100 / moduleIds.length);
  const remainder = 100 - base * moduleIds.length;
  moduleIds.forEach((moduleId, index) => {
    next[moduleId] = base + (index < remainder ? 1 : 0);
  });
  return next;
}

function normalizeModuleWeightsToHundred(moduleIds: string[], current: Record<string, number>): Record<string, number> {
  if (!moduleIds.length) {
    return {};
  }
  const total = moduleIds.reduce((sum, moduleId) => sum + Math.max(0, current[moduleId] ?? 0), 0);
  if (total <= 0) {
    return distributeModuleWeights(moduleIds, {});
  }
  const next: Record<string, number> = {};
  let roundedTotal = 0;
  moduleIds.forEach((moduleId, index) => {
    if (index === moduleIds.length - 1) {
      next[moduleId] = Math.max(0, 100 - roundedTotal);
      return;
    }
    const normalized = Math.round(((current[moduleId] ?? 0) / total) * 100);
    next[moduleId] = normalized;
    roundedTotal += normalized;
  });
  return next;
}

function buildModuleWeightInstruction(
  moduleWeights: Record<string, number>,
  modules: ModuleRecord[]
): string {
  const weightedModules = modules
    .map((module) => ({
      module,
      weight: moduleWeights[module.module_id] ?? 0
    }))
    .filter((item) => item.weight > 0);
  if (!weightedModules.length) {
    return "";
  }
  return `Target module coverage: ${weightedModules
    .map(({ module, weight }) => `${module.module_number} ${module.display_name} ${Math.round(weight)}%`)
    .join("; ")}.`;
}

function deriveExamScopeLabel(
  exam: MockExamBundle,
  courseName: string | undefined,
  modules: ModuleRecord[]
): string {
  const scopedModuleIds = Array.from(new Set(exam.module_ids ?? (exam.module_id ? [exam.module_id] : [])));
  if (scopedModuleIds.length === 0) {
    return `${courseName ?? "Course"} · whole course`;
  }
  const labels = scopedModuleIds
    .map((moduleId) => modules.find((module) => module.module_id === moduleId))
    .filter((module): module is ModuleRecord => Boolean(module))
    .map((module) => `${module.module_number} · ${module.display_name}`);
  if (!labels.length) {
    return `${courseName ?? "Course"} · ${scopedModuleIds.length} modules`;
  }
  if (labels.length <= 2) {
    return `${courseName ?? "Course"} · ${labels.join(", ")}`;
  }
  return `${courseName ?? "Course"} · ${labels.length} modules`;
}

function buildSuggestedTopics(courseName?: string, moduleName?: string): string[] {
  return buildFallbackTopics(courseName, moduleName);
}

function extractBookExamWeightings(sections: SourceSection[], materialName: string): ExamWeightingItem[] {
  return sections
    .filter((section) => /exam\s+weight(?:ing|s)?/i.test(`${section.section_title}\n${section.text}`))
    .flatMap((section) => parseWeightingRows(section.text, materialName));
}

function parseWeightingRows(text: string, materialName: string): ExamWeightingItem[] {
  const rows: ExamWeightingItem[] = [];
  const rowPattern = /^\s*(\d+)\s+(.+?)\s+(\d{1,3}(?:\.\d+)?)%\s+(\d+)\s*$/;
  text.split(/\n+/).forEach((line) => {
    const match = rowPattern.exec(line.replace(/\s+/g, " ").trim());
    if (!match) {
      return;
    }
    rows.push({
      book: match[1],
      topicArea: match[2].trim(),
      examWeight: `${match[3]}%`,
      examQuestions: match[4],
      materialName
    });
  });
  if (rows.length > 0) {
    return rows;
  }
  const globalPattern = /(\d+)\s+([A-Za-z][A-Za-z &/,-]+?)\s+(\d{1,3}(?:\.\d+)?)%\s+(\d+)/g;
  for (const match of text.replace(/\s+/g, " ").matchAll(globalPattern)) {
    rows.push({
      book: match[1],
      topicArea: match[2].trim(),
      examWeight: `${match[3]}%`,
      examQuestions: match[4],
      materialName
    });
  }
  return rows;
}

function uniqueBookWeightings(rows: ExamWeightingItem[]): ExamWeightingItem[] {
  const seen = new Set<string>();
  return rows.filter((row) => {
    const key = `${row.book}:${row.topicArea}`.toLowerCase();
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

function sourceBankToSummary(bank: MockExamSourceBank): MockExamSourceBankSummary {
  return {
    bank_id: bank.bank_id,
    course_id: bank.course_id,
    file_name: bank.file_name,
    uploaded_at: bank.uploaded_at,
    exam_count: bank.exams.length,
    question_count: bank.exams.reduce((sum, exam) => sum + exam.question_count, 0),
    exams: bank.exams.map((exam) => ({
      source_exam_id: exam.source_exam_id,
      title: exam.title,
      question_count: exam.question_count,
      answer_count: exam.answer_count,
      average_difficulty: exam.questions.length
        ? exam.questions.reduce((sum, question) => sum + question.difficulty, 0)
          / exam.questions.length
        : 0.6
    })),
    warnings: bank.warnings
  };
}

function selectedSourceLabel(
  banks: MockExamSourceBankSummary[],
  sourceExamId: string
): string | null {
  for (const bank of banks) {
    const exam = bank.exams.find((item) => item.source_exam_id === sourceExamId);
    if (exam) {
      return `${bank.file_name} · ${exam.title}`;
    }
  }
  return null;
}

function qualityBadgeClass(accepted: boolean): string {
  return `question-quality-badge ${accepted ? "question-quality-badge-passed" : "question-quality-badge-review"}`;
}

function buildFallbackTopics(courseName?: string, moduleName?: string): string[] {
  const seedLabels = [moduleName, courseName, defaultTopic.topic, "Core course concepts"];
  return Array.from(new Set(seedLabels.map((label) => label?.trim()).filter(Boolean) as string[])).slice(0, 4);
}
