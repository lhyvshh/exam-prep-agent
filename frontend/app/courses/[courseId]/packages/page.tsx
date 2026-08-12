import React from "react";

import { CourseWorkspaceFrame } from "@/components/courses/course-workspace-frame";
import { PackageWorkspace } from "@/components/packages/package-workspace";

export default async function CoursePackagesPage({
  params
}: {
  params: Promise<{ courseId: string }>;
}): Promise<JSX.Element> {
  const { courseId } = await params;
  return (
    <CourseWorkspaceFrame courseId={courseId} activeTab="packages">
      <PackageWorkspace courseId={courseId} />
    </CourseWorkspaceFrame>
  );
}
