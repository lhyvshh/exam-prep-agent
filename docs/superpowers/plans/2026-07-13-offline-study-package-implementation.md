# Offline Study Package Generator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert validated course materials into versioned, downloadable, self-contained offline study files while preserving the existing hosted application and FRM Part I curriculum guardrails.

**Architecture:** Add a package domain beside the existing material, quiz, and exam domains. Package services consume existing parsed/study documents and exam records, validate immutable snapshots, render safe standalone HTML, persist metadata in SQLite, and store generated artifacts under the existing ignored runtime root. FastAPI and a secondary CLI call the same services; Next.js becomes the package-management surface.

**Tech Stack:** Python 3.11, Pydantic v2, FastAPI, SQLite, existing local repositories, PyTorch quality service, HTML/CSS/vanilla JavaScript offline runtimes, Next.js 15, React 18, TypeScript 5.6, pytest, Vitest, Playwright.

---

## File Map

New backend package code lives under `backend/src/exam_prep/packages/` so package schemas, policies,
renderers, validation, and assembly remain independent of the existing large study and question
services. Persistence protocols stay under `repositories/`; HTTP routes stay under `api/routes/`.

- `backend/src/exam_prep/packages/frm_policy.py`: typed FRM Part I allocation policy and arithmetic
- `backend/src/exam_prep/packages/models.py`: immutable package snapshots and export schemas
- `backend/src/exam_prep/packages/curriculum.py`: source-linked curriculum snapshot builder
- `backend/src/exam_prep/packages/rendering.py`: safe self-contained HTML renderers
- `backend/src/exam_prep/packages/validation.py`: hard validation results and completion gate
- `backend/src/exam_prep/packages/assembler.py`: manifest, hashes, files, and ZIP construction
- `backend/src/exam_prep/packages/service.py`: package application service and version orchestration
- `backend/src/exam_prep/packages/cli.py`: secondary command-line surface
- `backend/src/exam_prep/repositories/package_store.py`: persistence protocol
- `backend/src/exam_prep/repositories/sqlite/package_store.py`: SQLite metadata implementation
- `backend/src/exam_prep/api/routes/packages.py`: package CRUD, build, validate, and download API
- `frontend/components/packages/package-workspace.tsx`: package management experience
- `frontend/app/courses/[courseId]/packages/page.tsx`: course package route

---

### Task 1: FRM Part I Policy Contract

**Files:**
- Create: `backend/src/exam_prep/packages/__init__.py`
- Create: `backend/src/exam_prep/packages/frm_policy.py`
- Test: `backend/tests/unit/test_frm_package_policy.py`

- [ ] **Step 1: Write the failing allocation tests**

```python
from exam_prep.packages.frm_policy import FRM_PART_I_POLICY


def test_frm_part_i_major_domain_weights_and_three_exam_counts() -> None:
    policy = FRM_PART_I_POLICY
    assert policy.domain_weights == {
        "Foundations of Risk Management": 20,
        "Quantitative Analysis": 20,
        "Financial Markets and Products": 30,
        "Valuation and Risk Models": 30,
    }
    assert [sum(exam.values()) for exam in policy.exam_domain_counts] == [100, 100, 100]
    assert {
        domain: sum(exam[domain] for exam in policy.exam_domain_counts)
        for domain in policy.domain_weights
    } == {
        "Foundations of Risk Management": 60,
        "Quantitative Analysis": 60,
        "Financial Markets and Products": 90,
        "Valuation and Risk Models": 90,
    }


def test_frm_part_i_fallback_profiles_each_total_one_hundred() -> None:
    policy = FRM_PART_I_POLICY
    assert sum(policy.question_type_counts.values()) == 100
    assert [sum(profile.values()) for profile in policy.difficulty_counts] == [100, 100, 100]
    assert {domain: sum(counts.values()) for domain, counts in policy.subtopic_counts.items()} == (
        policy.domain_weights
    )
```

- [ ] **Step 2: Run the tests and confirm the missing module failure**

Run: `PYTHONPATH=backend/src python3 -m pytest backend/tests/unit/test_frm_package_policy.py -q`

