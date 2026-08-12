"use client";

import React, { useMemo, useState } from "react";

import { packageVersionFileUrl } from "@/lib/api";
import type {
  ImportedExamAttemptRecord,
  StudyPackageFile,
  StudyPackageGenerationJob,
  StudyPackageRecord,
  StudyPackageValidationReport,
  StudyPackageVersion
} from "@/lib/schemas";

type PackageDetailsProps = {
  readonly packages: readonly StudyPackageRecord[];
  readonly selectedPackage: StudyPackageRecord | null;
  readonly job: StudyPackageGenerationJob | null;
  readonly validation: StudyPackageValidationReport | null;
  readonly files: readonly StudyPackageFile[];
  readonly versions: readonly StudyPackageVersion[];
  readonly viewedVersion: StudyPackageVersion | null;
  readonly importedAttempts: readonly ImportedExamAttemptRecord[];
  readonly isWorking: boolean;
  readonly onSelectPackage: (packageRecord: StudyPackageRecord) => Promise<void>;
  readonly onValidate: () => Promise<void>;
  readonly onVersionSelect: (version: StudyPackageVersion) => Promise<void>;
  readonly onImportAttempt: (file: File) => Promise<void>;
};

const FILE_LABELS: Record<StudyPackageFile["kind"], string> = {
  exam_blueprint: "Exam blueprint",
  flashcards: "Study cards",
  formula_review: "Formula review",
  manifest: "Package manifest",
  mock_exam: "Mock exam",
  validation_html: "Validation report",
  validation_json: "Validation data",
  zip: "Complete package"
};

