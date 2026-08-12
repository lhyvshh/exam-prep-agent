"use client";

import React, { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import {
  createModule,
  deleteMaterial,
  fetchCourseMaterials,
  fetchMaterialStudy,
  fetchMaterialStudySection,
  fetchQuizGenerationJob,
  generateQuiz,
  gradeQuiz,
  markMaterialStudySection,
  reprocessMaterial,
  retryMaterialProcessing,
  trackActivityEvent,
  uploadMaterial
} from "@/lib/api";
import { useCourseSelection } from "@/components/shared/course-context";
import { cleanDisplayText } from "@/components/shared/data-widgets";
import { SourceViewerPane, type SourceViewerState } from "@/components/shared/source-viewer";
import { writeCourseResume } from "@/lib/course-resume";
import { scopeFromSection } from "@/lib/scope";
import type {
  CourseMaterialsResponse,
  MaterialRecord,
  MaterialStudyGroup,
  MaterialStudyResponse,
  MaterialStudySection,
  OriginalBookItem,
  QuestionType,
  QuizBundle,
  QuizGenerationJobResponse,
  QuizGradeResponse,
  QuizSubmissionAnswer,
  StudyConceptCard,
  StudyFlashcard,
  StudyFormulaCard,
  StudyLearningOutcome
} from "@/lib/schemas";

const MATERIALS_STATE_KEY = "course-materials-origin";
const QUIZ_MODAL_POLL_MS = 1500;
const ALL_SECTIONS_GROUP_ID = "all-sections";
const FORMULAS_GROUP_ID = "formulas-session";
const WINDOW_BASE_Z_INDEX = 70;
const MIN_FLASHCARDS_PER_LEARNING_OUTCOME = 10;

type FloatingWindowKind = "study" | "source" | "quiz";

export type QuizModalState = {
  section: MaterialStudySection;
  material: MaterialRecord;
};

function fireAndForget(promiseLike: Promise<unknown> | void): void {
  if (promiseLike && typeof promiseLike.catch === "function") {
    void promiseLike.catch(() => undefined);
  }
}

export function CourseMaterialsWorkspace({ courseId }: { courseId: string }): JSX.Element {
  const { selectedModuleId, refresh } = useCourseSelection();
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [materials, setMaterials] = useState<CourseMaterialsResponse | null>(null);
  const [selectedMaterialId, setSelectedMaterialId] = useState<string | null>(null);
  const [selectedGroupId, setSelectedGroupId] = useState<string | null>(null);
  const [selectedStudy, setSelectedStudy] = useState<MaterialStudyResponse | null>(null);
  const [query, setQuery] = useState<string>("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [moduleForm, setModuleForm] = useState({ module_number: "", display_name: "", description: "" });
  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [isLoadingDetail, setIsLoadingDetail] = useState<boolean>(false);
  const [reprocessingMaterialId, setReprocessingMaterialId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sourceViewer, setSourceViewer] = useState<SourceViewerState | null>(null);
  const [quizModal, setQuizModal] = useState<QuizModalState | null>(null);
  const [studyModal, setStudyModal] = useState<QuizModalState | null>(null);
  const [minimizedWindows, setMinimizedWindows] = useState<Record<FloatingWindowKind, boolean>>({
    study: false,
    source: false,
    quiz: false
  });
  const [windowOrder, setWindowOrder] = useState<Record<FloatingWindowKind, number>>({
    study: WINDOW_BASE_Z_INDEX + 1,
    source: WINDOW_BASE_Z_INDEX + 2,
    quiz: WINDOW_BASE_Z_INDEX + 3
  });
  const [windowLayoutMode, setWindowLayoutMode] = useState<"free" | "arranged">("free");
  const [windowLayoutVersion, setWindowLayoutVersion] = useState<number>(0);
  const sectionRefs = useRef<Record<string, HTMLElement | null>>({});
  const originScopeKey = `${courseId}:${selectedModuleId ?? "all"}`;

  useEffect(() => {
    void loadMaterials();
  }, [courseId, selectedModuleId]);

  useEffect(() => {
    const materialId = searchParams?.get("materialId");
    const groupId = searchParams?.get("groupId");
    const sectionId = searchParams?.get("sectionId");
    const sourceId = searchParams?.get("sourceId");
    const restored = searchParams?.get("restore") === "1" ? readOriginState(originScopeKey) : null;
    if (restored) {
      setQuery(restored.query);
    }
    if (materialId) {
      setSelectedMaterialId(materialId);
      setSelectedGroupId(groupId);
      const backendGroupId =
        groupId === FORMULAS_GROUP_ID
          ? formulaBackendGroupId(selectedStudy?.groups ?? [], materialId)
          : backendStudyGroupId(groupId);
      void loadStudy(materialId, sectionId, backendGroupId, sourceId);
    }
  }, [searchParams, originScopeKey]);

  useEffect(() => {
    const sectionId = searchParams?.get("sectionId");
    const sourceId = searchParams?.get("sourceId");
    const sourcePage = Number(searchParams?.get("page") ?? "");
    const shouldOpenStudy = searchParams?.get("study") === "1";
    const shouldOpenQuiz = searchParams?.get("quiz") === "1";
    const targetId = sectionId ?? sourceId;
    if (!targetId || !selectedStudy) {
      if (searchParams?.get("source") === "1" && sourceId && selectedStudy) {
        const section = selectedStudy.sections.find((item) => item.source_ids.includes(sourceId));
        if (section) {
          const requestedPage = Number.isFinite(sourcePage) && sourcePage > 0 ? sourcePage : undefined;
          setSourceViewer({
            material: selectedStudy.record,
            section,
            initialPage: requestedPage
          });
        }
      }
      return;
    }
    const targetSection = selectedStudy.sections.find(
      (section) => section.section_id === targetId || section.source_ids.includes(targetId)
    );
    if (shouldOpenStudy && targetSection) {
      setStudyModal({ material: selectedStudy.record, section: targetSection });
      bringWindowToFront("study");
    }
    if (shouldOpenQuiz && targetSection) {
      setQuizModal({ material: selectedStudy.record, section: targetSection });
      bringWindowToFront("quiz");
    }
    if (searchParams?.get("source") === "1" && sourceId && targetSection) {
      const requestedPage = Number.isFinite(sourcePage) && sourcePage > 0 ? sourcePage : undefined;
      setSourceViewer({
        material: selectedStudy.record,
        section: targetSection,
        initialPage: requestedPage
      });
      bringWindowToFront("source");
    }
    window.setTimeout(() => {
      sectionRefs.current[targetSection?.section_id ?? targetId]?.scrollIntoView({ block: "center" });
      const restored = searchParams?.get("restore") === "1" ? readOriginState(originScopeKey) : null;
      if (restored?.scrollY) {
        window.scrollTo({ top: restored.scrollY, behavior: "auto" });
        window.setTimeout(() => {
          sectionRefs.current[targetSection?.section_id ?? targetId]?.scrollIntoView({ block: "center" });
        }, 80);
      }
    }, 60);
  }, [selectedStudy, searchParams, originScopeKey]);

  useEffect(() => {
    function handleWindowShortcuts(event: KeyboardEvent): void {
      const topWindow = getTopOpenWindow(
        {
          study: Boolean(studyModal) && !minimizedWindows.study,
          source: Boolean(sourceViewer) && !minimizedWindows.source,
          quiz: Boolean(quizModal) && !minimizedWindows.quiz,
        },
        windowOrder
      );

      if (!topWindow) {
        return;
      }

      if (event.key === "Escape") {
        closeFloatingWindow(topWindow);
      }

      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "m") {
        event.preventDefault();
        minimizeWindow(topWindow);
      }
    }

    window.addEventListener("keydown", handleWindowShortcuts);
    return () => window.removeEventListener("keydown", handleWindowShortcuts);
  }, [studyModal, sourceViewer, quizModal, minimizedWindows, windowOrder]);

  async function loadMaterials(): Promise<void> {
    try {
      const response = await fetchCourseMaterials(courseId, selectedModuleId);
      setMaterials(response);
      setError(null);
      const scopedMaterialIds = new Set(response.records.map((record) => record.material_id));
      const requestedMaterialId = searchParams?.get("materialId");
      const requestedGroupId = searchParams?.get("groupId");
      const studyGroupId = backendStudyGroupId(requestedGroupId);
      const preservedSelectedMaterialId =
        selectedMaterialId && scopedMaterialIds.has(selectedMaterialId)
          ? selectedMaterialId
          : null;
      const materialId =
        (requestedMaterialId && scopedMaterialIds.has(requestedMaterialId) ? requestedMaterialId : null) ??
        preservedSelectedMaterialId ??
        null;
      const requestedBackendGroupId =
        materialId && requestedGroupId === FORMULAS_GROUP_ID
          ? formulaBackendGroupId([], materialId)
          : studyGroupId;
      setSelectedMaterialId(materialId);
      setSelectedGroupId(materialId ? requestedGroupId : null);
      if (requestedMaterialId && !scopedMaterialIds.has(requestedMaterialId)) {
        replaceSearchParams(router, pathname, searchParams, {
          materialId,
          groupId: null,
          sectionId: null,
          source: null,
          sourceId: null,
          page: null,
          returnTo: null,
          restore: null,
        });
      }
      if (materialId) {
        await loadStudy(materialId, searchParams?.get("sectionId"), requestedBackendGroupId, searchParams?.get("sourceId"));
      } else {
        setSelectedStudy(null);
      }
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Unable to load materials.");
      setMaterials(null);
    }
  }

  async function loadStudy(
    materialId: string,
    requestedSectionId?: string | null,
    requestedGroupId?: string | null,
    requestedSourceId?: string | null
  ): Promise<void> {
    setIsLoadingDetail(true);
    try {
      const response = await fetchMaterialStudy(materialId, { groupId: requestedGroupId, offset: 0, limit: 30 });
      const targetId = requestedSectionId ?? requestedSourceId;
      const targetInPage = targetId
        ? response.sections.some((section) => section.section_id === targetId || section.source_ids.includes(targetId))
        : true;
      if (targetId && !targetInPage) {
        try {
          const sectionResponse = await fetchMaterialStudySection(materialId, targetId);
          setSelectedStudy({
            ...response,
            sections: [sectionResponse.section, ...response.sections],
            total_sections: Math.max(response.total_sections, response.sections.length + 1),
          });
        } catch {
          setSelectedStudy(response);
        }
      } else {
        setSelectedStudy(response);
      }
      fireAndForget(trackActivityEvent({
        course_id: response.record.course_id,
        module_id: response.record.module_id ?? selectedModuleId,
        material_id: response.record.material_id,
        event_type: "material_opened",
        metadata_json: {
          requested_section_id: requestedSectionId ?? null,
          requested_group_id: requestedGroupId ?? null,
          requested_source_id: requestedSourceId ?? null
        }
      }));
      writeCourseResume(response.record.course_id, {
        lastModule: buildMaterialResumeLink(courseId, response.record, response.sections, requestedSectionId, requestedSourceId, requestedGroupId)
      });
      setError(null);
    } catch (loadError) {
      setSelectedStudy(null);
      setError(loadError instanceof Error ? loadError.message : "Unable to load material detail.");
    } finally {
      setIsLoadingDetail(false);
    }
  }

  function trackSectionActivity(
    eventType: "material_section_viewed" | "pdf_source_clicked" | "quiz_started",
    material: MaterialRecord,
    section: MaterialStudySection,
    metadata: Record<string, unknown> = {}
  ): void {
    fireAndForget(trackActivityEvent({
      course_id: material.course_id,
      module_id: material.module_id ?? selectedModuleId,
      material_id: material.material_id,
      section_id: section.section_id,
      event_type: eventType,
      metadata_json: {
        section_title: section.normalized_title,
        page_start: section.page_start ?? null,
        page_end: section.page_end ?? null,
        source_ids: section.source_ids,
        ...metadata
      }
    }));
  }

  async function handleUpload(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!selectedFile) {
      setError("Choose a file before uploading.");
      return;
    }
    setIsUploading(true);
    try {
      const response = await uploadMaterial(courseId, selectedFile, selectedModuleId);
      setSelectedFile(null);
      setSelectedMaterialId(response.record.material_id);
      setSelectedGroupId(null);
      await refresh();
      await loadMaterials();
      await loadStudy(response.record.material_id);
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : "Upload failed.");
    } finally {
      setIsUploading(false);
    }
  }

  async function handleCreateModule(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!moduleForm.module_number.trim() || !moduleForm.display_name.trim()) {
      setError("Module number and name are required.");
      return;
    }
    try {
      await createModule({
        course_id: courseId,
        module_number: moduleForm.module_number.trim(),
        display_name: moduleForm.display_name.trim(),
        description: moduleForm.description.trim() || null
      });
      setModuleForm({ module_number: "", display_name: "", description: "" });
      await refresh();
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "Unable to add module.");
    }
  }

  async function handleDeleteMaterial(material: MaterialRecord): Promise<void> {
    if (!window.confirm("Delete this material and its study breakdown?")) {
      return;
    }
    try {
      await deleteMaterial(material.material_id);
      goToLibrary();
      await refresh();
      await loadMaterials();
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "Unable to delete material.");
    }
  }

  async function handleRegenerate(materialId: string): Promise<void> {
    if (reprocessingMaterialId === materialId) {
      return;
    }
    setReprocessingMaterialId(materialId);
    try {
      setSelectedGroupId(null);
      setSelectedStudy(null);
      setStudyModal(null);
      setQuizModal(null);
      setSourceViewer(null);
      setMinimizedWindows({ study: false, source: false, quiz: false });
      replaceSearchParams(router, pathname, searchParams, {
        materialId,
        groupId: null,
        sectionId: null,
        source: null,
        sourceId: null,
        page: null,
        returnTo: null,
        restore: null,
      });
      await reprocessMaterial(materialId);
      await refresh();
      await loadMaterials();
      await loadStudy(materialId);
    } catch (regenerateError) {
      setError(regenerateError instanceof Error ? regenerateError.message : "Unable to reprocess material.");
      await loadMaterials();
    } finally {
      setReprocessingMaterialId(null);
    }
  }

  async function handleRetry(materialId: string): Promise<void> {
    try {
      await retryMaterialProcessing(materialId);
      await loadStudy(materialId);
    } catch (retryError) {
      setError(retryError instanceof Error ? retryError.message : "Unable to retry material.");
    }
  }

  async function handleMarkStudied(section: MaterialStudySection): Promise<void> {
    if (!selectedStudy) {
      return;
    }
    try {
      const response = await markMaterialStudySection(
        section.material_id,
        section.section_id,
        section.studied_status !== "studied"
      );
      setSelectedStudy((current) => current ? {
        ...current,
        sections: current.sections.map((item) => item.section_id === section.section_id ? response.section : item)
      } : current);
    } catch (markError) {
      setError(markError instanceof Error ? markError.message : "Unable to update study status.");
    }
  }

  function bringWindowToFront(kind: FloatingWindowKind): void {
    setWindowOrder((current) => ({
      ...current,
      [kind]: Math.max(...Object.values(current)) + 1
    }));
    setMinimizedWindows((current) => ({
      ...current,
      [kind]: false
    }));
    setWindowLayoutMode("free");
  }

  function minimizeWindow(kind: FloatingWindowKind): void {
    setMinimizedWindows((current) => ({
      ...current,
      [kind]: true
    }));
  }

  function closeFloatingWindow(kind: FloatingWindowKind): void {
    if (kind === "study") {
      setStudyModal(null);
      return;
    }
    if (kind === "quiz") {
      setQuizModal(null);
      return;
    }
    closeSourceViewer();
  }

  function closeAllFloatingWindows(): void {
    setStudyModal(null);
    setQuizModal(null);
    setSourceViewer(null);
    setMinimizedWindows({ study: false, source: false, quiz: false });
    replaceSearchParams(router, pathname, searchParams, {
      source: null,
      sourceId: null,
      page: null,
      returnTo: null,
    });
  }

  function arrangeFloatingWindows(): void {
    setWindowLayoutMode("arranged");
    setWindowLayoutVersion((current) => current + 1);
    setMinimizedWindows({ study: false, source: false, quiz: false });
    setWindowOrder({
      study: WINDOW_BASE_Z_INDEX + 1,
      source: WINDOW_BASE_Z_INDEX + 2,
      quiz: WINDOW_BASE_Z_INDEX + 3
    });
  }

  function goToLibrary(): void {
    setSelectedMaterialId(null);
    setSelectedGroupId(null);
    setSelectedStudy(null);
    closeAllFloatingWindows();
    replaceSearchParams(router, pathname, searchParams, {
      materialId: null,
      groupId: null,
      sectionId: null,
      source: null,
      sourceId: null,
      page: null,
      returnTo: null,
      restore: null,
    });
  }

  function closeSourceViewer(): void {
    setSourceViewer(null);
    const returnTo = searchParams?.get("returnTo");
    if (returnTo && searchParams?.get("source") === "1") {
      router.push(returnTo);
      return;
    }
    replaceSearchParams(router, pathname, searchParams, {
      source: null,
      sourceId: null,
      page: null,
      returnTo: null,
    });
  }

  function returnToBookModules(materialId: string): void {
    setSelectedGroupId(null);
    void loadStudy(materialId);
    replaceSearchParams(router, pathname, searchParams, {
      materialId,
      groupId: null,
      sectionId: null,
      source: null,
      sourceId: null,
      page: null,
    });
  }

  const filteredRecords = useMemo(() => {
    const records = materials?.records ?? [];
    const normalizedQuery = query.toLowerCase().trim();
    if (!normalizedQuery) {
      return records;
    }
    return records.filter((record) =>
      `${record.display_name ?? ""} ${record.file_name}`.toLowerCase().includes(normalizedQuery)
    );
  }, [materials, query]);

  const selectedMaterial = selectedStudy?.record ?? filteredRecords.find((record) => record.material_id === selectedMaterialId) ?? null;
  const selectedGroup = selectedStudy?.groups.find((group) => group.group_id === selectedGroupId) ?? null;
  const formulaCards = useMemo(() => collectFormulaCardsFromStudy(selectedStudy), [selectedStudy]);
  const isFormulaStudySession = selectedGroupId === FORMULAS_GROUP_ID;
  const selectedGroupTitle = isFormulaStudySession ? "Formulas" : selectedGroup?.title ?? "All study sections";
  const activeWindowZ = Math.max(...Object.values(windowOrder));
  const openFloatingWindowCount = [studyModal, sourceViewer, quizModal].filter(Boolean).length;

  return (
    <div className="book-library-layout">
      {!selectedMaterial ? (
        <>
          <section className="book-library-header">
            <div>
              <p className="eyebrow">Book library</p>
              <h2>Course books</h2>
              <p className="subtle">Upload a book, open its modules, then study and quiz directly from each section.</p>
            </div>
            <label className="material-search">
              <span>Search</span>
              <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Find a book" />
            </label>
          </section>

          {error ? (
            <div className="status-panel error-panel" aria-live="polite">
              <strong>Issue:</strong> {error}
            </div>
          ) : null}

          <section className="book-shelf-grid">
            <form className="book-upload-slot" onSubmit={handleUpload}>
              <div className="book-upload-cover" aria-hidden="true">+</div>
              <div>
                <h3>Add book</h3>
                <p className="subtle">PDFs, slides, notes, and review sheets become study modules.</p>
              </div>
              <input
                aria-label="Upload material"
                accept=".pdf,.docx,.pptx,.txt"
                type="file"
                onChange={(event) => setSelectedFile(event.target.files?.[0] ?? null)}
              />
              <button className="primary-button" disabled={isUploading || !selectedFile} type="submit">
                {isUploading ? "Uploading..." : "Upload book"}
              </button>
            </form>

            {filteredRecords.map((material) => (
              <button
                className="book-card"
                key={material.material_id}
                onClick={() => {
                  setSelectedMaterialId(material.material_id);
                  setSelectedGroupId(null);
                  void loadStudy(material.material_id);
                  replaceSearchParams(router, pathname, searchParams, {
                    materialId: material.material_id,
                    groupId: null,
                    sectionId: null,
                    source: null,
                    sourceId: null,
                    page: null,
                    returnTo: null,
                    restore: null,
                  });
                }}
                type="button"
              >
                <span className="book-cover">
                  <strong>{bookInitials(material)}</strong>
                </span>
                <span className="book-card-copy">
                  <strong>{material.display_name || material.file_name}</strong>
                  <small>
                    {material.page_count ? `${material.page_count} pages · ` : ""}
                    {material.section_count} sections · {statusLabel(material)}
                  </small>
                </span>
              </button>
            ))}
          </section>

          <details className="compact-details book-module-admin">
            <summary>Add course module</summary>
            <form className="compact-form" onSubmit={handleCreateModule}>
              <label className="field">
                <span>Module number</span>
                <input value={moduleForm.module_number} onChange={(event) => setModuleForm((current) => ({ ...current, module_number: event.target.value }))} />
              </label>
              <label className="field">
                <span>Name</span>
                <input value={moduleForm.display_name} onChange={(event) => setModuleForm((current) => ({ ...current, display_name: event.target.value }))} />
              </label>
              <button className="secondary-button" type="submit">Add module</button>
            </form>
          </details>

          {filteredRecords.length === 0 ? (
            <article className="course-empty-card">
              <h3>No books in this scope</h3>
              <p>Use the upload slot to add a PDF, slide deck, note packet, or review sheet.</p>
            </article>
          ) : null}
        </>
      ) : (
        <section className="book-detail-page">
          <div className="book-page-header">
            <div>
              <nav className="book-context-breadcrumb" aria-label="Book location">
                <button onClick={goToLibrary} type="button">Book Library</button>
                <span>/</span>
                {selectedGroupId ? (
                  <>
                    <button onClick={() => returnToBookModules(selectedMaterial.material_id)} type="button">
                      {selectedMaterial.display_name || selectedMaterial.file_name}
                    </button>
                    <span>/</span>
                    <strong>{selectedGroupTitle}</strong>
                  </>
                ) : (
                  <strong>{selectedMaterial.display_name || selectedMaterial.file_name}</strong>
                )}
              </nav>
              <button
                className="breadcrumb-link book-back-button"
                onClick={() => {
                  if (selectedGroupId) {
                    returnToBookModules(selectedMaterial.material_id);
                    return;
                  }
                  goToLibrary();
                }}
                type="button"
              >
                {selectedGroupId ? "Back to book modules" : "Back to library"}
              </button>
              <p className="eyebrow">{statusLabel(selectedMaterial)}</p>
              <h2>{selectedMaterial.display_name || selectedMaterial.file_name}</h2>
              <p className="subtle">
                {selectedMaterial.page_count ? `${selectedMaterial.page_count} pages · ` : ""}
                {selectedMaterial.section_count} parsed sections
                {selectedGroupId ? ` · ${selectedGroupTitle}` : ""}
              </p>
            </div>
            <div className="action-row">
              {selectedMaterial.status === "failed" ? (
                <button className="secondary-button" onClick={() => void handleRetry(selectedMaterial.material_id)} type="button">Retry</button>
              ) : null}
              <button className="secondary-button" disabled={reprocessingMaterialId === selectedMaterial.material_id} onClick={() => void handleRegenerate(selectedMaterial.material_id)} type="button">
                {reprocessingMaterialId === selectedMaterial.material_id ? "Reprocessing..." : "Reprocess"}
              </button>
              <button className="danger-button" onClick={() => void handleDeleteMaterial(selectedMaterial)} type="button">Delete</button>
            </div>
          </div>

          {isLoadingDetail ? <p className="subtle">Loading book...</p> : null}
          {error ? (
            <div className="status-panel error-panel" aria-live="polite">
              <strong>Issue:</strong> {error}
            </div>
          ) : null}

          {!selectedGroupId ? (
            <BookModuleList
              courseId={courseId}
              material={selectedMaterial}
              groups={selectedStudy?.groups ?? []}
              hasSections={Boolean(selectedStudy?.sections.length)}
              formulas={formulaCards}
              onOpenFormulaSource={(formula) => {
                const section = buildFormulaSourceSection(selectedMaterial, selectedStudy, formula);
                setSourceViewer({ section, material: selectedMaterial, initialPage: section.page_start ?? undefined });
                bringWindowToFront("source");
                replaceSearchParams(router, pathname, searchParams, {
                  materialId: selectedMaterial.material_id,
                  groupId: FORMULAS_GROUP_ID,
                  source: "1",
                  sourceId: section.source_ids[0] ?? null,
                  page: section.page_start ? String(section.page_start) : null,
                });
              }}
              onOpenGroup={(groupId) => {
                const nextGroupId = groupId === ALL_SECTIONS_GROUP_ID ? ALL_SECTIONS_GROUP_ID : groupId;
                setSelectedGroupId(nextGroupId);
                const backendGroupId =
                  groupId === FORMULAS_GROUP_ID
                    ? formulaBackendGroupId(selectedStudy?.groups ?? [], selectedMaterial.material_id)
                    : backendStudyGroupId(groupId);
                void loadStudy(selectedMaterial.material_id, null, backendGroupId);
                replaceSearchParams(router, pathname, searchParams, {
                  materialId: selectedMaterial.material_id,
                  groupId: nextGroupId,
                  sectionId: null,
                  source: null,
                  sourceId: null,
                  page: null,
                });
              }}
              onPracticeFormulas={(formula) => {
                const targetSection = findFormulaPracticeSection(selectedStudy, formula);
                if (!targetSection) {
                  setError("No quiz-ready section is available for these formulas yet.");
                  return;
                }
                setQuizModal({ section: targetSection, material: selectedMaterial });
                bringWindowToFront("quiz");
              }}
            />
          ) : (
            <section className="book-module-page">
              <div className="section-header">
                <div>
                  <h3>{selectedGroupTitle}</h3>
                  <p className="subtle">
                    {isFormulaStudySession
                      ? "Study official formulas, trace source pages, and create formula flashcards without leaving the book."
                      : "Study the module, trace the source, and generate focused quizzes without leaving the book."}
                  </p>
                </div>
                <button className="secondary-button" onClick={() => returnToBookModules(selectedMaterial.material_id)} type="button">
                  Return to book
                </button>
              </div>
              {isFormulaStudySession ? (
                <FormulaStudySessionPage
                  material={selectedMaterial}
                  formulas={formulaCards}
                  onCreateFlashcard={(formula) => {
                    saveFormulaFlashcardToLocalStorage(formula);
                  }}
                  onOpenSource={(formula) => {
                    const section = buildFormulaSourceSection(selectedMaterial, selectedStudy, formula);
                    setSourceViewer({ section, material: selectedMaterial, initialPage: section.page_start ?? undefined });
                    bringWindowToFront("source");
                  }}
                  onPractice={(formula) => {
                    const targetSection = findFormulaPracticeSection(selectedStudy, formula);
                    if (!targetSection) {
                      setError("No quiz-ready section is available for this formula yet.");
                      return;
                    }
                    setQuizModal({ section: targetSection, material: selectedMaterial });
                    bringWindowToFront("quiz");
                  }}
                />
              ) : (
                <div className="book-section-grid">
                  {(selectedStudy?.sections ?? []).map((section) => (
                    <BookStudySectionCard
                      courseId={courseId}
                      key={section.section_id}
                      material={selectedMaterial}
                      section={section}
                      sectionRef={(node) => {
                        sectionRefs.current[section.section_id] = node;
                      }}
                      onStudy={() => {
                        trackSectionActivity("material_section_viewed", selectedMaterial, section, {
                          origin: "book_library_section_card"
                        });
                        setStudyModal({ section, material: selectedMaterial });
                        bringWindowToFront("study");
                      }}
                      onQuiz={() => {
                        trackSectionActivity("quiz_started", selectedMaterial, section, {
                          origin: "book_library_section_card"
                        });
                        setQuizModal({ section, material: selectedMaterial });
                        bringWindowToFront("quiz");
                      }}
                      onOpenSource={() => {
                        trackSectionActivity("pdf_source_clicked", selectedMaterial, section, {
                          origin: "book_library_section_card"
                        });
                        setSourceViewer({ section, material: selectedMaterial, initialPage: section.page_start ?? undefined });
                        bringWindowToFront("source");
                        replaceSearchParams(router, pathname, searchParams, {
                          materialId: selectedMaterial.material_id,
                          groupId: selectedGroupId,
                          source: "1",
                          sourceId: section.source_ids[0] ?? null,
                          page: section.page_start ? String(section.page_start) : null,
                        });
                      }}
                    />
                  ))}
                  {selectedStudy && selectedStudy.sections.length === 0 ? (
                    <article className="course-empty-card">
                      <h3>No study sections in this module</h3>
                      <p>Reprocess the book breakdown or choose another module.</p>
                    </article>
                  ) : null}
                </div>
              )}
            </section>
          )}
        </section>
      )}

      {sourceViewer ? (
        <FloatingSourceWindow
          defaultPosition={getFloatingWindowPosition("source", windowLayoutMode)}
          initialPage={sourceViewer.initialPage ?? sourceViewer.section.page_start ?? Number(searchParams?.get("page") ?? 1)}
          isActive={windowOrder.source === activeWindowZ}
          isMinimized={minimizedWindows.source}
          positionKey={`${windowLayoutMode}-${windowLayoutVersion}`}
          state={sourceViewer}
          zIndex={windowOrder.source}
          onClose={closeSourceViewer}
          onFocus={() => bringWindowToFront("source")}
          onMinimize={() => minimizeWindow("source")}
        />
      ) : null}
      {quizModal ? (
        <SectionQuizModal
          courseId={courseId}
          defaultPosition={getFloatingWindowPosition("quiz", windowLayoutMode)}
          floating
          isActive={windowOrder.quiz === activeWindowZ}
          isMinimized={minimizedWindows.quiz}
          positionKey={`${windowLayoutMode}-${windowLayoutVersion}`}
          state={quizModal}
          zIndex={windowOrder.quiz}
          onClose={() => setQuizModal(null)}
          onFocus={() => bringWindowToFront("quiz")}
          onMinimize={() => minimizeWindow("quiz")}
        />
      ) : null}
      {studyModal ? (
        <StudySectionModal
          defaultPosition={getFloatingWindowPosition("study", windowLayoutMode)}
          isActive={windowOrder.study === activeWindowZ}
          isMinimized={minimizedWindows.study}
          positionKey={`${windowLayoutMode}-${windowLayoutVersion}`}
          state={studyModal}
          onClose={() => setStudyModal(null)}
          zIndex={windowOrder.study}
          onFocus={() => bringWindowToFront("study")}
          onMinimize={() => minimizeWindow("study")}
          onOpenSource={(page) => {
            trackSectionActivity("pdf_source_clicked", studyModal.material, studyModal.section, {
              origin: "study_section_window",
              source_page: page ?? studyModal.section.page_start ?? null
            });
            setSourceViewer({
              material: studyModal.material,
              section: studyModal.section,
              initialPage: page ?? studyModal.section.page_start ?? undefined
            });
            bringWindowToFront("source");
          }}
          onQuiz={() => {
            trackSectionActivity("quiz_started", studyModal.material, studyModal.section, {
              origin: "study_section_window"
            });
            setQuizModal(studyModal);
            bringWindowToFront("quiz");
          }}
          onMarkStudied={() => void handleMarkStudied(studyModal.section)}
        />
      ) : null}
      <FloatingWindowDock
        windows={[
          { kind: "study", label: studyModal?.section.normalized_title ?? "Study", isOpen: Boolean(studyModal), isMinimized: minimizedWindows.study },
          { kind: "source", label: sourceViewer?.section.normalized_title ?? "Source", isOpen: Boolean(sourceViewer), isMinimized: minimizedWindows.source },
          { kind: "quiz", label: quizModal?.section.normalized_title ?? "Quiz", isOpen: Boolean(quizModal), isMinimized: minimizedWindows.quiz },
        ]}
        openCount={openFloatingWindowCount}
        onArrange={arrangeFloatingWindows}
        onCloseAll={closeAllFloatingWindows}
        onRestore={bringWindowToFront}
      />
    </div>
  );
}

