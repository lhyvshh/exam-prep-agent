# Exam Prep Agent Framework

Local-first exam preparation platform with a typed `FastAPI` backend, `LangGraph` orchestration boundaries, a `Next.js` frontend, local storage, and a required PyTorch-backed question quality gate.

## What is in this repo

- typed backend APIs for config, ingestion, retrieval, quizzes, remediation, mock exams, dashboard, and ML scoring
- mobile-friendly frontend pages for config, materials, dashboard, quiz, mock exam, and wrong-question review
- local document parsing for `PDF`, `DOCX`, `PPTX`, and `TXT`
- local retrieval and grounded question generation
- quiz grading, mastery tracking, wrong-concept storage, remediation, and mock exam analytics
- validated, self-contained study-card and mock-exam packages for PDF-based courses such as FRM, CFA, and other professional or academic exams
- a trainable PyTorch question quality classifier with local checkpoint and evaluation outputs
- backend and frontend automated tests, regression fixtures, and evaluation scripts
- GitHub CI, issue templates, contribution guidance, and artifact hygiene policy

## Repository layout

```text
backend/                 FastAPI app, domain logic, LangGraph boundaries, ML, tests, scripts
frontend/                Next.js app, typed API client, UI components, frontend tests
docs/                    Architecture notes, screenshot placeholders, handoff materials
backend/artifacts/       Versioned delivery checkpoint plus local evaluation reports
```

## Architecture

The full architecture write-up is in [docs/architecture.md](docs/architecture.md).

At a glance:

- API routes translate HTTP only
- deterministic services own ingestion, retrieval, grading, analytics, and exam logic
- repositories isolate local storage
- LangGraph state and node boundaries stay separate from deterministic services
- frontend types mirror backend response contracts
- delivery validation requires the bundled PyTorch checkpoint; heuristic scoring is diagnostic only
- FRM Part I remains an explicit preset with its 20/20/30/30 topic allocation
- source-defined exams preserve the uploaded exam's length, answer-choice count, topic/LO, question type, and difficulty one for one

## Fresh clone setup

### Prerequisites

- `Python 3.11+`
- `node`, `npm`, and `npx`
- optional but recommended: a virtual environment

### One-time install

1. Clone the repo and enter it.
2. Copy the env file:

```bash
cp .env.example .env
```

3. Install backend dependencies:

```bash
python3 -m pip install -e ".[dev]"
```

4. Install frontend dependencies:

```bash
npm install --prefix frontend
```

You can also use the bundled targets:

```bash
make setup
```

## Local startup

### Required env for live OpenAI use

Set these in `.env` when you want real provider-backed generation:

```bash
EXAM_PREP_DEMO_MODE=false
EXAM_PREP_DEFAULT_LLM_PROVIDER=openai
EXAM_PREP_DEFAULT_LLM_MODEL=gpt-5.4-mini
EXAM_PREP_OPENAI_API_BASE_URL=https://api.openai.com/v1
```

The actual API key and selected model can also be saved from the `/config` page and are persisted in
local SQLite state. NVIDIA remains supported as an alternate live provider.

### Backend

```bash
uvicorn exam_prep.main:app --app-dir backend/src --reload
```

Health endpoint:

```text
http://127.0.0.1:8000/api/v1/health
```

### Frontend

```bash
npm run dev --prefix frontend
```

Frontend URL:

```text
http://localhost:3000
```

If `3000` is already in use, Next.js will print another local port such as `http://localhost:3001`.
The frontend now proxies `/api/v1/*` calls to the backend automatically, so browser requests stay on
the frontend origin and local CORS issues are avoided.

### Full local workflow

1. Start the backend.
2. Start the frontend.
3. Open the frontend URL printed by Next.js.
4. Use the pages in this order:
   - config
   - materials
   - dashboard
   - quiz
   - mock exam
   - offline package
   - wrong-question review

## Offline study packages

Open a course and select **Offline Package** to create an immutable ZIP that can be reused on any
device without the local app. Upload one or more PDF books, then either build a study-card package or
upload a sample exam with its answer key and build a new source-matched mock exam. Study-card ZIPs
contain only interactive flashcard HTML; mock-exam ZIPs contain only learner-facing exam HTML.
Validation reports and manifests stay inside the app database and are never placed in learner ZIPs.

