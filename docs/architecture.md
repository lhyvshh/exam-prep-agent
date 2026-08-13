# Architecture

## Product Shape

The app is a course-first exam-prep workspace. Users open a course, upload books or lecture packs into the Book Library, study generated sections, quiz from those sections, build mock exams, and review missed questions with source traceability.

Current primary routes:

- `/courses`
- `/courses/[courseId]/overview`
- `/courses/[courseId]/materials`
- `/courses/[courseId]/mock-exam`
- `/courses/[courseId]/packages`
- `/courses/[courseId]/wrong-questions`
- `/settings/models`
- `/settings/notifications`

Legacy top-level routes redirect into the course-first structure.

## Frontend

The frontend lives in `frontend/` and uses Next.js. The main UX pieces are:

- Course Library with course management and compact AI setup modals.
- Course Workspace tabs for offline packages, overview, book library, and wrong questions.
- Book Library flow for upload, book detail, module pages, study sections, source viewing, and section quiz generation.
- Floating, movable, resizable study/source/quiz windows with a small dock for minimized windows.
- Study Coach panel with LLM-backed chat, stored recommendations, memory settings, and LangGraph trace visibility.

Frontend state stays thin. API contracts live in typed client helpers and schemas, while domain behavior stays backend-owned.

## Backend

The backend lives in `backend/src/exam_prep/` and is split into:

- `api/`: FastAPI routes and dependencies.
- `schemas/`: Pydantic contracts.
- `services/`: business logic for materials, study documents, quizzes, mock exams, agents, and notifications.
- `repositories/`: SQLite/file persistence boundaries.
- `ingestion/`: document extraction and parsing.
- `retrieval/`: source selection and grounding.
- `graph/`: LangGraph orchestration nodes.
- `ml/`: PyTorch quality scoring.

## Source Trust Layer

The shared source system resolves material, section, page, anchor text, extracted assets, and source file links. It is used by study cards, wrong-question review, history, mock exam review, and coach recommendations so the user can jump back to exact source context.

## Study Pipeline

Uploaded material is converted into study sections with:

- normalized titles
- exam summaries
- key points
- memorize terms
- syntax, formulas, and rules
- common traps
- difficulty
- page anchors and source ids

The section study service filters title-only pages, logistics, schedules, office-hour content, and low-signal fragments before creating quizable sections.

## Assessment Flow

Quizzes and mock exams use explicit scope:

- course
- modules
- materials
- sections
- source type

Section quizzes can run inside the floating quiz window so users do not lose their book/module context.

## Offline Package Pipeline

The hosted mock-exam service generates and stores source-grounded, quality-approved exam sessions.
The package service snapshots selected course books plus stored exam sessions into an immutable
version. Its provider-neutral path accepts 1-32 books and preserves every source exam question's
number, answer-choice count, topic/learning objective, question type, and difficulty. The separate FRM Part I
preset retains the 20/20/30/30 domain blueprint and fixed profile. Both paths enforce configured cards
per concept, cross-exam uniqueness, answer/source completeness, and PyTorch acceptance before assembly.

The assembler emits network-free learner HTML and one ZIP. SQLite privately stores package,
version, job, manifest, file, and validation records; operational reports are not placed in downloads.
Downloads are resolved under the configured material
root and are served only while the active version has a persisted passing validation report. The
frontend and `study-package` CLI call the same service boundary.

## Agent Layer

The visible agent layer is built around:

- Supervisor
- Materials Agent
- Assessment Agent
- Study Coach Agent
- Quality Agent

LangGraph runs store node status, agent messages, recommendations, and quality summaries. The Study Coach surfaces these as actions such as studying a section, practicing a concept, opening source, or starting a mock exam.

## PyTorch Quality Layer

The bundled PyTorch-trained question-quality model scores generated questions after deterministic
grounding, format, answer, rationale, and uniqueness checks. A native PyTorch checkpoint is preferred;
platforms without a supported wheel use a hash-verified NumPy export with tested score parity.
Low-quality outputs are regenerated and cannot enter an offline package. The training set includes
valid 3-choice through 8-choice assessment shapes so source format is not confused with quality.

## Testing

Key verification commands:

```bash
npm test --prefix frontend -- --run
npm run build --prefix frontend
EXAM_PREP_SQLITE_PATH=/tmp/exam_prep_eval.sqlite3 EXAM_PREP_MATERIAL_STORAGE_PATH=/tmp/exam_prep_eval_materials PYTHONPATH=backend/src python3 -m pytest backend/tests/integration/test_agentic_layer_api.py backend/tests/integration/test_dashboard_api.py backend/tests/integration/test_materials_api.py backend/tests/integration/test_mock_exam_api.py backend/tests/integration/test_quiz_api.py backend/tests/integration/test_quiz_job_flow.py backend/tests/unit/test_agent_service.py backend/tests/unit/test_question_pipeline.py backend/tests/unit/test_quiz_service.py
```

## Deployment Boundary

`docker-compose.yml` runs separate frontend and backend containers and persists all runtime state in
the `exam-prep-data` volume. The backend image includes OCR and the tracked quality checkpoint. The
application is designed for a single trusted study workspace; internet-facing multi-tenant hosting
would additionally require authentication, authorization, quotas, and tenant-isolated storage.

## Known Gaps

- Multi-provider routing has OpenAI/NVIDIA shape and settings UI, but additional providers need full request adapters.
- Email reminders are designed and partially modeled, but should remain opt-in and require real delivery-provider setup.
- Real provider output still benefits from periodic comparison against newly uploaded official exam samples.
