import React, { Suspense } from "react";

import { CourseFlashcardsWorkspace } from "@/components/courses/course-flashcards-workspace";
import { CourseWorkspaceFrame } from "@/components/courses/course-workspace-frame";

export default async function CourseFlashcardsPage({
  params
}: {
  params: Promise<{ courseId: string }>;
}): Promise<JSX.Element> {
  const { courseId } = await params;
  return (
    <CourseWorkspaceFrame courseId={courseId} activeTab="flashcards">
      <Suspense fallback={<p className="subtle">Loading flashcards...</p>}>
        <CourseFlashcardsWorkspace courseId={courseId} />
      </Suspense>
    </CourseWorkspaceFrame>
  );
}
