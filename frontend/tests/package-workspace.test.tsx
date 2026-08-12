import React from "react";
import { readFileSync } from "node:fs";
import path from "node:path";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import packageJson from "../package.json";
import { PackageWorkspace } from "@/components/packages/package-workspace";
import {
  buildStudyPackage,
  createStudyPackage,
  fetchCourseMaterials,
  fetchImportedExamAttempts,
  fetchPackageVersion,
  fetchPackageFiles,
  fetchLatestPackageJob,
  fetchPackageVersions,
  fetchMockExamSources,
  fetchStudyPackages,
  generateMockExam,
  importCompletedExam,
  uploadMockExamSource,
  validateStudyPackage
} from "@/lib/api";

const packageRecord = {
  package_id: "package-1",
  course_id: "course-1",
  title: "FRM Part I Offline Package",
  package_kind: "complete" as const,
  exam_name: "Financial Risk Manager",
  exam_part: "Part I",
  status: "complete" as const,
  active_version: 1,
  created_at: "2026-07-13T12:00:00Z",
  updated_at: "2026-07-13T12:05:00Z"
};

const completeJob = {
  job_id: "job-1",
  package_id: "package-1",
  version: 1,
  status: "complete" as const,
  current_step: "complete",
  accepted_flashcards: 870,
  expected_flashcards: 870,
  accepted_questions: 300,
  expected_questions: 300,
  artifact_size_bytes: 2400000,
  created_at: "2026-07-13T12:01:00Z",
  updated_at: "2026-07-13T12:05:00Z",
  completed_at: "2026-07-13T12:05:00Z",
  error_message: null
};

const zipFile = {
  file_id: "zip-1",
  package_id: "package-1",
  version: 1,
  kind: "zip" as const,
  file_name: "FRM-Part-I-Offline-Package.zip",
  media_type: "application/zip",
  size_bytes: 2400000,
  sha256: "a".repeat(64),
  content_count: 300,
  artifact_path: "package-1/v1/FRM-Part-I-Offline-Package.zip"
};

const packageVersion = {
  package_id: "package-1",
  version: 1,
  status: "complete" as const,
  configuration: {
    course_id: "course-1",
    title: "FRM Part I Offline Package",
    package_kind: "complete" as const,
    exam_blueprint_mode: "frm_part_i" as const,
    exam_name: "Financial Risk Manager",
    exam_part: "Part I",
    mock_exam_count: 3,
    questions_per_exam: 100,
    cards_per_concept: 10 as const,
    timer_minutes: 240,
    include_formula_review: true,
    include_source_references: true,
    material_ids: ["book-1", "book-2", "book-3", "book-4"],
    source_exam_id: "source-exam-1",
    generated_exam_ids: []
  },
  created_at: "2026-07-13T12:00:00Z",
  completed_at: "2026-07-13T12:05:00Z",
  generator_version: "1",
  source_fingerprint: "source-1",
  model_metadata: {},
  prompt_versions: {}
};

const importedAttempt = {
  attempt: {
    schema_version: "1" as const,
    attempt_id: "attempt-1",
    package_id: "package-1",
    package_version: 1,
    file_id: "mock-exam-1",
    exam_id: "exam-1",
    content_sha256: "a".repeat(64),
    started_at: "2026-08-06T12:00:00Z",
    completed_at: "2026-08-06T13:00:00Z",
    remaining_seconds: 1800,
    answers: { "question-1": 0 },
    flags: {}
  },
  imported_at: "2026-08-06T13:05:00Z",
  grade: {
    exam_id: "exam-1",
    course_id: "course-1",
    module_id: null,
    module_ids: [],
    completed_at: "2026-08-06T13:05:00Z",
    overall_score: 82,
    analytics_by_concept: [],
    results: []
  }
};

