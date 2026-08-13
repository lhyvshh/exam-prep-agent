BACKEND_TYPE_TARGETS := \
	backend/src/exam_prep/packages \
	backend/src/exam_prep/schemas \
	backend/src/exam_prep/core \
	backend/src/exam_prep/domain \
	backend/src/exam_prep/llm/base.py \
	backend/src/exam_prep/llm/models.py \
	backend/src/exam_prep/llm/registry.py \
	backend/src/exam_prep/agent_core/models.py \
	backend/src/exam_prep/agent_core/profiles.py \
	backend/src/exam_prep/ml/inference.py \
	backend/src/exam_prep/ml/question_quality_model.py

.PHONY: setup-backend setup-frontend setup lint-backend type-backend test-backend type-frontend test-frontend test-e2e-offline build-frontend test check eval run-backend run-frontend

setup-backend:
	python3 -m pip install -e ".[dev]"

setup-frontend:
	npm install --prefix frontend

setup: setup-backend setup-frontend

lint-backend:
	python3 -m ruff check backend/src backend/tests

type-backend:
	python3 -m mypy $(BACKEND_TYPE_TARGETS)

test-backend:
	PYTHONPATH=backend/src python3 -m pytest backend/tests

type-frontend:
	npm run typecheck --prefix frontend

test-frontend:
	npm test --prefix frontend -- --run

test-e2e-offline:
	npm run test:e2e:offline --prefix frontend

build-frontend:
	npm run build --prefix frontend

test: test-backend test-frontend

check: lint-backend type-backend test-backend type-frontend test-frontend test-e2e-offline build-frontend

eval:
	PYTHONPATH=backend/src python3 backend/scripts/evaluate_quality_and_grading.py

run-backend:
	uvicorn exam_prep.main:app --app-dir backend/src --reload --reload-exclude "data/*"

run-frontend:
	npm run dev --prefix frontend
