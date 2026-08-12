import { afterEach, describe, expect, it, vi } from "vitest";

import { chatWithAgent, reprocessMaterial, validateConfig } from "@/lib/api";

describe("material API helpers", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("reprocesses a material through the hard parser pipeline", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({
      record: {
        material_id: "mat-1",
        course_id: "course-1",
        file_name: "book.pdf",
        content_type: "application/pdf",
        status: "completed",
        chunk_count: 10,
        section_count: 4,
        error_message: null
      }
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    await reprocessMaterial("mat-1");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/materials/mat-1/reprocess",
      expect.objectContaining({ method: "POST" })
    );
  });
});

describe("agent and config API helpers", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("saves the Butler model profile separately from the default model", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({
      is_valid: true,
      status: "demo_ready",
      message: "Demo mode is enabled.",
      config: {
        provider: "openai",
        model: "gpt-5.4",
        api_key: null,
        demo_mode: true
      },
      can_proceed: true
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    await validateConfig({
      provider: "openai",
      model: "gpt-5.4",
      api_key: null,
      demo_mode: true
    }, "butler");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/config/validate?profile=butler",
      expect.objectContaining({ method: "POST" })
    );
  });

  it("saves the parser agent model profile separately from the default model", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({
      is_valid: true,
      status: "demo_ready",
      message: "Demo mode is enabled.",
      config: {
        provider: "openai",
        model: "gpt-5.4-parser",
        api_key: null,
        demo_mode: true
      },
      can_proceed: true
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    await validateConfig({
      provider: "openai",
      model: "gpt-5.4-parser",
      api_key: null,
      demo_mode: true
    }, "parser");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/config/validate?profile=parser",
      expect.objectContaining({ method: "POST" })
    );
  });

  it("posts bounded Butler page context with chat requests", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({
      course_id: "course-1",
      message: "Grounded answer",
      response_mode: "grounded_fallback",
      actions: [],
      memory: {
        course_id: "course-1",
        preferred_study_style: "balanced",
        preferred_quiz_format: "mcq",
        default_question_count: 3,
        focus_areas: [],
        encouragement_style: "steady",
        progress_notes: [],
        updated_at: null
      },
      recommendations: [],
      active_agent_profile: {
        agent_name: "study_coach_agent",
        display_name: "Exam Butler",
        role: "Coach",
        personality: "Direct",
        skills: [],
        operating_rules: [],
        sample_line: null
      },
      agent_profiles: []
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    await chatWithAgent(
      "course-1",
      "Why did I miss question 10?",
      { course_id: "course-1", module_ids: [], material_ids: [], section_ids: [], source_type: "study_material" },
      {
        page_type: "quiz_review",
        route: "/courses/course-1/quiz",
        title: "Quiz review",
        visible_text: "Question 10 selected answer A correct answer C",
        source_ids: ["source-10"],
        material_ids: ["material-1"],
        section_ids: ["source-10"],
        question: null
      }
    );

    const request = ((fetchMock.mock.calls[0] as unknown[] | undefined)?.[1]) as RequestInit;
    const body = JSON.parse(String(request.body)) as { page_context?: { source_ids?: string[] } };
    expect(body.page_context?.source_ids).toEqual(["source-10"]);
  });
});
