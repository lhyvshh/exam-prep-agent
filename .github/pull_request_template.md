## Summary

- Describe the change and the user-facing outcome.

## Verification

- [ ] `make check`
- [ ] Backend-specific checks:
- [ ] Frontend-specific checks:
- [ ] Manual QA:

## Data and artifact hygiene

- [ ] No real API keys, local databases, parsed learner materials, OCR output, or unapproved model checkpoints are included.
- [ ] Screenshots under `docs/screenshots/` use synthetic or public-safe data; runtime captures with learner data remain excluded.
- [ ] Any added fixtures are deterministic and live under `backend/tests/fixtures/` or `frontend/tests/`.

## Notes for reviewers

- Call out risks, follow-ups, or manual QA details.
