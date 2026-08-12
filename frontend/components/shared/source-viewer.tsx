"use client";

import React, { useEffect, useState } from "react";

import {
  fetchCourseMaterials,
  fetchMaterialPageImages,
  fetchMaterialStudy,
  resolveSourceTarget
} from "@/lib/api";
import type {
  MaterialPageImageItem,
  MaterialRecord,
  MaterialStudySection,
  SourceChunk,
} from "@/lib/schemas";

export type SourceViewerState = {
  material: MaterialRecord;
  section: MaterialStudySection;
  initialPage?: number | null;
};

export function ReviewSourceModal({
  citation,
  returnHref,
  returnLabel = "Back",
  onClose
}: {
  citation: SourceChunk;
  returnHref?: string | null;
  returnLabel?: string;
  onClose: () => void;
}): JSX.Element {
  const [state, setState] = useState<SourceViewerState | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setState(null);
    setError(null);
    void resolveCitationSourceViewerState(citation)
      .then((resolved) => {
        if (!cancelled) {
          setState(resolved);
        }
      })
      .catch((loadError) => {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : "Unable to open the cited source.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [citation]);

  if (state) {
    return (
      <SourceViewerModal
        initialPage={citation.locator.page_number ?? state.section.page_start ?? 1}
        returnHref={returnHref}
        returnLabel={returnLabel}
        state={state}
        onClose={onClose}
      />
    );
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <section className="section-quiz-modal" role="dialog" aria-modal="true" aria-label="Loading source">
        <div className="drawer-header">
          <div>
            <p className="eyebrow">{citation.file_name}</p>
            <h2>Open source</h2>
            <p>{citation.section_title}</p>
          </div>
          <button className="secondary-button" onClick={onClose} type="button">
            Close
          </button>
        </div>
        {error ? (
          <div className="status-panel error-panel" aria-live="polite">
            <strong>Issue:</strong> {error}
          </div>
        ) : (
          <div className="status-panel" aria-live="polite">
            <strong>Loading cited source...</strong>
            <p className="subtle">We’re resolving the exact material section and page reference.</p>
          </div>
        )}
      </section>
    </div>
  );
}

export function SourceViewerModal({
  state,
  initialPage,
  returnHref,
  returnLabel = "Back",
  onClose
}: {
  state: SourceViewerState;
  initialPage?: number;
  returnHref?: string | null;
  returnLabel?: string;
  onClose: () => void;
}): JSX.Element {
  const resolvedInitialPage = initialPage ?? state.initialPage ?? state.section.page_start ?? 1;
  const [page, setPage] = useState<number>(resolvedInitialPage);

  useEffect(() => {
    setPage(initialPage ?? state.initialPage ?? state.section.page_start ?? 1);
  }, [initialPage, state.initialPage, state.section.page_start, state.section.section_id]);

  const pageRange = buildPageRangeLabel(state.section);
  const linkedPages = buildPageRangeNumbers(state.section, state.material.page_count);

  return (
    <div className="modal-backdrop" role="presentation">
      <section className="source-modal" role="dialog" aria-modal="true" aria-label="Source viewer">
        <div className="source-modal-left">
          <div className="drawer-header">
            <div>
              <p className="eyebrow">{state.material.file_name}</p>
              <h2>{state.section.normalized_title}</h2>
              {pageRange ? <p className="subtle">{pageRange}</p> : null}
            </div>
            <button className="secondary-button" onClick={onClose} type="button">
              Close
            </button>
          </div>
          <div className="study-summary-callout">
            <span className="study-callout-label">Quoted section</span>
            <p>{state.section.summary}</p>
          </div>
          {state.section.memorize_keywords.length > 0 ? (
            <section className="study-panel study-panel-accent">
              <h4>Terms to lock in</h4>
              <div className="study-chip-list">
                {state.section.memorize_keywords.slice(0, 8).map((term) => (
                  <span className="study-keyword-chip" key={term}>
                    {term}
                  </span>
                ))}
              </div>
            </section>
          ) : null}
          <section className="study-panel">
            <h4>Source anchor</h4>
            <p className="source-anchor-copy">{state.section.source_anchor}</p>
          </section>
          {linkedPages.length > 1 ? (
            <section className="study-panel source-page-range-panel">
              <h4>Module pages</h4>
              <p className="subtle">Open any linked page in this module.</p>
              <div className="source-page-range-list">
                {linkedPages.map((linkedPage) => (
                  <button
                    aria-current={linkedPage === page ? "page" : undefined}
                    className={`source-page-chip${linkedPage === page ? " active" : ""}`}
                    key={linkedPage}
                    onClick={() => setPage(linkedPage)}
                    type="button"
                  >
                    Page {linkedPage}
                  </button>
                ))}
              </div>
            </section>
          ) : null}
          <div className="action-row">
            <button
              className="secondary-button"
              disabled={page <= 1}
              onClick={() => setPage((current) => Math.max(1, current - 1))}
              type="button"
            >
              Previous page
            </button>
            <button
              className="secondary-button"
              disabled={page >= (state.material.page_count ?? page)}
              onClick={() => setPage((current) => Math.min(state.material.page_count ?? current, current + 1))}
              type="button"
            >
              Next page
            </button>
          </div>
          <div className="action-row">
            {returnHref ? (
              <a className="secondary-button" href={returnHref}>
                {returnLabel}
              </a>
            ) : null}
            <a
              className="primary-button"
              href={buildFileUrl(state.material.material_id, page)}
              target="_blank"
              rel="noreferrer"
            >
              Open full PDF
            </a>
          </div>
        </div>
        <SourceViewerPane
          className="source-modal-page"
          page={page}
          showControls={false}
          state={state}
          variant="modal"
        />
      </section>
    </div>
  );
}

export function SourceViewerPane({
  state,
  page,
  variant = "inline",
  className = "",
  showControls = true
}: {
  state: SourceViewerState;
  page?: number;
  variant?: "inline" | "modal";
  className?: string;
  showControls?: boolean;
}): JSX.Element {
  const resolvedPage = page ?? state.section.page_start ?? 1;
  const [pageImageFailed, setPageImageFailed] = useState<boolean>(false);
  const [pageImageLoaded, setPageImageLoaded] = useState<boolean>(false);
  const [embeddedImages, setEmbeddedImages] = useState<MaterialPageImageItem[]>([]);
  const pageRange = buildPageRangeLabel(state.section);
  const fileUrl = buildFileUrl(state.material.material_id, resolvedPage);
  const imageUrl = buildImageUrl(state.material.material_id, resolvedPage, variant === "inline" ? 900 : 1200);
  const isPdf =
    state.material.content_type === "application/pdf" ||
    state.material.file_name.toLowerCase().endsWith(".pdf");
  const shouldTryPageImage = variant === "inline";

  useEffect(() => {
    let isCancelled = false;
    setPageImageFailed(false);
    setPageImageLoaded(false);
    setEmbeddedImages([]);
    void fetchMaterialPageImages(state.material.material_id, resolvedPage)
      .then((response) => {
        if (!isCancelled) {
          setEmbeddedImages(response.images.slice(0, 4));
        }
      })
      .catch(() => {
        if (!isCancelled) {
          setEmbeddedImages([]);
        }
      });
    return () => {
      isCancelled = true;
    };
  }, [resolvedPage, state.material.material_id]);

  return (
    <aside
      className={`${variant === "inline" ? "inline-source-viewer" : ""} ${className}`.trim()}
      aria-label={`Source for ${state.section.normalized_title}`}
    >
      <div className={variant === "inline" ? "inline-source-header" : "source-modal-page-header"}>
        <div>
          <strong>{showControls ? `Page ${resolvedPage}` : "Quoted page"}</strong>
          <p className="subtle">
            {state.material.file_name}
            {pageRange ? ` · ${pageRange}` : resolvedPage ? ` · page ${resolvedPage}` : ""}
          </p>
        </div>
        {variant === "modal" ? <span className="subtle">{state.section.source_anchor}</span> : null}
      </div>
      {shouldTryPageImage && !pageImageFailed ? (
        <>
          {!pageImageLoaded ? (
            <div className="source-loading-state" aria-live="polite">
              <strong>Loading source page...</strong>
              <p className="subtle">Preparing the exact quoted page for this section.</p>
            </div>
          ) : null}
          <img
            alt={variant === "inline" ? `${state.section.normalized_title} quoted page` : `${state.material.file_name} page ${resolvedPage}`}
            className={variant === "inline" ? "inline-source-image" : "source-modal-image"}
            hidden={!pageImageLoaded}
            onError={() => setPageImageFailed(true)}
            onLoad={() => setPageImageLoaded(true)}
            src={imageUrl}
          />
        </>
      ) : isPdf ? (
        <iframe
          className={variant === "inline" ? "inline-source-frame" : "source-modal-frame"}
          key={fileUrl}
          src={fileUrl}
          title={`${state.material.file_name} page ${resolvedPage}`}
        />
      ) : (
        <div className="study-list-block">
          <h4>Quoted section</h4>
          <p>{state.section.summary}</p>
          <ul>
            {state.section.key_points.slice(0, 4).map((point) => (
              <li key={point}>{point}</li>
            ))}
          </ul>
        </div>
      )}
      {embeddedImages.length > 0 ? (
        <div className="source-image-strip">
          {embeddedImages.map((image) => (
            <img
              alt={image.name}
              className="source-extracted-image"
              key={image.image_id}
              src={image.src}
            />
          ))}
        </div>
      ) : null}
      {variant === "inline" ? <p className="source-anchor-copy">{state.section.source_anchor}</p> : null}
    </aside>
  );
}

function buildFileUrl(materialId: string, page: number): string {
  return `/api/v1/materials/${encodeURIComponent(materialId)}/file#page=${page}`;
}

function buildImageUrl(materialId: string, page: number, width: number): string {
  return `/api/v1/materials/${encodeURIComponent(materialId)}/pages/${page}/image?width=${width}`;
}

function buildPageRangeLabel(section: MaterialStudySection): string | null {
  if (section.page_start && section.page_end && section.page_end > section.page_start) {
    return `pages ${section.page_start}-${section.page_end}`;
  }
  if (section.page_start) {
    return `page ${section.page_start}`;
  }
  return null;
}

function buildPageRangeNumbers(section: MaterialStudySection, maxPage?: number | null): number[] {
  const start = section.page_start ?? section.page_end ?? null;
  if (!start) {
    return [];
  }
  const end = section.page_end && section.page_end >= start ? section.page_end : start;
  const boundedStart = Math.max(1, start);
  const boundedEnd = maxPage ? Math.min(end, maxPage) : end;
  const pages: number[] = [];
  for (let linkedPage = boundedStart; linkedPage <= boundedEnd; linkedPage += 1) {
    pages.push(linkedPage);
  }
  return pages;
}

async function resolveCitationSourceViewerState(citation: SourceChunk): Promise<SourceViewerState> {
  try {
    const resolved = await resolveSourceTarget({
      material_id: citation.material_id,
      section_id: citation.source_id,
      source_id: citation.source_id,
      page_start: citation.locator.page_number,
      page_end: citation.locator.page_number,
      anchor_text: citation.text,
      return_origin: {
        course_id: citation.course_id,
        module_id: citation.module_id ?? null,
      },
    });
    return {
      material: resolved.material,
      section: resolved.section ?? buildFallbackSection(citation),
    };
  } catch {
    // Fall back to the older client-side resolver for existing local data and tests.
  }

  const materialGroups = await loadCitationMaterialGroups(citation);
  const record =
    materialGroups.find((response) => response.records.some((item) => item.material_id === citation.material_id))
      ?.records.find((item) => item.material_id === citation.material_id) ??
    buildFallbackMaterial(citation);

  for (const group of materialGroups) {
    const material = group.records.find((item) => item.material_id === citation.material_id);
    if (!material) {
      continue;
    }
    const resolved = await findSectionForCitation(material, citation);
    if (resolved) {
      return {
        material,
        section: resolved,
      };
    }
  }

  return {
    material: record,
    section: buildFallbackSection(citation),
  };
}

async function loadCitationMaterialGroups(citation: SourceChunk) {
  const requestedModuleId = citation.module_id ?? null;
  const primary = await fetchCourseMaterials(citation.course_id, requestedModuleId);
  if (requestedModuleId && !primary.records.some((item) => item.material_id === citation.material_id)) {
    const fallback = await fetchCourseMaterials(citation.course_id, null);
    return [primary, fallback];
  }
  return [primary];
}

async function findSectionForCitation(
  material: MaterialRecord,
  citation: SourceChunk
): Promise<MaterialStudySection | null> {
  let offset = 0;
  let hasMore = true;
  while (hasMore) {
    const study = await fetchMaterialStudy(material.material_id, { offset, limit: 24 });
    const exact = study.sections.find((section) => section.source_ids.includes(citation.source_id));
    if (exact) {
      return exact;
    }

    const pageNumber = citation.locator.page_number;
    if (pageNumber) {
      const byPage = study.sections.find((section) => {
        const start = section.page_start ?? pageNumber;
        const end = section.page_end ?? start;
        return pageNumber >= start && pageNumber <= end;
      });
      if (byPage) {
        return byPage;
      }
    }

    hasMore = study.has_more;
    offset += study.limit;
  }

  return null;
}

function buildFallbackMaterial(citation: SourceChunk): MaterialRecord {
  return {
    material_id: citation.material_id,
    course_id: citation.course_id,
    module_id: citation.module_id ?? null,
    file_name: citation.file_name,
    display_name: citation.file_name,
    content_type: citation.content_type,
    status: "completed",
    page_count: citation.locator.page_number ?? null,
    processing_status: "ready",
    processing_progress: 100,
    outline_status: "completed",
    enrichment_status: "completed",
    chunk_count: 0,
    section_count: 0,
    error_message: null,
  };
}

function buildFallbackSection(citation: SourceChunk): MaterialStudySection {
  const locatorPage = citation.locator.page_number ?? citation.locator.slide_number ?? null;
  return {
    section_id: citation.source_id,
    material_id: citation.material_id,
    parent_group_id: null,
    title: citation.section_title,
    normalized_title: cleanLabel(citation.section_title),
    page_start: locatorPage,
    page_end: locatorPage,
    source_anchor: citation.citation_label,
    summary: cleanExcerpt(citation.text),
    key_points: [cleanExcerpt(citation.text)],
    memorize_keywords: [],
    memorize_functions_or_formulas: [],
    traps: [],
    difficulty: "medium",
    studied_status: "not_started",
    quiz_ready: false,
    display_order: 0,
    enrichment_status: "completed",
    source_ids: [citation.source_id],
  };
}

function cleanExcerpt(value: string): string {
  return value.replace(/\s+/g, " ").trim().slice(0, 280);
}

function cleanLabel(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}
