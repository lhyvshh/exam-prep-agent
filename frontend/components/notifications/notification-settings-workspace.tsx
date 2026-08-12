"use client";

import React, { FormEvent, useEffect, useMemo, useState } from "react";

import {
  createReminderDraft,
  fetchMaterialLibrary,
  fetchNotificationPreference,
  fetchReminderDrafts,
  saveNotificationPreference,
  sendReminderDraft
} from "@/lib/api";
import type {
  CourseLibraryItem,
  NotificationPreference,
  ReminderDraft,
  ReminderType
} from "@/lib/schemas";

const defaultPreference = (courseId: string): NotificationPreference => ({
  course_id: courseId,
  email_enabled: false,
  email_address: null,
  daily_reminder_enabled: false,
  final_week_enabled: false,
  weak_concept_enabled: true,
  exam_date: null,
  preferred_reminder_time: "19:00",
  busy_windows: [],
  updated_at: null
});

export function NotificationSettingsWorkspace(): JSX.Element {
  const [courses, setCourses] = useState<CourseLibraryItem[]>([]);
  const [selectedCourseId, setSelectedCourseId] = useState<string>("");
  const [preference, setPreference] = useState<NotificationPreference | null>(null);
  const [drafts, setDrafts] = useState<ReminderDraft[]>([]);
  const [draftType, setDraftType] = useState<ReminderType>("weak_concept");
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [isDrafting, setIsDrafting] = useState<boolean>(false);

  useEffect(() => {
    let cancelled = false;
    async function loadCourses(): Promise<void> {
      try {
        const library = await fetchMaterialLibrary();
        if (cancelled) {
          return;
        }
        setCourses(library.courses);
        setSelectedCourseId((current) => current || library.courses[0]?.course.course_id || "");
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : "Unable to load courses.");
        }
      }
    }
    void loadCourses();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!selectedCourseId) {
      setPreference(null);
      setDrafts([]);
      return;
    }
    let cancelled = false;
    async function loadPreference(): Promise<void> {
      try {
        const [nextPreference, nextDrafts] = await Promise.all([
          fetchNotificationPreference(selectedCourseId),
          fetchReminderDrafts(selectedCourseId)
        ]);
        if (!cancelled) {
          setPreference(nextPreference);
          setDrafts(nextDrafts);
          setStatus(null);
          setError(null);
        }
      } catch (loadError) {
        if (!cancelled) {
          setPreference(defaultPreference(selectedCourseId));
          setError(loadError instanceof Error ? loadError.message : "Unable to load notification settings.");
        }
      }
    }
    void loadPreference();
    return () => {
      cancelled = true;
    };
  }, [selectedCourseId]);

  const selectedCourse = useMemo(
    () => courses.find((item) => item.course.course_id === selectedCourseId),
    [courses, selectedCourseId]
  );

  async function handleSave(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!preference || !selectedCourseId) {
      return;
    }
    setIsSaving(true);
    try {
      const saved = await saveNotificationPreference(selectedCourseId, {
        email_enabled: preference.email_enabled,
        email_address: preference.email_address || null,
        daily_reminder_enabled: preference.daily_reminder_enabled,
        final_week_enabled: preference.final_week_enabled,
        weak_concept_enabled: preference.weak_concept_enabled,
        exam_date: preference.exam_date || null,
        preferred_reminder_time: preference.preferred_reminder_time,
        busy_windows: preference.busy_windows
      });
      setPreference(saved);
      setStatus("Reminder preferences saved.");
      setError(null);
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Unable to save reminder preferences.");
    } finally {
      setIsSaving(false);
    }
  }

  async function handleDraft(): Promise<void> {
    if (!selectedCourseId) {
      return;
    }
    setIsDrafting(true);
    try {
      const draft = await createReminderDraft(selectedCourseId, draftType);
      setDrafts((current) => [draft, ...current.filter((item) => item.draft_id !== draft.draft_id)]);
      setStatus("Study Coach drafted a reminder and Quality Agent reviewed it.");
      setError(null);
    } catch (draftError) {
      setError(draftError instanceof Error ? draftError.message : "Unable to draft reminder.");
    } finally {
      setIsDrafting(false);
    }
  }

  async function handleSend(draftId: string): Promise<void> {
    try {
      const response = await sendReminderDraft(draftId);
      setDrafts((current) => current.map((item) => item.draft_id === draftId ? response.draft : item));
      setStatus(response.delivery_message);
      setError(null);
    } catch (sendError) {
      setError(sendError instanceof Error ? sendError.message : "Unable to send reminder.");
    }
  }

  return (
    <div className="stack">
      <section className="card notification-settings-card">
        <div className="section-header">
          <div>
            <h3>Reminder preferences</h3>
            <p className="subtle">Opt in by course. The Study Coach drafts the message; the Quality Agent checks it before sending.</p>
          </div>
          <span className="quality-badge">Opt-in only</span>
        </div>

        {error ? <p className="error-text">{error}</p> : null}
        {status ? <p className="success-text">{status}</p> : null}

        <form className="config-form" onSubmit={(event) => void handleSave(event)}>
          <label className="field">
            <span>Course</span>
            <select value={selectedCourseId} onChange={(event) => setSelectedCourseId(event.target.value)}>
              {courses.length === 0 ? <option value="">No courses yet</option> : null}
              {courses.map((item) => (
                <option key={item.course.course_id} value={item.course.course_id}>
                  {item.course.display_name}
                </option>
              ))}
            </select>
          </label>

          {preference ? (
            <>
              <div className="two-column-grid">
                <label className="toggle">
                  <input
                    checked={preference.email_enabled}
                    onChange={(event) => setPreference({ ...preference, email_enabled: event.target.checked })}
                    type="checkbox"
                  />
                  <span>Email reminders</span>
                </label>
                <label className="toggle">
                  <input
                    checked={preference.final_week_enabled}
                    onChange={(event) => setPreference({ ...preference, final_week_enabled: event.target.checked })}
                    type="checkbox"
                  />
                  <span>Final-week urgency mode</span>
                </label>
                <label className="toggle">
                  <input
                    checked={preference.daily_reminder_enabled}
                    onChange={(event) => setPreference({ ...preference, daily_reminder_enabled: event.target.checked })}
                    type="checkbox"
                  />
                  <span>Daily study nudge</span>
                </label>
                <label className="toggle">
                  <input
                    checked={preference.weak_concept_enabled}
                    onChange={(event) => setPreference({ ...preference, weak_concept_enabled: event.target.checked })}
                    type="checkbox"
                  />
                  <span>Weak-concept reinforcement</span>
                </label>
                <label className="field">
                  <span>Email address</span>
                  <input
                    placeholder="student@example.com"
                    type="email"
                    value={preference.email_address ?? ""}
                    onChange={(event) => setPreference({ ...preference, email_address: event.target.value })}
                  />
                </label>
                <label className="field">
                  <span>Exam date</span>
                  <input
                    type="date"
                    value={preference.exam_date ?? ""}
                    onChange={(event) => setPreference({ ...preference, exam_date: event.target.value })}
                  />
                </label>
                <label className="field">
                  <span>Preferred reminder time</span>
                  <input
                    type="time"
                    value={preference.preferred_reminder_time}
                    onChange={(event) => setPreference({ ...preference, preferred_reminder_time: event.target.value })}
                  />
                </label>
                <label className="field">
                  <span>Busy / away windows</span>
                  <input
                    placeholder="Mon 9-5, Fri evening"
                    type="text"
                    value={preference.busy_windows.join(", ")}
                    onChange={(event) => setPreference({ ...preference, busy_windows: splitList(event.target.value) })}
                  />
                </label>
              </div>
              <button className="primary-button" disabled={isSaving || !selectedCourseId} type="submit">
                {isSaving ? "Saving..." : "Save preferences"}
              </button>
            </>
          ) : null}
        </form>
      </section>

      <section className="card notification-settings-card">
        <div className="section-header">
          <div>
            <h3>Agent reminder draft</h3>
            <p className="subtle">
              {selectedCourse
                ? `Draft from ${selectedCourse.course.display_name} progress, memory, and weak concepts.`
                : "Choose a course to draft a reminder."}
            </p>
          </div>
          <span className="quality-badge">Quality reviewed</span>
        </div>
        <div className="action-row">
          <select value={draftType} onChange={(event) => setDraftType(event.target.value as ReminderType)}>
            <option value="weak_concept">Weak concept</option>
            <option value="daily">Daily nudge</option>
            <option value="final_week">Final week</option>
          </select>
          <button className="primary-button" disabled={isDrafting || !selectedCourseId} onClick={() => void handleDraft()} type="button">
            {isDrafting ? "Drafting..." : "Draft reminder"}
          </button>
        </div>

        {drafts.length === 0 ? (
          <p className="subtle">No reminder drafts for this course yet.</p>
        ) : (
          <div className="notification-draft-list">
            {drafts.map((draft) => {
              const alreadyDelivered = draft.status === "sent" || draft.status === "simulated_sent";

              return (
                <article className="notification-draft-card" key={draft.draft_id}>
                  <div className="section-header">
                    <div>
                      <span className="agent-chip">{draft.status.replace(/_/g, " ")}</span>
                      <h4>{draft.subject}</h4>
                    </div>
                    <button
                      className="secondary-button"
                      disabled={alreadyDelivered}
                      onClick={() => void handleSend(draft.draft_id)}
                      type="button"
                    >
                      {alreadyDelivered ? "Sent" : "Send / simulate"}
                    </button>
                  </div>
                  <pre>{draft.body}</pre>
                  <div className="agent-memory-notes">
                    {draft.quality_notes.map((note) => (
                      <span className="study-keyword-chip" key={note}>{note}</span>
                    ))}
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}

function splitList(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, 6);
}
