"use client";

import React from "react";
import type { FormEvent } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";

import {
  createCourse,
  createModule,
  deleteMaterial,
  fetchCourseMaterials,
  fetchMaterialPreview,
  fetchMaterialStudy,
  fetchMaterialStatus,
  markMaterialStudySection,
  reprocessMaterial,
  retryMaterialProcessing,
  startMaterialSectionQuiz,
  uploadMaterial
} from "@/lib/api";
import { useCourseSelection } from "@/components/shared/course-context";
import { SourceViewerPane, type SourceViewerState } from "@/components/shared/source-viewer";
import type {
  CourseMaterialsResponse,
  CourseLibraryItem,
  MaterialPreviewResponse,
  MaterialRecord,
  MaterialStudyGroup,
  MaterialStudyResponse,
  MaterialStudySection
} from "@/lib/schemas";

const supportedFormats = ["PDF", "DOCX", "PPTX", "TXT"];
const SECTION_PAGE_SIZE = 12;
const STATUS_POLL_MS = 1800;

export function MaterialsWorkspace(): JSX.Element {
  const {
    library,
    selectedCourseId,
    selectedModuleId,
    selectedCourse,
    selectedModule,
    refresh,
    setSelection
  } = useCourseSelection();
  const searchParams = useSearchParams();
  const routeParams = useParams<{ materialId?: string }>();
  const routeMaterialId = typeof routeParams?.materialId === "string" ? routeParams.materialId : null;
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [scopedMaterials, setScopedMaterials] = useState<CourseMaterialsResponse | null>(null);
  const [selectedMaterialId, setSelectedMaterialId] = useState<string | null>(null);
  const [study, setStudy] = useState<MaterialStudyResponse | null>(null);
  const [activeGroupId, setActiveGroupId] = useState<string | null>(null);
  const [preview, setPreview] = useState<MaterialPreviewResponse | null>(null);
  const [expandedSectionId, setExpandedSectionId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [isLoadingStudy, setIsLoadingStudy] = useState<boolean>(false);
  const [isStartingQuiz, setIsStartingQuiz] = useState<string | null>(null);
  const [reprocessingMaterialId, setReprocessingMaterialId] = useState<string | null>(null);
  const [courseForm, setCourseForm] = useState({
    course_code: "",
    display_name: "",
    description: ""
  });
  const [moduleForm, setModuleForm] = useState({
    module_number: "",
    display_name: "",
    description: ""
  });
  const statusPollRef = useRef<number | null>(null);

  useEffect(() => {
    void loadScopedMaterials();
    return () => clearStatusPoll();
  }, [selectedCourseId, selectedModuleId]);

  useEffect(() => {
    const materialId = routeMaterialId ?? searchParams?.get("materialId");
    if (materialId) {
      setSelectedMaterialId(materialId);
    }
  }, [routeMaterialId, searchParams]);

  useEffect(() => {
    if (!selectedMaterialId) {
      return;
    }
    if (searchParams?.get("page") || searchParams?.get("sourceId") || searchParams?.get("section")) {
      void handlePreview(selectedMaterialId);
    }
  }, [selectedMaterialId, searchParams]);

  useEffect(() => {
    if (!selectedMaterialId) {
      setStudy(null);
      setPreview(null);
      clearStatusPoll();
      return;
    }
    void loadStudy(selectedMaterialId, { offset: 0, groupId: activeGroupId });
  }, [selectedMaterialId, activeGroupId]);

  const selectedMaterial = useMemo(() => {
    const records = scopedMaterials?.records ?? [];
    return records.find((record) => record.material_id === selectedMaterialId) ?? study?.record ?? null;
  }, [scopedMaterials, selectedMaterialId, study]);

  async function loadScopedMaterials(): Promise<void> {
    clearStatusPoll();
    setStudy(null);
    setPreview(null);

    if (!selectedCourseId) {
      setScopedMaterials(null);
      setSelectedMaterialId(null);
      return;
    }

    try {
      const materials = await fetchCourseMaterials(selectedCourseId, selectedModuleId);
      setScopedMaterials(materials);
      setError(null);
      const requestedMaterialId = routeMaterialId ?? searchParams?.get("materialId");
      const nextMaterialId =
        requestedMaterialId ??
        selectedMaterialId ??
        materials.records[0]?.material_id ??
        null;
      setSelectedMaterialId(nextMaterialId);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Unable to load materials.");
      setScopedMaterials(null);
    }
  }

  async function loadStudy(
    materialId: string,
    options: { offset?: number; groupId?: string | null } = {}
  ): Promise<void> {
    setIsLoadingStudy(true);
    try {
      const response = await fetchMaterialStudy(materialId, {
        offset: options.offset ?? 0,
        limit: SECTION_PAGE_SIZE,
        groupId: options.groupId ?? null
      });
      setStudy(response);
      setError(null);
      if (isProcessing(response.record)) {
        startStatusPoll(response.record.material_id);
      } else {
        clearStatusPoll();
      }
    } catch (studyError) {
      setStudy(null);
      setError(studyError instanceof Error ? studyError.message : "Unable to load study material.");
    } finally {
      setIsLoadingStudy(false);
    }
  }

  function startStatusPoll(materialId: string): void {
    clearStatusPoll();
    statusPollRef.current = window.setTimeout(async () => {
      try {
        const status = await fetchMaterialStatus(materialId);
        setStudy((current) => current ? { ...current, record: status.record } : current);
        if (isProcessing(status.record)) {
          startStatusPoll(materialId);
        } else {
          await refresh();
          await loadScopedMaterials();
          await loadStudy(materialId, { offset: study?.offset ?? 0, groupId: activeGroupId });
        }
      } catch {
        clearStatusPoll();
      }
    }, STATUS_POLL_MS);
  }

  function clearStatusPoll(): void {
    if (statusPollRef.current !== null) {
      window.clearTimeout(statusPollRef.current);
      statusPollRef.current = null;
    }
  }

  async function handleUpload(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setError(null);

    if (!selectedCourseId) {
      setError("Choose a course before uploading material.");
      return;
    }
    if (!selectedFile) {
      setError("Choose a file before uploading.");
      return;
    }

    setIsUploading(true);
    try {
      const uploadResponse = await uploadMaterial(selectedCourseId, selectedFile, selectedModuleId);
      setSelectedFile(null);
      setSelectedMaterialId(uploadResponse.record.material_id);
      await refresh();
      await loadScopedMaterials();
      await loadStudy(uploadResponse.record.material_id);
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : "Upload failed.");
    } finally {
      setIsUploading(false);
    }
  }

  async function handleCreateCourse(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    try {
      await createCourse(courseForm);
      setCourseForm({ course_code: "", display_name: "", description: "" });
      await refresh();
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "Unable to create course.");
    }
  }

  async function handleCreateModule(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!selectedCourseId) {
      setError("Choose a course before creating a module.");
      return;
    }

    try {
      await createModule({
        course_id: selectedCourseId,
        ...moduleForm
      });
      setModuleForm({ module_number: "", display_name: "", description: "" });
      await refresh();
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "Unable to create module.");
    }
  }

  async function handleDelete(record: MaterialRecord): Promise<void> {
    const confirmed = window.confirm("Delete this material and its study breakdown?");
    if (!confirmed) {
      return;
    }
    try {
      await deleteMaterial(record.material_id);
      if (record.material_id === selectedMaterialId) {
        setSelectedMaterialId(null);
        setStudy(null);
      }
      await refresh();
      await loadScopedMaterials();
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "Unable to delete material.");
    }
  }

  async function handleRetry(materialId: string): Promise<void> {
    try {
      const status = await retryMaterialProcessing(materialId);
      setStudy((current) => current ? { ...current, record: status.record } : current);
      startStatusPoll(materialId);
    } catch (retryError) {
      setError(retryError instanceof Error ? retryError.message : "Unable to retry processing.");
    }
  }

  async function handleRegenerate(materialId: string): Promise<void> {
    if (reprocessingMaterialId === materialId) {
      return;
    }
    setReprocessingMaterialId(materialId);
    setIsLoadingStudy(true);
    try {
      await reprocessMaterial(materialId);
      const response = await fetchMaterialStudy(materialId);
      setStudy(response);
      setError(null);
    } catch (regenerateError) {
      setError(regenerateError instanceof Error ? regenerateError.message : "Unable to reprocess material.");
    } finally {
      setReprocessingMaterialId(null);
      setIsLoadingStudy(false);
    }
  }

  async function handlePreview(materialId: string): Promise<void> {
    try {
      setPreview(await fetchMaterialPreview(materialId, 0));
    } catch (previewError) {
      setError(previewError instanceof Error ? previewError.message : "Unable to load source preview.");
    }
  }

  async function handleMarkStudied(section: MaterialStudySection): Promise<void> {
    if (!study) {
      return;
    }
    try {
      const response = await markMaterialStudySection(
        study.record.material_id,
        section.section_id,
        section.studied_status !== "studied"
      );
      setStudy((current) => {
        if (!current) {
          return current;
        }
        const previousSection = current.sections.find(
          (item) => item.section_id === response.section.section_id
        );
        const previousStudied = previousSection?.studied_status === "studied";
        const nextStudied = response.section.studied_status === "studied";
        const studiedDelta = previousStudied === nextStudied ? 0 : nextStudied ? 1 : -1;
        const sections = current.sections.map((item) =>
          item.section_id === response.section.section_id ? response.section : item
        );
        return {
          ...current,
          sections,
          studied_sections: Math.max(0, current.studied_sections + studiedDelta)
        };
      });
    } catch (markError) {
      setError(markError instanceof Error ? markError.message : "Unable to update study status.");
    }
  }

  async function handleQuizSection(section: MaterialStudySection): Promise<void> {
    if (!study) {
      return;
    }
    setIsStartingQuiz(section.section_id);
    try {
      const response = await startMaterialSectionQuiz(study.record.material_id, section.section_id);
      navigateToQuizJob(response.job_id);
    } catch (quizError) {
      setError(quizError instanceof Error ? quizError.message : "Unable to start section quiz.");
      setIsStartingQuiz(null);
    }
  }

  async function loadNextPage(): Promise<void> {
    if (!study || !selectedMaterialId) {
      return;
    }
    const response = await fetchMaterialStudy(selectedMaterialId, {
      groupId: activeGroupId,
      offset: study.offset + study.limit,
      limit: SECTION_PAGE_SIZE
    });
    setStudy({
      ...response,
      sections: [...study.sections, ...response.sections],
      offset: 0,
      limit: study.sections.length + response.sections.length
    });
  }

  const metrics = study
    ? [
        { label: "Sections ready", value: `${study.ready_sections}/${study.total_sections}` },
        { label: "Studied", value: `${study.studied_sections}/${study.total_sections}` },
        { label: "Progress", value: `${study.record.processing_progress ?? 0}%` }
      ]
    : [
        { label: "Sections ready", value: "0/0" },
        { label: "Studied", value: "0/0" },
        { label: "Progress", value: "0%" }
      ];

  return (
    <div className="materials-study-layout">
      <aside className="materials-sidebar">
        <UploadPanel
          courseForm={courseForm}
          moduleForm={moduleForm}
          selectedCourse={selectedCourse?.display_name ?? null}
          selectedModule={selectedModule?.display_name ?? null}
          selectedCourseId={selectedCourseId}
          selectedFile={selectedFile}
          isUploading={isUploading}
          onCourseFormChange={setCourseForm}
          onModuleFormChange={setModuleForm}
          onCreateCourse={handleCreateCourse}
          onCreateModule={handleCreateModule}
          onFileChange={setSelectedFile}
          onUpload={handleUpload}
        />

        <MaterialsTree
          library={library?.courses ?? []}
          selectedMaterialId={selectedMaterialId}
          onSelectMaterial={setSelectedMaterialId}
          onSelectScope={(courseId, moduleId) => void setSelection(courseId, moduleId)}
        />
      </aside>

      <main className="materials-main-panel">
        {error ? (
          <div className="status-panel error-panel" aria-live="polite">
            <strong>Issue:</strong> {error}
          </div>
        ) : null}

        {!selectedMaterialId || !selectedMaterial ? (
          <EmptyStudyState />
        ) : (
          <>
            <MaterialStudyHeader
              material={study?.record ?? selectedMaterial}
              courseLabel={selectedCourse?.display_name ?? "Selected course"}
              moduleLabel={selectedModule?.display_name ?? null}
              isReprocessing={reprocessingMaterialId === selectedMaterial.material_id}
              onDelete={() => void handleDelete(study?.record ?? selectedMaterial)}
              onPreview={() => void handlePreview(selectedMaterial.material_id)}
              onRegenerate={() => void handleRegenerate(selectedMaterial.material_id)}
              onRetry={() => void handleRetry(selectedMaterial.material_id)}
            />

            <MaterialProcessingStatus record={study?.record ?? selectedMaterial} />

            <GroupSelector
              groups={study?.groups ?? []}
              activeGroupId={activeGroupId}
              onSelectGroup={setActiveGroupId}
            />

            {isLoadingStudy ? (
              <section className="study-empty-state">
                <h3>Preparing study sections</h3>
                <p>Loading the next set of section cards.</p>
              </section>
            ) : study && study.sections.length > 0 ? (
              <SectionGroupList
                expandedSectionId={expandedSectionId}
                isStartingQuiz={isStartingQuiz}
                material={study.record}
                sections={study.sections}
                onExpand={setExpandedSectionId}
                onMarkStudied={(section) => void handleMarkStudied(section)}
                onQuiz={(section) => void handleQuizSection(section)}
                sourceHrefForSection={(section) => buildSectionSourceHref(section)}
              />
            ) : (
              <NoSectionsState record={study?.record ?? selectedMaterial} onRetry={() => void handleRetry(selectedMaterial.material_id)} />
            )}

            {study?.has_more ? (
              <button className="secondary-button load-more-button" onClick={() => void loadNextPage()} type="button">
                Load more sections
              </button>
            ) : null}

            {preview ? (
              <SourcePreview
                page={searchParams?.get("page")}
                preview={preview}
                sectionId={searchParams?.get("section")}
                sourceId={searchParams?.get("sourceId")}
              />
            ) : null}
          </>
        )}
      </main>

      <aside className="materials-inspector">
        <section className="card compact-card">
          <h3>Study coverage</h3>
          <div className="metric-list">
            {metrics.map((metric) => (
              <div className="metric-line" key={metric.label}>
                <span>{metric.label}</span>
                <strong>{metric.value}</strong>
              </div>
            ))}
          </div>
        </section>
        <section className="card compact-card">
          <h3>Formats</h3>
          <div className="pill-row">
            {supportedFormats.map((format) => (
              <span className="pill" key={format}>
                {format}
              </span>
            ))}
          </div>
        </section>
      </aside>
    </div>
  );
}

