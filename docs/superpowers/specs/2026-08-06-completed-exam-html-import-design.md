# Completed Exam HTML Import Design

## Goal

Turn the study-package workspace into a producer hub whose outputs work without the local app. A learner can complete a generated mock exam in any modern browser, save that completed attempt as a new self-contained HTML file, and later import that file into the web app for trusted grading and progress updates.

## Product Boundary

- Generated study cards and exams remain self-contained HTML downloads.
- Study-card HTML is output-only. Existing JSON progress export/import remains local to the card file.
- Only generated completed-exam HTML can be imported into the app.
- Imported HTML is used only for evaluation and progress. It cannot edit, regenerate, or replace source material.
- The package producer remains the canonical source of exam identity, questions, answer keys, and version metadata.

## Offline Exam Contract

Every generated exam contains an inert `study-data` JSON script with:

- package ID, package version, and file ID;
- canonical exam content;
- a SHA-256 fingerprint calculated from the canonical exam payload.

On submission, the exam creates an immutable attempt envelope containing:

- schema version;
- attempt ID;
- package ID, package version, file ID, exam ID, and content fingerprint;
- start and completion timestamps;
- remaining time;
- selected choice index per question;
- flagged question IDs.

`Save completed exam` downloads a new HTML file containing both the original `study-data` and the inert `attempt-data` JSON script. Opening that file restores the submitted result without a server. Starting a new attempt does not mutate a previously downloaded completed file.

## Trusted Import

The backend treats uploaded HTML as untrusted text and never renders or executes it.

1. Reject files over the configured size limit or without an HTML filename.
2. Use `html.parser.HTMLParser` to extract only `script[type="application/json"]#study-data` and `#attempt-data`.
3. Parse both blocks through strict Pydantic schemas.
4. Recalculate the canonical exam fingerprint and compare it with both payloads.
5. Verify package ID, version, file ID, exam ID, question IDs, and choice ranges.
6. Load the canonical stored exam and answer key by exam ID.
7. Regrade submitted choices on the server. Ignore any score or explanation present in the uploaded file.
8. Store the graded attempt under its attempt ID. Re-importing the same attempt is idempotent and returns the prior result.

The import endpoint never accepts API keys, remote URLs, arbitrary JSON files, or raw exam documents.

## Persistence

Imported attempts are stored separately from package files and generation jobs. Each record retains:

- immutable attempt identity and package/exam binding;
- sanitized answer and timing payload;
- authoritative server grade;
- import timestamp.

The package workspace can list its imported attempts in newest-first order. Existing quiz and exam analytics continue to receive the authoritative grade through the normal grading service.

## Producer Hub

The package workspace uses three compact stages:

1. **Sources** shows the four curriculum books and source-exam readiness.
2. **Produce** shows flashcard and mock-exam readiness, links to the exam producer for missing exams, and starts the validated package build when requirements pass.
3. **Evaluate and download** provides the package download, completed-exam HTML import, import result, and recent attempt history.

The import control is shown only when a completed package exists. Errors remain inline and name the corrective action. A successful import shows the authoritative score and whether the attempt was newly recorded or already present.

## Failure Behavior

- Missing JSON blocks: reject as an unsupported or incomplete exam file.
- Metadata or fingerprint mismatch: reject as modified or from another package.
- Unknown package version, file, or exam: reject without grading.
- Invalid question or choice IDs: reject the whole attempt.
- Duplicate attempt ID: return the existing grade without adding progress twice.
- Storage or grading failure: return a non-success response and preserve prior data.

## Verification

- Unit tests cover fingerprint stability, HTML extraction, tamper rejection, and renderer controls.
- API integration tests cover successful import, canonical regrading, and idempotency.
- Frontend tests cover staged producer status, HTML-only upload, success, duplicate, and error states.
- Browser QA completes an offline exam, downloads completed HTML, reopens it, imports it through the producer hub, and observes the server-generated score/history.
