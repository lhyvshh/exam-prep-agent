# Repository Quality

This project is intended to be safe to clone, review, and run without local private study data.

## Tracked source

Tracked files should be deterministic source, tests, fixtures, documentation, or repository metadata.
Do not commit:

- provider API keys or `.env` files
- uploaded learner materials
- parsed document stores
- local SQLite databases
- OCR output
- model artifacts other than the allowlisted delivery checkpoint and its portable export
- generated evaluation reports other than the allowlisted delivery summary
- Playwright screenshots containing learner data

The ignored local output paths are listed in `.gitignore`.

The allowlisted quality dataset, checkpoint, portable export, and evaluation summary under
`backend/data/` and `backend/artifacts/` are deterministic deployment fixtures. Update them together
through the documented training and export commands, then include the resulting tests and metrics in
the same change.

## Verification gate

Run the full local gate before merging:

```bash
make check
```

This covers:

- backend linting with Ruff
- backend type checking with MyPy on the stable typed boundary
- backend tests
- frontend type checking
- frontend tests
- frontend production build

## Known cleanup debt

Some service and UI modules are larger than ideal because they still combine product logic,
generation rules, and presentation concerns. Split these only behind behavior-preserving tests.
The highest-priority candidates are:

- `backend/src/exam_prep/services/section_study_service.py`
- `backend/src/exam_prep/services/question_pipeline.py`
- `backend/src/exam_prep/ingestion/parsers.py`
- large route-level frontend pages under `frontend/app/courses/`

Do not split these files as a cosmetic change. Prefer extracting a tested domain boundary, such as a
rule bank, parser strategy, scoring policy, or UI component used by more than one page.

The current full-repo strict MyPy pass is not yet clean. Keep `make type-backend` green while
expanding the typed target set as the older repository, parser, and service modules are tightened.
