"use client";

import React, { useEffect, useMemo, useState } from "react";

import type { ExamBlueprintMode, MaterialRecord, MockExamSourceSummary } from "@/lib/schemas";

type ProducerMode = "study_cards" | "mock_exam";
const MAX_SOURCE_PDF_BYTES = 250 * 1024 * 1024;

type PackageProducerProps = {
  readonly materials: readonly MaterialRecord[];
  readonly sourceExams: readonly MockExamSourceSummary[];
  readonly isWorking: boolean;
  readonly workLabel: string | null;
  readonly onCreateStudyCards: (materials: readonly MaterialRecord[]) => Promise<void>;
  readonly onCreateMockExam: (
    sourceExam: MockExamSourceSummary,
    examFormat: ExamBlueprintMode
  ) => Promise<void>;
  readonly onUploadSource: (file: File, enableOcr: boolean) => Promise<void>;
};

export function PackageProducer({
  materials,
  sourceExams,
  isWorking,
  workLabel,
  onCreateStudyCards,
  onCreateMockExam,
  onUploadSource
}: PackageProducerProps): JSX.Element {
  const [mode, setMode] = useState<ProducerMode>("study_cards");
  const [selectedMaterialIds, setSelectedMaterialIds] = useState<readonly string[]>([]);
  const [sourceExamId, setSourceExamId] = useState<string | null>(null);
  const [sourceFile, setSourceFile] = useState<File | null>(null);
  const [sourceFileError, setSourceFileError] = useState<string | null>(null);
  const [enableOcr, setEnableOcr] = useState(true);
  const [examFormat, setExamFormat] = useState<ExamBlueprintMode>("frm_part_i");

  useEffect(() => {
    setSelectedMaterialIds((current) => {
      const available = new Set(materials.map((material) => material.material_id));
      const retained = current.filter((materialId) => available.has(materialId));
      return retained.length > 0 ? retained : materials.map((material) => material.material_id);
    });
  }, [materials]);

  const visibleSourceExams = useMemo(
    () => examFormat === "frm_part_i"
      ? sourceExams.filter((exam) => exam.question_count === 100)
      : sourceExams,
    [examFormat, sourceExams]
  );

  useEffect(() => {
    setSourceExamId(visibleSourceExams[0]?.source_exam_id ?? null);
  }, [visibleSourceExams]);

  const selectedMaterials = useMemo(
    () => materials.filter((material) => selectedMaterialIds.includes(material.material_id)),
    [materials, selectedMaterialIds]
  );
  const selectedSource = visibleSourceExams.find(
    (exam) => exam.source_exam_id === sourceExamId
  ) ?? null;

  function toggleMaterial(materialId: string): void {
    setSelectedMaterialIds((current) =>
      current.includes(materialId)
        ? current.filter((candidate) => candidate !== materialId)
        : [...current, materialId]
    );
  }

  async function uploadSource(): Promise<void> {
    if (!sourceFile) {
      return;
    }
    await onUploadSource(sourceFile, enableOcr);
    setSourceFile(null);
  }

  return (
    <section className="package-producer" aria-labelledby="package-producer-title">
      <div className="package-producer-heading">
        <div>
          <p className="eyebrow">Create a download</p>
          <h2 id="package-producer-title">Offline package producer</h2>
          <p className="subtle">Choose an output, select its source, and generate the reusable HTML package.</p>
        </div>
        <div className="package-mode-tabs" role="tablist" aria-label="Package type">
          <button
            aria-selected={mode === "study_cards"}
            className={mode === "study_cards" ? "is-active" : undefined}
            onClick={() => setMode("study_cards")}
            role="tab"
            type="button"
          >
            Study cards
          </button>
          <button
            aria-selected={mode === "mock_exam"}
            className={mode === "mock_exam" ? "is-active" : undefined}
            onClick={() => setMode("mock_exam")}
            role="tab"
            type="button"
          >
            Mock exam
          </button>
        </div>
      </div>

      {mode === "study_cards" ? (
        <div className="package-producer-body" role="tabpanel">
          <div className="package-step-heading">
            <div>
              <span>1</span>
              <div>
                <h3>Choose books</h3>
                <p>{selectedMaterials.length} of {materials.length} selected</p>
              </div>
            </div>
            <button
              className="text-button"
              disabled={materials.length === 0}
              onClick={() => setSelectedMaterialIds(materials.map((material) => material.material_id))}
              type="button"
            >
              Select all
            </button>
          </div>
          <div className="package-book-grid">
            {materials.map((material) => {
              const name = material.display_name ?? material.file_name;
              return (
                <label className="package-book-choice" key={material.material_id}>
                  <input
                    aria-label={name}
                    checked={selectedMaterialIds.includes(material.material_id)}
                    onChange={() => toggleMaterial(material.material_id)}
                    type="checkbox"
                  />
                  <span>
                    <strong>{name}</strong>
                    <small>{material.section_count} sections</small>
                  </span>
                </label>
              );
            })}
          </div>
          {materials.length === 0 ? (
            <p className="package-empty-copy">No parsed books are ready yet. Add books in the library first.</p>
          ) : null}
          <div className="package-producer-action">
            <div>
              <strong>10 grounded cards per learning objective</strong>
              <span>Includes book references, objective filters, and a clickable card browser.</span>
            </div>
            <button
              className="primary-button"
              disabled={isWorking || selectedMaterials.length === 0}
              onClick={() => void onCreateStudyCards(selectedMaterials)}
              type="button"
            >
              Generate study-card package
            </button>
          </div>
        </div>
      ) : (
        <div className="package-producer-body" role="tabpanel">
          <div className="package-format-selector" aria-label="Exam framework">
            <button
              aria-label="FRM Part I"
              aria-pressed={examFormat === "frm_part_i"}
              className={examFormat === "frm_part_i" ? "is-active" : undefined}
              onClick={() => setExamFormat("frm_part_i")}
              type="button"
            >
              <strong>FRM Part I</strong>
              <span>Fixed 100-question curriculum preset</span>
            </button>
            <button
              aria-label="Other exams"
              aria-pressed={examFormat === "source_exam"}
              className={examFormat === "source_exam" ? "is-active" : undefined}
              onClick={() => setExamFormat("source_exam")}
              type="button"
            >
              <strong>Other exams</strong>
              <span>Use the uploaded exam's own format</span>
            </button>
          </div>
          <div className="package-exam-source-grid">
            <div className="package-exam-select">
              <div className="package-step-heading">
                <div>
                  <span>1</span>
                  <div>
                    <h3>Choose source exam</h3>
                    <p>Exams with a complete parsed answer key</p>
                  </div>
                </div>
              </div>
              <label>
                Source exam
                <select
                  disabled={visibleSourceExams.length === 0 || isWorking}
                  onChange={(event) => setSourceExamId(event.target.value || null)}
                  value={sourceExamId ?? ""}
                >
                  {visibleSourceExams.length === 0 ? <option value="">No matching exam ready</option> : null}
                  {visibleSourceExams.map((exam) => (
                    <option key={exam.source_exam_id} value={exam.source_exam_id}>
                      {exam.title} - {exam.question_count} questions
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="package-exam-upload">
              <div className="package-step-heading">
                <div>
                  <span>2</span>
                  <div>
                    <h3>Or upload an exam</h3>
                    <p>PDF with questions and answer key; OCR is ready for scans</p>
                  </div>
                </div>
              </div>
              <label>
                Upload exam PDF
                <input
                  accept=".pdf,application/pdf"
                  disabled={isWorking}
                  onChange={(event) => {
                    const file = event.target.files?.[0] ?? null;
                    if (file && file.size > MAX_SOURCE_PDF_BYTES) {
                      setSourceFile(null);
                      setSourceFileError("Choose a PDF smaller than 250 MB.");
                      return;
                    }
                    setSourceFile(file);
                    setSourceFileError(null);
                  }}
                  type="file"
                />
              </label>
              {sourceFileError ? <p className="package-file-error" role="alert">{sourceFileError}</p> : null}
              <label className="package-ocr-toggle">
                <input checked={enableOcr} onChange={(event) => setEnableOcr(event.target.checked)} type="checkbox" />
                Use OCR for scanned pages
              </label>
              <button
                className="secondary-button"
                disabled={!sourceFile || isWorking}
                onClick={() => void uploadSource()}
                type="button"
              >
                Upload and parse exam
              </button>
            </div>
          </div>
          <div className="package-producer-action">
            <div>
              <strong>One new question for every source question</strong>
              <span>Fresh content with the source format, concepts, and difficulty preserved; PyTorch quality gated.</span>
            </div>
            <button
              className="primary-button"
              disabled={isWorking || selectedSource === null || materials.length === 0}
              onClick={() => selectedSource && void onCreateMockExam(selectedSource, examFormat)}
              type="button"
            >
              Generate new mock exam package
            </button>
          </div>
        </div>
      )}

      {workLabel ? <p className="package-work-status" role="status">{workLabel}</p> : null}
    </section>
  );
}
