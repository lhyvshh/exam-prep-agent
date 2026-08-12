# Contributing

## Local setup

```bash
cp .env.example .env
python3 -m pip install -e ".[dev]"
npm install --prefix frontend
```

Install the optional ML runtime only when you need PyTorch inference or training:

```bash
python3 -m pip install -e ".[dev,ml]"
```

## Quality checks

Run the full local gate before opening a pull request:

```bash
make check
```

For faster backend-only work:

```bash
make lint-backend
make type-backend
make test-backend
```

For faster frontend-only work:

```bash
make type-frontend
make test-frontend
make build-frontend
```

## Data and artifacts

Do not commit local learner data, generated material stores, model checkpoints, OCR output, or Playwright screenshots. These paths are intentionally ignored:

- `data/`
- `backend/data/`
- `backend/artifacts/`
- `output/`
- `tmp/`

Use fixtures under `backend/tests/fixtures/` for deterministic test data.

## Pull request expectations

- Keep backend contracts typed with Pydantic models.
- Keep frontend API types aligned with backend schemas.
- Add or update tests when behavior changes.
- Include manual QA notes for UI, ingestion, quiz, or mock-exam changes.
- Keep generated files out of the diff unless they are explicit test fixtures.
