import { redirect } from "next/navigation";

export default async function CourseStudyPage({
  params,
  searchParams
}: {
  params: Promise<{ courseId: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}): Promise<never> {
  const { courseId } = await params;
  const incoming = await searchParams;
  const nextParams = new URLSearchParams();

  copyParam(incoming, nextParams, "materialId");
  copyParam(incoming, nextParams, "sectionId");
  copyParam(incoming, nextParams, "sourceId");
  copyParam(incoming, nextParams, "page");
  if (nextParams.get("sectionId")) {
    nextParams.set("groupId", "all-sections");
  }
  if (nextParams.get("sourceId")) {
    nextParams.set("source", "1");
  }

  const suffix = nextParams.toString() ? `?${nextParams.toString()}` : "";
  redirect(`/courses/${encodeURIComponent(courseId)}/materials${suffix}`);
}

function copyParam(
  incoming: Record<string, string | string[] | undefined>,
  nextParams: URLSearchParams,
  key: string
): void {
  const value = incoming[key];
  if (Array.isArray(value)) {
    if (value[0]) {
      nextParams.set(key, value[0]);
    }
    return;
  }
  if (value) {
    nextParams.set(key, value);
  }
}