function BookModuleList({
  courseId,
  material,
  groups,
  hasSections,
  formulas,
  onOpenFormulaSource,
  onOpenGroup,
  onPracticeFormulas
}: {
  courseId: string;
  material: MaterialRecord;
  groups: MaterialStudyGroup[];
  hasSections: boolean;
  formulas: StudyFormulaCard[];
  onOpenFormulaSource: (formula?: StudyFormulaCard) => void;
  onOpenGroup: (groupId: string) => void;
  onPracticeFormulas: (formula?: StudyFormulaCard) => void;
}): JSX.Element {
  const backendFormulaGroup = groups.find(isBackendFormulaGroup) ?? null;
  const visibleGroups = groups.filter((group) => !isBackendFormulaGroup(group));
  const bookModules = visibleGroups.length > 0
    ? visibleGroups
    : hasSections
      ? [{
          group_id: ALL_SECTIONS_GROUP_ID,
          material_id: "",
          title: "All study sections",
          page_start: null,
          page_end: null,
          display_order: 0,
          section_count: 0,
          ready_count: 0,
          studied_count: 0
        }]
      : [];
  const hasFormulaSession = bookModules.length > 0 || hasSections || formulas.length > 0 || backendFormulaGroup !== null;
  const formulaStatusText = formulas.length > 0
    ? `${formatFormulaPageRange(formulas)} · ready`
    : backendFormulaGroup
      ? `${formatGroupPageRange(backendFormulaGroup)} · ${backendFormulaGroup.ready_count ? "ready" : "needs review"}`
      : "No formulas detected yet.";

  return (
    <section className="book-module-list">
      <div className="section-header">
        <div>
          <h3>Study sessions and readings</h3>
          <p className="subtle">Open a reading to study its modules, inspect source pages, and launch quizzes.</p>
        </div>
      </div>
      {bookModules.length === 0 && !hasFormulaSession ? (
        <article className="course-empty-card">
          <h3>No modules ready</h3>
          <p>This book is still processing or did not produce usable study modules yet.</p>
        </article>
      ) : (
        <div className="book-module-grid">
          {bookModules.map((group) => (
            <article className="book-module-card" key={group.group_id} aria-label={`${group.title} study session`}>
              <button className="book-module-card-main" onClick={() => onOpenGroup(group.group_id)} type="button">
                <span className="book-module-number">{group.display_order + 1}</span>
                <span className="book-module-card-copy">
                  <strong>{group.title}</strong>
                  <small>
                    {formatGroupPageRange(group)}
                    {group.ready_count || group.section_count ? ` · ${group.ready_count || group.section_count} ready` : ""}
                    {group.studied_count ? ` · ${group.studied_count} studied` : ""}
                  </small>
                </span>
              </button>
            </article>
          ))}
          {hasFormulaSession ? (
            <article className="book-module-card formula-session-card" aria-label="Formulas study session">
              <button className="book-module-card-main" onClick={() => onOpenGroup(FORMULAS_GROUP_ID)} type="button">
                <span className="book-module-number">ƒ</span>
                <span className="book-module-card-copy">
                  <h4>Formulas</h4>
                  <small>Official formula sheet / extracted formulas</small>
                  <small>{material.display_name || material.file_name}</small>
                  <small>{formulaStatusText}</small>
                </span>
              </button>
              <div className="book-module-card-actions">
                <button className="secondary-button compact-button" onClick={() => onOpenGroup(FORMULAS_GROUP_ID)} type="button">
                  Study formulas
                </button>
                <button
                  className="secondary-button compact-button"
                  disabled={formulas.length === 0}
                  onClick={() => onPracticeFormulas(formulas[0])}
                  type="button"
                >
                  Practice formulas
                </button>
                <button
                  className="secondary-button compact-button"
                  disabled={formulas.length === 0}
                  onClick={() => onOpenFormulaSource(formulas[0])}
                  type="button"
                >
                  Open source
                </button>
                <a
                  className="secondary-button compact-button"
                  href={`/courses/${encodeURIComponent(courseId)}/flashcards?materialId=${encodeURIComponent(material.material_id)}&formula=1`}
                >
                  Study formula cards
                </a>
              </div>
            </article>
          ) : null}
        </div>
      )}
    </section>
  );
}

