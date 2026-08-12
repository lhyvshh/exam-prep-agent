"use client";

import React, { FormEvent, useEffect, useRef, useState } from "react";

import { ConfigForm } from "@/components/config/config-form";
import { MockExamWorkspace } from "@/components/exams/mock-exam-workspace";
import { useCourseSelection } from "@/components/shared/course-context";
import { createCourse, deleteCourse, fetchMaterialLibrary, updateCourse } from "@/lib/api";
import type { MaterialLibraryResponse } from "@/lib/schemas";

export function CourseLibrary(): JSX.Element {
  const { setSelection } = useCourseSelection();
  const [library, setLibrary] = useState<MaterialLibraryResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isCreating, setIsCreating] = useState<boolean>(false);
  const [activeCourseActionId, setActiveCourseActionId] = useState<string | null>(null);
  const [activeLibraryModal, setActiveLibraryModal] = useState<"courses" | "api" | "mock-exams" | null>(null);
  const [activeMockCourseLabel, setActiveMockCourseLabel] = useState<string>("Mock exams");
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({ course_code: "", display_name: "", description: "" });
  const [courseForms, setCourseForms] = useState<Record<string, { course_code: string; display_name: string; description: string }>>({});
  const didOpenQueryMockExam = useRef<boolean>(false);

  useEffect(() => {
    void loadLibrary();
  }, []);

  useEffect(() => {
    if (!library || didOpenQueryMockExam.current || typeof window === "undefined") {
      return;
    }
    const courseId = new URLSearchParams(window.location.search).get("mockExamCourseId");
    if (!courseId) {
      return;
    }
    const courseItem = library.courses.find((item) => item.course.course_id === courseId);
    if (!courseItem) {
      return;
    }
    didOpenQueryMockExam.current = true;
    void handleOpenMockExams(courseId, courseItem.course.display_name);
    window.history.replaceState(null, "", "/courses");
  }, [library]);

  async function loadLibrary(): Promise<void> {
    setIsLoading(true);
    try {
      const nextLibrary = await fetchMaterialLibrary();
      setLibrary(nextLibrary);
      setCourseForms(
        Object.fromEntries(
          nextLibrary.courses.map((item) => [
            item.course.course_id,
            {
              course_code: item.course.course_code,
              display_name: item.course.display_name,
              description: item.course.description ?? ""
            }
          ])
        )
      );
      setError(null);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Unable to load courses.");
      setLibrary(null);
    } finally {
      setIsLoading(false);
    }
  }

  async function handleCreateCourse(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!form.course_code.trim() || !form.display_name.trim()) {
      setError("Course code and name are required.");
      return;
    }
    setIsCreating(true);
    try {
      await createCourse({
        course_code: form.course_code.trim(),
        display_name: form.display_name.trim(),
        description: form.description.trim() || null
      });
      setForm({ course_code: "", display_name: "", description: "" });
      await loadLibrary();
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "Unable to create course.");
    } finally {
      setIsCreating(false);
    }
  }

  async function handleUpdateCourse(courseId: string): Promise<void> {
    const nextForm = courseForms[courseId];
    if (!nextForm?.course_code.trim() || !nextForm.display_name.trim()) {
      setError("Course code and name are required.");
      return;
    }
    setActiveCourseActionId(courseId);
    try {
      await updateCourse(courseId, {
        course_code: nextForm.course_code.trim(),
        display_name: nextForm.display_name.trim(),
        description: nextForm.description.trim() || null
      });
      await loadLibrary();
    } catch (updateError) {
      setError(updateError instanceof Error ? updateError.message : "Unable to update course.");
    } finally {
      setActiveCourseActionId(null);
    }
  }

  async function handleDeleteCourse(courseId: string, label: string): Promise<void> {
    if (!window.confirm(`Delete ${label}? This removes its workspace scope.`)) {
      return;
    }
    setActiveCourseActionId(courseId);
    try {
      await deleteCourse(courseId);
      await loadLibrary();
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "Unable to delete course.");
    } finally {
      setActiveCourseActionId(null);
    }
  }

  async function handleOpenMockExams(courseId: string, label: string): Promise<void> {
    setActiveCourseActionId(courseId);
    try {
      await setSelection(courseId, null);
      setActiveMockCourseLabel(label);
      setActiveLibraryModal("mock-exams");
      setError(null);
    } catch (openError) {
      setError(openError instanceof Error ? openError.message : "Unable to open mock exams.");
    } finally {
      setActiveCourseActionId(null);
    }
  }

  return (
    <main className="course-library-page" id="main-content">
      <section className="course-library-hero">
        <div>
          <p className="eyebrow">Course Library</p>
          <h1>Your exam-prep workspace</h1>
          <p>Open a course to study materials, generate quizzes, build mock exams, and review misses.</p>
        </div>
      </section>

      {error ? (
        <div className="status-panel error-panel" aria-live="polite">
          <strong>Issue:</strong> {error}
        </div>
      ) : null}

      <section className="course-library-actions">
        <button className="library-action-button" onClick={() => setActiveLibraryModal("courses")} type="button">
          Manage courses
        </button>
        <button className="library-action-button" onClick={() => setActiveLibraryModal("api")} type="button">
          API setup
        </button>
      </section>

      {activeLibraryModal === "courses" ? (
        <LibraryModal eyebrow="Course library" onClose={() => setActiveLibraryModal(null)} title="Manage courses">
          <div className="course-management-panel">
            <form className="course-create-form course-create-form-compact" onSubmit={handleCreateCourse}>
              <label className="field">
                <span>New course code</span>
                <input
                  aria-label="Course code"
                  value={form.course_code}
                  onChange={(event) => setForm((current) => ({ ...current, course_code: event.target.value }))}
                />
              </label>
              <label className="field">
                <span>New course name</span>
                <input
                  aria-label="Course name"
                  value={form.display_name}
                  onChange={(event) => setForm((current) => ({ ...current, display_name: event.target.value }))}
                />
              </label>
              <label className="field">
                <span>Description</span>
                <input
                  aria-label="Course description"
                  value={form.description}
                  onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))}
                />
              </label>
              <button className="primary-button" disabled={isCreating} type="submit">
                {isCreating ? "Creating..." : "Create course"}
              </button>
            </form>

            <div className="course-management-list">
              {(library?.courses ?? []).map((item) => {
                const courseForm = courseForms[item.course.course_id] ?? {
                  course_code: item.course.course_code,
                  display_name: item.course.display_name,
                  description: item.course.description ?? ""
                };
                const isBusy = activeCourseActionId === item.course.course_id;
                return (
                  <article className="course-management-row" key={item.course.course_id}>
                    <div className="course-management-fields">
                      <label className="field">
                        <span>Code</span>
                        <input
                          aria-label={`Course code for ${item.course.display_name}`}
                          value={courseForm.course_code}
                          onChange={(event) =>
                            setCourseForms((current) => ({
                              ...current,
                              [item.course.course_id]: {
                                ...courseForm,
                                course_code: event.target.value
                              }
                            }))
                          }
                        />
                      </label>
                      <label className="field">
                        <span>Name</span>
                        <input
                          aria-label={`Course name for ${item.course.display_name}`}
                          value={courseForm.display_name}
                          onChange={(event) =>
                            setCourseForms((current) => ({
                              ...current,
                              [item.course.course_id]: {
                                ...courseForm,
                                display_name: event.target.value
                              }
                            }))
                          }
                        />
                      </label>
                      <label className="field">
                        <span>Description</span>
                        <input
                          aria-label={`Course description for ${item.course.display_name}`}
                          value={courseForm.description}
                          onChange={(event) =>
                            setCourseForms((current) => ({
                              ...current,
                              [item.course.course_id]: {
                                ...courseForm,
                                description: event.target.value
                              }
                            }))
                          }
                        />
                      </label>
                    </div>
                    <div className="action-row">
                      <button className="secondary-button" disabled={isBusy} onClick={() => void handleUpdateCourse(item.course.course_id)} type="button">
                        {isBusy ? "Saving..." : "Save"}
                      </button>
                      <button className="danger-button" disabled={isBusy} onClick={() => void handleDeleteCourse(item.course.course_id, item.course.display_name)} type="button">
                        Delete
                      </button>
                    </div>
                  </article>
                );
              })}
            </div>
          </div>
        </LibraryModal>
      ) : null}

      {activeLibraryModal === "api" ? (
        <LibraryModal eyebrow="Runtime setup" onClose={() => setActiveLibraryModal(null)} title="API setup">
          <div className="library-config-shell">
            <div className="library-config-header">
              <div>
                <strong>Provider + model setup</strong>
                <p className="subtle">
                  Keep runtime configuration on the library page so new courses are ready to study immediately.
                </p>
              </div>
              <a className="secondary-button" href="/settings/models">
                Open model hub
              </a>
            </div>
            <ConfigForm compact />
          </div>
        </LibraryModal>
      ) : null}

      {activeLibraryModal === "mock-exams" ? (
        <LibraryModal eyebrow="Mock exams" onClose={() => setActiveLibraryModal(null)} title={activeMockCourseLabel}>
          <MockExamWorkspace />
        </LibraryModal>
      ) : null}

      {isLoading ? <p className="subtle">Loading courses...</p> : null}

      <section className="course-card-grid">
        {(library?.courses ?? []).length === 0 && !isLoading ? (
          <article className="course-empty-card">
            <h2>No courses yet</h2>
            <p>Create your first course, then upload materials inside its workspace.</p>
          </article>
        ) : null}

        {(library?.courses ?? []).map((item) => (
          <CourseCard
            isBusy={activeCourseActionId === item.course.course_id}
            key={item.course.course_id}
            item={item}
            onOpenMockExams={() => void handleOpenMockExams(item.course.course_id, item.course.display_name)}
          />
        ))}
      </section>
    </main>
  );
}