Expected: collection fails because `exam_prep.packages.frm_policy` does not exist.

- [ ] **Step 3: Implement the frozen policy and import-time arithmetic checks**

```python
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FRMPartIPolicy:
    domain_weights: dict[str, int]
    exam_domain_counts: tuple[dict[str, int], dict[str, int], dict[str, int]]
    subtopic_counts: dict[str, dict[str, int]]
    question_type_counts: dict[str, int]
    difficulty_counts: tuple[dict[str, int], dict[str, int], dict[str, int]]

    def validate(self) -> None:
        if sum(self.domain_weights.values()) != 100:
            raise ValueError("FRM Part I domain weights must total 100.")
        if any(sum(exam.values()) != 100 for exam in self.exam_domain_counts):
            raise ValueError("Every FRM Part I mock exam must contain 100 questions.")
        if set(self.domain_weights) != set(self.subtopic_counts):
            raise ValueError("Every FRM Part I domain requires a subtopic policy.")


FRM_PART_I_POLICY = FRMPartIPolicy(
    domain_weights={
        "Foundations of Risk Management": 20,
        "Quantitative Analysis": 20,
        "Financial Markets and Products": 30,
        "Valuation and Risk Models": 30,
    },
    exam_domain_counts=(
        {
            "Foundations of Risk Management": 20,
            "Quantitative Analysis": 20,
            "Financial Markets and Products": 30,
            "Valuation and Risk Models": 30,
        },
        {
            "Foundations of Risk Management": 19,
            "Quantitative Analysis": 21,
            "Financial Markets and Products": 31,
            "Valuation and Risk Models": 29,
        },
        {
            "Foundations of Risk Management": 21,
            "Quantitative Analysis": 19,
            "Financial Markets and Products": 29,
            "Valuation and Risk Models": 31,
        },
    ),
    subtopic_counts={
        "Foundations of Risk Management": {
            "Risk types, risk appetite, and enterprise risk management": 4,
            "Corporate governance and risk-management frameworks": 3,
            "Portfolio theory, diversification, and efficient portfolios": 4,
            "CAPM, factor models, and risk-adjusted performance": 4,
            "Financial failures, crises, and risk-management lessons": 3,
            "Ethics and professional conduct": 2,
        },
        "Quantitative Analysis": {
            "Probability, random variables, and distributions": 4,
            "Sampling, estimation, and hypothesis testing": 3,
            "Correlation and linear regression": 4,
            "Multiple regression and model interpretation": 3,
            "Time-series analysis and forecasting": 3,
            "Simulation and Monte Carlo methods": 2,
            "Data quality and machine-learning concepts": 1,
        },
        "Financial Markets and Products": {
            "Financial institutions, exchanges, OTC markets, and clearing": 4,
            "Forwards and futures": 6,
            "Options and option strategies": 6,
            "Swaps": 5,
            "Fixed-income and credit-market instruments": 4,
            "Mortgages, mortgage-backed securities, and securitization": 3,
            "Foreign exchange and commodity markets": 2,
        },
        "Valuation and Risk Models": {
            "Discounting, arbitrage, and interest-rate fundamentals": 3,
            "Bond pricing, yields, and return measures": 3,
            "Duration, convexity, DV01, and term-structure risk": 5,
            "Binomial-tree and Black-Scholes-Merton valuation": 5,
            "Option Greeks and hedging": 3,
            "Value at Risk, Expected Shortfall, and risk measures": 5,
            "Volatility, correlation, and portfolio-risk estimation": 2,
            "Credit ratings, default risk, and country risk": 2,
            "Stress testing, backtesting, and model limitations": 2,
        },
    },
    question_type_counts={
        "Applied conceptual": 38,
        "Numerical calculation": 38,
        "Scenario or mini-case": 16,
        "Model interpretation and limitations": 6,
        "Ethics and professional conduct": 2,
    },
    difficulty_counts=(
        {"Foundational": 15, "Standard exam-level": 60, "Difficult": 25},
        {"Foundational": 14, "Standard exam-level": 60, "Difficult": 26},
        {"Foundational": 14, "Standard exam-level": 58, "Difficult": 28},
    ),
)
FRM_PART_I_POLICY.validate()
```