function BookStudySectionCard({
  courseId,
  material,
  section,
  sectionRef,
  onStudy,
  onQuiz,
  onOpenSource
}: {
  courseId: string;
  material: MaterialRecord;
  section: MaterialStudySection;
  sectionRef?: (node: HTMLElement | null) => void;
  onStudy: () => void;
  onQuiz: () => void;
  onOpenSource: (page?: number) => void;
}): JSX.Element {
  const hasOfficialWorkbookContent = hasOfficialWorkbookBlocks(section);

  return (
    <article className="study-section-card-pro book-study-section-card" ref={sectionRef}>
      <div className="section-card-top">
        <div>
          <div className="section-meta-row">
            <span className={`difficulty-tag difficulty-${section.difficulty}`}>{section.difficulty}</span>
            {section.page_start ? <span className="subtle">page {section.page_start}</span> : null}
            {section.studied_status === "studied" ? <span className="studied-tag">studied</span> : null}
          </div>
          <h3>{section.normalized_title}</h3>
        </div>
      </div>
      {hasOfficialWorkbookContent ? (
        null
      ) : (
        <>
          <div className="study-summary-callout">
            <span className="study-callout-label">Exam summary</span>
            <p className="section-summary">{section.summary}</p>
          </div>
          <StudyMiniHighlights section={section} />
        </>
      )}
      <div className="action-row">
        <button className="secondary-button" onClick={onStudy} type="button">Study section</button>
        <button className="primary-button" disabled={!section.quiz_ready} onClick={onQuiz} type="button">Quiz this section</button>
        <button className="secondary-button" onClick={() => onOpenSource()} type="button">Open source</button>
        <a
          className="secondary-button"
          href={`/courses/${encodeURIComponent(courseId)}/flashcards?materialId=${encodeURIComponent(material.material_id)}&sectionId=${encodeURIComponent(section.section_id)}`}
        >
          Study cards
        </a>
      </div>
    </article>
  );
}