function UploadPanel({
  courseForm,
  moduleForm,
  selectedCourse,
  selectedModule,
  selectedCourseId,
  selectedFile,
  isUploading,
  onCourseFormChange,
  onModuleFormChange,
  onCreateCourse,
  onCreateModule,
  onFileChange,
  onUpload
}: {
  courseForm: { course_code: string; display_name: string; description: string };
  moduleForm: { module_number: string; display_name: string; description: string };
  selectedCourse: string | null;
  selectedModule: string | null;
  selectedCourseId: string | null;
  selectedFile: File | null;
  isUploading: boolean;
  onCourseFormChange: React.Dispatch<React.SetStateAction<{ course_code: string; display_name: string; description: string }>>;
  onModuleFormChange: React.Dispatch<React.SetStateAction<{ module_number: string; display_name: string; description: string }>>;
  onCreateCourse: (event: FormEvent<HTMLFormElement>) => Promise<void>;
  onCreateModule: (event: FormEvent<HTMLFormElement>) => Promise<void>;
  onFileChange: (file: File | null) => void;
  onUpload: (event: FormEvent<HTMLFormElement>) => Promise<void>;
}): JSX.Element {
  return (
    <section className="materials-toolbox">
      <form className="compact-form" onSubmit={onUpload}>
        <h3>Upload</h3>
        <p className="subtle">
          {selectedCourse
            ? `${selectedCourse}${selectedModule ? ` · ${selectedModule}` : " · whole course"}`
            : "Choose or create a course first."}
        </p>
        <label className="field">
          <span>Document file</span>
          <input
            aria-label="Document file"
            type="file"
            accept=".pdf,.docx,.pptx,.txt"
            onChange={(event) => onFileChange(event.target.files?.[0] ?? null)}
          />
        </label>
        <button className="primary-button" disabled={isUploading || !selectedCourseId || !selectedFile} type="submit">
          {isUploading ? "Uploading..." : "Upload material"}
        </button>
      </form>

      <details className="compact-details">
        <summary>Add course</summary>
        <form className="compact-form" onSubmit={onCreateCourse}>
          <label className="field">
            <span>Course code</span>
            <input
              aria-label="Course code"
              value={courseForm.course_code}
              onChange={(event) => onCourseFormChange((current) => ({ ...current, course_code: event.target.value }))}
            />
          </label>
          <label className="field">
            <span>Name</span>
            <input
              aria-label="Course display name"
              value={courseForm.display_name}
              onChange={(event) => onCourseFormChange((current) => ({ ...current, display_name: event.target.value }))}
            />
          </label>
          <button className="secondary-button" type="submit">Create course</button>
        </form>
      </details>

      <details className="compact-details">
        <summary>Add module</summary>
        <form className="compact-form" onSubmit={onCreateModule}>
          <label className="field">
            <span>Module number</span>
            <input
              aria-label="Module number"
              value={moduleForm.module_number}
              onChange={(event) => onModuleFormChange((current) => ({ ...current, module_number: event.target.value }))}
            />
          </label>
          <label className="field">
            <span>Name</span>
            <input
              aria-label="Module display name"
              value={moduleForm.display_name}
              onChange={(event) => onModuleFormChange((current) => ({ ...current, display_name: event.target.value }))}
            />
          </label>
          <button className="secondary-button" disabled={!selectedCourseId} type="submit">Create module</button>
        </form>
      </details>
    </section>
  );
}