Keep these values identical to the approved design specification; changing them requires a new policy
version and matching allocation tests.

- [ ] **Step 4: Run the policy tests**

Run: `PYTHONPATH=backend/src python3 -m pytest backend/tests/unit/test_frm_package_policy.py -q`

Expected: `2 passed`.

---

### Task 2: Immutable Package Schemas

**Files:**
- Create: `backend/src/exam_prep/packages/models.py`
- Test: `backend/tests/unit/test_package_models.py`
- Modify: `Makefile`

- [ ] **Step 1: Write schema tests for strict validation and file identity**

```python
import pytest
from pydantic import ValidationError

from exam_prep.packages.models import PackageCreateRequest, PackageFile, PackageFileKind


def test_package_create_request_defaults_to_frm_part_i() -> None:
    request = PackageCreateRequest(course_id="course-1", title="FRM Part I 2026")
    assert request.exam_name == "Financial Risk Manager"
    assert request.exam_part == "Part I"
    assert request.mock_exam_count == 3
    assert request.questions_per_exam == 100
    assert request.cards_per_concept == 10


def test_package_file_rejects_parent_directory_paths() -> None:
    with pytest.raises(ValidationError):
        PackageFile(
            file_id="file-1",
            package_id="package-1",
            version=1,
            kind=PackageFileKind.FLASHCARDS,
            file_name="../unsafe.html",
            media_type="text/html",
            size_bytes=1,
            sha256="0" * 64,
        )
```

- [ ] **Step 2: Run the tests and confirm the missing model failure**

Run: `PYTHONPATH=backend/src python3 -m pytest backend/tests/unit/test_package_models.py -q`

Expected: collection fails because `exam_prep.packages.models` does not exist.

- [ ] **Step 3: Implement strict package schemas**

Define strict Pydantic v2 models and string enums for:

```python
class PackageStatus(StrEnum):
    DRAFT = "draft"
    BUILDING = "building"
    PARTIALLY_COMPLETE = "partially_complete"
    FAILED = "failed"
    COMPLETE = "complete"
    CANCELLED = "cancelled"


class PackageFileKind(StrEnum):
    FLASHCARDS = "flashcards"
    MOCK_EXAM = "mock_exam"
    FORMULA_REVIEW = "formula_review"
    EXAM_BLUEPRINT = "exam_blueprint"
    VALIDATION_HTML = "validation_html"
    VALIDATION_JSON = "validation_json"
    MANIFEST = "manifest"
    ZIP = "zip"


class PackageCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    exam_name: str = "Financial Risk Manager"
    exam_part: str = "Part I"
    mock_exam_count: int = Field(default=3, ge=1, le=10)
    questions_per_exam: int = Field(default=100, ge=1, le=200)
    cards_per_concept: Literal[10] = 10
    timer_minutes: int = Field(default=240, ge=0, le=720)
    include_formula_review: bool = True
    include_source_references: bool = True
```

Add `PackageRecord`, `PackageVersion`, `PackageFile`, `PackageManifest`, `ValidationFinding`,
`PackageValidationReport`, `OfflineFlashcard`, `OfflineFormula`, `OfflineExamQuestion`,
`OfflineMockExam`, and response wrapper models. Validate that file names are basenames and that hashes
are lowercase 64-character SHA-256 strings.

- [ ] **Step 4: Add `backend/src/exam_prep/packages` as the first path in the existing `BACKEND_TYPE_TARGETS` assignment**

Preserve every current target and add one continuation line containing
`backend/src/exam_prep/packages` before `backend/src/exam_prep/schemas`.

- [ ] **Step 5: Run schema tests and MyPy**

Run: `PYTHONPATH=backend/src python3 -m pytest backend/tests/unit/test_package_models.py -q`

Expected: `2 passed`.

Run: `make type-backend`

Expected: `Success: no issues found`.

---

### Task 3: SQLite Package Metadata Store