vi.mock("@/lib/api", () => ({
  buildStudyPackage: vi.fn(async () => completeJob),
  createStudyPackage: vi.fn(async () => packageRecord),
  fetchCourseMaterials: vi.fn(async () => ({
    course_id: "course-1",
    records: ["book-1", "book-2", "book-3", "book-4"].map((materialId, index) => ({
      material_id: materialId,
      course_id: "course-1",
      file_name: `Book ${index + 1}.pdf`,
      display_name: `Book ${index + 1}`,
      content_type: "application/pdf",
      status: "parsed" as const,
      processing_status: "ready" as const,
      chunk_count: 20,
      section_count: 10,
      error_message: null
    })),
    sections: [],
    quiz_sources: [],
    default_source_ids: [],
    default_quiz_source_ids: []
  })),
  fetchMockExamSources: vi.fn(async () => ({
    sources: [{
      bank_id: "source-bank-1",
      course_id: "course-1",
      file_name: "FRM exams.pdf",
      uploaded_at: "2026-07-13T12:00:00Z",
      exam_count: 1,
      question_count: 100,
      exams: [{
        source_exam_id: "source-exam-1",
        title: "FRM Sample Exam",
        question_count: 100,
        answer_count: 100,
        average_difficulty: 0.64
      }],
      warnings: []
    }]
  })),
  fetchPackageFiles: vi.fn(async () => ({ files: [zipFile] })),
  fetchImportedExamAttempts: vi.fn(async () => ({ attempts: [] })),
  fetchLatestPackageJob: vi.fn(async () => completeJob),
  fetchPackageVersions: vi.fn(async () => ({ versions: [packageVersion] })),
  fetchPackageVersion: vi.fn(async () => ({
    package: packageRecord,
    version: packageVersion,
    files: [zipFile],
    validation: {
      package_id: "package-1",
      version: 1,
      passed: true,
      created_at: "2026-07-13T12:05:00Z",
      findings: []
    }
  })),
  fetchStudyPackages: vi.fn(async () => ({ packages: [packageRecord] })),
  generateMockExam: vi.fn(async () => ({
    exam: {
      exam_id: "fresh-exam-1",
      course_id: "course-1",
      module_id: null,
      module_ids: [],
      blueprint: {
        title: "FRM Part I Practice Exam",
        instructions: "Choose the best answer.",
        topic_coverage: [],
        target_difficulty: 0.65,
        style_example: "FRM Sample Exam"
      },
      questions: []
    }
  })),
  packageFileUrl: (packageId: string, fileId: string) =>
    `/api/v1/packages/${packageId}/files/${fileId}`,
  packageVersionFileUrl: (packageId: string, version: number, fileId: string) =>
    `/api/v1/packages/${packageId}/versions/${version}/files/${fileId}`,
  importCompletedExam: vi.fn(async () => ({
    record: importedAttempt,
    duplicate: false
  })),
  uploadMockExamSource: vi.fn(async () => ({
    bank: {
      bank_id: "source-bank-2",
      course_id: "course-1",
      file_name: "New FRM exam.pdf",
      uploaded_at: "2026-08-11T12:00:00Z",
      extraction_mode: "text",
      exams: [{
        source_exam_id: "source-exam-2",
        title: "FRM Sample Exam 2",
        question_count: 100,
        answer_count: 100,
        questions: []
      }],
      warnings: []
    }
  })),
  validateStudyPackage: vi.fn(async () => ({
    package_id: "package-1",
    version: 1,
    passed: true,
    created_at: "2026-07-13T12:05:00Z",
    findings: []
  }))
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("PackageWorkspace", () => {
  it("shows truthful package output and a primary ZIP download", async () => {
    render(<PackageWorkspace courseId="course-1" />);

    const region = await screen.findByRole("region", { name: "Offline study package" });
    expect(region).toHaveAttribute("data-bottom-clearance", "exam-butler");
    expect(within(region).getByRole("heading", { name: "FRM Part I Offline Package" })).toBeInTheDocument();
    expect(within(region).getByText("870 of 870")).toBeInTheDocument();
    expect(within(region).getByText("300 of 300")).toBeInTheDocument();
    expect(within(region).getByText("Validation passed")).toBeInTheDocument();
    expect(within(region).getByText("Ready for download").closest(".package-validation-summary")).not.toBeNull();

    const download = within(region).getByRole("link", { name: /Download offline package/i });
    expect(download).toHaveAttribute(
      "href",
      "/api/v1/packages/package-1/versions/1/files/zip-1"
    );
    expect(download).toHaveAttribute("download", "FRM-Part-I-Offline-Package.zip");
    expect(within(region).getByRole("heading", { name: "Version history" })).toBeInTheDocument();
    expect(within(region).getByRole("heading", { name: "Package history" })).toBeInTheDocument();
    expect(within(region).getByRole("button", { name: /Version 1/i })).toBeInTheDocument();
    expect(fetchPackageVersions).toHaveBeenCalledWith("package-1");
    expect(fetchCourseMaterials).toHaveBeenCalledWith("course-1");
    expect(fetchMockExamSources).toHaveBeenCalledWith("course-1");
  });

  it("imports completed exam HTML and shows its authoritative grade", async () => {
    const user = userEvent.setup();
    render(<PackageWorkspace courseId="course-1" />);

    const file = new File(["<html></html>"], "completed-exam.html", {
      type: "text/html"
    });
    const input = await screen.findByLabelText("Completed exam HTML");
    await user.upload(input, file);
    await user.click(screen.getByRole("button", { name: "Import completed exam" }));

    await waitFor(() => expect(importCompletedExam).toHaveBeenCalledWith("package-1", file));
    expect(screen.getByText("82% authoritative score")).toBeInTheDocument();
    expect(screen.getByText("Attempt imported")).toBeInTheDocument();
    expect(fetchImportedExamAttempts).toHaveBeenCalledWith("package-1");
  });

  it("creates a study-card package from the selected books", async () => {
    vi.mocked(fetchStudyPackages).mockResolvedValueOnce({ packages: [] });
    const user = userEvent.setup();

    render(<PackageWorkspace courseId="course-1" />);

    await user.click(await screen.findByRole("checkbox", { name: "Book 2" }));
    await user.click(screen.getByRole("checkbox", { name: "Book 3" }));
    await user.click(screen.getByRole("checkbox", { name: "Book 4" }));
    await user.click(screen.getByRole("button", { name: "Generate study-card package" }));

    await waitFor(() => {
      expect(createStudyPackage).toHaveBeenCalledWith({
        course_id: "course-1",
        title: "Book 1 Study Cards",
        package_kind: "study_cards",
        exam_blueprint_mode: "source_exam",
        exam_name: "Course study materials",
        exam_part: "Study cards",
        mock_exam_count: 0,
        questions_per_exam: 100,
        cards_per_concept: 10,
        timer_minutes: 240,
        include_formula_review: false,
        include_source_references: true,
        material_ids: ["book-1"],
        source_exam_id: null,
        generated_exam_ids: []
      });
      expect(buildStudyPackage).toHaveBeenCalledWith("package-1");
    });
  });

  it("generates a fresh mock exam before building its package", async () => {
    vi.mocked(fetchStudyPackages).mockResolvedValueOnce({ packages: [] });
    const user = userEvent.setup();

    render(<PackageWorkspace courseId="course-1" />);

    await user.click(await screen.findByRole("tab", { name: "Mock exam" }));
    await user.click(screen.getByRole("button", { name: "Generate new mock exam package" }));

    await waitFor(() => expect(generateMockExam).toHaveBeenCalledTimes(1));
    expect(createStudyPackage).toHaveBeenCalledWith(expect.objectContaining({
      package_kind: "mock_exam",
      exam_blueprint_mode: "frm_part_i",
      mock_exam_count: 1,
      source_exam_id: "source-exam-1",
      generated_exam_ids: ["fresh-exam-1"]
    }));
    expect(buildStudyPackage).toHaveBeenCalledWith("package-1");
  });

  it("accepts a complete non-FRM source exam and preserves its question count", async () => {
    vi.mocked(fetchStudyPackages).mockResolvedValueOnce({ packages: [] });
    vi.mocked(fetchMockExamSources).mockResolvedValueOnce({
      sources: [{
        bank_id: "biology-bank",
        course_id: "course-1",
        file_name: "biology-exam.pdf",
        uploaded_at: "2026-08-12T12:00:00Z",
        exam_count: 1,
        question_count: 3,
        exams: [{
          source_exam_id: "biology-exam-1",
          title: "Biology Placement Practice Exam",
          question_count: 3,
          answer_count: 3,
          average_difficulty: 0.48
        }],
        warnings: []
      }]
    });
    const user = userEvent.setup();

    render(<PackageWorkspace courseId="course-1" />);

    await user.click(await screen.findByRole("tab", { name: "Mock exam" }));
    await user.click(screen.getByRole("button", { name: "Other exams" }));
    expect(screen.getByRole("option", { name: /Biology Placement Practice Exam/ })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Generate new mock exam package" }));

    await waitFor(() => expect(generateMockExam).toHaveBeenCalledTimes(1));
    expect(generateMockExam).toHaveBeenCalledWith(expect.objectContaining({
      blueprint: expect.objectContaining({ target_difficulty: 0.48 })
    }));
    expect(createStudyPackage).toHaveBeenCalledWith(expect.objectContaining({
      exam_blueprint_mode: "source_exam",
      exam_name: "Biology Placement Practice Exam",
      questions_per_exam: 3
    }));
  });

  it("shows only the newest copy of a re-uploaded source exam", async () => {
    vi.mocked(fetchStudyPackages).mockResolvedValueOnce({ packages: [] });
    vi.mocked(fetchMockExamSources).mockResolvedValueOnce({
      sources: [
        {
          bank_id: "new-bank",
          course_id: "course-1",
          file_name: "FRM exams.pdf",
          uploaded_at: "2026-08-11T12:00:00Z",
          exam_count: 1,
          question_count: 100,
          exams: [{
            source_exam_id: "new-source-exam",
            title: "FRM Sample Exam",
            question_count: 100,
            answer_count: 100,
            average_difficulty: 0.64
          }],
          warnings: []
        },
        {
          bank_id: "old-bank",
          course_id: "course-1",
          file_name: "FRM exams.pdf",
          uploaded_at: "2026-07-13T12:00:00Z",
          exam_count: 1,
          question_count: 100,
          exams: [{
            source_exam_id: "old-source-exam",
            title: "FRM Sample Exam",
            question_count: 100,
            answer_count: 100,
            average_difficulty: 0.64
          }],
          warnings: []
        }
      ]
    });
    const user = userEvent.setup();

    render(<PackageWorkspace courseId="course-1" />);
    await user.click(await screen.findByRole("tab", { name: "Mock exam" }));

    expect(screen.getAllByRole("option", { name: /FRM Sample Exam/ })).toHaveLength(1);
  });

  it("uploads an exam PDF from the package producer", async () => {
    vi.mocked(fetchStudyPackages).mockResolvedValueOnce({ packages: [] });
    const user = userEvent.setup();

    render(<PackageWorkspace courseId="course-1" />);

    await user.click(await screen.findByRole("tab", { name: "Mock exam" }));
    const file = new File(["exam"], "New FRM exam.pdf", { type: "application/pdf" });
    await user.upload(screen.getByLabelText("Upload exam PDF"), file);
    await user.click(screen.getByRole("button", { name: "Upload and parse exam" }));

    await waitFor(() => expect(uploadMockExamSource).toHaveBeenCalledWith("course-1", file, true));
    expect(screen.getByRole("option", { name: /FRM Sample Exam 2/ })).toBeInTheDocument();
    expect(screen.getByLabelText("Source exam")).toHaveValue("source-exam-2");
  });

  it("keeps failed validation visible and withholds downloads", async () => {
    vi.mocked(fetchPackageVersion).mockResolvedValueOnce({
      package: packageRecord,
      version: packageVersion,
      files: [],
      validation: {
      package_id: "package-1",
      version: 1,
      passed: false,
      created_at: "2026-07-13T12:05:00Z",
      findings: [
        {
          code: "question_quality_failed",
          severity: "error",
          message: "Two exam questions did not pass the PyTorch quality gate.",
          file_id: null,
          evidence: { count: "2" }
        }
      ]
      }
    });

    render(<PackageWorkspace courseId="course-1" />);

    expect(await screen.findByText("Needs attention")).toBeInTheDocument();
    expect(screen.getByText("Two exam questions did not pass the PyTorch quality gate.")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Download offline package/i })).not.toBeInTheDocument();
  });

  it("loads CLI-built packages when no background job record exists", async () => {
    vi.mocked(fetchLatestPackageJob).mockRejectedValueOnce(new Error("Package job not found."));

    render(<PackageWorkspace courseId="course-1" />);

    expect(await screen.findByText("Validation passed")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Download offline package/i })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Package progress" })).not.toBeInTheDocument();
  });

  it("does not ship react debug injection or debug dependencies", () => {
    const allDependencies = {
      ...packageJson.dependencies,
      ...packageJson.devDependencies
    };
    const layoutSource = readFileSync(path.join(process.cwd(), "app/layout.tsx"), "utf8");
    const courseFrameSource = readFileSync(
      path.join(process.cwd(), "components/courses/course-workspace-frame.tsx"),
      "utf8"
    );
    const globalStyles = readFileSync(path.join(process.cwd(), "app/globals.css"), "utf8");

    expect(allDependencies).not.toHaveProperty("react-grab");
    expect(allDependencies).not.toHaveProperty("react-scan");
    expect(layoutSource).not.toContain("react-grab");
    expect(layoutSource).not.toContain("react-scan");
    expect(courseFrameSource).toContain("course-workspace-packages");
    expect(globalStyles).toContain(
      ".course-workspace-packages .course-workspace-header {\n  position: static;"
    );
  });
});