function MaterialsTree({
  library,
  selectedMaterialId,
  onSelectMaterial,
  onSelectScope
}: {
  library: CourseLibraryItem[];
  selectedMaterialId: string | null;
  onSelectMaterial: (materialId: string) => void;
  onSelectScope: (courseId: string, moduleId: string | null) => void;
}): JSX.Element {
  if (library.length === 0) {
    return (
      <section className="materials-tree">
        <h3>Materials</h3>
        <p className="subtle">Create a course, then upload a file to start studying.</p>
      </section>
    );
  }

  return (
    <section className="materials-tree">
      <h3>Materials</h3>
      {library.map((courseItem) => (
        <div className="tree-course" key={courseItem.course.course_id}>
          <button
            className="tree-scope-button"
            onClick={() => onSelectScope(courseItem.course.course_id, null)}
            type="button"
          >
            <strong>{courseItem.course.course_code}</strong>
            <span>{courseItem.course.display_name}</span>
          </button>
          <MaterialButtons
            materials={courseItem.root_materials}
            selectedMaterialId={selectedMaterialId}
            onSelectMaterial={onSelectMaterial}
          />
          {courseItem.modules.map((moduleItem) => (
            <div className="tree-module" key={moduleItem.module.module_id}>
              <button
                className="tree-scope-button"
                onClick={() => onSelectScope(courseItem.course.course_id, moduleItem.module.module_id)}
                type="button"
              >
                <strong>{moduleItem.module.module_number}</strong>
                <span>{moduleItem.module.display_name}</span>
              </button>
              <MaterialButtons
                materials={moduleItem.materials}
                selectedMaterialId={selectedMaterialId}
                onSelectMaterial={onSelectMaterial}
              />
            </div>
          ))}
        </div>
      ))}
    </section>
  );
}

