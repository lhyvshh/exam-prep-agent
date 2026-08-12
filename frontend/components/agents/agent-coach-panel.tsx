"use client";

import React, { FormEvent, useMemo, useState } from "react";

import {
  chatWithAgent,
  runAgentCheck,
  trackActivityEvent
} from "@/lib/api";
import { currentButlerPageContext } from "@/lib/butler-context";
import type {
  AgentActionCard,
  AgentRecommendation,
  StudyScope
} from "@/lib/schemas";

type CoachMessage = {
  role: "user" | "assistant";
  text: string;
};

export function AgentCoachPanel({
  courseId,
  moduleId = null
}: {
  courseId: string;
  moduleId?: string | null;
}): JSX.Element {
  const [chatInput, setChatInput] = useState<string>("");
  const [chatMessages, setChatMessages] = useState<CoachMessage[]>([]);
  const [chatActions, setChatActions] = useState<AgentActionCard[]>([]);
  const [isOpen, setIsOpen] = useState<boolean>(false);
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [isChatting, setIsChatting] = useState<boolean>(false);
  const [responseMode, setResponseMode] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const scope = useMemo<StudyScope>(() => ({
    course_id: courseId,
    module_ids: moduleId ? [moduleId] : [],
    material_ids: [],
    section_ids: [],
    source_type: "study_material"
  }), [courseId, moduleId]);

  async function handleRunCheck(showOpen: boolean = true): Promise<void> {
    setIsRunning(true);
    try {
      const run = await runAgentCheck("progress_check", scope);
      setError(null);
      if (showOpen) {
        setIsOpen(true);
      }
      setChatActions(actionsFromRecommendations(run.recommendations.slice(0, 3)));
      setChatMessages((current) => [
        ...current.slice(-4),
        { role: "assistant", text: `Checked progress and prepared ${run.recommendations.length} next-step options.` }
      ]);
    } catch (runError) {
      setError(runError instanceof Error ? runError.message : "Unable to run progress check.");
    } finally {
      setIsRunning(false);
    }
  }

  async function handleCoachChat(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const message = chatInput.trim();
    if (!message || isChatting) {
      return;
    }
    setChatInput("");
    setChatMessages((current) => [...current.slice(-5), { role: "user", text: message }]);
    setIsChatting(true);
    try {
      const reply = await chatWithAgent(courseId, message, scope, currentButlerPageContext());
      setChatActions(reply.actions);
      setResponseMode(reply.response_mode ?? null);
      setChatMessages((current) => [...current.slice(-5), { role: "assistant", text: reply.message }]);
      setError(null);
    } catch (chatError) {
      setError(chatError instanceof Error ? chatError.message : "Exam Butler could not respond.");
    } finally {
      setIsChatting(false);
    }
  }

  return (
    <aside className={`agent-coach-panel${isOpen ? " agent-coach-panel-open" : ""}`} aria-label="Exam Butler agent">
      <button className="agent-coach-toggle" onClick={() => setIsOpen((current) => !current)} type="button">
        <span className="agent-pulse" aria-hidden="true" />
        <span>
          <strong>Exam Butler</strong>
          <small>Ask about this page</small>
        </span>
      </button>

      {isOpen ? (
        <div className="agent-coach-body">
          <div className="agent-coach-header">
            <div>
              <p className="eyebrow">Teaching assistant</p>
              <h3>Exam Butler</h3>
              <p className="subtle">Ask about the current page, a missed question, or a specific topic.</p>
            </div>
            <div className="action-row">
              {responseMode ? (
                <span className="quality-badge">
                  {responseMode === "live_llm" ? "Live model" : "Book-grounded fallback"}
                </span>
              ) : null}
              <button className="secondary-button" disabled={isRunning} onClick={() => void handleRunCheck()} type="button">
                {isRunning ? "Checking..." : "Run progress check"}
              </button>
            </div>
          </div>

          {error ? <p className="error-text">{error}</p> : null}

          <section className="agent-chat-card">
            <div className="agent-chat-log" aria-live="polite">
              {chatMessages.length === 0 ? (
                <p className="subtle">
                  Ask about this page, a missed question, or a specific topic.
                </p>
              ) : (
                chatMessages.map((message, index) => (
                  <p className={`agent-chat-message agent-chat-${message.role}`} key={`${message.role}-${index}`}>
                    <strong>{message.role === "user" ? "You" : "Butler"}:</strong> {sanitizeButlerCopy(message.text)}
                  </p>
                ))
              )}
            </div>
            <form className="agent-chat-form" onSubmit={(event) => void handleCoachChat(event)}>
              <input
                aria-label="Message Exam Butler"
                onChange={(event) => setChatInput(event.target.value)}
                placeholder="Ask about this page..."
                type="text"
                value={chatInput}
              />
              <button className="primary-button" disabled={isChatting || !chatInput.trim()} type="submit">
                {isChatting ? "Thinking..." : "Send"}
              </button>
            </form>
          </section>

          {chatActions.length > 0 ? (
            <div className="agent-action-card-list">
              {chatActions.map((action, index) => (
                action.href ? (
                  <a
                    className={action.tone === "primary" ? "primary-button" : "secondary-button"}
                    href={action.href}
                    key={`${action.action}-${index}`}
                    onClick={() => {
                      void trackActivityEvent({
                        course_id: courseId,
                        module_id: moduleId,
                        event_type: "recommendation_clicked",
                        metadata_json: {
                          origin: "exam_butler_chat",
                          action: action.action,
                          href: action.href,
                          payload: action.payload ?? {}
                        }
                      }).catch(() => undefined);
                    }}
                  >
                    {sanitizeButlerCopy(action.label)}
                  </a>
                ) : (
                  <span className="quality-badge" key={`${action.action}-${index}`}>
                    {action.label}
                  </span>
                )
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </aside>
  );
}

function recommendationHref(recommendation: AgentRecommendation): string | null {
  const href = recommendation.target_payload.href;
  return typeof href === "string" ? href : null;
}

function actionsFromRecommendations(recommendations: AgentRecommendation[]): AgentActionCard[] {
  const actions: AgentActionCard[] = [];
  for (const recommendation of recommendations) {
    const href = recommendationHref(recommendation);
    if (!href) {
      continue;
    }
    actions.push({
      label: actionLabel(recommendation.target_action),
      action: recommendation.target_action,
      href,
      payload: recommendation.target_payload,
      tone: recommendation.target_action === "study_section" || recommendation.target_action === "practice_concept"
        ? "primary"
        : "secondary"
    });
  }
  return actions;
}

function actionLabel(action: string): string {
  if (action === "study_section") {
    return "Study now";
  }
  if (action === "practice_concept") {
    return "Practice";
  }
  if (action === "mock_exam") {
    return "Mock exam";
  }
  if (action === "open_materials") {
    return "Open library";
  }
  return "Open";
}

function sanitizeButlerCopy(value: string | null | undefined): string {
  const raw = value ?? "";
  return raw
    .replace(/\b[a-f0-9]{20,}(?:-[a-z]+-\d+)?\b/gi, "this section")
    .replace(/\b[\w-]*section-\d+\b/gi, "this section")
    .replace(/\s{2,}/g, " ")
    .trim();
}
