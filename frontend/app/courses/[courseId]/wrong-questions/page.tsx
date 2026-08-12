import React, { Suspense } from "react";

import { CourseWorkspaceFrame } from "@/components/courses/course-workspace-frame";
import { WrongQuestionReview } from "@/components/review/wrong-question-review";

export default async function CourseWrongQuestionsPage({
  params
}: {
  params: Promise<{ courseId: string }>;
}): Promise<JSX.Element> {
  const { courseId } = await params;
  return (
    <CourseWorkspaceFrame courseId={courseId} activeTab="wrong-questions">
      <Suspense fallback={<p className="subtle">Loading wrong-question review...</p>}>
        <WrongQuestionReview />
      </Suspense>
    </CourseWorkspaceFrame>
  );
}