export function PackageDetails({
  packages,
  selectedPackage,
  job,
  validation,
  files,
  versions,
  viewedVersion,
  importedAttempts,
  isWorking,
  onSelectPackage,
  onValidate,
  onVersionSelect,
  onImportAttempt
}: PackageDetailsProps): JSX.Element {
  const [attemptFile, setAttemptFile] = useState<File | null>(null);
  const [isImporting, setIsImporting] = useState(false);
  const orderedFiles = useMemo(
    () => [...files].sort((left, right) => Number(right.kind === "zip") - Number(left.kind === "zip")),
    [files]
  );
  const zipFile = orderedFiles.find((file) => file.kind === "zip") ?? null;
  const hasMockExam = selectedPackage?.package_kind !== "study_cards"
    || orderedFiles.some((file) => file.kind === "mock_exam");
  const versionNumber = viewedVersion?.version ?? selectedPackage?.active_version ?? 1;
  const isReady = selectedPackage?.status === "complete" && validation?.passed === true;

  async function importAttempt(): Promise<void> {
    if (!attemptFile) {
      return;
    }
    setIsImporting(true);
    try {
      await onImportAttempt(attemptFile);
      setAttemptFile(null);
    } finally {
      setIsImporting(false);
    }
  }

  return (
    <section className="package-library" aria-labelledby="package-history-title">
      <div className="package-section-heading">
        <div>
          <p className="eyebrow">Downloads</p>
          <h2 id="package-history-title">Package history</h2>
        </div>
        <span>{packages.length} saved</span>
      </div>

      {packages.length > 0 ? (
        <div className="package-history-list" role="list">
          {packages.map((packageRecord) => (
            <button
              aria-pressed={packageRecord.package_id === selectedPackage?.package_id}
              className="package-history-item"
              disabled={isWorking}
              key={packageRecord.package_id}
              onClick={() => void onSelectPackage(packageRecord)}
              role="listitem"
              type="button"
            >
              <span>{packageRecord.package_kind === "study_cards" ? "Study cards" : "Mock exam"}</span>
              <strong>{packageRecord.title}</strong>
              <small>{packageRecord.status.replaceAll("_", " ")} - {new Date(packageRecord.updated_at).toLocaleDateString()}</small>
            </button>
          ))}
        </div>
      ) : (
        <p className="package-empty-copy">Generated packages will appear here and remain available for download.</p>
      )}

      {selectedPackage ? (
        <div className="package-output">
          <header className="package-output-header">
            <div>
              <span className={`package-status package-status-${selectedPackage.status}`}>
                {selectedPackage.status.replaceAll("_", " ")}
              </span>
              <h2>{selectedPackage.title}</h2>
              <p>Version {versionNumber} - updated {new Date(selectedPackage.updated_at).toLocaleString()}</p>
            </div>
            {isReady && zipFile ? (
              <a
                className="primary-button package-download-primary"
                download={zipFile.file_name}
                href={packageVersionFileUrl(selectedPackage.package_id, versionNumber, zipFile.file_id)}
              >
                Download offline package
              </a>
            ) : null}
          </header>

          {job ? (
            <div className="package-progress-row" aria-label="Package progress">
              <div>
                <span>Study cards</span>
                <strong>{job.accepted_flashcards} of {job.expected_flashcards}</strong>
              </div>
              <div>
                <span>Exam questions</span>
                <strong>{job.accepted_questions} of {job.expected_questions}</strong>
              </div>
              <div>
                <span>Package size</span>
                <strong>{formatBytes(job.artifact_size_bytes)}</strong>
              </div>
              {job.error_message ? <p role="alert">{job.error_message}</p> : null}
            </div>
          ) : null}

          {validation ? (
            <section className="package-quality package-validation-summary" aria-labelledby="package-validation-title">
              <div>
                <p className="eyebrow">Quality gate</p>
                <h3 id="package-validation-title">
                  {validation.passed ? "Validation passed" : "Needs attention"}
                </h3>
                <span>{validation.passed ? "Ready for download" : "Download withheld"}</span>
              </div>
              <button className="secondary-button" disabled={isWorking} onClick={() => void onValidate()} type="button">
                Run validation
              </button>
              {validation.findings.length > 0 ? (
                <ul>
                  {validation.findings.map((finding) => (
                    <li key={`${finding.code}-${finding.message}`}>{finding.message}</li>
                  ))}
                </ul>
              ) : null}
            </section>
          ) : null}

          {versions.length > 0 ? (
            <section className="package-version-section" aria-labelledby="package-version-title">
              <h3 id="package-version-title">Version history</h3>
              <div className="package-version-row">
              {versions.map((version) => (
                <button
                  aria-pressed={version.version === viewedVersion?.version}
                  className="secondary-button compact-button"
                  disabled={isWorking}
                  key={version.version}
                  onClick={() => void onVersionSelect(version)}
                  type="button"
                >
                  Version {version.version}
                </button>
              ))}
              </div>
            </section>
          ) : null}

          {isReady && hasMockExam ? (
            <section className="package-attempt-import" aria-labelledby="package-import-title">
              <div>
                <p className="eyebrow">Progress import</p>
                <h3 id="package-import-title">Evaluate completed exams</h3>
                <p>Import the completed HTML exam to record its authoritative score.</p>
              </div>
              <label>
                Completed exam HTML
                <input
                  accept=".html,text/html"
                  onChange={(event) => setAttemptFile(event.target.files?.[0] ?? null)}
                  type="file"
                />
              </label>
              <button
                className="primary-button"
                disabled={!attemptFile || isImporting}
                onClick={() => void importAttempt()}
                type="button"
              >
                {isImporting ? "Checking exam..." : "Import completed exam"}
              </button>
              {importedAttempts[0] ? (
                <strong>{Math.round(importedAttempts[0].grade.overall_score)}% authoritative score</strong>
              ) : null}
            </section>
          ) : null}

          {isReady && orderedFiles.length > 0 ? (
            <ul className="package-file-list" aria-label="Download files">
              {orderedFiles.map((file) => (
                <li className={file.kind === "zip" ? "package-file-primary" : undefined} key={file.file_id}>
                  <div>
                    <strong>{FILE_LABELS[file.kind]}</strong>
                    <span>{file.file_name} - {formatBytes(file.size_bytes)}</span>
                  </div>
                  <a
                    className={file.kind === "zip" ? "primary-button compact-button" : "secondary-button compact-button"}
                    download={file.file_name}
                    href={packageVersionFileUrl(file.package_id, file.version, file.file_id)}
                  >
                    Download
                  </a>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