function hasOfficialWorkbookBlocks(section: MaterialStudySection): boolean {
  return Boolean(
    section.workbook_key_concepts?.length ||
    section.workbook_module_quiz?.length ||
    section.workbook_answer_key?.length
  );
}

function StudyMiniHighlights({ section }: { section: MaterialStudySection }): JSX.Element {
  const concepts = cleanStudyList(section.key_points).slice(0, 2);
  const terms = cleanStudyList(section.memorize_keywords).slice(0, 4);
  const rules = cleanStudyList(section.memorize_functions_or_formulas).slice(0, 2);
  return (
    <div className="study-mini-highlights">
      {concepts.length > 0 ? (
        <div>
          <span>Concepts</span>
          <ul>
            {concepts.map((concept) => <li key={concept}>{concept}</li>)}
          </ul>
        </div>
      ) : null}
      {terms.length > 0 ? (
        <div>
          <span>Terms</span>
          <div className="study-chip-list study-chip-list-compact">
            {terms.map((term) => <span className="study-keyword-chip" key={term}>{term}</span>)}
          </div>
        </div>
      ) : null}
      {rules.length > 0 ? (
        <div>
          <span>Rules</span>
          <div className="study-code-stack study-code-stack-compact">
            {rules.map((rule) => <code className="study-code-card" key={rule}>{rule}</code>)}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function buildMaterialResumeLink(
  courseId: string,
  material: MaterialRecord,
  sections: MaterialStudySection[],
  requestedSectionId?: string | null,
  requestedSourceId?: string | null,
  requestedGroupId?: string | null
): { title: string; href: string; meta: string; updatedAt: string } {
  const targetId = requestedSectionId ?? requestedSourceId ?? null;
  const targetSection = targetId
    ? sections.find((section) => section.section_id === targetId || section.source_ids.includes(targetId))
    : sections[0] ?? null;
  const title = targetSection?.normalized_title || targetSection?.title || material.display_name || material.file_name;
  const params = new URLSearchParams({
    materialId: material.material_id
  });
  const groupId = targetSection?.parent_group_id ?? requestedGroupId ?? null;
  if (groupId) {
    params.set("groupId", groupId);
  }
  if (targetSection) {
    params.set("sectionId", targetSection.section_id);
    params.set("study", "1");
  }

  return {
    title,
    href: `/courses/${encodeURIComponent(courseId)}/materials?${params.toString()}`,
    meta: material.display_name || material.file_name,
    updatedAt: new Date().toISOString()
  };
}

function FloatingWindowFrame({
  kind,
  title,
  eyebrow,
  defaultPosition,
  isActive,
  isMinimized = false,
  positionKey,
  zIndex,
  onClose,
  onFocus,
  onMinimize,
  children
}: {
  kind: FloatingWindowKind;
  title: string;
  eyebrow?: string;
  defaultPosition: { x: number; y: number };
  isActive: boolean;
  isMinimized?: boolean;
  positionKey: string;
  zIndex: number;
  onClose: () => void;
  onFocus: () => void;
  onMinimize: () => void;
  children: React.ReactNode;
}): JSX.Element {
  const [position, setPosition] = useState(defaultPosition);
  const dragRef = useRef<{ pointerId: number; offsetX: number; offsetY: number } | null>(null);

  useEffect(() => {
    setPosition(defaultPosition);
  }, [defaultPosition.x, defaultPosition.y, positionKey]);

  function handlePointerDown(event: React.PointerEvent<HTMLElement>): void {
    if ((event.target as HTMLElement).closest("button, a, input, textarea, select")) {
      return;
    }
    onFocus();
    dragRef.current = {
      pointerId: event.pointerId,
      offsetX: event.clientX - position.x,
      offsetY: event.clientY - position.y
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function handlePointerMove(event: React.PointerEvent<HTMLElement>): void {
    if (!dragRef.current || dragRef.current.pointerId !== event.pointerId) {
      return;
    }
    const maxX = Math.max(16, window.innerWidth - 300);
    const maxY = Math.max(16, window.innerHeight - 180);
    setPosition({
      x: Math.min(Math.max(12, event.clientX - dragRef.current.offsetX), maxX),
      y: Math.min(Math.max(12, event.clientY - dragRef.current.offsetY), maxY)
    });
  }

  function handlePointerUp(event: React.PointerEvent<HTMLElement>): void {
    if (dragRef.current?.pointerId === event.pointerId) {
      dragRef.current = null;
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }

  return (
    <section
      aria-hidden={isMinimized}
      className={`floating-window floating-window-${kind}${isActive ? " floating-window-active" : ""}${isMinimized ? " floating-window-minimized" : ""}`}
      onMouseDown={onFocus}
      role="dialog"
      style={{ transform: `translate(${position.x}px, ${position.y}px)`, zIndex }}
    >
      <header
        className="floating-window-titlebar"
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
      >
        <div>
          {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
          <h2>{title}</h2>
        </div>
        <span className="window-drag-grip" aria-hidden="true">::</span>
        <div className="floating-window-actions">
          <button className="secondary-button compact-button" onClick={onMinimize} type="button">Minimize</button>
          <button className="secondary-button compact-button" onClick={onClose} type="button">Close</button>
        </div>
      </header>
      <div className="floating-window-body">
        {children}
      </div>
    </section>
  );
}

function FloatingSourceWindow({
  state,
  initialPage,
  defaultPosition,
  isActive,
  isMinimized,
  positionKey,
  zIndex,
  onClose,
  onFocus,
  onMinimize
}: {
  state: SourceViewerState;
  initialPage: number;
  defaultPosition: { x: number; y: number };
  isActive: boolean;
  isMinimized: boolean;
  positionKey: string;
  zIndex: number;
  onClose: () => void;
  onFocus: () => void;
  onMinimize: () => void;
}): JSX.Element {
  const [page, setPage] = useState<number>(initialPage || state.section.page_start || 1);

  useEffect(() => {
    setPage(initialPage || state.section.page_start || 1);
  }, [initialPage, state.section.page_start, state.section.section_id]);

  const maxPage = state.material.page_count ?? page;
  const linkedPages = buildLinkedSectionPages(state.section, maxPage);

  return (
    <FloatingWindowFrame
      defaultPosition={defaultPosition}
      eyebrow={state.material.file_name}
      isActive={isActive}
      isMinimized={isMinimized}
      kind="source"
      positionKey={positionKey}
      title="Source page"
      zIndex={zIndex}
      onClose={onClose}
      onFocus={onFocus}
      onMinimize={onMinimize}
    >
      <div className="floating-source-layout">
        <aside className="floating-source-summary">
          <h3>{state.section.normalized_title}</h3>
          <p className="subtle">{formatSectionPageRange(state.section)}</p>
          <div className="study-summary-callout">
            <span className="study-callout-label">Quoted section</span>
            <p>{state.section.summary}</p>
          </div>
          <StudyCollection title="Terms to lock in" values={state.section.memorize_keywords} variant="chips" tone="accent" />
          <section className="study-panel">
            <h4>Source anchor</h4>
            <p className="source-anchor-copy">{state.section.source_anchor}</p>
          </section>
          {linkedPages.length > 1 ? (
            <section className="study-panel source-page-range-panel">
              <h4>Module pages</h4>
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
              Previous
            </button>
            <button
              className="secondary-button"
              disabled={page >= maxPage}
              onClick={() => setPage((current) => Math.min(maxPage, current + 1))}
              type="button"
            >
              Next
            </button>
          </div>
          <a
            className="primary-button"
            href={buildMaterialFileUrl(state.material.material_id, page)}
            rel="noreferrer"
            target="_blank"
          >
            Open full PDF
          </a>
        </aside>
        <SourceViewerPane
          className="floating-source-pane"
          page={page}
          showControls={false}
          state={state}
          variant="modal"
        />
      </div>
    </FloatingWindowFrame>
  );
}

function buildLinkedSectionPages(section: MaterialStudySection, maxPage?: number | null): number[] {
  const start = Math.max(1, Number(section.page_start) || 1);
  const rawEnd = Math.max(start, Number(section.page_end) || start);
  const end = maxPage ? Math.min(rawEnd, maxPage) : rawEnd;
  const pageCount = end - start + 1;
  if (pageCount <= 0) {
    return [start];
  }
  const maxLinkedPages = 80;
  const cappedEnd = pageCount > maxLinkedPages ? start + maxLinkedPages - 1 : end;
  return Array.from({ length: cappedEnd - start + 1 }, (_, index) => start + index);
}

function FloatingWindowDock({
  windows,
  openCount,
  onArrange,
  onCloseAll,
  onRestore
}: {
  windows: Array<{ kind: FloatingWindowKind; label: string; isOpen: boolean; isMinimized: boolean }>;
  openCount: number;
  onArrange: () => void;
  onCloseAll: () => void;
  onRestore: (kind: FloatingWindowKind) => void;
}): JSX.Element | null {
  const dockedWindows = windows.filter((windowItem) => windowItem.isOpen && windowItem.isMinimized);
  if (!dockedWindows.length && openCount < 2) {
    return null;
  }
  return (
    <nav className="floating-window-dock" aria-label="Minimized study windows">
      {openCount >= 2 ? (
        <>
          <button className="window-dock-button window-dock-control" onClick={onArrange} type="button">
            <span>Arrange</span>
            <strong>Side by side</strong>
          </button>
          <button className="window-dock-button window-dock-control" onClick={onCloseAll} type="button">
            <span>Close</span>
            <strong>All windows</strong>
          </button>
        </>
      ) : null}
      {dockedWindows.map((windowItem) => (
        <button
          className="window-dock-button"
          key={windowItem.kind}
          onClick={() => onRestore(windowItem.kind)}
          type="button"
        >
          <span>{windowItem.kind}</span>
          <strong>{windowItem.label}</strong>
        </button>
      ))}
    </nav>
  );
}

export function StudySectionModal({
  state,
  defaultPosition,
  isActive,
  isMinimized = false,
  positionKey,
  onClose,
  onFocus,
  onMinimize,
  zIndex,
  onOpenSource,
  onQuiz,
  onMarkStudied
}: {
  state: QuizModalState;
  defaultPosition: { x: number; y: number };
  isActive: boolean;
  isMinimized?: boolean;
  positionKey: string;
  onClose: () => void;
  onFocus: () => void;
  onMinimize: () => void;
  zIndex: number;
  onOpenSource: (page?: number) => void;
  onQuiz: () => void;
  onMarkStudied: () => void;
}): JSX.Element {
  const { material, section } = state;
  const hasOfficialWorkbookContent = hasOfficialWorkbookBlocks(section);

  return (
    <FloatingWindowFrame
      defaultPosition={defaultPosition}
      eyebrow={material.file_name}
      isActive={isActive}
      isMinimized={isMinimized}
      kind="study"
      positionKey={positionKey}
      title={section.normalized_title}
      zIndex={zIndex}
      onClose={onClose}
      onFocus={onFocus}
      onMinimize={onMinimize}
    >
      <section className="study-section-modal study-section-modal-floating" aria-label="Study section">
        <p className="subtle">{section.page_start ? `page ${section.page_start}` : "source page available"}</p>
        {hasOfficialWorkbookContent ? (
          <OfficialWorkbookBlocks section={section} onOpenSource={onOpenSource} onQuiz={onQuiz} />
        ) : (
          <>
            <div className="study-summary-callout">
              <span className="study-callout-label">Exam summary</span>
              <p className="section-summary">{section.summary}</p>
            </div>
            <div className="study-detail-grid study-detail-grid-pro">
              <StudyCollection title="Key concepts" values={section.key_points} variant="list" />
              <StudyCollection title="Must memorize" values={section.memorize_keywords} variant="chips" />
              <StudyCollection title="Syntax / formulas / rules" values={section.memorize_functions_or_formulas} variant="code" />
              <StudyCollection title="Common traps" values={section.traps} variant="list" tone="warn" />
              <StudyCollection title="Likely exam angles" values={deriveExamAngles(section)} variant="list" tone="accent" />
            </div>
          </>
        )}
        <div className="section-quiz-modal-footer">
          <button className="secondary-button" onClick={() => onOpenSource()} type="button">Open source</button>
          <button className="primary-button" disabled={!section.quiz_ready} onClick={onQuiz} type="button">Quiz this section</button>
          <button className="secondary-button" onClick={onMarkStudied} type="button">
            {section.studied_status === "studied" ? "Mark unstudied" : "Mark studied"}
          </button>
        </div>
      </section>
    </FloatingWindowFrame>
  );
}

function OfficialWorkbookBlocks({
  section,
  onOpenSource,
  onQuiz
}: {
  section: MaterialStudySection;
  onOpenSource: (page?: number) => void;
  onQuiz: () => void;
}): JSX.Element | null {
  const originalContent = section.original_book_content;
  const keyConceptItems = originalContent?.key_concepts?.length
    ? originalContent.key_concepts
    : originalItemsFromLines("Original Key Concepts", section.workbook_key_concepts ?? [], "key-concepts");
  const moduleQuizItems = originalContent?.module_quiz?.length
    ? originalContent.module_quiz
    : originalItemsFromLines("Original Module Quiz", section.workbook_module_quiz ?? [], "module-quiz");
  const answerItems = originalContent?.answers?.length
    ? originalContent.answers
    : originalItemsFromLines("Original Answer Key", section.workbook_answer_key ?? [], "answers");
  const tabs = [
    keyConceptItems.length
      ? { id: "key-concepts", label: "Key Concepts", title: "Original Key Concepts", items: keyConceptItems, tone: "accent" as const }
      : null,
    moduleQuizItems.length
      ? { id: "module-quiz", label: "Module Quiz", title: "Original Module Quiz", items: moduleQuizItems, tone: "neutral" as const }
      : null,
    answerItems.length
      ? { id: "answers", label: "Answers", title: "Original Answer Key", items: answerItems, tone: "warn" as const }
      : null
  ].filter((tab): tab is { id: string; label: string; title: string; items: OriginalBookItem[]; tone: "neutral" | "accent" | "warn" } => Boolean(tab));
  const [activeTabId, setActiveTabId] = useState<string>(tabs[0]?.id ?? "key-concepts");
  const activeTab = tabs.find((tab) => tab.id === activeTabId) ?? tabs[0];

  if (!activeTab) {
    return null;
  }

  return (
    <section className="official-workbook-blocks" aria-label="Official workbook material">
      <div className="official-workbook-heading">
        <span className="study-callout-label">Original from Book</span>
        <h3>Book-provided study blocks</h3>
        <p className="subtle">Exact source content is preserved here. AI-generated study help is separated below.</p>
      </div>
      <div className="official-workbook-tabs" role="tablist" aria-label="Official workbook blocks">
        {tabs.map((tab) => (
          <button
            aria-selected={tab.id === activeTab.id}
            className={`official-workbook-tab${tab.id === activeTab.id ? " official-workbook-tab-active" : ""}`}
            key={tab.id}
            onClick={() => setActiveTabId(tab.id)}
            role="tab"
            type="button"
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div role="tabpanel">
        <WorkbookItemBlock title={activeTab.title} items={activeTab.items} tone={activeTab.tone} />
      </div>
      <LayeredStudyEnhancements section={section} onOpenSource={onOpenSource} onQuiz={onQuiz} />
    </section>
  );
}

function originalItemsFromLines(title: string, lines: string[], idPrefix: string): OriginalBookItem[] {
  const cleanLines = lines.map((line) => line.trim()).filter(Boolean);
  if (!cleanLines.length) {
    return [];
  }
  return [
    {
      item_id: `${idPrefix}-fallback`,
      title,
      content: cleanLines.join("\n"),
      source_pages: [],
      original_order: 1,
      content_origin: "original_book",
      source_block_ids: []
    }
  ];
}

function WorkbookItemBlock({
  title,
  items,
  tone = "neutral"
}: {
  title: string;
  items: OriginalBookItem[];
  tone?: "neutral" | "accent" | "warn";
}): JSX.Element | null {
  if (!items.length) {
    return null;
  }

  return (
    <article className={`workbook-text-block workbook-text-block-${tone}`}>
      <div className="workbook-text-header">
        <h4>{title}</h4>
        <span className="origin-badge">Original from Book</span>
      </div>
      <div className="workbook-text-lines">
        {items.map((item) => (
          <section className="original-book-item" key={item.item_id}>
            <div className="original-book-item-meta">
              <strong>{item.title}</strong>
              {item.source_pages.length ? (
                <span className="source-page-badge">
                  page{item.source_pages.length > 1 ? "s" : ""} {formatPageRange(item.source_pages)}
                </span>
              ) : null}
            </div>
            {item.content.split("\n").map((line, index) => (
              <p key={`${item.item_id}-${index}`}>{line}</p>
            ))}
          </section>
        ))}
      </div>
    </article>
  );
}

function LayeredStudyEnhancements({
  section,
  onOpenSource,
  onQuiz
}: {
  section: MaterialStudySection;
  onOpenSource: (page?: number) => void;
  onQuiz: () => void;
}): JSX.Element | null {
  const learningOutcomes = section.learning_outcomes ?? [];
  const concepts = section.concepts ?? [];
  const formulas = section.formulas ?? [];
  const flashcards = section.flashcards ?? [];
  const flashcardCoverage = buildFlashcardCoverageByOutcome(learningOutcomes, concepts, flashcards);
  const [savedFormulaFlashcards, setSavedFormulaFlashcards] = useState<Set<string>>(() => new Set());

  function handleCreateFormulaFlashcard(formula: StudyFormulaCard): void {
    if (saveFormulaFlashcardToLocalStorage(formula)) {
      setSavedFormulaFlashcards((current) => new Set(current).add(formula.formula_id));
    }
  }

  if (!learningOutcomes.length && !concepts.length && !formulas.length && !flashcards.length) {
    return null;
  }

  return (
    <section className="study-enhancement-layer" aria-label="AI-enhanced study layers">
      <div className="official-workbook-heading">
        <span className="study-callout-label">AI-Generated Study Layer</span>
        <h3>Practice and review tools</h3>
        <p className="subtle">These cards are generated from the original book blocks and never replace them.</p>
      </div>
      <div className="study-detail-grid study-detail-grid-pro">
        {learningOutcomes.length ? (
          <section className="study-panel study-panel-accent">
            <h4>Learning outcomes</h4>
            <div className="learning-outcome-list">
              {learningOutcomes.slice(0, 6).map((outcome) => (
                <details key={outcome.outcome_id}>
                  <summary>
                    <span>{outcome.outcome_title}</span>
                    <span className="origin-badge">{formatOrigin(outcome.content_origin)}</span>
                  </summary>
                  {outcome.concepts.map((concept) => (
                    <p key={concept.concept_id}>{concept.simplified_explanation || concept.title}</p>
                  ))}
                </details>
              ))}
            </div>
          </section>
        ) : null}
        {concepts.length ? (
          <section className="study-panel">
            <h4>Concept cards</h4>
            <div className="concept-card-stack">
              {concepts.slice(0, 4).map((concept) => (
                <article className="concept-mini-card" key={concept.concept_id}>
                  <div>
                    <strong>{concept.title}</strong>
                    <span className="source-page-badge">{concept.learning_outcome}</span>
                  </div>
                  <p>{concept.simplified_explanation}</p>
                  {concept.key_terms.length ? (
                    <div className="study-chip-list study-chip-list-compact">
                      {concept.key_terms.slice(0, 5).map((term) => (
                        <span className="study-keyword-chip" key={`${concept.concept_id}-${term}`}>{term}</span>
                      ))}
                    </div>
                  ) : null}
                </article>
              ))}
            </div>
          </section>
        ) : null}
        {formulas.length ? (
          <section className="study-panel">
            <h4>Formula / rule cards</h4>
            <div className="formula-card-stack">
              {formulas.slice(0, 5).map((formula) => (
                <FormulaStudyCard
                  formula={formula}
                  isSaved={savedFormulaFlashcards.has(formula.formula_id)}
                  key={formula.formula_id}
                  onCreateFlashcard={handleCreateFormulaFlashcard}
                  onOpenSource={onOpenSource}
                  onPractice={onQuiz}
                />
              ))}
            </div>
          </section>
        ) : null}
        {flashcards.length ? (
          <section className="study-panel study-panel-warn">
            <h4>Flashcards due</h4>
            <p className="subtle">{flashcards.length} generated from original source blocks.</p>
            {flashcardCoverage.length ? (
              <div className="flashcard-coverage-list" aria-label="Flashcard coverage by learning outcome">
                <h5>Flashcard coverage by LO</h5>
                {flashcardCoverage.map((item) => (
                  <div className="flashcard-coverage-row" key={item.id}>
                    <span>{item.label}</span>
                    <strong>{item.count} / {MIN_FLASHCARDS_PER_LEARNING_OUTCOME} cards</strong>
                    {item.needsMoreSource ? <span className="origin-badge">Needs more source</span> : null}
                  </div>
                ))}
              </div>
            ) : null}
            <div className="concept-card-stack">
              {flashcards.slice(0, 3).map((flashcard) => (
                <article className="concept-mini-card" key={flashcard.flashcard_id}>
                  <strong>{flashcard.front}</strong>
                  <p>{flashcard.back_concise?.trim() || flashcard.back}</p>
                  <span className="origin-badge">{formatOrigin(flashcard.content_origin)}</span>
                </article>
              ))}
            </div>
          </section>
        ) : null}
      </div>
    </section>
  );
}

function FormulaStudySessionPage({
  material,
  formulas,
  onCreateFlashcard,
  onOpenSource,
  onPractice
}: {
  material: MaterialRecord;
  formulas: StudyFormulaCard[];
  onCreateFlashcard: (formula: StudyFormulaCard) => void;
  onOpenSource: (formula: StudyFormulaCard) => void;
  onPractice: (formula: StudyFormulaCard) => void;
}): JSX.Element {
  const formulasByReading = groupFormulasByReading(formulas);
  return (
    <section className="formula-study-session" aria-label="Formulas study session page">
      <div className="official-workbook-heading">
        <span className="study-callout-label">Official formula sheet / extracted formulas</span>
        <h3>Official formula sheet</h3>
        <p className="subtle">
          Formulas extracted from {material.display_name || material.file_name}, grouped by reading and linked back to source pages.
        </p>
      </div>
      {formulasByReading.map((group) => (
        <section className="formula-reading-group" key={group.label}>
          <div className="section-header section-header-compact">
            <div>
              <h4>{group.label}</h4>
              <p className="subtle">{group.formulas.length} official formula{group.formulas.length === 1 ? "" : "s"}</p>
            </div>
          </div>
          <div className="formula-card-stack">
            {group.formulas.map((formula) => (
              <FormulaStudyCard
                formula={formula}
                isSaved={false}
                key={formula.formula_id}
                onCreateFlashcard={onCreateFlashcard}
                onOpenSource={() => onOpenSource(formula)}
                onPractice={() => onPractice(formula)}
              />
            ))}
          </div>
        </section>
      ))}
      {formulasByReading.length === 0 ? (
        <article className="course-empty-card">
          <h3>No formulas extracted yet</h3>
          <p>Reprocess the book to detect the official formula appendix.</p>
        </article>
      ) : null}
    </section>
  );
}

function FormulaStudyCard({
  formula,
  isSaved,
  onCreateFlashcard,
  onOpenSource,
  onPractice
}: {
  formula: StudyFormulaCard;
  isSaved: boolean;
  onCreateFlashcard: (formula: StudyFormulaCard) => void;
  onOpenSource: (page?: number) => void;
  onPractice: () => void;
}): JSX.Element {
  const variables = Object.entries(formula.variables_json ?? {});
  const displayName = formula.formula_name || "Formula";
  const cropPath = formula.source_image_crop_path ?? "";
  const canRenderCrop = cropPath.startsWith("/") || cropPath.startsWith("data:image");
  return (
    <article className="formula-study-card">
      <div className="formula-card-header">
        <div>
          <span className="study-callout-label">{formatOrigin(formula.content_origin)}</span>
          <h5>{displayName}</h5>
        </div>
        {formula.source_page ? <span className="source-page-badge">page {formula.source_page}</span> : null}
      </div>
      <div className="formula-metadata-row" aria-label={`${displayName} metadata`}>
        {formula.reading_number ? <span className="origin-badge">Reading {formula.reading_number}</span> : null}
        {formula.formula_section_page ? (
          <span className="origin-badge">Formula source page {formula.formula_section_page}</span>
        ) : null}
        {formula.parse_confidence ? (
          <span className="origin-badge">{formatFormulaConfidence(formula.parse_confidence)} confidence</span>
        ) : null}
        {formula.needs_review ? <span className="origin-badge warning-badge">Needs review</span> : null}
      </div>
      <code className="formula-expression">{formula.formula_latex || formula.formula_text}</code>
      {formula.source_image_crop_path && canRenderCrop ? (
        <img
          alt={`${displayName} source crop`}
          className="formula-source-crop"
          src={formula.source_image_crop_path}
        />
      ) : null}
      {formula.source_image_crop_path && !canRenderCrop ? (
        <p className="subtle">Formula image crop preserved for source review.</p>
      ) : null}
      {variables.length ? (
        <dl className="formula-variable-list" aria-label={`${displayName} variables`}>
          {variables.map(([name, meaning]) => (
            <div key={name}>
              <dt>{name}</dt>
              <dd>{meaning}</dd>
            </div>
          ))}
        </dl>
      ) : null}
      {formula.usage_note ? <p className="subtle">{formula.usage_note}</p> : null}
      {formula.example_if_available ? (
        <p className="formula-example">{formula.example_if_available}</p>
      ) : null}
      <div className="formula-action-row">
        <button className="secondary-button" onClick={onPractice} type="button">Practice Calculation</button>
        <button className="secondary-button" onClick={() => onCreateFlashcard(formula)} type="button">
          {isSaved ? "Flashcard Added" : "Create Flashcard"}
        </button>
        <button className="secondary-button" onClick={() => onOpenSource(formula.source_page ?? undefined)} type="button">
          Open Source Page
        </button>
      </div>
    </article>
  );
}

function formulaFlashcardStorageKey(courseId: string): string {
  return `exam-prep-flashcard-custom:${courseId}`;
}

function saveFormulaFlashcardToLocalStorage(formula: StudyFormulaCard): boolean {
  const courseId = formula.course_id;
  if (!courseId || typeof window === "undefined") {
    return false;
  }
  const flashcard = buildFormulaFlashcard(formula);
  const storageKey = formulaFlashcardStorageKey(courseId);
  let existing: StudyFlashcard[] = [];
  try {
    const raw = window.localStorage.getItem(storageKey);
    existing = raw ? (JSON.parse(raw) as StudyFlashcard[]) : [];
  } catch {
    existing = [];
  }
  const next = existing.some((card) => card.flashcard_id === flashcard.flashcard_id)
    ? existing.map((card) => card.flashcard_id === flashcard.flashcard_id ? flashcard : card)
    : [flashcard, ...existing];
  window.localStorage.setItem(storageKey, JSON.stringify(next));
  return true;
}

function buildFormulaFlashcard(formula: StudyFormulaCard): StudyFlashcard {
  const formulaName = formula.formula_name || "this formula";
  return {
    flashcard_id: `formula-${formula.formula_id}`,
    course_id: formula.course_id,
    material_id: formula.material_id,
    module_id: formula.module_id,
    learning_outcome_id: null,
    concept_id: formula.concept_id,
    formula_id: formula.formula_id,
    front: `What is the formula for ${formulaName}?`,
    back: formula.formula_text,
    back_concise: formula.formula_text,
    card_type: "formula",
    source_page: formula.source_page,
    source_excerpt: formula.source_excerpt || formula.formula_text,
    difficulty: "medium",
    confidence_group: "new",
    interval_days: 0,
    ease_factor: 2.5,
    repetitions: 0,
    due_at: null,
    last_reviewed_at: null,
    archived: false,
    content_origin: "ai_generated_from_original"
  };
}

type FlashcardCoverageItem = {
  id: string;
  label: string;
  count: number;
  needsMoreSource: boolean;
};

function mergeFlashcardCoverageRows(
  rows: Array<FlashcardCoverageItem & { cardIds: Set<string> }>
): FlashcardCoverageItem[] {
  const byLabel = new Map<string, FlashcardCoverageItem & { cardIds: Set<string> }>();
  for (const row of rows) {
    const key = flashcardCoverageRowKey(row.label);
    const existing = byLabel.get(key);
    if (!existing) {
      byLabel.set(key, {
        ...row,
        id: key,
        label: compactLearningOutcomeLabel(row.label),
        cardIds: new Set(row.cardIds)
      });
      continue;
    }
    for (const cardId of row.cardIds) {
      existing.cardIds.add(cardId);
    }
    existing.count = existing.cardIds.size;
    existing.needsMoreSource = existing.needsMoreSource || row.needsMoreSource;
  }

  return Array.from(byLabel.values()).map(({ cardIds, ...row }) => ({
    ...row,
    count: cardIds.size
  }));
}

function flashcardCoverageRowKey(label: string): string {
  const compact = compactLearningOutcomeLabel(label);
  const loMatch = compact.match(/\bLO\s*(\d+)\.([a-z])\b/i);
  if (loMatch) {
    return `lo-${loMatch[1]}.${loMatch[2].toLowerCase()}`;
  }
  return compact.trim().replace(/\s+/g, " ").toLowerCase();
}

function buildFlashcardCoverageByOutcome(
  learningOutcomes: StudyLearningOutcome[],
  concepts: StudyConceptCard[],
  flashcards: StudyFlashcard[]
): FlashcardCoverageItem[] {
  if (!flashcards.length) {
    return [];
  }

  const conceptById = new Map(concepts.map((concept) => [concept.concept_id, concept]));

  if (learningOutcomes.length) {
    const rows = learningOutcomes.map((outcome) => {
      const matchIds = new Set<string>([
        outcome.outcome_id,
        outcome.outcome_title,
        ...outcome.related_original_key_concept_ids
      ].filter(Boolean));
      for (const concept of outcome.concepts) {
        matchIds.add(concept.concept_id);
        if (concept.related_original_key_concept_id) {
          matchIds.add(concept.related_original_key_concept_id);
        }
      }
      const matchingCards = flashcards.filter((card) => {
        const linkedConcept = card.concept_id ? conceptById.get(card.concept_id) : null;
        return (
          Boolean(card.learning_outcome_id && matchIds.has(card.learning_outcome_id)) ||
          Boolean(card.concept_id && matchIds.has(card.concept_id)) ||
          Boolean(linkedConcept?.related_original_key_concept_id && matchIds.has(linkedConcept.related_original_key_concept_id))
        );
      });

      return {
        id: outcome.outcome_id,
        label: compactLearningOutcomeLabel(outcome.outcome_title),
        count: matchingCards.length,
        cardIds: new Set(matchingCards.map((card) => card.flashcard_id)),
        needsMoreSource: matchingCards.length < MIN_FLASHCARDS_PER_LEARNING_OUTCOME
      };
    });
    return mergeFlashcardCoverageRows(rows);
  }

  const rows = concepts.map((concept) => {
    const matchIds = new Set<string>([concept.concept_id, concept.related_original_key_concept_id ?? ""].filter(Boolean));
    const matchingCards = flashcards.filter((card) => {
      return (
        Boolean(card.concept_id && matchIds.has(card.concept_id)) ||
        Boolean(card.learning_outcome_id && matchIds.has(card.learning_outcome_id))
      );
    });
    return {
      id: concept.concept_id,
      label: compactLearningOutcomeLabel(concept.learning_outcome || concept.title),
      count: matchingCards.length,
      cardIds: new Set(matchingCards.map((card) => card.flashcard_id)),
      needsMoreSource: matchingCards.length < MIN_FLASHCARDS_PER_LEARNING_OUTCOME
    };
  });
  return mergeFlashcardCoverageRows(rows);
}

function compactLearningOutcomeLabel(label: string): string {
  const loMatch = label.match(/\bLO\s*(\d+)\s*\.?\s*([a-z])\b/i);
  if (loMatch) {
    return `LO ${loMatch[1]}.${loMatch[2].toLowerCase()}`;
  }
  return label;
}

function formatOrigin(origin: string): string {
  if (origin === "original_book") {
    return "Original from Book";
  }
  if (origin === "ai_generated_from_original") {
    return "AI-Generated from Original";
  }
  return "AI-Generated";
}

function formatFormulaConfidence(confidence: string): string {
  return confidence.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatPageRange(pages: number[]): string {
  if (!pages.length) {
    return "";
  }
  const sorted = Array.from(new Set(pages)).sort((a, b) => a - b);
  if (sorted.length === 1) {
    return String(sorted[0]);
  }
  return `${sorted[0]}-${sorted[sorted.length - 1]}`;
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
            <span className="study-keyword-chip" key={value}>{value}</span>
          ))}
        </div>
      ) : null}
      {variant === "code" ? (
        <div className="study-code-stack">
          {unique.map((value) => (
            <code className="study-code-card" key={value}>{value}</code>
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
  return [
    section.key_points[0] ? `Define or recognize ${section.normalized_title}.` : "",
    section.memorize_functions_or_formulas[0] ? "Apply the rule or syntax in a short example." : "",
    section.traps[0] ? `Avoid this trap: ${section.traps[0]}` : "",
    section.memorize_keywords[0] ? `Compare ${section.memorize_keywords[0]} with nearby concepts.` : ""
  ].filter(Boolean);
}

function getFloatingWindowPosition(kind: FloatingWindowKind, mode: "free" | "arranged"): { x: number; y: number } {
  if (mode === "arranged") {
    if (kind === "study") {
      return { x: 28, y: 92 };
    }
    if (kind === "source") {
      return { x: 560, y: 92 };
    }
    return { x: 280, y: 180 };
  }
  if (kind === "study") {
    return { x: 180, y: 96 };
  }
  if (kind === "source") {
    return { x: 260, y: 72 };
  }
  return { x: 260, y: 120 };
}

function getTopOpenWindow(
  openWindows: Record<FloatingWindowKind, boolean>,
  windowOrder: Record<FloatingWindowKind, number>
): FloatingWindowKind | null {
  return (Object.keys(openWindows) as FloatingWindowKind[])
    .filter((kind) => openWindows[kind])
    .sort((left, right) => windowOrder[right] - windowOrder[left])[0] ?? null;
}

function cleanStudyList(values: string[]): string[] {
  return Array.from(
    new Set(
      values
        .map((value) => value.replace(/\s+/g, " ").trim())
        .filter(Boolean)
    )
  );
}

function backendStudyGroupId(groupId?: string | null): string | null {
  if (!groupId || groupId === ALL_SECTIONS_GROUP_ID || groupId === FORMULAS_GROUP_ID) {
    return null;
  }
  return groupId;
}

function isBackendFormulaGroup(group: MaterialStudyGroup): boolean {
  const groupId = group.group_id.toLowerCase();
  const title = normalizeFormulaGroupText(group.title);
  return (
    groupId.endsWith("-formula") ||
    groupId.endsWith("-formulas") ||
    groupId.includes("formula") ||
    groupId.includes("formulas") ||
    title === "formula" ||
    title === "formulas" ||
    title.startsWith("formulas ") ||
    title.startsWith("formula ") ||
    title.includes(" formula ") ||
    title.includes("formula sheet") ||
    title.includes("official formula") ||
    title.includes("extracted formulas") ||
    title === "official formula sheet"
  );
}

function normalizeFormulaGroupText(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

function formulaBackendGroupId(groups: MaterialStudyGroup[], materialId: string): string {
  return groups.find(isBackendFormulaGroup)?.group_id ?? `${materialId}-formulas`;
}

function collectFormulaCardsFromStudy(study: MaterialStudyResponse | null): StudyFormulaCard[] {
  const formulas = study?.sections.flatMap((section) => section.formulas ?? []) ?? [];
  const seen = new Set<string>();
  return formulas.filter((formula) => {
    const key = formula.formula_id || `${formula.formula_name ?? "formula"}:${formula.formula_text}`;
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

function formatFormulaPageRange(formulas: StudyFormulaCard[]): string {
  const pages = formulas
    .map((formula) => formula.formula_section_page ?? formula.source_page)
    .filter((page): page is number => typeof page === "number" && Number.isFinite(page));
  if (!pages.length) {
    return "source pages";
  }
  const uniquePages = Array.from(new Set(pages)).sort((left, right) => left - right);
  if (uniquePages.length === 1) {
    return `page ${uniquePages[0]}`;
  }
  return `pages ${uniquePages[0]}-${uniquePages[uniquePages.length - 1]}`;
}

function groupFormulasByReading(formulas: StudyFormulaCard[]): Array<{ label: string; formulas: StudyFormulaCard[] }> {
  const groups = new Map<string, StudyFormulaCard[]>();
  formulas.forEach((formula) => {
    const label = formula.reading_number ? `Reading ${formula.reading_number}` : "Unmatched formulas";
    groups.set(label, [...(groups.get(label) ?? []), formula]);
  });
  return Array.from(groups.entries())
    .sort(([leftLabel], [rightLabel]) => {
      const leftNumber = Number(leftLabel.match(/\d+/)?.[0] ?? Number.MAX_SAFE_INTEGER);
      const rightNumber = Number(rightLabel.match(/\d+/)?.[0] ?? Number.MAX_SAFE_INTEGER);
      return leftNumber - rightNumber || leftLabel.localeCompare(rightLabel);
    })
    .map(([label, groupFormulas]) => ({
      label,
      formulas: groupFormulas.sort((left, right) =>
        (left.source_page ?? left.formula_section_page ?? 0) - (right.source_page ?? right.formula_section_page ?? 0)
      )
    }));
}

function findFormulaPracticeSection(
  study: MaterialStudyResponse | null,
  formula?: StudyFormulaCard
): MaterialStudySection | null {
  const sections = study?.sections ?? [];
  if (!sections.length) {
    return null;
  }
  if (!formula) {
    return sections.find((section) => section.quiz_ready) ?? sections[0] ?? null;
  }
  return (
    sections.find((section) => (section.formulas ?? []).some((item) => item.formula_id === formula.formula_id) && section.quiz_ready) ??
    sections.find((section) => section.quiz_ready) ??
    sections[0] ??
    null
  );
}

function buildFormulaSourceSection(
  material: MaterialRecord,
  study: MaterialStudyResponse | null,
  formula?: StudyFormulaCard
): MaterialStudySection {
  const matchedSection = findFormulaPracticeSection(study, formula);
  const sourcePage = formula?.source_page ?? formula?.formula_section_page ?? matchedSection?.page_start ?? null;
  const formulaTitle = formula?.formula_name || "Formulas";
  return {
    section_id: formula ? `formula-${formula.formula_id}` : "formulas-session-source",
    material_id: material.material_id,
    parent_group_id: FORMULAS_GROUP_ID,
    title: formulaTitle,
    normalized_title: formulaTitle,
    page_start: sourcePage,
    page_end: sourcePage,
    source_anchor: `${material.file_name} | ${formulaTitle}`,
    summary: formula?.source_excerpt || formula?.formula_text || "Official formula sheet / extracted formulas",
    key_points: formula ? [formula.formula_text] : [],
    memorize_keywords: formula ? Object.keys(formula.variables_json ?? {}) : [],
    memorize_functions_or_formulas: formula ? [formula.formula_text] : [],
    traps: [],
    workbook_key_concepts: [],
    workbook_module_quiz: [],
    workbook_answer_key: [],
    original_book_content: matchedSection?.original_book_content,
    learning_outcomes: matchedSection?.learning_outcomes ?? [],
    concepts: matchedSection?.concepts ?? [],
    formulas: formula ? [formula] : collectFormulaCardsFromStudy(study),
    flashcards: [],
    due_flashcard_count: 0,
    mastery_percent: 0,
    weakest_concepts: [],
    difficulty: "medium",
    studied_status: "not_started",
    quiz_ready: Boolean(matchedSection?.quiz_ready),
    display_order: matchedSection?.display_order ?? 0,
    enrichment_status: matchedSection?.enrichment_status ?? "completed",
    source_ids: formula ? [formula.formula_id] : matchedSection?.source_ids ?? [],
  };
}

function formatGroupPageRange(group: MaterialStudyGroup): string {
  if (group.page_start && group.page_end && group.page_start !== group.page_end) {
    return `pages ${group.page_start}-${group.page_end}`;
  }
  if (group.page_start) {
    return `page ${group.page_start}`;
  }
  return "study module";
}

function formatSectionPageRange(section: MaterialStudySection): string {
  if (section.page_start && section.page_end && section.page_start !== section.page_end) {
    return `pages ${section.page_start}-${section.page_end}`;
  }
  if (section.page_start) {
    return `page ${section.page_start}`;
  }
  return "source page available";
}

function buildMaterialFileUrl(materialId: string, page: number): string {
  return `/api/v1/materials/${encodeURIComponent(materialId)}/file#page=${page}`;
}

function bookInitials(material: MaterialRecord): string {
  const label = material.display_name || material.file_name;
  return label
    .replace(/\.[^.]+$/, "")
    .split(/\s|-/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("") || "B";
}

export function SectionQuizModal({
  courseId,
  state,
  onClose,
  floating = false,
  defaultPosition = getFloatingWindowPosition("quiz", "free"),
  isActive = true,
  isMinimized = false,
  positionKey = "default",
  zIndex = WINDOW_BASE_Z_INDEX,
  onFocus = () => undefined,
  onMinimize = () => undefined
}: {
  courseId: string;
  state: QuizModalState;
  onClose: () => void;
  floating?: boolean;
  defaultPosition?: { x: number; y: number };
  isActive?: boolean;
  isMinimized?: boolean;
  positionKey?: string;
  zIndex?: number;
  onFocus?: () => void;
  onMinimize?: () => void;
}): JSX.Element {
  const { selectedModuleId } = useCourseSelection();
  const searchParams = useSearchParams();
  const [questionCount, setQuestionCount] = useState<number>(3);
  const [questionTypes, setQuestionTypes] = useState<QuestionType[]>(["mcq"]);
  const [isGenerating, setIsGenerating] = useState<boolean>(false);
  const [isGrading, setIsGrading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [isExpanded, setIsExpanded] = useState<boolean>(false);
  const [activeJob, setActiveJob] = useState<QuizGenerationJobResponse | null>(null);
  const [quiz, setQuiz] = useState<QuizBundle | null>(null);
  const [answers, setAnswers] = useState<Record<string, QuizSubmissionAnswer>>({});
  const [gradeResult, setGradeResult] = useState<QuizGradeResponse | null>(null);
  const pollTimerRef = useRef<number | null>(null);
  const answeredEventRef = useRef<Set<string>>(new Set());
  const focusQuestionType = searchParams?.get("questionType");

  useEffect(() => {
    return () => {
      if (pollTimerRef.current !== null) {
        window.clearTimeout(pollTimerRef.current);
      }
    };
  }, []);

  function toggleType(type: QuestionType): void {
    setQuestionTypes((current) => {
      const next = current.includes(type) ? current.filter((item) => item !== type) : [...current, type];
      return next.length > 0 ? next : [type];
    });
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
      fireAndForget(trackActivityEvent({
        course_id: courseId,
        module_id: selectedModuleId,
        material_id: state.material.material_id,
        section_id: state.section.section_id,
        quiz_id: quiz?.quiz_id ?? null,
        question_id: questionId,
        question_type: question?.question_type ?? null,
        difficulty: question?.difficulty ?? null,
        event_type: "question_answered",
        metadata_json: {
          origin: "section_quiz_window",
          answer_field: field
        }
      }));
    }
  }

  function startPolling(jobId: string): void {
    if (pollTimerRef.current !== null) {
      window.clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
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
        pollTimerRef.current = window.setTimeout(() => {
          void pollJob(jobId);
        }, QUIZ_MODAL_POLL_MS);
        return;
      }
      setIsGenerating(false);
      if (job.status === "failed" || job.status === "cancelled") {
        setError(job.error_summary ?? `Quiz generation ${job.status}.`);
      } else if (job.status === "partial" && job.error_summary) {
        setError(job.error_summary);
      }
    } catch (generateError) {
      setIsGenerating(false);
      setError(generateError instanceof Error ? generateError.message : "Unable to load quiz progress.");
    }
  }

  async function handleGenerate(): Promise<void> {
    setIsGenerating(true);
    setError(null);
    setGradeResult(null);
    try {
      const response = await generateQuiz({
        course_id: courseId,
        module_id: selectedModuleId,
        query: focusQuestionType
          ? `Section practice: ${state.section.normalized_title}; emphasize ${focusQuestionType.replace(/_/g, " ")} questions`
          : `Section practice: ${state.section.normalized_title}`,
        question_count: questionCount,
        question_types: ["mcq"],
        retrieval_top_k: 6,
        selected_source_ids: state.section.source_ids,
        scope: scopeFromSection(courseId, state.material, state.section, selectedModuleId),
        client_request_id: `section-modal-${state.section.section_id}-${Date.now()}`
      });
      setActiveJob(null);
      setQuiz(null);
      setAnswers({});
      answeredEventRef.current.clear();
      startPolling(response.job_id);
    } catch (generateError) {
      setError(generateError instanceof Error ? generateError.message : "Unable to start section quiz.");
      setIsGenerating(false);
    }
  }

  async function handleGrade(): Promise<void> {
    if (!quiz) {
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
    } catch (gradeError) {
      setError(gradeError instanceof Error ? gradeError.message : "Unable to grade quiz.");
    } finally {
      setIsGrading(false);
    }
  }

  const modalClassName = `section-quiz-modal${quiz ? " section-quiz-modal-live" : ""}${isExpanded ? " section-quiz-modal-expanded" : ""}${floating ? " section-quiz-modal-floating" : ""}`;
  const modalContent = (
      <section
        className={modalClassName}
        role="dialog"
        aria-modal="true"
        aria-label="Quiz this section"
      >
        <div className="drawer-header">
          <div>
            <p className="eyebrow">{state.material.file_name}</p>
            <h2>Quiz this section</h2>
            <p>{state.section.normalized_title}</p>
            {focusQuestionType ? (
              <span className="quality-badge">Focus: {focusQuestionType.replace(/_/g, " ")}</span>
            ) : null}
          </div>
          <div className="action-row">
            <button className="secondary-button" onClick={() => setIsExpanded((current) => !current)} type="button">
              {isExpanded ? "Default size" : "Expand"}
            </button>
            <button className="secondary-button" onClick={onClose} type="button">Close</button>
          </div>
        </div>
        <div className="section-quiz-modal-body">
          <div className="two-column-grid">
            <label className="field">
              <span>Question count</span>
              <input type="number" min={1} max={10} value={questionCount} onChange={(event) => setQuestionCount(Number(event.target.value))} />
            </label>
            <div className="field">
              <span>Question format</span>
              <div className="chip-toggle-row">
                {(["mcq"] as const).map((type) => (
                  <button
                    aria-pressed={questionTypes.includes(type)}
                    className={`chip-toggle${questionTypes.includes(type) ? " chip-toggle-active" : ""}`}
                    key={type}
                    onClick={() => toggleType(type)}
                    type="button"
                  >
                    MCQ
                  </button>
                ))}
              </div>
            </div>
          </div>
          {activeJob ? (
            <div className="status-panel" aria-live="polite">
              <strong>Quiz job:</strong> {activeJob.status}
              <p className="subtle">
                {activeJob.progress.completed_questions} / {activeJob.progress.total_questions} questions ready
              </p>
              <p className="subtle">Auto-sized for the current quiz, and you can also resize this window manually.</p>
            </div>
          ) : null}
          {error ? <p className="error-text">{error}</p> : null}
          {!quiz ? (
            <div className="status-panel">
              <strong>Ready to generate</strong>
              <p className="subtle">The quiz will stay in this window so you can answer and grade it without losing context.</p>
            </div>
          ) : (
            <div className="section-quiz-preview-list">
              {quiz.questions.map((question, index) => (
                <article className="section-quiz-question-card" key={question.question_id}>
                  <div className="preview-header">
                    <strong>
                      Question {index + 1}: {question.concept}
                    </strong>
                    <span className="subtle">
                      MCQ
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
                  <p>{question.prompt}</p>
                  {question.question_type === "mcq" ? (
                    <div className="option-list">
                      {question.options.map((option) => (
                        <label className="option-card" key={option.option_id}>
                          <input
                            checked={answers[question.question_id]?.selected_option_id === option.option_id}
                            name={question.question_id}
                            onChange={(event) => updateAnswer(question.question_id, "selected_option_id", event.target.value)}
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
                        aria-label={`Section quiz answer for question ${index + 1}`}
                        className="text-area"
                        rows={4}
                        value={answers[question.question_id]?.answer_text ?? ""}
                        onChange={(event) => updateAnswer(question.question_id, "answer_text", event.target.value)}
                      />
                    </label>
                  )}
                </article>
                ))}
              </div>
            )}

          {gradeResult ? (
            <div className="section-quiz-review-list">
              {gradeResult.results.map((result) => (
                <article className="preview-item review-card review-card-compact" key={result.question_id}>
                  <div className="preview-header">
                    <strong>{cleanDisplayText(result.concept || "Question review")}</strong>
                    <span className={`result-badge ${result.is_correct ? "result-good" : "result-bad"}`}>
                      {result.is_correct ? "Correct" : "Incorrect"}
                    </span>
                  </div>
                  <p className="subtle">
                    Your answer: {result.submitted_answer || "No answer provided"}
                  </p>
                  <p className="subtle">
                    Correct answer: {result.correct_answer}
                  </p>
                  <p>{result.explanation}</p>
                </article>
              ))}
            </div>
          ) : null}
        </div>
        <div className="section-quiz-modal-footer">
          {!quiz ? (
            <>
              <button className="primary-button" disabled={isGenerating} onClick={() => void handleGenerate()} type="button">
                {isGenerating ? "Generating..." : "Generate quiz"}
              </button>
              <button className="secondary-button" onClick={onClose} type="button">Cancel</button>
            </>
          ) : (
            <>
              <button className="primary-button" disabled={isGrading} onClick={() => void handleGrade()} type="button">
                {isGrading ? "Scoring..." : "Grade quiz"}
              </button>
              <a
                className="secondary-button"
                href={`/courses/${encodeURIComponent(courseId)}/wrong-questions`}
              >
                Quiz/exam history
              </a>
              <button className="secondary-button" onClick={onClose} type="button">Close</button>
            </>
          )}
        </div>
      </section>
  );

  if (floating) {
    return (
      <FloatingWindowFrame
        defaultPosition={defaultPosition}
        eyebrow={state.material.file_name}
        isActive={isActive}
        isMinimized={isMinimized}
        kind="quiz"
        positionKey={positionKey}
        title="Quiz this section"
        zIndex={zIndex}
        onClose={onClose}
        onFocus={onFocus}
        onMinimize={onMinimize}
      >
        {modalContent}
      </FloatingWindowFrame>
    );
  }

  return (
    <div className="modal-backdrop" role="presentation">
      {modalContent}
    </div>
  );
}

export function saveOriginState(scopeKey: string, value: { materialId: string; sectionId: string; scrollY: number; query: string }): void {
  if (typeof window === "undefined") {
    return;
  }
  window.sessionStorage.setItem(`${MATERIALS_STATE_KEY}:${scopeKey}`, JSON.stringify(value));
}

function readOriginState(scopeKey: string): { materialId: string; sectionId: string; scrollY: number; query: string } | null {
  if (typeof window === "undefined") {
    return null;
  }
  const raw = window.sessionStorage.getItem(`${MATERIALS_STATE_KEY}:${scopeKey}`);
  if (!raw) {
    return null;
  }
  try {
    return JSON.parse(raw) as { materialId: string; sectionId: string; scrollY: number; query: string };
  } catch {
    return null;
  }
}

function statusLabel(record: MaterialRecord): string {
  return (record.processing_status ?? record.status).replace("_", " ");
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

function replaceSearchParams(
  router: ReturnType<typeof useRouter>,
  pathname: string | null,
  searchParams: ReturnType<typeof useSearchParams>,
  updates: Record<string, string | null>
): void {
  const params = new URLSearchParams(searchParams?.toString() ?? "");
  Object.entries(updates).forEach(([key, value]) => {
    if (!value) {
      params.delete(key);
      return;
    }
    params.set(key, value);
  });
  const target = params.toString() ? `${pathname ?? ""}?${params.toString()}` : (pathname ?? "");
  router.replace(target, { scroll: false });
}
