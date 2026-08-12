import type {
  CourseListResponse,
  CreateCourseRequest,
  CreateModuleRequest,
  DeleteScopeResponse,
  ConfigHealthResponse,
  ConfigValidationRequest,
  ConfigValidationResponse,
  CourseMaterialsResponse,
  CourseDashboardResponse,
  FlashcardReviewPayload,
  FlashcardReviewRecord,
  AgentPageContext,
  AgentChatResponse,
  AgentMemoryProfile,
  AgentMemoryUpdateRequest,
  AgentRecommendationListResponse,
  ActivityEventPayload,
  AgentRunRecord,
  CurrentWorkflowResponse,
  HealthResponse,
  MaterialLibraryResponse,
  MaterialPageImagesResponse,
  MaterialStudyResponse,
  MaterialStudySectionResponse,
  MaterialPreviewResponse,
  MaterialDeleteResponse,
  MaterialStatusResponse,
  MaterialUploadResponse,
  MockExamGenerationRequest,
  MockExamGenerationResponse,
  MockExamGradeResponse,
  MockExamReviewResponse,
  MockExamSourceIngestResponse,
  MockExamSourceListResponse,
  ModuleListResponse,
  NotificationPreference,
  NotificationPreferenceUpdateRequest,
  QuizReviewResponse,
  QuizGenerationAcceptedResponse,
  QuizGenerationCancelResponse,
  QuizGenerationJobResponse,
  QuizGenerationRequest,
  QuizGradeResponse,
  QuizSubmissionAnswer,
  RuntimeConfigResponse,
  ReminderDraft,
  ReminderDraftSendResponse,
  ReminderType,
  SourceResolveResponse,
  SourceTarget,
  SmartAgentStudyPlanResponse,
  StudyScope,
  StudyPackageCreateRequest,
  StudyPackageFileListResponse,
  StudyPackageGenerationJob,
  StudyPackageListResponse,
  StudyPackageRecord,
  StudyPackageValidationReport,
  StudyPackageVersionListResponse,
  StudyPackageVersionResponse,
  CompletedExamImportResponse,
  ImportedExamAttemptListResponse
} from "@/lib/schemas";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api/v1").replace(/\/$/, "");
const BACKEND_UNAVAILABLE_MESSAGE =
  "The local backend is unavailable. Start FastAPI on http://127.0.0.1:8000 and retry.";

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      cache: "no-store",
      ...init
    });
  } catch (error) {
    if (error instanceof TypeError) {
      throw new Error(BACKEND_UNAVAILABLE_MESSAGE);
    }

    throw error;
  }

  let parsedBody: unknown = null;

  if (typeof response.json === "function" && typeof response.text !== "function") {
    parsedBody = (await response.json()) as unknown;
  } else {
    const responseText = await response.text();

    if (responseText) {
      try {
        parsedBody = JSON.parse(responseText) as unknown;
      } catch {
        throw new Error(
          response.ok
            ? "The backend returned an unexpected response. Check that the local API is running."
            : `Request failed with status ${response.status}.`
        );
      }
    }
  }

  if (!response.ok) {
    throw new Error(formatApiError(parsedBody, response.status));
  }

  return parsedBody as T;
}

function formatApiError(parsedBody: unknown, status: number): string {
  if (!parsedBody || typeof parsedBody !== "object") {
    return `Request failed with status ${status}.`;
  }

  const errorBody = parsedBody as {
    detail?: unknown;
    message?: unknown;
  };

  if (typeof errorBody.detail === "string") {
    return errorBody.detail;
  }
  if (errorBody.detail && typeof errorBody.detail === "object") {
    const detail = errorBody.detail as {
      error?: unknown;
      failure_reason?: unknown;
      parser_phase?: unknown;
      file_name?: unknown;
    };
    if (typeof detail.failure_reason === "string") {
      const fileName = typeof detail.file_name === "string" ? `${detail.file_name}: ` : "";
      const phase = typeof detail.parser_phase === "string" ? ` (${detail.parser_phase})` : "";
      return `${fileName}${detail.failure_reason}${phase}`;
    }
    if (typeof detail.error === "string") {
      return detail.error.replace(/_/g, " ");
    }
  }
  if (typeof errorBody.message === "string") {
    return errorBody.message;
  }
  return `Request failed with status ${status}.`;
}

