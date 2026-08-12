import type {
  MaterialRecord,
  MaterialStudySection,
  QuestionGradeResult,
  SourceChunk,
  StudyScope
} from "@/lib/schemas";

export function scopeFromSection(
  courseId: string,
  material: MaterialRecord,
  section: MaterialStudySection,
  moduleId?: string | null
): StudyScope {
  return {
    course_id: courseId,
    module_ids: moduleId ? [moduleId] : material.module_id ? [material.module_id] : [],
    material_ids: [material.material_id],
    section_ids: section.source_ids,
    source_type: "study_material"
  };
}

export function scopeFromQuestionResult(
  courseId: string,
  result: QuestionGradeResult,
  fallbackModuleId?: string | null
): StudyScope {
  const citations = result.citations;
  const sourceIds = unique(citations.map((citation) => citation.source_id));
  const materialIds = unique(citations.map((citation) => citation.material_id));
  const moduleIds = unique([
    ...(fallbackModuleId ? [fallbackModuleId] : []),
    ...citations
      .map((citation) => citation.module_id)
      .filter((moduleId): moduleId is string => Boolean(moduleId))
  ]);

  return {
    course_id: courseId,
    module_ids: moduleIds,
    material_ids: materialIds,
    section_ids: sourceIds,
    source_type: "study_material"
  };
}

export function sourceHrefFromCitation(citation: SourceChunk, returnTo?: string | null): string {
  const params = new URLSearchParams({
    materialId: citation.material_id,
    sourceId: citation.source_id,
    groupId: "all-sections",
    study: "1",
    source: "1"
  });
  if (citation.locator.page_number) {
    params.set("page", String(citation.locator.page_number));
  }
  if (returnTo) {
    params.set("returnTo", returnTo);
  }
  return `/courses/${encodeURIComponent(citation.course_id)}/materials?${params.toString()}`;
}

export function studyHrefFromCitation(citation: SourceChunk, returnTo?: string | null): string {
  const params = new URLSearchParams({
    materialId: citation.material_id,
    sourceId: citation.source_id,
    groupId: "all-sections",
    study: "1"
  });
  if (citation.locator.page_number) {
    params.set("page", String(citation.locator.page_number));
  }
  if (returnTo) {
    params.set("returnTo", returnTo);
  }
  return `/courses/${encodeURIComponent(citation.course_id)}/materials?${params.toString()}`;
}

function unique(values: Array<string | null | undefined>): string[] {
  return Array.from(new Set(values.filter((value): value is string => Boolean(value))));
}