function MaterialButtons({
  materials,
  selectedMaterialId,
  onSelectMaterial
}: {
  materials: MaterialRecord[];
  selectedMaterialId: string | null;
  onSelectMaterial: (materialId: string) => void;
}): JSX.Element {
  if (materials.length === 0) {
    return <p className="tree-empty subtle">No materials.</p>;
  }
  return (
    <div className="tree-material-list">
      {materials.map((material) => (
        <button
          className={`tree-material-button${material.material_id === selectedMaterialId ? " tree-material-active" : ""}`}
          key={material.material_id}
          onClick={() => onSelectMaterial(material.material_id)}
          type="button"
        >
          <span>{material.display_name || material.file_name}</span>
          <small>{materialStatusLabel(material)}</small>
        </button>
      ))}
    </div>
  );
}

function MaterialStudyHeader({
  material,
  isReprocessing,
  courseLabel,
  moduleLabel,
  onDelete,
  onPreview,
  onRegenerate,
  onRetry
}: {
  material: MaterialRecord;
  isReprocessing: boolean;
  courseLabel: string;
  moduleLabel: string | null;
  onDelete: () => void;
  onPreview: () => void;
  onRegenerate: () => void;
  onRetry: () => void;
}): JSX.Element {
  return (
    <section className="material-study-header">
      <div>
        <p className="eyebrow">{courseLabel}{moduleLabel ? ` · ${moduleLabel}` : ""}</p>
        <h2>{material.display_name || material.file_name}</h2>
        <p className="subtle">
          {material.page_count ? `${material.page_count} pages · ` : ""}
          {material.section_count} sections · {material.chunk_count} retrieval chunks
        </p>
      </div>
      <div className="action-row">
        {material.status === "failed" ? (
          <button className="secondary-button" onClick={onRetry} type="button">Retry</button>
        ) : null}
        <button className="secondary-button" onClick={onPreview} type="button">View source</button>
        <button className="secondary-button" disabled={isReprocessing} onClick={onRegenerate} type="button">
          {isReprocessing ? "Reprocessing..." : "Reprocess"}
        </button>
        <button className="secondary-button" onClick={onDelete} type="button">Delete</button>
      </div>
    </section>
  );
}