function LibraryModal({
  children,
  eyebrow,
  onClose,
  title
}: {
  children: React.ReactNode;
  eyebrow: string;
  onClose: () => void;
  title: string;
}): JSX.Element {
  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent): void {
      if (event.key === "Escape") {
        onClose();
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return (
    <div
      className="library-modal-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
      role="presentation"
    >
      <section aria-label={title} aria-modal="true" className="library-modal" role="dialog">
        <div className="library-modal-header">
          <div>
            <p className="eyebrow">{eyebrow}</p>
            <h2>{title}</h2>
          </div>
          <button className="secondary-button" onClick={onClose} type="button">
            Close
          </button>
        </div>
        <div className="library-modal-body">{children}</div>
      </section>
    </div>
  );
}

function CourseCard({
  isBusy,
  item,
  onOpenMockExams
}: {
  isBusy: boolean;
  item: MaterialLibraryResponse["courses"][number];
  onOpenMockExams: () => void;
}): JSX.Element {
  return (
    <article className="course-card">
      <div>
        <p className="eyebrow">{item.course.course_code}</p>
        <h2>{item.course.display_name}</h2>
        {item.course.description ? <p>{item.course.description}</p> : null}
      </div>
      <div className="course-card-actions">
        <a className="primary-button" href={`/courses/${encodeURIComponent(item.course.course_id)}/overview`}>
          Open course
        </a>
        <button className="secondary-button" disabled={isBusy} onClick={onOpenMockExams} type="button">
          {isBusy ? "Opening..." : "Mock exams"}
        </button>
      </div>
    </article>
  );
}