Study cards are grouped by descriptive learning objective and include multi-select objective filters,
a scrollable card browser, direct card jumps, local ratings, and progress import/export. Source-defined
mock exams keep the source exam's exact question count and per-question choice count, topic/learning
objective, question type, and difficulty while requiring different wording and content. Every delivered question
must have book evidence, a complete answer explanation, uniqueness checks, and accepted PyTorch
quality provenance. FRM Part I's fixed curriculum percentages remain available through the
`frm_part_i` package preset rather than being imposed on other courses.

The hosted mock-exam service owns question generation and durable exam sessions. Package export
consumes those stored, quality-approved sessions and renders them into network-free HTML; it does
not maintain a second generation pipeline.

The same workflow is available from the CLI:

```bash
study-package create --course-id COURSE_ID --title "FRM Part I Offline Package"
study-package list --course-id COURSE_ID
study-package validate --package-id PACKAGE_ID
study-package export --package-id PACKAGE_ID
```

`create` prints the package ID used by `validate` and `export`. Course materials must finish study
extraction, and the requested mock exams must already exist, before export can pass.

## Container deployment

The production compose file runs the API and web app with a persistent volume for SQLite, uploaded
books, generated exams, and package versions:

```bash
docker compose up --build
```

Open `http://localhost:3000`, configure separate parser and Butler models in the model settings page,
then upload course books. The backend image includes Tesseract for scanned PDFs and the versioned
PyTorch delivery checkpoint. For a hosted deployment, mount `/data` on durable storage, set
`EXAM_PREP_FRONTEND_ORIGIN` to the public frontend origin, and place both services behind TLS.

## Testing

### Backend test suite

```bash
PYTHONPATH=backend/src python3 -m pytest backend/tests
```

### Frontend test suite

```bash
npm test --prefix frontend
```

### Combined

```bash
make test
```

### Full release gate

Run the same gate used by CI before opening a pull request:

```bash
make check
```

Repository hygiene expectations are documented in [docs/repo-quality.md](docs/repo-quality.md).

## Evaluation and regression

### Question quality classifier artifacts

The delivery dataset, checkpoint, and training metrics are versioned so a fresh deployment has the
same quality gate:

- dataset: `backend/data/question_quality_labeled.jsonl`
- checkpoint: `backend/artifacts/question_quality_classifier.pt`
- training metrics: `backend/artifacts/question_quality_eval.json`

Use the tracked training script to regenerate local artifacts when needed:

- training script: [backend/scripts/train_question_quality.py](backend/scripts/train_question_quality.py)

### Regression fixtures

- question quality fixture: [backend/tests/fixtures/regression/question_quality_cases.json](backend/tests/fixtures/regression/question_quality_cases.json)
- grading consistency fixture: [backend/tests/fixtures/regression/grading_consistency_cases.json](backend/tests/fixtures/regression/grading_consistency_cases.json)

### Example evaluation script

```bash
PYTHONPATH=backend/src python3 backend/scripts/evaluate_quality_and_grading.py
```

This writes a combined report to:

- `backend/artifacts/evaluation_report.json`

## Screenshots

Screenshot placeholders live in [docs/screenshots/README.md](docs/screenshots/README.md).

Suggested captures:

- config page
- materials upload
- dashboard
- quiz flow
- mock exam flow
- wrong-question review

## Current verification status

Most recently verified locally:

- backend test suite passing
- frontend test suite passing
- frontend dev server starts successfully
- offline package API, CLI, validation, download, and standalone browser flows pass
- PyTorch training script runs and saves a checkpoint
- PyTorch inference wrapper loads the saved checkpoint

## Roadmap

- deepen graph orchestration around longer remediation and exam workflows
- add richer retrieval ranking and section-level filtering
- add end-to-end frontend flows for submitting remediation answers
- upgrade frontend visual polish and accessibility audits
- expand regression fixtures for ingestion edge cases and mock exam grading
- expand CI coverage with browser smoke tests and selected evaluation checks
- add hosted observability and backup/restore runbooks

## Handy commands

```bash
make setup
make test
make check
make eval
make run-backend
make run-frontend
```