function MaterialProcessingStatus({ record }: { record: MaterialRecord }): JSX.Element {
  const progress = record.processing_progress ?? (record.status === "completed" ? 100 : 0);
  return (
    <section className="processing-strip">
      <div>
        <strong>{materialStatusLabel(record)}</strong>
        <span>
          Extraction {record.outline_status ?? "pending"} · Enrichment {record.enrichment_status ?? "pending"}
        </span>
      </div>
      <div className="processing-track" aria-hidden="true">
        <div className="processing-bar" style={{ width: `${Math.max(4, progress)}%` }} />
      </div>
      {record.error_message ? <p className="error-text">{record.error_message}</p> : null}
    </section>
  );
}

function GroupSelector({
  groups,
  activeGroupId,
  onSelectGroup
}: {
  groups: MaterialStudyGroup[];
  activeGroupId: string | null;
  onSelectGroup: (groupId: string | null) => void;
}): JSX.Element | null {
  if (groups.length <= 1) {
    return null;
  }
  return (
    <div className="group-selector">
      <button className={!activeGroupId ? "group-button group-button-active" : "group-button"} onClick={() => onSelectGroup(null)} type="button">
        All
      </button>
      {groups.map((group) => (
        <button
          className={activeGroupId === group.group_id ? "group-button group-button-active" : "group-button"}
          key={group.group_id}
          onClick={() => onSelectGroup(group.group_id)}
          type="button"
        >
          {group.title}
          <span>{group.studied_count}/{group.section_count}</span>
        </button>
      ))}
    </div>
  );
}

