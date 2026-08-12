export type CourseResumeLink = {
  title: string;
  href: string;
  meta?: string;
  updatedAt: string;
};

export type CourseResumeState = {
  lastModule?: CourseResumeLink;
  lastStudyCard?: CourseResumeLink;
};

const COURSE_RESUME_STORAGE_PREFIX = "exam-prep-course-resume:";

export function readCourseResume(courseId: string): CourseResumeState {
  if (typeof window === "undefined") {
    return {};
  }

  try {
    const rawValue = window.localStorage.getItem(storageKey(courseId));
    if (!rawValue) {
      return {};
    }

    const parsed = JSON.parse(rawValue) as unknown;
    if (!parsed || typeof parsed !== "object") {
      return {};
    }

    const record = parsed as Record<string, unknown>;
    return {
      lastModule: resumeLinkFromUnknown(record.lastModule),
      lastStudyCard: resumeLinkFromUnknown(record.lastStudyCard)
    };
  } catch {
    return {};
  }
}

export function writeCourseResume(courseId: string, patch: CourseResumeState): void {
  if (typeof window === "undefined") {
    return;
  }

  try {
    const nextResume = {
      ...readCourseResume(courseId),
      ...patch
    };
    window.localStorage.setItem(storageKey(courseId), JSON.stringify(nextResume));
  } catch {}
}

function storageKey(courseId: string): string {
  return `${COURSE_RESUME_STORAGE_PREFIX}${courseId}`;
}

function resumeLinkFromUnknown(value: unknown): CourseResumeLink | undefined {
  if (!value || typeof value !== "object") {
    return undefined;
  }

  const record = value as Record<string, unknown>;
  const title = typeof record.title === "string" ? record.title.trim() : "";
  const href = typeof record.href === "string" ? record.href.trim() : "";
  const updatedAt = typeof record.updatedAt === "string" ? record.updatedAt.trim() : "";
  const meta = typeof record.meta === "string" ? record.meta.trim() : "";

  if (!title || !href || !updatedAt) {
    return undefined;
  }

  return {
    title,
    href,
    ...(meta ? { meta } : {}),
    updatedAt
  };
}
