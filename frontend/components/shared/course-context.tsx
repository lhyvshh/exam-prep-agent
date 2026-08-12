"use client";

import React, { createContext, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { usePathname } from "next/navigation";

import { fetchCurrentWorkflow, fetchMaterialLibrary, setCurrentWorkflow } from "@/lib/api";
import type {
  CourseLibraryItem,
  CourseRecord,
  CurrentWorkflowResponse,
  MaterialLibraryResponse,
  ModuleRecord
} from "@/lib/schemas";

type CourseSelectionState = {
  selectedCourseId: string | null;
  selectedModuleId: string | null;
  workflow: CurrentWorkflowResponse | null;
  library: MaterialLibraryResponse | null;
  courses: CourseRecord[];
  modules: ModuleRecord[];
  selectedCourse: CourseRecord | null;
  selectedModule: ModuleRecord | null;
  isLoading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  setSelection: (courseId: string | null, moduleId?: string | null) => Promise<void>;
};

const CourseSelectionContext = createContext<CourseSelectionState | null>(null);

export function shouldLoadSharedCourseContext(pathname: string | null): boolean {
  return pathname !== "/config";
}

export function CourseSelectionProvider({ children }: { children: ReactNode }): JSX.Element {
  const pathname = usePathname();
  const shouldLoadContext = shouldLoadSharedCourseContext(pathname);
  const [workflow, setWorkflow] = useState<CurrentWorkflowResponse | null>(null);
  const [library, setLibrary] = useState<MaterialLibraryResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!shouldLoadContext) {
      setIsLoading(false);
      setError(null);
      return;
    }

    void refresh();
  }, [shouldLoadContext]);

  async function refresh(): Promise<void> {
    if (!shouldLoadContext) {
      setIsLoading(false);
      setError(null);
      return;
    }

    setIsLoading(true);
    try {
      const [nextWorkflow, nextLibrary] = await Promise.all([
        fetchCurrentWorkflow(),
        fetchMaterialLibrary()
      ]);
      setWorkflow(nextWorkflow);
      setLibrary(nextLibrary);
      setError(null);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Unable to load course context.");
    } finally {
      setIsLoading(false);
    }
  }

  async function setSelection(courseId: string | null, moduleId?: string | null): Promise<void> {
    if (!shouldLoadContext) {
      return;
    }

    const nextWorkflow = await setCurrentWorkflow(courseId, moduleId ?? null);
    setWorkflow(nextWorkflow);
    const nextLibrary = await fetchMaterialLibrary();
    setLibrary(nextLibrary);
    setError(null);
  }

  const courses = library?.courses.map((item) => item.course) ?? [];
  const selectedCourseItem = library?.courses.find(
    (item) => item.course.course_id === workflow?.course_id
  ) ?? null;
  const modules = selectedCourseItem?.modules.map((item) => item.module) ?? [];
  const selectedModule =
    selectedCourseItem?.modules.find((item) => item.module.module_id === workflow?.module_id)?.module ??
    null;

  return (
    <CourseSelectionContext.Provider
      value={{
        selectedCourseId: workflow?.course_id ?? null,
        selectedModuleId: workflow?.module_id ?? null,
        workflow,
        library,
        courses,
        modules,
        selectedCourse: selectedCourseItem?.course ?? null,
        selectedModule,
        isLoading,
        error,
        refresh,
        setSelection
      }}
    >
      {children}
    </CourseSelectionContext.Provider>
  );
}

export function useCourseSelection(): CourseSelectionState {
  const context = useContext(CourseSelectionContext);
  if (!context) {
    throw new Error("useCourseSelection must be used within CourseSelectionProvider.");
  }
  return context;
}

export function findLibraryCourse(
  library: MaterialLibraryResponse | null,
  courseId: string | null,
): CourseLibraryItem | null {
  if (!library || !courseId) {
    return null;
  }
  return library.courses.find((item) => item.course.course_id === courseId) ?? null;
}
