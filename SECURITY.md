# Security Policy

## Supported versions

The `main` branch is the supported development line.

## Reporting a vulnerability

Do not open a public issue for vulnerabilities, leaked credentials, or private learner data exposure. Report the issue privately to the repository owner with:

- affected route, script, or workflow
- reproduction steps
- expected impact
- relevant logs with secrets removed

## Secrets and local data

Never commit real provider API keys, local SQLite databases, parsed materials, generated model artifacts, OCR output, or screenshots containing learner data.

The sample `.env.example` intentionally leaves API key values blank.
