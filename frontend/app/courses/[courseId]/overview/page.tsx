import React from "react";

import { CourseOverview } from "@/components/courses/course-overview";
import { CourseWorkspaceFrame } from "@/components/courses/course-workspace-frame";

export default async function CourseOverviewPage({
  params
}: {
  params: Promise<{ courseId: string }>;
}): Promise<JSX.Element> {
  const { courseId } = await params;
  return (
    <CourseWorkspaceFrame courseId={courseId} activeTab="overview">
      <CourseOverview courseId={courseId} />
    </CourseWorkspaceFrame>
  );
}
