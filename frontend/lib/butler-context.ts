import type { AgentPageContext, AgentPageQuestionContext } from "@/lib/schemas";

const STORAGE_KEY = "exam-prep-butler-page-context";
const MAX_VISIBLE_TEXT_LENGTH = 4000;

export function writeButlerPageContext(context: AgentPageContext): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(context));
}

export function readStoredButlerPageContext(): AgentPageContext | null {
  if (typeof window === "undefined") {
    return null;
  }
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) {
    return null;
  }
  try {
    return normalizePageContext(JSON.parse(raw));
  } catch {
    return null;
  }
}

export function currentButlerPageContext(): AgentPageContext {
  const stored = readStoredButlerPageContext();
  const visibleText = browserVisibleText();
  const route = typeof window === "undefined" ? "" : `${window.location.pathname}${window.location.search}`;
  const title = typeof document === "undefined" ? "" : document.title;
  const routeIds = routeContextIds();
  return {
    page_type: stored?.page_type ?? inferPageType(route),
    route: stored?.route || route,
    title: stored?.title || title,
    visible_text: visibleText || stored?.visible_text || "",
    source_ids: stored?.source_ids.length ? stored.source_ids : routeIds.source_ids,
    material_ids: stored?.material_ids.length ? stored.material_ids : routeIds.material_ids,
    section_ids: stored?.section_ids.length ? stored.section_ids : routeIds.section_ids,
    question: stored?.question ?? null
  };
}

function browserVisibleText(): string {
  if (typeof document === "undefined") {
    return "";
  }
  const root = document.querySelector("main") ?? document.body;
  return compactText(root?.textContent ?? "").slice(0, MAX_VISIBLE_TEXT_LENGTH);
}

function compactText(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

function inferPageType(route: string): string {
  if (route.includes("quiz")) {
    return "quiz_review";
  }
  if (route.includes("mock")) {
    return "mock_exam_review";
  }
  if (route.includes("flashcards")) {
    return "study_cards";
  }
  if (route.includes("materials")) {
    return "materials";
  }
  return "course";
}

function routeContextIds(): Pick<AgentPageContext, "source_ids" | "material_ids" | "section_ids"> {
  if (typeof window === "undefined") {
    return { source_ids: [], material_ids: [], section_ids: [] };
  }
  const params = new URLSearchParams(window.location.search);
  const materialId = params.get("materialId");
  const sourceId = params.get("sourceId");
  const sectionId = params.get("sectionId");
  return {
    source_ids: [sourceId, sectionId].filter(nonEmpty),
    material_ids: [materialId].filter(nonEmpty),
    section_ids: [sectionId, sourceId].filter(nonEmpty)
  };
}

function normalizePageContext(value: unknown): AgentPageContext | null {
  if (!isRecord(value)) {
    return null;
  }
  return {
    page_type: stringValue(value["page_type"]) || "course",
    route: stringValue(value["route"]),
    title: stringValue(value["title"]),
    visible_text: stringValue(value["visible_text"]).slice(0, MAX_VISIBLE_TEXT_LENGTH),
    source_ids: stringArray(value["source_ids"]),
    material_ids: stringArray(value["material_ids"]),
    section_ids: stringArray(value["section_ids"]),
    question: normalizeQuestionContext(value["question"])
  };
}

function normalizeQuestionContext(value: unknown): AgentPageQuestionContext | null {
  if (!isRecord(value)) {
    return null;
  }
  return {
    question_number: nullableNumber(value["question_number"]),
    question_id: nullableString(value["question_id"]),
    prompt: stringValue(value["prompt"]),
    selected_option_id: nullableString(value["selected_option_id"]),
    correct_option_id: nullableString(value["correct_option_id"]),
    correct_answer: nullableString(value["correct_answer"]),
    explanation: nullableString(value["explanation"]),
    concept: nullableString(value["concept"]),
    source_page: nullableNumber(value["source_page"]),
    options: stringRecordArray(value["options"]).map((option) => ({
      option_id: stringValue(option["option_id"]),
      text: stringValue(option["text"])
    })).filter((option) => option.option_id && option.text)
  };
}

function isRecord(value: unknown): value is { readonly [key: string]: unknown } {
  return typeof value === "object" && value !== null;
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? compactText(value) : "";
}

function nullableString(value: unknown): string | null {
  const normalized = stringValue(value);
  return normalized || null;
}

function nullableNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function stringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.map(stringValue).filter(Boolean).slice(0, 12);
}

function nonEmpty(value: string | null): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function stringRecordArray(value: unknown): Array<{ readonly [key: string]: unknown }> {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter(isRecord).slice(0, 8);
}