export async function fetchHealth(): Promise<HealthResponse> {
  return requestJson<HealthResponse>("/health", {
    method: "GET",
    headers: {
      "Content-Type": "application/json"
    }
  });
}

export async function trackActivityEvent(payload: ActivityEventPayload): Promise<void> {
  if (process.env.NODE_ENV === "test") {
    return;
  }

  const body = JSON.stringify({
    user_id: "demo-user",
    metadata_json: {},
    ...payload
  });

  if (typeof navigator !== "undefined" && typeof navigator.sendBeacon === "function") {
    const blob = new Blob([body], { type: "application/json" });
    navigator.sendBeacon(`${API_BASE_URL}/activity/events`, blob);
    return;
  }

  await fetch(`${API_BASE_URL}/activity/events`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body,
    keepalive: true
  });
}

export async function recordFlashcardReview(
  payload: FlashcardReviewPayload
): Promise<FlashcardReviewRecord> {
  return requestJson<FlashcardReviewRecord>("/activity/flashcard-reviews", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      user_id: "demo-user",
      metadata_json: {},
      ...payload
    })
  });
}

export async function fetchRuntimeConfig(): Promise<RuntimeConfigResponse> {
  return requestJson<RuntimeConfigResponse>("/config/runtime", {
    method: "GET",
    headers: {
      "Content-Type": "application/json"
    }
  });
}