function SectionGroupList({
  material,
  sections,
  expandedSectionId,
  isStartingQuiz,
  onExpand,
  onMarkStudied,
  onQuiz,
  sourceHrefForSection
}: {
  material: MaterialRecord;
  sections: MaterialStudySection[];
  expandedSectionId: string | null;
  isStartingQuiz: string | null;
  onExpand: (sectionId: string | null) => void;
  onMarkStudied: (section: MaterialStudySection) => void;
  onQuiz: (section: MaterialStudySection) => void;
  sourceHrefForSection: (section: MaterialStudySection) => string;
}): JSX.Element {
  return (
    <section className="section-study-list">
      {sections.map((section) => (
        <SectionStudyCard
          expanded={expandedSectionId === section.section_id}
          isStartingQuiz={isStartingQuiz === section.section_id}
          key={section.section_id}
          material={material}
          section={section}
          onExpand={onExpand}
          onMarkStudied={onMarkStudied}
          onQuiz={onQuiz}
          sourceHref={sourceHrefForSection(section)}
        />
      ))}
    </section>
  );
}

function SectionStudyCard({
  material,
  section,
  expanded,
  isStartingQuiz,
  onExpand,
  onMarkStudied,
  onQuiz,
  sourceHref
}: {
  material: MaterialRecord;
  section: MaterialStudySection;
  expanded: boolean;
  isStartingQuiz: boolean;
  onExpand: (sectionId: string | null) => void;
  onMarkStudied: (section: MaterialStudySection) => void;
  onQuiz: (section: MaterialStudySection) => void;
  sourceHref: string;
}): JSX.Element {
  return (
    <article className="section-study-card">
      <div className="section-card-top">
        <div>
          <div className="section-meta-row">
            <span className={`difficulty-tag difficulty-${section.difficulty}`}>{section.difficulty}</span>
            {section.page_start ? <span className="subtle">page {section.page_start}</span> : null}
            {section.studied_status === "studied" ? <span className="studied-tag">studied</span> : null}
          </div>
          <h3>{section.normalized_title}</h3>
        </div>
        <div className="action-row">
          <button className="secondary-button" onClick={() => onExpand(expanded ? null : section.section_id)} type="button">
            {expanded ? "Collapse" : "Study section"}
          </button>
          <button className="primary-button" disabled={!section.quiz_ready || isStartingQuiz} onClick={() => onQuiz(section)} type="button">
            {isStartingQuiz ? "Starting..." : "Quiz this section"}
          </button>
        </div>
      </div>
      <p className="section-summary">{section.summary}</p>

      {expanded ? (
        <div className="expanded-study-view">
            <div className="study-detail-grid">
              <div className="study-detail-notes">
              <StudyList title="Key points" values={section.key_points} />
              <StudyList title="Memorize terms" values={section.memorize_keywords} />
              <StudyList title="Functions / formulas / rules" values={section.memorize_functions_or_formulas} variant="code" />
              <StudyList title="Common traps" values={section.traps} />
              <div className="action-row">
                <button className="secondary-button" onClick={() => onMarkStudied(section)} type="button">
                  {section.studied_status === "studied" ? "Mark unstudied" : "Mark as studied"}
                </button>
                <a className="secondary-button" href={sourceHref}>
                  Open full source
                </a>
              </div>
              </div>
            <InlineSourceViewer section={section} state={{ material, section }} />
          </div>
        </div>
      ) : null}
    </article>
  );
}