**Files:**
- Modify: `backend/src/exam_prep/db/sqlite.py`
- Create: `backend/src/exam_prep/repositories/package_store.py`
- Create: `backend/src/exam_prep/repositories/sqlite/package_store.py`
- Modify: `backend/src/exam_prep/api/deps.py`
- Modify: `backend/src/exam_prep/main.py`
- Test: `backend/tests/unit/test_package_store.py`
- Test: `backend/tests/unit/test_sqlite_schema.py`

- [ ] **Step 1: Write failing persistence and migration tests**

```python
def test_package_store_round_trips_version_and_files(database: SQLiteDatabase) -> None:
    store = SQLitePackageStore(database)
    package = package_fixture()
    store.create_package(package)
    store.save_version(version_fixture(package.package_id))
    store.replace_files(package.package_id, 1, [file_fixture(package.package_id)])
    assert store.get_package(package.package_id) == package
    assert store.get_version(package.package_id, 1) is not None
    assert len(store.list_files(package.package_id, 1)) == 1
```

Also assert `study_packages`, `package_versions`, `generation_jobs`, `generation_job_steps`, and
`export_files` exist after `SQLiteDatabase.initialize()`.

- [ ] **Step 2: Run the tests and confirm missing tables/store failures**

Run: `PYTHONPATH=backend/src python3 -m pytest backend/tests/unit/test_package_store.py backend/tests/unit/test_sqlite_schema.py -q`

Expected: failures identify the missing package store and tables.

- [ ] **Step 3: Add idempotent package tables and indexes**

Add `CREATE TABLE IF NOT EXISTS` statements to `SQLiteDatabase.initialize()` for package metadata,
immutable versions, durable jobs/steps, validation results, and export files. Store JSON snapshots as
text and artifacts as runtime-relative paths. Use `(package_id, version)` and
`(package_id, version, file_id)` uniqueness constraints.

- [ ] **Step 4: Implement the protocol and SQLite store**

Define a `PackageStore` protocol with these exact signatures: `create_package(record) ->
PackageRecord`, `get_package(package_id) -> PackageRecord | None`, `list_packages(course_id) ->
list[PackageRecord]`, `save_version(version) -> None`, `get_version(package_id, version) ->
PackageVersion | None`, `replace_files(package_id, version, files) -> None`, and
`list_files(package_id, version) -> list[PackageFile]`.

Use model JSON for immutable snapshots and explicit columns for queryable state. Convert rows through
private `_row_to_*` helpers.

- [ ] **Step 5: Register the store in application state and dependencies**

```python
app.state.package_store = SQLitePackageStore(database)


def get_package_store(request: Request) -> PackageStore:
    return cast(PackageStore, request.app.state.package_store)
```

- [ ] **Step 6: Run store tests and the existing SQLite suite**

Run: `PYTHONPATH=backend/src python3 -m pytest backend/tests/unit/test_package_store.py backend/tests/unit/test_sqlite_schema.py -q`

Expected: package tests pass and existing schema assertions remain green.

---

### Task 4: Curriculum Snapshot Builder

**Files:**
- Create: `backend/src/exam_prep/packages/curriculum.py`
- Test: `backend/tests/unit/test_package_curriculum.py`

- [ ] **Step 1: Write a failing source-linkage test**

```python
def test_curriculum_builder_groups_cards_and_formulas_by_material() -> None:
    snapshot = CurriculumSnapshotBuilder().build(
        course_id="course-1",
        materials=[material_record_fixture()],
        study_documents=[study_document_fixture()],
    )
    assert snapshot.books[0].material_id == "material-1"
    assert snapshot.books[0].concepts[0].source_pages == [12]
    assert len(snapshot.books[0].concepts[0].flashcards) == 10
    assert snapshot.books[0].formulas[0].source_page == 12
```

- [ ] **Step 2: Run the test and confirm the missing builder failure**

Run: `PYTHONPATH=backend/src python3 -m pytest backend/tests/unit/test_package_curriculum.py -q`

- [ ] **Step 3: Implement normalized snapshot construction**

The builder accepts records and study documents already loaded by `MaterialStore`; it performs no I/O.
Group sections, learning outcomes, concepts, flashcards, and formulas into immutable book snapshots.
Deduplicate concepts by normalized `(learning_outcome, title)` while unioning source pages and chunk
anchors. Reject cards without a concept or source page from export eligibility and report those counts
to validation rather than inventing metadata.