export async function validateConfig(
  payload: ConfigValidationRequest,
  profile: "current" | "butler" | "parser" = "current"
): Promise<ConfigValidationResponse> {
  const query = profile === "current" ? "" : `?profile=${profile}`;
  return requestJson<ConfigValidationResponse>(`/config/validate${query}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  });
}

export async function fetchConfigHealth(): Promise<ConfigHealthResponse> {
  return requestJson<ConfigHealthResponse>("/config/health", {
    method: "GET",
    headers: {
      "Content-Type": "application/json"
    }
  });
}

export async function fetchAgentRecommendations(
  courseId: string
): Promise<AgentRecommendationListResponse> {
  return requestJson<AgentRecommendationListResponse>(
    `/agents/courses/${encodeURIComponent(courseId)}/recommendations`,
    {
      method: "GET",
      headers: {
        "Content-Type": "application/json"
      }
    }
  );
}

export async function fetchSmartAgentStudyPlan(
  courseId: string
): Promise<SmartAgentStudyPlanResponse> {
  return requestJson<SmartAgentStudyPlanResponse>(
    `/agent/study-plan?courseId=${encodeURIComponent(courseId)}`,
    {
      method: "GET",
      headers: {
        "Content-Type": "application/json"
      }
    }
  );
}

export async function fetchAgentMemory(courseId: string): Promise<AgentMemoryProfile> {
  return requestJson<AgentMemoryProfile>(
    `/agents/courses/${encodeURIComponent(courseId)}/memory`,
    {
      method: "GET",
      headers: {
        "Content-Type": "application/json"
      }
    }
  );
}

export async function saveAgentMemory(
  courseId: string,
  payload: AgentMemoryUpdateRequest
): Promise<AgentMemoryProfile> {
  return requestJson<AgentMemoryProfile>(
    `/agents/courses/${encodeURIComponent(courseId)}/memory`,
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    }
  );
}

export async function chatWithAgent(
  courseId: string,
  message: string,
  scope: StudyScope,
  pageContext?: AgentPageContext | null
): Promise<AgentChatResponse> {
  return requestJson<AgentChatResponse>("/agents/chat", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ course_id: courseId, message, scope, page_context: pageContext ?? null })
  });
}

export async function runAgentCheck(
  intent: string,
  scope: StudyScope
): Promise<AgentRunRecord> {
  return requestJson<AgentRunRecord>("/agents/run", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ intent, scope })
  });
}

export async function dismissAgentRecommendation(
  recommendationId: string
): Promise<{ id: string; dismissed: boolean }> {
  return requestJson<{ id: string; dismissed: boolean }>(
    `/agents/recommendations/${encodeURIComponent(recommendationId)}/dismiss`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      }
    }
  );
}

export async function resolveSourceTarget(
  target: SourceTarget
): Promise<SourceResolveResponse> {
  return requestJson<SourceResolveResponse>("/source/resolve", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ target })
  });
}

export async function fetchNotificationPreference(courseId: string): Promise<NotificationPreference> {
  return requestJson<NotificationPreference>(
    `/notifications/courses/${encodeURIComponent(courseId)}/preferences`,
    {
      method: "GET",
      headers: {
        "Content-Type": "application/json"
      }
    }
  );
}

export async function saveNotificationPreference(
  courseId: string,
  payload: NotificationPreferenceUpdateRequest
): Promise<NotificationPreference> {
  return requestJson<NotificationPreference>(
    `/notifications/courses/${encodeURIComponent(courseId)}/preferences`,
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    }
  );
}

export async function fetchReminderDrafts(courseId: string): Promise<ReminderDraft[]> {
  return requestJson<ReminderDraft[]>(
    `/notifications/courses/${encodeURIComponent(courseId)}/drafts`,
    {
      method: "GET",
      headers: {
        "Content-Type": "application/json"
      }
    }
  );
}

export async function createReminderDraft(
  courseId: string,
  reminderType: ReminderType
): Promise<ReminderDraft> {
  return requestJson<ReminderDraft>(
    `/notifications/courses/${encodeURIComponent(courseId)}/drafts`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ reminder_type: reminderType })
    }
  );
}

export async function sendReminderDraft(draftId: string): Promise<ReminderDraftSendResponse> {
  return requestJson<ReminderDraftSendResponse>(
    `/notifications/drafts/${encodeURIComponent(draftId)}/send`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      }
    }
  );
}

export async function uploadMaterial(
  courseId: string,
  file: File,
  moduleId?: string | null
): Promise<MaterialUploadResponse> {
  const formData = new FormData();
  formData.append("course_id", courseId);
  if (moduleId) {
    formData.append("module_id", moduleId);
  }
  formData.append("file", file);

  return requestJson<MaterialUploadResponse>("/materials/upload", {
    method: "POST",
    body: formData
  });
}

export async function fetchMaterialStatus(materialId: string): Promise<MaterialStatusResponse> {
  return requestJson<MaterialStatusResponse>(`/materials/${materialId}/status`, {
    method: "GET",
    headers: {
      "Content-Type": "application/json"
    }
  });
}

export async function fetchMaterialPreview(
  materialId: string,
  chunkLimit: number = 5
): Promise<MaterialPreviewResponse> {
  return requestJson<MaterialPreviewResponse>(
    `/materials/${materialId}/preview?chunk_limit=${chunkLimit}`,
    {
      method: "GET",
      headers: {
        "Content-Type": "application/json"
      }
    }
  );
}

export async function fetchMaterialStudy(
  materialId: string,
  options: { groupId?: string | null; offset?: number; limit?: number } = {}
): Promise<MaterialStudyResponse> {
  const params = new URLSearchParams();
  if (options.groupId) {
    params.set("group_id", options.groupId);
  }
  if (typeof options.offset === "number") {
    params.set("offset", String(options.offset));
  }
  if (typeof options.limit === "number") {
    params.set("limit", String(options.limit));
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson<MaterialStudyResponse>(`/materials/${materialId}/study${suffix}`, {
    method: "GET",
    headers: {
      "Content-Type": "application/json"
    }
  });
}

export async function fetchMaterialStudySection(
  materialId: string,
  sectionId: string
): Promise<MaterialStudySectionResponse> {
  return requestJson<MaterialStudySectionResponse>(
    `/materials/${materialId}/study/sections/${sectionId}`,
    {
      method: "GET",
      headers: {
        "Content-Type": "application/json"
      }
    }
  );
}

export async function markMaterialStudySection(
  materialId: string,
  sectionId: string,
  studied: boolean
): Promise<MaterialStudySectionResponse> {
  return requestJson<MaterialStudySectionResponse>(
    `/materials/${materialId}/study/sections/${sectionId}`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        studied_status: studied ? "studied" : "not_started"
      })
    }
  );
}

export async function regenerateMaterialStudy(materialId: string): Promise<MaterialStudyResponse> {
  return requestJson<MaterialStudyResponse>(`/materials/${materialId}/study/regenerate`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    }
  });
}

export async function reprocessMaterial(materialId: string): Promise<MaterialStatusResponse> {
  return requestJson<MaterialStatusResponse>(`/materials/${materialId}/reprocess`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    }
  });
}

export async function startMaterialSectionQuiz(
  materialId: string,
  sectionId: string
): Promise<QuizGenerationAcceptedResponse> {
  return requestJson<QuizGenerationAcceptedResponse>(
    `/materials/${materialId}/study/sections/${sectionId}/quiz`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      }
    }
  );
}

export async function fetchMaterialPageImages(
  materialId: string,
  pageNumber: number
): Promise<MaterialPageImagesResponse> {
  return requestJson<MaterialPageImagesResponse>(
    `/materials/${materialId}/pages/${pageNumber}/images`,
    {
      method: "GET",
      headers: {
        "Content-Type": "application/json"
      }
    }
  );
}

export async function retryMaterialProcessing(materialId: string): Promise<MaterialStatusResponse> {
  return requestJson<MaterialStatusResponse>(`/materials/${materialId}/retry`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    }
  });
}

export async function fetchCourseMaterials(
  courseId: string,
  moduleId?: string | null
): Promise<CourseMaterialsResponse> {
  const suffix = moduleId ? `?module_id=${encodeURIComponent(moduleId)}` : "";
  return requestJson<CourseMaterialsResponse>(`/materials/course/${courseId}${suffix}`, {
    method: "GET",
    headers: {
      "Content-Type": "application/json"
    }
  });
}

export async function deleteMaterial(materialId: string): Promise<MaterialDeleteResponse> {
  return requestJson<MaterialDeleteResponse>(`/materials/${materialId}`, {
    method: "DELETE",
    headers: {
      "Content-Type": "application/json"
    }
  });
}

export async function fetchCourseDashboard(
  courseId: string,
  moduleId?: string | null
): Promise<CourseDashboardResponse> {
  const suffix = moduleId ? `?module_id=${encodeURIComponent(moduleId)}` : "";
  return requestJson<CourseDashboardResponse>(`/dashboard/${courseId}${suffix}`, {
    method: "GET",
    headers: {
      "Content-Type": "application/json"
    }
  });
}

export async function fetchCurrentWorkflow(): Promise<CurrentWorkflowResponse> {
  return requestJson<CurrentWorkflowResponse>("/workflow/current", {
    method: "GET",
    headers: {
      "Content-Type": "application/json"
    }
  });
}

export async function setCurrentWorkflow(
  courseId: string | null,
  moduleId?: string | null
): Promise<CurrentWorkflowResponse> {
  return requestJson<CurrentWorkflowResponse>("/workflow/current", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      course_id: courseId,
      module_id: moduleId ?? null
    })
  });
}

export async function fetchCourses(): Promise<CourseListResponse> {
  return requestJson<CourseListResponse>("/courses", {
    method: "GET",
    headers: {
      "Content-Type": "application/json"
    }
  });
}

export async function createCourse(payload: CreateCourseRequest): Promise<void> {
  await requestJson("/courses", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  });
}

export async function updateCourse(courseId: string, payload: CreateCourseRequest): Promise<void> {
  await requestJson(`/courses/${courseId}`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  });
}

export async function deleteCourse(courseId: string): Promise<DeleteScopeResponse> {
  return requestJson<DeleteScopeResponse>(`/courses/${courseId}`, {
    method: "DELETE",
    headers: {
      "Content-Type": "application/json"
    }
  });
}

export async function fetchModules(courseId: string): Promise<ModuleListResponse> {
  return requestJson<ModuleListResponse>(`/courses/${courseId}/modules`, {
    method: "GET",
    headers: {
      "Content-Type": "application/json"
    }
  });
}

export async function createModule(payload: CreateModuleRequest): Promise<void> {
  await requestJson("/courses/modules", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  });
}

export async function updateModule(
  moduleId: string,
  payload: Omit<CreateModuleRequest, "course_id">
): Promise<void> {
  await requestJson(`/courses/modules/${moduleId}`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  });
}

export async function deleteModule(moduleId: string): Promise<DeleteScopeResponse> {
  return requestJson<DeleteScopeResponse>(`/courses/modules/${moduleId}`, {
    method: "DELETE",
    headers: {
      "Content-Type": "application/json"
    }
  });
}

export async function fetchMaterialLibrary(): Promise<MaterialLibraryResponse> {
  return requestJson<MaterialLibraryResponse>("/courses/library", {
    method: "GET",
    headers: {
      "Content-Type": "application/json"
    }
  });
}

export async function generateQuiz(
  payload: QuizGenerationRequest
): Promise<QuizGenerationAcceptedResponse> {
  return requestJson<QuizGenerationAcceptedResponse>("/quiz/generate", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  });
}

export async function fetchQuizGenerationJob(
  jobId: string
): Promise<QuizGenerationJobResponse> {
  return requestJson<QuizGenerationJobResponse>(`/quiz/jobs/${jobId}`, {
    method: "GET",
    headers: {
      "Content-Type": "application/json"
    }
  });
}

export async function cancelQuizGenerationJob(
  jobId: string
): Promise<QuizGenerationCancelResponse> {
  return requestJson<QuizGenerationCancelResponse>(`/quiz/jobs/${jobId}/cancel`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    }
  });
}

export async function gradeQuiz(
  quizId: string,
  answers: QuizSubmissionAnswer[]
): Promise<QuizGradeResponse> {
  return requestJson<QuizGradeResponse>("/quiz/grade", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      quiz_id: quizId,
      answers
    })
  });
}

export async function fetchQuizReview(quizId: string): Promise<QuizReviewResponse> {
  return requestJson<QuizReviewResponse>(`/quiz/${quizId}/review`, {
    method: "GET",
    headers: {
      "Content-Type": "application/json"
    }
  });
}

export async function fetchStudyPackages(courseId: string): Promise<StudyPackageListResponse> {
  return requestJson<StudyPackageListResponse>(
    `/packages?course_id=${encodeURIComponent(courseId)}`,
    { method: "GET" }
  );
}

export async function createStudyPackage(
  payload: StudyPackageCreateRequest
): Promise<StudyPackageRecord> {
  return requestJson<StudyPackageRecord>("/packages", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
}

export async function buildStudyPackage(packageId: string): Promise<StudyPackageGenerationJob> {
  return requestJson<StudyPackageGenerationJob>(
    `/packages/${encodeURIComponent(packageId)}/build`,
    { method: "POST" }
  );
}

export async function fetchPackageJob(jobId: string): Promise<StudyPackageGenerationJob> {
  return requestJson<StudyPackageGenerationJob>(
    `/packages/jobs/${encodeURIComponent(jobId)}`,
    { method: "GET" }
  );
}

export async function fetchLatestPackageJob(
  packageId: string
): Promise<StudyPackageGenerationJob | null> {
  return requestJson<StudyPackageGenerationJob | null>(
    `/packages/${encodeURIComponent(packageId)}/jobs/latest`,
    { method: "GET" }
  );
}

export async function validateStudyPackage(
  packageId: string
): Promise<StudyPackageValidationReport> {
  return requestJson<StudyPackageValidationReport>(
    `/packages/${encodeURIComponent(packageId)}/validate`,
    { method: "POST" }
  );
}

export async function fetchPackageFiles(packageId: string): Promise<StudyPackageFileListResponse> {
  return requestJson<StudyPackageFileListResponse>(
    `/packages/${encodeURIComponent(packageId)}/files`,
    { method: "GET" }
  );
}

export async function fetchPackageVersions(
  packageId: string
): Promise<StudyPackageVersionListResponse> {
  return requestJson<StudyPackageVersionListResponse>(
    `/packages/${encodeURIComponent(packageId)}/versions`,
    { method: "GET" }
  );
}

export async function fetchPackageVersion(
  packageId: string,
  version: number
): Promise<StudyPackageVersionResponse> {
  return requestJson<StudyPackageVersionResponse>(
    `/packages/${encodeURIComponent(packageId)}/versions/${version}`,
    { method: "GET" }
  );
}

export function packageFileUrl(packageId: string, fileId: string): string {
  return `${API_BASE_URL}/packages/${encodeURIComponent(packageId)}/files/${encodeURIComponent(fileId)}`;
}

export function packageVersionFileUrl(
  packageId: string,
  version: number,
  fileId: string
): string {
  return `${API_BASE_URL}/packages/${encodeURIComponent(packageId)}/versions/${version}/files/${encodeURIComponent(fileId)}`;
}

export async function fetchImportedExamAttempts(
  packageId: string
): Promise<ImportedExamAttemptListResponse> {
  return requestJson<ImportedExamAttemptListResponse>(
    `/packages/${encodeURIComponent(packageId)}/attempts`,
    { method: "GET" }
  );
}

export async function importCompletedExam(
  packageId: string,
  file: File
): Promise<CompletedExamImportResponse> {
  const formData = new FormData();
  formData.append("file", file);
  return requestJson<CompletedExamImportResponse>(
    `/packages/${encodeURIComponent(packageId)}/attempts/import`,
    { method: "POST", body: formData }
  );
}

export async function deleteQuizAttempt(quizId: string): Promise<{ deleted: boolean; quiz_id: string }> {
  return requestJson<{ deleted: boolean; quiz_id: string }>(`/quiz/${quizId}`, {
    method: "DELETE",
    headers: {
      "Content-Type": "application/json"
    }
  });
}

export async function generateMockExam(
  payload: MockExamGenerationRequest
): Promise<MockExamGenerationResponse> {
  return requestJson<MockExamGenerationResponse>("/exams/generate", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  });
}

export async function fetchMockExamSources(courseId: string): Promise<MockExamSourceListResponse> {
  return requestJson<MockExamSourceListResponse>(
    `/exams/sources?course_id=${encodeURIComponent(courseId)}`,
    {
      method: "GET",
      headers: {
        "Content-Type": "application/json"
      }
    }
  );
}

export async function uploadMockExamSource(
  courseId: string,
  file: File,
  enableOcr: boolean
): Promise<MockExamSourceIngestResponse> {
  const formData = new FormData();
  formData.append("course_id", courseId);
  formData.append("enable_ocr", enableOcr ? "true" : "false");
  formData.append("file", file);

  return requestJson<MockExamSourceIngestResponse>("/exams/sources/upload", {
    method: "POST",
    body: formData
  });
}

export async function gradeMockExam(
  examId: string,
  answers: QuizSubmissionAnswer[]
): Promise<MockExamGradeResponse> {
  return requestJson<MockExamGradeResponse>("/exams/grade", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      exam_id: examId,
      answers
    })
  });
}

export async function fetchMockExamReview(examId: string): Promise<MockExamReviewResponse> {
  return requestJson<MockExamReviewResponse>(`/exams/${examId}/review`, {
    method: "GET",
    headers: {
      "Content-Type": "application/json"
    }
  });
}
