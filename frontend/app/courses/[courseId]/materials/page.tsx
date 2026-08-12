import React, { Suspense } from "react";

import { CourseMaterialsWorkspace } from "@/components/courses/course-materials-workspace";
import { CourseWorkspaceFrame } from "@/components/courses/course-workspace-frame";

export default async function CourseMaterialsPage({
  params
}: {
  params: Promise<{ courseId: string }>;
}): Promise<JSX.Element> {
  const { courseId } = await params;
  return (
    <CourseWorkspaceFrame courseId={courseId} activeTab="materials">
      <Suspense fallback={<p className="subtle">Loading materials...</p>}>
        <CourseMaterialsWorkspace courseId={courseId} />
      </Suspense>
    </CourseWorkspaceFrame>
  );
}
