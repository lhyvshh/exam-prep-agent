"use client";

import React, { useCallback, useEffect, useState } from "react";

import { PackageDetails } from "@/components/packages/package-details";
import { PackageProducer } from "@/components/packages/package-producer";
import {
  buildStudyPackage,
  createStudyPackage,
  fetchCourseMaterials,
  fetchImportedExamAttempts,
  fetchLatestPackageJob,
  fetchMockExamSources,
  fetchPackageJob,
  fetchPackageVersion,
  fetchPackageVersions,
  fetchStudyPackages,
  generateMockExam,
  importCompletedExam,
  uploadMockExamSource,
  validateStudyPackage
} from "@/lib/api";
import type {
  ImportedExamAttemptRecord,
  ExamBlueprintMode,
  MaterialRecord,
  MockExamSourceSummary,
  StudyPackageCreateRequest,
  StudyPackageFile,
  StudyPackageGenerationJob,
  StudyPackageRecord,
  StudyPackageValidationReport,
  StudyPackageVersion
} from "@/lib/schemas";

const ACTIVE_JOB_STATUSES = new Set(["queued", "running", "paused"]);

export function PackageWorkspace({ courseId }: { readonly courseId: string }): JSX.Element {
  const [materials, setMaterials] = useState<readonly MaterialRecord[]>([]);
  const [sourceExams, setSourceExams] = useState<readonly MockExamSourceSummary[]>([]);
  const [packages, setPackages] = useState<readonly StudyPackageRecord[]>([]);
  const [selectedPackage, setSelectedPackage] = useState<StudyPackageRecord | null>(null);
  const [job, setJob] = useState<StudyPackageGenerationJob | null>(null);
  const [validation, setValidation] = useState<StudyPackageValidationReport | null>(null);
  const [files, setFiles] = useState<readonly StudyPackageFile[]>([]);
  const [versions, setVersions] = useState<readonly StudyPackageVersion[]>([]);
  const [viewedVersion, setViewedVersion] = useState<StudyPackageVersion | null>(null);
  const [importedAttempts, setImportedAttempts] = useState<readonly ImportedExamAttemptRecord[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isWorking, setIsWorking] = useState(false);
  const [workLabel, setWorkLabel] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadPackage = useCallback(async (packageRecord: StudyPackageRecord): Promise<void> => {
    setSelectedPackage(packageRecord);
    setValidation(null);
    setFiles([]);
    setVersions([]);
    setViewedVersion(null);
    setImportedAttempts([]);

    if (packageRecord.status === "complete") {
      const [jobResult, versionResult, attemptResult] = await Promise.all([
        fetchLatestPackageJob(packageRecord.package_id).catch(() => null),
        fetchPackageVersions(packageRecord.package_id),
        fetchImportedExamAttempts(packageRecord.package_id)
      ]);
      const activeVersion = versionResult.versions.find(
        (version) => version.version === packageRecord.active_version
      ) ?? versionResult.versions[0] ?? null;
      setJob(jobResult);
      setVersions(versionResult.versions);
      setImportedAttempts(attemptResult.attempts);
      if (activeVersion) {
        const response = await fetchPackageVersion(packageRecord.package_id, activeVersion.version);
        setViewedVersion(response.version);
        setValidation(response.validation);
        setFiles(response.files);
      }
      return;
    }

    if (packageRecord.status === "building") {
      setJob(await fetchLatestPackageJob(packageRecord.package_id));
    } else {
      setJob(null);
    }
  }, []);

  useEffect(() => {
    let isCurrent = true;
    setIsLoading(true);
    setError(null);
    void Promise.all([
      fetchCourseMaterials(courseId),
      fetchMockExamSources(courseId),
      fetchStudyPackages(courseId)
    ])
      .then(async ([materialResponse, sourceResponse, packageResponse]) => {
        if (!isCurrent) {
          return;
        }
        const readyMaterials = materialResponse.records.filter(
          (material) => material.processing_status === "ready" || material.status === "completed"
        );
        const completeSources = uniqueCompleteSourceExams(
          sourceResponse.sources.flatMap((source) => source.exams)
        );
        setMaterials(readyMaterials);
        setSourceExams(completeSources);
        setPackages(packageResponse.packages);
        const firstPackage = packageResponse.packages[0] ?? null;
        if (firstPackage) {
          await loadPackage(firstPackage);
        }
      })
      .catch((reason: unknown) => {
        if (isCurrent) {
          setError(reason instanceof Error ? reason.message : "Unable to load package sources.");
        }
      })
      .finally(() => {
        if (isCurrent) {
          setIsLoading(false);
        }
      });
    return () => {
      isCurrent = false;
    };
  }, [courseId, loadPackage]);

  useEffect(() => {
    if (!job || !ACTIVE_JOB_STATUSES.has(job.status)) {
      return;
    }
    let isCurrent = true;
    const timer = window.setTimeout(() => {
      void fetchPackageJob(job.job_id)
        .then(async (nextJob) => {
          if (!isCurrent) {
            return;
          }
          setJob(nextJob);
          if (nextJob.status === "complete") {
            const response = await fetchStudyPackages(courseId);
            setPackages(response.packages);
            const completed = response.packages.find(
              (packageRecord) => packageRecord.package_id === nextJob.package_id
            );
            if (completed) {
              await loadPackage(completed);
              setWorkLabel("Package ready for download.");
            }
          } else if (nextJob.status === "failed") {
            setWorkLabel(null);
            setError(nextJob.error_message ?? "Package generation failed.");
          }
        })
        .catch((reason: unknown) => {
          if (isCurrent) {
            setError(reason instanceof Error ? reason.message : "Unable to refresh package progress.");
          }
        });
    }, 1000);
    return () => {
      isCurrent = false;
      window.clearTimeout(timer);
    };
  }, [courseId, job, loadPackage]);

  async function startBuild(packageRecord: StudyPackageRecord): Promise<void> {
    const nextJob = await buildStudyPackage(packageRecord.package_id);
    const buildingRecord = { ...packageRecord, status: "building" as const };
    setJob(nextJob);
    setSelectedPackage(buildingRecord);
    setPackages((current) => current.map((item) =>
      item.package_id === packageRecord.package_id ? buildingRecord : item
    ));
    if (nextJob.status === "complete") {
      const completeRecord = { ...packageRecord, status: "complete" as const };
      setPackages((current) => current.map((item) =>
        item.package_id === packageRecord.package_id ? completeRecord : item
      ));
      await loadPackage(completeRecord);
      setWorkLabel("Package ready for download.");
    }
  }

  async function createAndBuild(request: StudyPackageCreateRequest): Promise<void> {
    const created = await createStudyPackage(request);
    setPackages((current) => [created, ...current.filter((item) => item.package_id !== created.package_id)]);
    await startBuild(created);
  }

  async function handleStudyCards(selectedMaterials: readonly MaterialRecord[]): Promise<void> {
    setIsWorking(true);
    setError(null);
    setWorkLabel("Building study-card package...");
    try {
      const title = selectedMaterials.length === 1
        ? `${selectedMaterials[0]?.display_name ?? selectedMaterials[0]?.file_name ?? "Book"} Study Cards`
        : `Study Cards (${selectedMaterials.length} Books)`;
      await createAndBuild(packageRequest({
        courseId,
        title,
        packageKind: "study_cards",
        materialIds: selectedMaterials.map((material) => material.material_id),
        sourceExamId: null,
        generatedExamIds: []
      }));
    } catch (reason) {
      setWorkLabel(null);
      setError(reason instanceof Error ? reason.message : "Unable to create the study-card package.");
    } finally {
      setIsWorking(false);
    }
  }

  async function handleMockExam(
    sourceExam: MockExamSourceSummary,
    examFormat: ExamBlueprintMode
  ): Promise<void> {
    setIsWorking(true);
    setError(null);
    setWorkLabel(`Generating ${sourceExam.question_count} new questions. This can take several minutes...`);
    try {
      const generated = await generateMockExam({
        course_id: courseId,
        module_id: null,
        module_ids: [],
        scope: {
          course_id: courseId,
          module_ids: [],
          material_ids: materials.map((material) => material.material_id),
          section_ids: [],
          source_type: "practice_exam"
        },
        source_exam_id: sourceExam.source_exam_id,
        blueprint: {
          title: examFormat === "frm_part_i"
            ? "FRM Part I Practice Exam"
            : `${sourceExam.title} - New Practice Exam`,
          instructions: "Choose the best answer for each question.",
          topic_coverage: [],
          target_difficulty: sourceExam.average_difficulty,
          style_example: sourceExam.title
        },
        retrieval_top_k: 8
      });
      setWorkLabel("Questions passed quality gates. Building the HTML package...");
      await createAndBuild(packageRequest({
        courseId,
        title: `${sourceExam.title} - New Mock Exam`,
        packageKind: "mock_exam",
        materialIds: materials.map((material) => material.material_id),
        sourceExamId: sourceExam.source_exam_id,
        generatedExamIds: [generated.exam.exam_id],
        sourceExam,
        examFormat
      }));
    } catch (reason) {
      setWorkLabel(null);
      setError(reason instanceof Error ? reason.message : "Unable to generate the mock exam package.");
    } finally {
      setIsWorking(false);
    }
  }

  async function handleSourceUpload(file: File, enableOcr: boolean): Promise<void> {
    setIsWorking(true);
    setError(null);
    setWorkLabel("Reading questions and answer keys. Large scanned PDFs can take several minutes...");
    try {
      const response = await uploadMockExamSource(courseId, file, enableOcr);
      const complete = uniqueCompleteSourceExams(response.bank.exams.map((exam) => ({
        source_exam_id: exam.source_exam_id,
        title: exam.title,
        question_count: exam.question_count,
        answer_count: exam.answer_count,
        average_difficulty: exam.questions.length
          ? exam.questions.reduce((sum, question) => sum + question.difficulty, 0)
            / exam.questions.length
          : 0.6
      })));
      setSourceExams((current) => uniqueCompleteSourceExams([...complete, ...current]));
      setWorkLabel(
        complete.length > 0
          ? "Exam parsed and ready."
          : "Parsing finished, but no exam with a complete answer key was found."
      );
    } catch (reason) {
      setWorkLabel(null);
      setError(reason instanceof Error ? reason.message : "Unable to parse the exam PDF.");
    } finally {
      setIsWorking(false);
    }
  }

  async function handleValidate(): Promise<void> {
    if (!selectedPackage) {
      return;
    }
    setIsWorking(true);
    setError(null);
    try {
      setValidation(await validateStudyPackage(selectedPackage.package_id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to validate the package.");
    } finally {
      setIsWorking(false);
    }
  }

  async function handleVersionSelect(version: StudyPackageVersion): Promise<void> {
    if (!selectedPackage || version.version === viewedVersion?.version) {
      return;
    }
    const response = await fetchPackageVersion(selectedPackage.package_id, version.version);
    setViewedVersion(response.version);
    setValidation(response.validation);
    setFiles(response.files);
  }

  async function handleImportAttempt(file: File): Promise<void> {
    if (!selectedPackage) {
      return;
    }
    setError(null);
    const result = await importCompletedExam(selectedPackage.package_id, file);
    setImportedAttempts((current) => [
      result.record,
      ...current.filter((item) => item.attempt.attempt_id !== result.record.attempt.attempt_id)
    ]);
    setWorkLabel(result.duplicate ? "Attempt already recorded" : "Attempt imported");
  }

  return (
    <section className="package-workspace" aria-label="Offline study package" data-bottom-clearance="exam-butler">
      <header className="package-page-intro">
        <div>
          <p className="eyebrow">Offline HTML</p>
          <h1>Build once. Study anywhere.</h1>
          <p>Generate interactive study cards or a source-matched mock exam for any device.</p>
        </div>
      </header>
      {error ? <div className="status-panel error-panel" role="alert">{error}</div> : null}
      {isLoading ? <p className="package-loading" role="status">Loading ready books and exams...</p> : null}
      {!isLoading ? (
        <>
          <PackageProducer
            isWorking={isWorking}
            materials={materials}
            onCreateMockExam={handleMockExam}
            onCreateStudyCards={handleStudyCards}
            onUploadSource={handleSourceUpload}
            sourceExams={sourceExams}
            workLabel={workLabel}
          />
          <PackageDetails
            files={files}
            importedAttempts={importedAttempts}
            isWorking={isWorking}
            job={job}
            onImportAttempt={handleImportAttempt}
            onSelectPackage={loadPackage}
            onValidate={handleValidate}
            onVersionSelect={handleVersionSelect}
            packages={packages}
            selectedPackage={selectedPackage}
            validation={validation}
            versions={versions}
            viewedVersion={viewedVersion}
          />
        </>
      ) : null}
    </section>
  );
}

type PackageRequestInput = {
  readonly courseId: string;
  readonly title: string;
  readonly packageKind: "study_cards" | "mock_exam";
  readonly materialIds: readonly string[];
  readonly sourceExamId: string | null;
  readonly generatedExamIds: readonly string[];
  readonly sourceExam?: MockExamSourceSummary;
  readonly examFormat?: ExamBlueprintMode;
};

function packageRequest(input: PackageRequestInput): StudyPackageCreateRequest {
  const isMockExam = input.packageKind === "mock_exam";
  return {
    course_id: input.courseId,
    title: input.title,
    package_kind: input.packageKind,
    exam_blueprint_mode: input.examFormat ?? "source_exam",
    exam_name: input.examFormat === "frm_part_i"
      ? "Financial Risk Manager"
      : input.sourceExam?.title ?? "Course study materials",
    exam_part: input.examFormat === "frm_part_i"
      ? "Part I"
      : input.sourceExam ? "Source-defined practice exam" : "Study cards",
    mock_exam_count: isMockExam ? 1 : 0,
    questions_per_exam: input.sourceExam?.question_count ?? 100,
    cards_per_concept: 10,
    timer_minutes: input.sourceExam
      ? Math.max(15, Math.min(720, Math.ceil(input.sourceExam.question_count * 2.4)))
      : 240,
    include_formula_review: false,
    include_source_references: true,
    material_ids: [...input.materialIds],
    source_exam_id: input.sourceExamId,
    generated_exam_ids: [...input.generatedExamIds]
  };
}

function uniqueCompleteSourceExams(
  exams: readonly MockExamSourceSummary[]
): readonly MockExamSourceSummary[] {
  const titles = new Set<string>();
  return exams.filter((exam) => {
    const title = exam.title.trim().toLocaleLowerCase();
    if (exam.question_count < 1 || exam.answer_count !== exam.question_count || titles.has(title)) {
      return false;
    }
    titles.add(title);
    return true;
  });
}
