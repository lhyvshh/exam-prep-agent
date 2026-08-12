"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";

import {
  fetchCourseMaterials,
  fetchMaterialStudy,
  fetchMaterialStudySection,
  markMaterialStudySection
} from "@/lib/api";
import { useCourseSelection } from "@/components/shared/course-context";
import type { MaterialRecord, MaterialStudySection } from "@/lib/schemas";
import { SectionQuizModal, type QuizModalState } from "@/components/courses/course-materials-workspace";
import { SourceViewerModal } from "@/components/shared/source-viewer";

type StudyItem = {
  material: MaterialRecord;
  section: MaterialStudySection;
};

export function CourseStudyWorkspace({ courseId }: { courseId: string }): JSX.Element {
  const { selectedModuleId } = useCourseSelection();
  const searchParams = useSearchParams();
  const [items, setItems] = useState<StudyItem[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [sourceViewer, setSourceViewer] = useState<StudyItem | null>(null);
  const [quizModal, setQuizModal] = useState<QuizModalState | null>(null);
  const sectionRefs = useRef<Record<string, HTMLElement | null>>({});

  useEffect(() => {
    void loadStudy();
  }, [courseId, selectedModuleId, searchParams]);

  useEffect(() => {
    const sectionId = searchParams?.get("sectionId");
    const sourceId = searchParams?.get("sourceId");
    const focusedItem = items.find((item) =>
      (sectionId && item.section.section_id === sectionId) ||
      (sourceId && item.section.source_ids.includes(sourceId))
    );
    if (!focusedItem) {
      return;
    }
    window.setTimeout(() => {
      sectionRefs.current[focusedItem.section.section_id]?.scrollIntoView({ block: "center" });
    }, 60);
  }, [items, searchParams]);

  async function loadStudy(): Promise<void> {
    setIsLoading(true);
    try {
      const materialId = searchParams?.get("materialId");
      const sectionId = searchParams?.get("sectionId");
      const sourceId = searchParams?.get("sourceId");
      const courseMaterials = await fetchCourseMaterials(courseId, selectedModuleId);
      const records = materialId
        ? courseMaterials.records.filter((record) => record.material_id === materialId)
        : courseMaterials.records;
      const loaded = await Promise.all(
        records.map(async (record) => {
          if (materialId && sectionId) {
            const sectionResponse = await fetchMaterialStudySection(record.material_id, sectionId);
            return [{ material: record, section: sectionResponse.section }];
          }

          const collected: StudyItem[] = [];
          let offset = 0;
          let hasMore = true;
          while (hasMore) {
            const study = await fetchMaterialStudy(record.material_id, { offset, limit: 12 });
            collected.push(
              ...study.sections.map((section) => ({ material: study.record, section }))
            );
            hasMore = study.has_more;
            offset += study.limit;
          }
          return collected;
        })
      );
      setItems(
        loaded
          .flat()
          .filter((item) => !sectionId || item.section.section_id === sectionId)
          .filter((item) => !sourceId || item.section.source_ids.includes(sourceId))
      );
      setError(null);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Unable to load study sections.");
      setItems([]);
    } finally {
      setIsLoading(false);
    }
  }

  async function handleMarkStudied(item: StudyItem): Promise<void> {
    try {
      const response = await markMaterialStudySection(
        item.material.material_id,
        item.section.section_id,
        item.section.studied_status !== "studied"
      );
      setItems((current) =>
        current.map((candidate) =>
          candidate.section.section_id === item.section.section_id
            ? { ...candidate, section: response.section }
            : candidate
        )
      );
    } catch (markError) {
      setError(markError instanceof Error ? markError.message : "Unable to update studied status.");
    }
  }

  const focused = Boolean(searchParams?.get("sectionId") || searchParams?.get("sourceId"));
  const backHref = useMemo(() => {
    const materialId = searchParams?.get("materialId");
    const sectionId = searchParams?.get("sectionId");
    const sourceId = searchParams?.get("sourceId");
    const originScope = searchParams?.get("originScope");
    if (!materialId) {
      return `/courses/${encodeURIComponent(courseId)}/materials`;
    }
    const params = new URLSearchParams({ materialId });
    if (sectionId) {
      params.set("sectionId", sectionId);
    }
    if (sourceId) {
      params.set("sourceId", sourceId);
    }
    if (originScope) {
      params.set("originScope", originScope);
    }
    params.set("restore", "1");
    return `/courses/${encodeURIComponent(courseId)}/materials?${params.toString()}`;
  }, [courseId, searchParams]);

  return (
    <div className="stack">
      <section className="card study-workspace-header">
        <div>
          <h2>{focused ? "Study section" : "Study sections"}</h2>
          <p>Concise exam-prep notes built from usable teaching sections only.</p>
        </div>
        <div className="action-row">
          {focused ? <a className="secondary-button" href={backHref}>Back to material</a> : null}
          <a className="secondary-button" href={`/courses/${encodeURIComponent(courseId)}/materials`}>Materials</a>
        </div>
      </section>

      {isLoading ? <p className="subtle">Loading study sections...</p> : null}
      {error ? (
        <div className="status-panel error-panel" aria-live="polite">
          <strong>Issue:</strong> {error}
        </div>
      ) : null}

      <section className="study-section-grid">
        {items.length === 0 && !isLoading ? (
          <article className="course-empty-card">
            <h3>No study sections ready</h3>
            <p>Upload materials or regenerate a material breakdown from the Materials tab.</p>
          </article>
        ) : null}
        {items.map((item) => (
          <StudySectionCard
            item={item}
            key={`${item.material.material_id}-${item.section.section_id}`}
            onOpenSource={() => setSourceViewer(item)}
            onPractice={() => setQuizModal({ material: item.material, section: item.section })}
            onMarkStudied={() => void handleMarkStudied(item)}
            sectionRef={(node) => {
              sectionRefs.current[item.section.section_id] = node;
            }}
          />
        ))}
      </section>

      {sourceViewer ? (
        <SourceViewerModal state={sourceViewer} onClose={() => setSourceViewer(null)} />
      ) : null}
      {quizModal ? (
        <SectionQuizModal courseId={courseId} state={quizModal} onClose={() => setQuizModal(null)} />
      ) : null}
    </div>
  );
}

function StudySectionCard({
  item,
  onOpenSource,
  onPractice,
  onMarkStudied,
  sectionRef
}: {
  item: StudyItem;
  onOpenSource: () => void;
  onPractice: () => void;
  onMarkStudied: () => void;
  sectionRef?: (node: HTMLElement | null) => void;
}): JSX.Element {
  const { section, material } = item;
  const examAngles = deriveExamAngles(section);
  return (
    <article className="study-section-card-pro" ref={sectionRef}>
      <div className="section-card-top">
        <div>
          <div className="section-meta-row">
            <span className={`difficulty-tag difficulty-${section.difficulty}`}>{section.difficulty}</span>
            {section.page_start ? <span className="subtle">page {section.page_start}</span> : null}
            <span className="subtle">{material.file_name}</span>
          </div>
          <h3>{section.normalized_title}</h3>
        </div>
      </div>
      <div className="study-summary-callout">
        <span className="study-callout-label">Exam summary</span>
        <p className="section-summary">{section.summary}</p>
      </div>
      <div className="study-detail-grid study-detail-grid-pro">
        <StudyCollection title="Key concepts" values={section.key_points} variant="list" />
        <StudyCollection title="Terms to lock in" values={section.memorize_keywords} variant="chips" />
        <StudyCollection
          title="Syntax / formulas / rules"
          values={section.memorize_functions_or_formulas}
          variant="code"
        />
        <StudyCollection title="Common traps" values={section.traps} variant="list" tone="warn" />
        <StudyCollection title="Likely exam angles" values={examAngles} variant="list" tone="accent" />
      </div>
      <div className="action-row">
        <button className="secondary-button" onClick={onOpenSource} type="button">Open source</button>
        <button className="primary-button" disabled={!section.quiz_ready} onClick={onPractice} type="button">Practice this section</button>
        <button className="secondary-button" onClick={onMarkStudied} type="button">
          {section.studied_status === "studied" ? "Mark unstudied" : "Mark studied"}
        </button>
      </div>
    </article>
  );
}

function StudyCollection({
  title,
  values,
  variant,
  tone = "neutral"
}: {
  title: string;
  values: string[];
  variant: "list" | "chips" | "code";
  tone?: "neutral" | "accent" | "warn";
}): JSX.Element | null {
  const unique = Array.from(new Set(values.filter(Boolean))).slice(0, 6);
  if (!unique.length) {
    return null;
  }
  return (
    <section className={`study-panel study-panel-${tone}`}>
      <h4>{title}</h4>
      {variant === "chips" ? (
        <div className="study-chip-list">
          {unique.map((value) => (
            <span className="study-keyword-chip" key={value}>
              {value}
            </span>
          ))}
        </div>
      ) : null}
      {variant === "code" ? (
        <div className="study-code-stack">
          {unique.map((value) => (
            <code className="study-code-card" key={value}>
              {value}
            </code>
          ))}
        </div>
      ) : null}
      {variant === "list" ? (
        <ul className="study-point-list">
          {unique.map((value) => <li key={value}>{value}</li>)}
        </ul>
      ) : null}
    </section>
  );
}

function deriveExamAngles(section: MaterialStudySection): string[] {
  const angles = [
    section.key_points[0] ? `Define or recognize ${section.normalized_title}.` : "",
    section.memorize_functions_or_formulas[0] ? "Apply the rule or syntax in a short example." : "",
    section.traps[0] ? `Avoid this trap: ${section.traps[0]}` : "",
    section.memorize_keywords[0] ? `Compare ${section.memorize_keywords[0]} with nearby concepts.` : ""
  ];
  return angles.filter(Boolean);
}