function StudyList({
  title,
  values,
  variant = "text"
}: {
  title: string;
  values: string[];
  variant?: "text" | "code";
}): JSX.Element | null {
  if (!values.length) {
    return null;
  }
  return (
    <div className="study-list-block">
      <h4>{title}</h4>
      <ul>
        {values.map((value) => (
          <li key={value}>{variant === "code" ? <code>{value}</code> : value}</li>
        ))}
      </ul>
    </div>
  );
}

function InlineSourceViewer({
  state,
  section
}: {
  state: SourceViewerState;
  section: MaterialStudySection;
}): JSX.Element {
  return <SourceViewerPane page={section.page_start ?? 1} showControls={false} state={state} variant="inline" />;
}

function EmptyStudyState(): JSX.Element {
  return (
    <section className="study-empty-state">
      <h3>No material selected</h3>
      <p>Select a material from the left panel, or upload one into the active course.</p>
    </section>
  );
}

function NoSectionsState({
  record,
  onRetry
}: {
  record: MaterialRecord;
  onRetry: () => void;
}): JSX.Element {
  if (record.status === "processing" || record.status === "pending") {
    return (
      <section className="study-empty-state">
        <h3>Sections are becoming available</h3>
        <p>The app is extracting, outlining, and enriching this material in stages.</p>
      </section>
    );
  }
  if (record.status === "failed") {
    return (
      <section className="study-empty-state">
        <h3>Processing failed</h3>
        <p>{record.error_message || "The document could not be processed."}</p>
        <button className="primary-button" onClick={onRetry} type="button">Retry processing</button>
      </section>
    );
  }
  return (
    <section className="study-empty-state">
      <h3>No study sections yet</h3>
      <p>This material did not produce usable study sections. Try regenerating the breakdown.</p>
    </section>
  );
}

