# Completed Exam HTML Import Implementation Plan

## Outcome

Deliver a package producer hub that exports reusable interactive HTML and accepts only completed generated exam HTML for trusted grading and progress import.

## Task 1: Lock the offline attempt format

- Add a canonical exam fingerprint helper.
- Add strict attempt-envelope and import-response schemas.
- Write failing renderer tests for `Save completed exam`, `attempt-data`, and imported-attempt restoration.
- Update the offline exam renderer to create a new completed HTML download after submission.
- Run the focused renderer tests.

## Task 2: Add secure parsing and persistence

- Write failing tests for inert script extraction, size/type validation, fingerprint mismatch, invalid choices, and duplicate attempts.
- Add an `HTMLParser`-based completed-exam parser that never executes uploaded content.
- Add an imported-attempt record and SQLite table with attempt ID uniqueness.
- Extend the package store with save, get, and list operations.
- Run package model, store, and schema tests.

## Task 3: Add canonical server-side import grading

- Write API integration tests that upload completed HTML.
- Verify package/version/file/exam binding against stored records.
- Translate choice indexes to canonical option IDs and call the existing grading service.
- Persist and return the authoritative grade; return the prior result for duplicate attempt IDs.
- Add list-attempts API support.
- Run package API and exam service tests.

## Task 4: Turn the package page into a producer hub

- Add typed frontend schemas and API functions for completed HTML import and attempt history.
- Write failing component tests for the three stages and import states.
- Refine the package workspace into Sources, Produce, and Evaluate and download stages.
- Keep generation workflows reachable without duplicating the mock-exam builder.
- Add an HTML-only file picker, inline result, and recent attempt history.
- Run frontend unit tests and type checking.

## Task 5: Exercise the real workflow

- Build the backend and frontend.
- Start both services on clear local ports.
- Generate or open a fixture offline exam, answer and submit it, and save completed HTML.
- Reopen the completed file and verify submitted state and explanations.
- Import the file through the package UI and verify authoritative score plus duplicate behavior.
- Capture desktop and mobile screenshots and obtain two independent read-only visual reviews.
- Fix any observed functional, accessibility, or layout defects.

## Task 6: Release gate

- Run Ruff, MyPy, backend pytest, frontend lint, tests, and production build.
- Confirm the working tree contains only intentional changes.
- Commit the verified implementation.
- Stop all local servers and confirm their ports are clear.
