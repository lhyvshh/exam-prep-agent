import React, { Suspense } from "react";

import { CourseLibrary } from "@/components/courses/course-library";

export default function CoursesPage(): JSX.Element {
  return (
    <Suspense fallback={<p className="subtle">Loading course library...</p>}>
      <CourseLibrary />
    </Suspense>
  );
}