- [ ] **Step 4: Run curriculum tests**

Run: `PYTHONPATH=backend/src python3 -m pytest backend/tests/unit/test_package_curriculum.py -q`

Expected: source-linkage and exact-card grouping tests pass.

---

### Task 5: Safe Standalone HTML Renderers

**Files:**
- Create: `backend/src/exam_prep/packages/rendering.py`
- Test: `backend/tests/unit/test_package_rendering.py`

- [ ] **Step 1: Write failing safety and offline-runtime tests**

```python
def test_flashcard_renderer_embeds_data_safely_and_has_no_network_dependencies() -> None:
    html = OfflineRenderer().render_flashcards(flashcard_file_fixture(front="</script><script>bad()</script>"))
    assert "https://" not in html
    assert "http://" not in html
    assert "</script><script>bad()" not in html
    assert "localStorage" in html
    assert "data-action=\"next\"" in html


def test_mock_exam_renderer_hides_answers_until_submission() -> None:
    html = OfflineRenderer().render_mock_exam(mock_exam_fixture())
    assert "data-correct-answer" not in html
    assert "correctAnswerId" in html
    assert "state.submitted" in html
```

- [ ] **Step 2: Run the tests and confirm the missing renderer failure**

Run: `PYTHONPATH=backend/src python3 -m pytest backend/tests/unit/test_package_rendering.py -q`

- [ ] **Step 3: Implement safe JSON embedding**

```python
def _json_for_script(value: BaseModel | dict[str, object]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return raw.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
```

Render data into `<script type="application/json" id="study-data">` and read it with
`JSON.parse(document.getElementById("study-data").textContent)`. Build learner text with `textContent`,
not `innerHTML`.

- [ ] **Step 4: Implement the flashcard runtime**

Inline CSS and JavaScript for flip, previous/next, shuffle, search, filters, Again/Hard/Good/Easy,
source reveal, progress, reset, fullscreen, keyboard controls, responsive layout, namespaced
`localStorage`, and JSON progress import/export.

- [ ] **Step 5: Implement mock exam, formula review, blueprint, and validation renderers**

Mock exam runtime includes timer, navigation, flags, autosave, resume, confirmation, grading,
breakdowns, post-submit explanations, filters, history, print, JSON export, and reset. Formula and
blueprint runtimes include their approved search, filter, reveal, and source-reference controls.

- [ ] **Step 6: Run renderer tests**

Run: `PYTHONPATH=backend/src python3 -m pytest backend/tests/unit/test_package_rendering.py -q`

Expected: safety, no-network, storage namespace, and answer-visibility tests pass.

---

### Task 6: Validation, Manifest, and ZIP Assembly

**Files:**
- Create: `backend/src/exam_prep/packages/validation.py`
- Create: `backend/src/exam_prep/packages/assembler.py`
- Test: `backend/tests/unit/test_package_validation.py`
- Test: `backend/tests/integration/test_package_assembler.py`

- [ ] **Step 1: Write failing hard-gate tests**

```python
def test_validation_rejects_concept_with_nine_cards() -> None:
    report = PackageValidator().validate(snapshot_fixture(cards_per_concept=9))
    assert report.is_complete is False
    assert {finding.code for finding in report.hard_failures} == {"concept_card_count"}


def test_assembler_creates_hash_verified_zip(tmp_path: Path) -> None:
    result = PackageAssembler(tmp_path).assemble(valid_snapshot_fixture())
    assert result.manifest.content_counts.flashcards == 10
    assert result.zip_path.exists()
    with ZipFile(result.zip_path) as archive:
        assert "package-manifest.json" in archive.namelist()
        assert "01-Foundations-Flashcards.html" in archive.namelist()
```

- [ ] **Step 2: Run tests and confirm missing validator/assembler failures**

Run: `PYTHONPATH=backend/src python3 -m pytest backend/tests/unit/test_package_validation.py backend/tests/integration/test_package_assembler.py -q`

