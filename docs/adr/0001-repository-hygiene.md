# ADR 0001: Repository Hygiene

## Status

Accepted.

## Context

The app works with private learner materials, generated retrieval stores, model checkpoints, and
evaluation outputs. Most of those files are local-only, but the production quality gate requires a
small deterministic dataset, checkpoint, and evaluation summary in every clean checkout.

## Decision

The repository tracks source, tests, deterministic fixtures, documentation, GitHub metadata, and the
versioned delivery artifacts explicitly allowlisted in `.gitignore`. Local materials, parsed data,
experimental checkpoints, ad hoc reports, and temporary outputs stay ignored.

CI runs backend lint/type/test checks and frontend type/test/build checks on pull requests and pushes
to `main`.

## Consequences

- A fresh clone is lightweight and does not contain private study material.
- The bundled PyTorch delivery checkpoint is reproducible from the versioned labeled fixture.
- Contributors must add deterministic fixtures instead of committing generated local outputs.
