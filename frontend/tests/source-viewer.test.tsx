import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SourceViewerModal } from "@/components/shared/source-viewer";
import { fetchMaterialPageImages } from "@/lib/api";
import type { MaterialRecord, MaterialStudySection } from "@/lib/schemas";

vi.mock("@/lib/api", () => ({
  fetchCourseMaterials: vi.fn(),
  fetchMaterialPageImages: vi.fn(async () => ({
    material_id: "mat-workbook",
    page_number: 114,
    images: []
  })),
  fetchMaterialStudy: vi.fn(),
  resolveSourceTarget: vi.fn()
}));

const material: MaterialRecord = {
  material_id: "mat-workbook",
  course_id: "course-demo",
  module_id: null,
  file_name: "FRM 2025 Part 1 KAPLAN Book 1.PDF",
  display_name: "FRM 2025 Part 1 KAPLAN Book 1.PDF",
  file_path: "/tmp/frm.pdf",
  uploaded_at: "2026-05-07T10:00:00Z",
  content_type: "application/pdf",
  status: "completed",
  page_count: 167,
  chunk_count: 3,
  section_count: 1,
  error_message: null
};

const section: MaterialStudySection = {
  section_id: "section-8-1",
  material_id: "mat-workbook",
  parent_group_id: "reading-8",
  title: "Module 8.1: Enterprise Risk Management",
  normalized_title: "Module 8.1: Enterprise Risk Management",
  page_start: 114,
  page_end: 117,
  source_anchor:
    "FRM 2025 Part 1 KAPLAN Book 1.PDF | Study Session 2 / Reading 8 / Module 8.1",
  summary: "Official workbook blocks extracted from key concepts, module quiz, and answer key.",
  key_points: [],
  memorize_keywords: [],
  memorize_functions_or_formulas: [],
  traps: [],
  difficulty: "medium",
  studied_status: "not_started",
  quiz_ready: true,
  display_order: 1,
  enrichment_status: "completed",
  source_ids: ["source-8-1"]
};

describe("SourceViewerModal", () => {
  beforeEach(() => {
    vi.mocked(fetchMaterialPageImages).mockResolvedValue({
      material_id: "mat-workbook",
      page_number: 114,
      images: []
    });
  });

  afterEach(() => {
    cleanup();
  });

  it("opens the full PDF at the cited page instead of trapping the pane on one rendered page", () => {
    render(
      <SourceViewerModal
        initialPage={116}
        state={{ material, section }}
        onClose={vi.fn()}
      />
    );

    expect(
      screen.getByTitle("FRM 2025 Part 1 KAPLAN Book 1.PDF page 116")
    ).toHaveAttribute("src", "/api/v1/materials/mat-workbook/file#page=116");
    expect(
      screen.queryByAltText("FRM 2025 Part 1 KAPLAN Book 1.PDF page 116")
    ).not.toBeInTheDocument();
  });

  it("lets students jump across every page linked to the module", async () => {
    const user = userEvent.setup();
    render(<SourceViewerModal state={{ material, section }} onClose={vi.fn()} />);

    expect(screen.getByRole("button", { name: "Page 114" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("button", { name: "Page 117" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Page 116" }));

    expect(screen.getByRole("button", { name: "Page 116" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Open full PDF" })).toHaveAttribute(
      "href",
      expect.stringContaining("#page=116")
    );
  });

  it("focuses a cited source page without losing the linked module page range", () => {
    render(
      <SourceViewerModal
        state={{ material, section, initialPage: 116 } as any}
        onClose={vi.fn()}
      />
    );

    expect(screen.getByRole("button", { name: "Page 114" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Page 117" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Page 116" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Open full PDF" })).toHaveAttribute(
      "href",
      expect.stringContaining("#page=116")
    );
  });

  it("renders extracted page image crops for image-heavy module quiz pages", async () => {
    vi.mocked(fetchMaterialPageImages).mockResolvedValueOnce({
      material_id: "mat-workbook",
      page_number: 114,
      images: [
        {
          image_id: "img-quiz-table",
          name: "module-quiz-8-2-table.png",
          media_type: "image/png",
          byte_count: 12345,
          src: "/api/v1/materials/mat-workbook/pages/114/images/img-quiz-table"
        }
      ]
    });

    render(<SourceViewerModal state={{ material, section }} onClose={vi.fn()} />);

    expect(await screen.findByAltText("module-quiz-8-2-table.png")).toHaveAttribute(
      "src",
      "/api/v1/materials/mat-workbook/pages/114/images/img-quiz-table"
    );
  });
});