- [ ] **Step 3: Implement deterministic hard validation**

Check exact card counts, source references, unique question answers, FRM domain totals, subtopic bounds,
question-type and difficulty totals, duplicate fingerprints, sample-exam similarity findings, and
required output presence. PyTorch scores are recorded but cannot clear deterministic failures.

- [ ] **Step 4: Implement assembly and manifests**

Render each validated snapshot, compute SHA-256 and byte size, write atomically into
`<material_storage_path>/_packages/<package_id>/v<version>/`, create manifest and validation reports,
then build a ZIP with normalized relative paths. Refuse absolute or parent-directory archive entries.

- [ ] **Step 5: Run validation and assembler tests**

Run: `PYTHONPATH=backend/src python3 -m pytest backend/tests/unit/test_package_validation.py backend/tests/integration/test_package_assembler.py -q`

Expected: hard-gate and artifact integrity tests pass.

---

### Task 7: Package Service, Durable Jobs, and API

**Files:**
- Create: `backend/src/exam_prep/packages/service.py`
- Create: `backend/src/exam_prep/packages/jobs.py`
- Create: `backend/src/exam_prep/api/routes/packages.py`
- Modify: `backend/src/exam_prep/main.py`
- Modify: `backend/src/exam_prep/api/deps.py`
- Test: `backend/tests/integration/test_package_api.py`

- [ ] **Step 1: Write a failing API lifecycle test**

```python
def test_package_create_build_list_and_download(client: TestClient) -> None:
    package = client.post(
        "/api/v1/packages",
        json={"course_id": "course-1", "title": "FRM Part I 2026"},
    ).json()
    build = client.post(f"/api/v1/packages/{package['package_id']}/build")
    assert build.status_code == 202
    completed = wait_for_package_job(client, build.json()["job_id"])
    assert completed["status"] == "complete"
    files = client.get(f"/api/v1/packages/{package['package_id']}/files").json()["files"]
    assert files
    download = client.get(f"/api/v1/packages/{package['package_id']}/files/{files[0]['file_id']}")
    assert download.status_code == 200
```

- [ ] **Step 2: Run the test and confirm missing routes**

Run: `PYTHONPATH=backend/src python3 -m pytest backend/tests/integration/test_package_api.py -q`

- [ ] **Step 3: Implement application service and durable runner**

The service loads course materials and study documents, builds the snapshot, loads source/generated
exam records when configured, validates, assembles, and stores immutable metadata. The runner uses
bounded background execution and SQLite step checkpoints; `create`, `list`, `detail`, `build`,
`validate`, `regenerate`, `cancel`, `job status`, `file list`, and `download` operations are explicit.

- [ ] **Step 4: Add routes and register them**

```python
app.include_router(packages.router, prefix="/api/v1")
```

Downloads resolve only `PackageFile` records from the store and use `FileResponse` with the stored
media type and filename.

- [ ] **Step 5: Run API tests and curl a live fixture build**

Run: `PYTHONPATH=backend/src python3 -m pytest backend/tests/integration/test_package_api.py -q`

Expected: lifecycle, partial-failure, regeneration, and download tests pass.

---

### Task 8: Secondary CLI Surface

**Files:**
- Create: `backend/src/exam_prep/packages/cli.py`
- Modify: `pyproject.toml`
- Test: `backend/tests/unit/test_package_cli.py`

- [ ] **Step 1: Write failing `--help`, create, validate, and export tests**

Use `subprocess.run` against the installed `study-package` entry point and assert clear exit codes and
JSON output for machine use.

- [ ] **Step 2: Add the script entry point**

```toml
[project.scripts]
study-package = "exam_prep.packages.cli:main"
```

- [ ] **Step 3: Implement `create`, `validate`, and `export` subcommands**

Commands load the same settings, database, repositories, and `PackageService` as FastAPI. They do not
reimplement package logic.

- [ ] **Step 4: Run CLI tests and manually exercise help and bad input**

Run: `PYTHONPATH=backend/src python3 -m pytest backend/tests/unit/test_package_cli.py -q`

Run: `study-package --help`

Run: `study-package validate --package-id missing`

