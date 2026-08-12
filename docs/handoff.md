# Handoff

## Date

2026-08-12

## Current Status

The current build is a course-first exam-prep platform with validated offline packages for PDF-based courses. FRM Part I remains a strict optional preset rather than a global assumption. The main learner flow is:

1. Open `/courses`.
2. Open a course workspace.
3. Use Book Library to upload/open a book.
4. Open a book module.
5. Study a section, open source, or generate a section quiz in floating windows.
6. Review quiz/exam history and missed questions from the course Wrong Questions tab.
7. Open Offline Package to validate and download a reusable study ZIP.

## Strongest Areas

- Course-first information architecture is in place.
- Book Library now replaces the old broad Materials/Study/Quiz tabs.
- Section study cards support study, quiz, source, and studied-state actions.
- Source, study, and quiz windows are movable, resizable, minimizable, and docked.
- Study Coach is connected to backend agent runs and can expose stored recommendations, chat, memory settings, and LangGraph trace.
- PyTorch quality scoring is part of the question pipeline and surfaced in quiz cards.
- Offline package versions, jobs, validation reports, and files are stored durably in SQLite.
- Standalone flashcards and mock exams retain progress locally and require no network connection.
- Generic PDF books create source-grounded concepts and at least the configured card count per concept.
- Source-defined mock exams preserve source length, choice count, LO/topic, and question type one for one.
- Learner ZIPs omit manifests and validation reports; those records remain available in the app.

## Main Recent Fixes

- Redirected legacy `/config`, `/dashboard`, `/mock-exam`, and `/wrong-questions` pages away from the old app frame.
- Tightened course/workspace/book-library visual sizing and reduced oversized typography.
- Made Study Coach details less noisy by grouping stored recommendations and LangGraph trace.
- Advanced the section-study pipeline version and strengthened parser cleanup against title pages, schedule/admin content, and merged bullet fragments.
- Updated architecture and handoff docs to match the current product shape.
- Added the package API, CLI, course workspace, immutable HTML/ZIP renderer, and strict FRM blueprint validation.
- Enforced backend download gating so direct URLs cannot bypass a failed validation result.
- Added multi-select learning-objective navigation and a scrollable card jump list to offline decks.
- Added a non-FRM PDF integration fixture and source-defined package validation.
- Added production Docker images, persistent Compose storage, OCR, and the tracked PyTorch checkpoint.

## Important Files

- `frontend/app/courses/page.tsx`
- `frontend/app/courses/[courseId]/overview/page.tsx`
- `frontend/app/courses/[courseId]/materials/page.tsx`
- `frontend/app/courses/[courseId]/mock-exam/page.tsx`
- `frontend/app/courses/[courseId]/wrong-questions/page.tsx`
- `frontend/app/courses/[courseId]/packages/page.tsx`
- `frontend/components/courses/course-library.tsx`
- `frontend/components/courses/course-materials-workspace.tsx`
- `frontend/components/agents/agent-coach-panel.tsx`
- `frontend/components/courses/course-workspace-frame.tsx`
- `backend/src/exam_prep/services/section_study_service.py`
- `backend/src/exam_prep/services/agent_orchestrator_service.py`
- `backend/src/exam_prep/ml/inference.py`
- `backend/src/exam_prep/packages/service.py`
- `backend/src/exam_prep/packages/validation.py`

## Next Recommended Polish

- Verify every Study Coach recommendation target opens the exact book/module/section state.
- Add fuller provider adapters behind the model hub.
- Compare new provider-generated exams against additional uploaded official samples as the corpus grows.
- Add browser-level smoke tests for floating windows, source viewer, and section quiz generation.
- Keep improving parser cleanup with real uploaded class materials as fixtures.

## Verification Checklist

Run these before calling the branch stable:

```bash
npm test --prefix frontend -- --run
npm run build --prefix frontend
EXAM_PREP_SQLITE_PATH=/tmp/exam_prep_eval.sqlite3 EXAM_PREP_MATERIAL_STORAGE_PATH=/tmp/exam_prep_eval_materials PYTHONPATH=backend/src python3 -m pytest backend/tests/integration/test_agentic_layer_api.py backend/tests/integration/test_dashboard_api.py backend/tests/integration/test_materials_api.py backend/tests/integration/test_mock_exam_api.py backend/tests/integration/test_quiz_api.py backend/tests/integration/test_quiz_job_flow.py backend/tests/unit/test_agent_service.py backend/tests/unit/test_question_pipeline.py backend/tests/unit/test_quiz_service.py
```