function SourcePreview({
  preview,
  sourceId,
  sectionId,
  page
}: {
  preview: MaterialPreviewResponse;
  sourceId?: string | null;
  sectionId?: string | null;
  page?: string | null;
}): JSX.Element {
  const sections = sourceId
    ? preview.sections.filter((section) => section.source_id === sourceId)
    : sectionId
    ? preview.sections.filter((section) => section.source_id === sectionId)
    : preview.sections.slice(0, 3);
  const isPdf = preview.record.content_type === "application/pdf" || preview.record.file_name.toLowerCase().endsWith(".pdf");
  const pageNumber = Number(page || sections[0]?.locator.page_number || 1);
  const fileUrl = `/api/v1/materials/${encodeURIComponent(preview.record.material_id)}/file#page=${Number.isFinite(pageNumber) ? pageNumber : 1}`;
  return (
    <section className="source-preview-panel">
      <div className="section-header">
        <div>
          <h3>Source</h3>
          <p className="subtle">
            {preview.record.file_name}
            {Number.isFinite(pageNumber) ? ` · page ${pageNumber}` : ""}
          </p>
        </div>
      </div>
      {isPdf ? (
        <iframe
          className="pdf-source-frame"
          src={fileUrl}
          title={`${preview.record.file_name} source page`}
        />
      ) : null}
      <div className="stacked-list">
        {sections.map((section) => (
          <article className="source-preview-item" key={section.source_id}>
            <strong>{section.section_title}</strong>
            <p className="subtle">{section.citation_label}</p>
            <p>{section.text.slice(0, 900)}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

function buildSectionSourceHref(section: MaterialStudySection): string {
  const params = new URLSearchParams();
  params.set("section", section.section_id);
  if (section.source_ids[0]) {
    params.set("sourceId", section.source_ids[0]);
  }
  if (section.page_start) {
    params.set("page", String(section.page_start));
  }
  return `/materials/${encodeURIComponent(section.material_id)}?${params.toString()}`;
}

function materialStatusLabel(record: MaterialRecord): string {
  const stage = record.processing_status ?? (record.status === "completed" ? "ready" : record.status);
  return stage.replace("_", " ");
}

function isProcessing(record: MaterialRecord): boolean {
  return record.status === "pending" || record.status === "processing";
}

function navigateToQuizJob(jobId: string): void {
  const target = `/quiz?jobId=${encodeURIComponent(jobId)}`;
  if (process.env.NODE_ENV === "test") {
    window.history.pushState({}, "", target);
    window.dispatchEvent(new PopStateEvent("popstate"));
    return;
  }
  window.location.href = target;
}