Expected: help exits 0; missing package exits non-zero with a concise message.

---

### Task 9: Package Management UI

**Files:**
- Modify: `DESIGN.md`
- Modify: `frontend/lib/schemas.ts`
- Modify: `frontend/lib/api.ts`
- Create: `frontend/components/packages/package-workspace.tsx`
- Create: `frontend/app/courses/[courseId]/packages/page.tsx`
- Modify: `frontend/components/courses/course-workspace-frame.tsx`
- Modify: `frontend/app/globals.css`
- Test: `frontend/tests/package-workspace.test.tsx`

- [ ] **Step 1: Update the design contract for package states and responsive behavior**

Define package stage rows, progress counts, validation severity, file download actions, empty/error
states, focus behavior, and mobile/tablet/desktop layout using existing tokens.

- [ ] **Step 2: Write failing UI tests**

```tsx
it("shows real generation counts and validated downloads", async () => {
  render(<PackageWorkspace courseId="course-1" />);
  expect(await screen.findByText("Flashcards accepted: 640 / 870")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Download all as ZIP" })).toHaveAttribute(
    "href",
    expect.stringContaining("/api/v1/packages/package-1/files/zip-1")
  );
});
```

- [ ] **Step 3: Add strict TypeScript schemas and API functions**

Define request/response types matching Pydantic aliases and add create, list, build, poll, validate,
regenerate, delete, preview, and download functions.

- [ ] **Step 4: Implement the package workspace**

Provide package creation, ordered book review, sample-exam status, configuration, actual generation
stages/counts, validation findings, and download center. Use semantic buttons and links, Lucide icons
if the project adds the existing icon dependency, and no fake progress animation.

- [ ] **Step 5: Add Packages as the primary course tab**

Keep Book Library and Wrong Questions accessible. Route the course root to Packages only after the
package route passes browser QA.

- [ ] **Step 6: Run frontend type, unit, and production build checks**

Run: `npm run typecheck --prefix frontend`

Run: `npm test --prefix frontend -- --run frontend/tests/package-workspace.test.tsx`

Run: `npm run build --prefix frontend`

Expected: all commands exit 0.

---

### Task 10: Direct Offline Browser Qualification and Documentation

**Files:**
- Create: `backend/tests/fixtures/package_course/`
- Create: `frontend/e2e/offline-package.spec.ts`
- Create: `frontend/playwright.config.ts`
- Modify: `frontend/package.json`
- Modify: `README.md`
- Create: `docs/offline-study-packages.md`
- Modify: `Makefile`

- [ ] **Step 1: Add deterministic curriculum and sample-exam fixtures**

Fixtures contain synthetic source material with two concepts, ten cards each, one formula, and a
small configurable exam. No production book text or user data is committed.

- [ ] **Step 2: Add a fixture package command**

```make
package-fixture:
	PYTHONPATH=backend/src python3 -m exam_prep.packages.cli export-fixture --output output/package-fixture
```

- [ ] **Step 3: Write Playwright `file://` interaction tests**

Open every generated HTML file directly. Record all requests and fail if any URL uses `http:` or
`https:`. Exercise flashcard flip/navigation/persistence, formula reveals, exam answer/flag/timer/
submit/grading/history, blueprint filters, reset behavior, and widths 375, 768, and 1280.

- [ ] **Step 4: Document operation and limitations**

Update the README and technical guide with architecture, environment variables, separate parser and
Butler model setup, upload/build/download workflow, outputs, migrations, tests, troubleshooting,
copyright-sensitive use, local artifact locations, and future agent automation.

- [ ] **Step 5: Extend the repository release gate**

```make
check: lint-backend type-backend test-backend type-frontend test-frontend build-frontend package-offline-test
```

- [ ] **Step 6: Run the complete release and manual QA gate**

Run: `make check`

Run: `make package-fixture`

Run: `npm run test:offline --prefix frontend`

Manually open each fixture file through `file://`, use its primary workflow, reload once, and inspect
the browser console and network panel.

Expected: all automated checks pass; all files work without network requests; the ZIP manifest hashes
match extracted file bytes.
