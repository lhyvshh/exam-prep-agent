# Offline Study Package Generator Design

## Status

Drafted from the architecture approved on 2026-07-13. Awaiting final specification review before
implementation planning.

## Product Goal

Transform the hosted exam-prep application into an authoring and validation system that produces
downloadable study packages. The generated files become the primary learner experience and must
work in a normal browser without a server, account, API key, internet connection, or installed app.

The first production target is FRM Part I with four curriculum books, one uploaded sample exam,
one flashcard file per book, three mock exams, formula review, exam blueprint, package manifest,
validation reports, and a complete ZIP. The architecture must also support courses with other book
counts and exam blueprints.

## Product Decisions

1. Every learner-facing output is a self-contained HTML document by default. CSS, JavaScript,
   structured content, and required formula rendering are embedded in the file.
2. The ZIP is a transport container, not a runtime dependency. A learner may move any generated
   HTML file independently and open it by double-clicking it.
3. The hosted application remains responsible for uploads, corrections, model configuration,
   generation, validation, previews, version management, and downloads.
4. Existing hosted study pages remain available as compatibility and preview surfaces. Package
   generation becomes the primary course workflow; working ingestion and study behavior is not
   deleted merely because an offline counterpart exists.
5. Completed package versions are immutable. Regeneration creates a new content or file version and
   never silently mutates a previously completed download.
6. A package is complete only when every configured hard quality gate passes. Partial outputs may be
   downloaded only when clearly labeled incomplete and must never masquerade as a validated package.
7. User-uploaded books are the source of truth for facts, formulas, learning objectives, and source
   references. The uploaded sample exam supplies style and allocation signals, not reusable wording.

## Chosen Architecture

The implementation extends the existing FastAPI, SQLite, retrieval, LLM-provider, PyTorch-quality,
and Next.js architecture. It does not introduce a second application stack.

```text
Uploaded curriculum PDFs       Uploaded sample exam PDF
           |                              |
 Existing material pipeline       Existing exam source parser
           |                              |
 Normalized curriculum map          Editable exam blueprint
           |                              |
 Concepts and formulas <--------- generation constraints
           |
 Candidate generation
           |
 Grounding, independent answer checks, PyTorch scoring, deduplication
           |
 Constrained card and exam assembly
           |
 Versioned package snapshot
           |
 Safe standalone HTML renderers
           |
 Manifest, validation reports, individual downloads, ZIP
```

## System Boundaries

### 1. Curriculum Extraction

Reuse the current material ingestion, parsing, page preservation, section hierarchy, chunk storage,
and retrieval indexing. Add a normalization step that converts parsed sections into explicit books,
chapters or readings, modules, learning objectives, concepts, and formulas.

Each normalized concept contains stable identifiers, hierarchy references, source page numbers, and
source chunk identifiers. Concepts are merged only when they are superficial wording variants. A
different definition, formula, assumption, application, risk implication, or learning objective
keeps a concept distinct.

The existing parser remains authoritative for raw extraction. The normalization service owns concept
identity and is the only source accepted by card generation. Arbitrary isolated chunks cannot create
cards directly.

### 2. Sample Exam Analysis

Reuse the existing mock-exam source upload and question/answer extraction services. Add a blueprint
analyzer that records both exam-level distributions and one record per source question:

- topic, subtopic, and mapped learning objective
- question type and cognitive level
- difficulty and estimated time
- answer-choice count and wording characteristics
- formula family and calculation steps
- scenario length and distractor patterns
- ordering and cross-topic behavior

Blueprint fields are editable before generation. Observed sample characteristics, configured
curriculum guardrails, and system generation decisions remain separate so the UI and exported
blueprint never imply that a fallback was measured from the sample.

### 3. Flashcard Generation

Generate exactly ten accepted cards for every included concept. The ten slots represent definition,
intuition, formula, formula interpretation, application, scenario, comparison, common trap, worked
step or decision, and synthesis. A slot may adapt for qualitative concepts, but it cannot collapse
into a paraphrase of another slot.

Candidate generation receives the concept, learning objective, retrieved passages, formula records,
nearby concepts when needed, and source metadata. Validation rejects unsupported claims, ambiguous
prompts, answer leakage, duplicate prompts, inconsistent notation, invalid page references, and
irrelevant card types. A concept remains incomplete until all ten slots have accepted cards.

### 4. Formula Review

Formula records are extracted from normalized curriculum content and retain variable definitions,
units, assumptions, valid-use conditions, invalid-use conditions, related formulas, examples, traps,
and source references. Formula markup is converted to safe inline presentation at render time. The
offline file cannot depend on a MathJax or KaTeX CDN.

### 5. Mock Exam Generation

Mock exams use a staged pipeline rather than a single generation call:

1. Create constrained question specifications from the blueprint and curriculum coverage targets.
2. Generate at least 1.5 candidates per required final question, increasing the multiplier for weak
   topics or high duplicate rates.
3. Independently verify conceptual support or recompute quantitative answers.
4. Score grounding, correctness, clarity, distractors, style, relevance, difficulty, uniqueness, and
   estimated time.
5. Assemble the highest-quality valid set under hard allocation constraints.

FRM Part I defaults to three 100-question, four-choice exams with a four-hour timer. The uploaded
curriculum remains the factual source, and the uploaded sample exam refines style and the permitted
small variations. The following curriculum and allocation guardrails are mandatory defaults. They
live in versioned configuration, not scattered constants in service or UI files.

#### FRM Part I Major-Domain Allocation

| Domain | Weight | Baseline questions |
| --- | ---: | ---: |
| Foundations of Risk Management | 20% | 20 |
| Quantitative Analysis | 20% | 20 |
| Financial Markets and Products | 30% | 30 |
| Valuation and Risk Models | 30% | 30 |
| Total | 100% | 100 |

Unless the user explicitly overrides it, the three-exam variation is:

| Domain | Mock Exam 1 | Mock Exam 2 | Mock Exam 3 | Combined |
| --- | ---: | ---: | ---: | ---: |
| Foundations of Risk Management | 20 | 19 | 21 | 60 |
| Quantitative Analysis | 20 | 21 | 19 | 60 |
| Financial Markets and Products | 30 | 31 | 29 | 90 |
| Valuation and Risk Models | 30 | 29 | 31 | 90 |
| Total | 100 | 100 | 100 | 300 |

This variation returns to the 20% / 20% / 30% / 30% curriculum weighting across the full package.
Random candidate generation cannot change these assembled major-domain counts.

#### Foundations of Risk Management

Baseline: 20 questions per exam.

| Subtopic | Baseline questions |
| --- | ---: |
| Risk types, risk appetite, and enterprise risk management | 4 |
| Corporate governance and risk-management frameworks | 3 |
| Portfolio theory, diversification, and efficient portfolios | 4 |
| CAPM, factor models, and risk-adjusted performance | 4 |
| Financial failures, crises, and risk-management lessons | 3 |
| Ethics and professional conduct | 2 |

Default style mix: 10 applied conceptual, 4 calculations or quantitative interpretations, 4 short
scenarios, and 2 ethics questions.

#### Quantitative Analysis

Baseline: 20 questions per exam.

| Subtopic | Baseline questions |
| --- | ---: |
| Probability, random variables, and distributions | 4 |
| Sampling, estimation, and hypothesis testing | 3 |
| Correlation and linear regression | 4 |
| Multiple regression and model interpretation | 3 |
| Time-series analysis and forecasting | 3 |
| Simulation and Monte Carlo methods | 2 |
| Data quality and machine-learning concepts | 1 |

Default style mix: 9 calculations, 6 statistical interpretations, 3 model-selection or diagnostic
questions, and 2 applied scenarios.

#### Financial Markets and Products

Baseline: 30 questions per exam.

| Subtopic | Baseline questions |
| --- | ---: |
| Financial institutions, exchanges, OTC markets, and clearing | 4 |
| Forwards and futures | 6 |
| Options and option strategies | 6 |
| Swaps | 5 |
| Fixed-income and credit-market instruments | 4 |
| Mortgages, mortgage-backed securities, and securitization | 3 |
| Foreign exchange and commodity markets | 2 |

Default style mix: 11 calculations, 10 product-mechanics questions, 6 hedging or risk-management
scenarios, and 3 market-structure questions.

#### Valuation and Risk Models

Baseline: 30 questions per exam.

| Subtopic | Baseline questions |
| --- | ---: |
| Discounting, arbitrage, and interest-rate fundamentals | 3 |
| Bond pricing, yields, and return measures | 3 |
| Duration, convexity, DV01, and term-structure risk | 5 |
| Binomial-tree and Black-Scholes-Merton valuation | 5 |
| Option Greeks and hedging | 3 |
| Value at Risk, Expected Shortfall, and risk measures | 5 |
| Volatility, correlation, and portfolio-risk estimation | 2 |
| Credit ratings, default risk, and country risk | 2 |
| Stress testing, backtesting, and model limitations | 2 |

Default style mix: 14 calculations, 7 model-interpretation questions, 6 risk-management scenarios,
and 3 model-limitation or validation questions.

#### Subtopic Variation Rules

- Preserve the exact major-domain count for each exam from the three-exam table.
- Permit most subtopics to vary by approximately one question from baseline.
- Do not omit a major subtopic or concentrate all advanced questions in one subtopic.
- Return close to the combined baseline subtopic allocation across all three exams.
- Use sample-exam evidence to choose small increases or decreases.
- Do not generate content outside the uploaded curriculum.

#### Question-Type Fallback

When the sample exam cannot be classified reliably, each 100-question exam uses:

| Question type | Target count |
| --- | ---: |
| Applied conceptual | 38 |
| Numerical calculation | 38 |
| Scenario or mini-case | 16 |
| Model interpretation and limitations | 6 |
| Ethics and professional conduct | 2 |
| Total | 100 |

#### Difficulty Fallback

| Difficulty | Mock Exam 1 | Mock Exam 2 | Mock Exam 3 |
| --- | ---: | ---: | ---: |
| Foundational | 15 | 14 | 14 |
| Standard exam-level | 60 | 60 | 58 |
| Difficult | 25 | 26 | 28 |
| Total | 100 | 100 | 100 |

Mock Exam 3 may be slightly harder but cannot require content outside the uploaded curriculum.
Difficulty is determined by reasoning steps, formula selection and count, distractor plausibility,
cross-concept integration, scenario length, numerical complexity, interpretation, and irrelevant
information, not by vocabulary alone.

The assembly layer rejects exact text duplicates, normalized reskins, semantic near-duplicates, and
questions that share both a narrow learning objective and solution template. It checks within an exam,
across all generated exams in the package, across prior completed package versions for the course,
and against the uploaded sample exam.

### 6. Validation

Validation is a separate domain service. Generation services produce candidates; they do not decide
that a package is complete.

Hard failures include:

- any included concept with fewer or more than ten accepted cards
- any required exam with fewer than its configured accepted question count
- no unique correct answer or more than one valid answer
- missing or fabricated source references
- allocation outside configured hard bounds
- prohibited duplicate or sample-exam similarity
- failed safe-rendering checks
- any exported learner file that fails direct offline browser verification

The existing PyTorch classifier remains one signal inside a mature composite gate. It cannot override
a deterministic grounding, answer, schema, allocation, deduplication, or offline-rendering failure.

Every package version receives machine-readable JSON and human-readable HTML validation reports.

### 7. Offline Rendering

Create four focused renderers:

- flashcard application renderer
- mock-exam application renderer
- formula-review application renderer
- exam-blueprint and validation-report renderer

Renderers accept validated snapshot schemas and return bytes. They do not call repositories, models,
or retrieval services. A shared build step injects compact inline CSS and JavaScript into each file.

Structured content is serialized as JSON, escaped for an HTML script context, and parsed at runtime.
All user, model, and source-derived text is rendered through text-safe DOM APIs. Uploaded content must
never become executable HTML or JavaScript.

Every rendered file includes a package ID, file ID, and content version. Local storage keys use all
three values so separate packages and regenerated files cannot overwrite one another.

### 8. Package Assembly

The package assembler creates:

```text
<package-slug>/
  01-<book-title>-Flashcards.html
  ... one flashcard file per book
  Mock-Exam-1.html
  Mock-Exam-2.html
  Mock-Exam-3.html
  Formula-Review.html
  Exam-Blueprint.html
  Validation-Report.html
  validation-report.json
  package-manifest.json
  <package-slug>.zip
```

The manifest records package and file versions, hashes, sizes, content counts, validation summary,
source document versions, model metadata, prompt versions, and generator version. ZIP paths are
normalized and cannot escape the package root.

## Data Model

Add SQLite migrations for focused package-generation tables. Existing course, material, chunk, quiz,
and exam records remain intact.

Core records:

- `study_packages`: package identity, course, configuration, active version, and lifecycle state
- `package_versions`: immutable generation snapshot and configuration version
- `curriculum_nodes`: normalized hierarchy with source ownership
- `learning_objectives`: normalized objective labels and hierarchy links
- `concepts`: accepted testable units and source metadata
- `formulas`: normalized formula records and source metadata
- `exam_blueprints`: editable exam-level analysis and guardrails
- `exam_blueprint_questions`: per-source-question structural analysis
- `flashcard_candidates` and `flashcards`: candidate lineage and accepted cards
- `question_specs`, `question_candidates`, and `validated_questions`: staged question lineage
- `generated_exams` and `generated_exam_questions`: ordered immutable exam snapshots
- `generation_jobs` and `generation_job_steps`: durable orchestration and checkpoints
- `validation_results`: typed validation findings and evidence
- `export_files`: rendered file metadata, hash, path, state, and version

Large source text and generated binaries stay in ignored local storage. SQLite stores metadata,
content records, version links, and artifact paths. Repository interfaces isolate persistence from
services and retain the existing local-first deployment model.

## Durable Job Model

Package generation runs outside request lifetimes. API calls create or control jobs; background
workers execute idempotent steps.

States are `queued`, `running`, `paused`, `partially_complete`, `failed`, `complete`, and `cancelled`.
Each step stores its input fingerprint, accepted count, rejected count, checkpoint, attempts, error,
provider usage, and output version. Restarting a worker resumes the first incomplete step rather than
regenerating accepted content.

Rate limits and transient provider failures use bounded retries with recorded backoff. Schema,
grounding, ambiguity, and quality rejections create new candidates within configured attempt budgets;
they are not retried as transport failures. One failed batch cannot erase completed batches.

Partial regeneration targets one book, formula review, blueprint, validation report, or mock exam and
then creates a new package version that reuses unchanged validated snapshots.

## Hosted Application Experience

The course workflow becomes:

1. Create package metadata.
2. Upload and order curriculum books.
3. Upload and analyze the sample exam.
4. Review and correct curriculum and blueprint summaries.
5. Configure outputs and models.
6. Start generation and monitor real counts and stages.
7. Resolve hard validation failures or regenerate affected outputs.
8. Preview and download individual files or the complete ZIP.

The package dashboard shows document state, concept and formula counts, expected output counts, actual
accepted and rejected counts, validation state, artifact size, version, and available actions. It does
not display fake time-based progress.

Package configuration selects the parser/extraction model and package-generation model independently.
The Butler retains its separate teaching-model configuration and is not part of offline package
generation. Changing a Butler model cannot invalidate or regenerate package content.

Existing hosted flashcard, quiz, mock-exam, and review surfaces remain accessible during migration.
Navigation emphasizes packages. Converting an existing study surface into a package preview requires
separate behavior-equivalence verification and is outside this implementation scope.

## Offline Learner Experience

Flashcard files provide flip, previous/next, shuffle, search, hierarchy and card-type filters,
difficulty filters, Again/Hard/Good/Easy grading, source visibility, progress, reset, fullscreen,
keyboard controls, responsive layout, local progress, and JSON progress import/export.

Mock-exam files provide an instructions screen, optional timer, practice mode, autosave and resume,
question navigation, flags, answer clearing, progress and unanswered counts, submission confirmation,
grading, domain/subtopic/type/difficulty breakdowns, post-submit explanations, review filters, attempt
history, print, JSON export, reset, and new attempts. Answers remain hidden before submission unless
practice mode explicitly enables immediate feedback.

Formula review and blueprint files provide focused search, filters, reveal controls, source references,
and local review state appropriate to their content.

All controls have keyboard focus states, semantic labels, touch-safe target sizes, and layouts tested
at mobile, tablet, and desktop widths.

## Reusable Service and CLI Boundary

Expose one application service with command objects for:

- create package
- ingest books
- analyze sample exam
- generate flashcards
- generate formula review
- generate mock exams
- validate package
- render files
- build ZIP

FastAPI routes and a local CLI call the same service. The CLI is a secondary automation surface and
does not duplicate generation or validation logic.

## Error Handling

Boundary errors are typed and learner-facing messages identify the failed stage and recoverable
action. Internal validation findings preserve machine-readable codes and evidence. Provider responses,
raw source passages, API keys, and private learner data are not copied into browser errors, logs,
validation downloads, or package manifests.

Malformed or image-heavy PDFs fail with document and page context and may be retried with OCR when
configured. Unsupported or ungrounded generated content is rejected rather than silently repaired
with model knowledge.

## Copyright and Privacy

Generated files contain original cards, questions, explanations, and short necessary formula or
definition fragments. They do not contain full extracted passages, copied sample questions, numerical
reskins, or reconstructed source books. Source references identify book hierarchy and pages without
embedding unnecessary copyrighted text.

Uploaded materials, parsed stores, model checkpoints, and generated learner packages remain ignored
local artifacts under the repository hygiene policy. Deterministic synthetic fixtures are the only
study documents committed to Git.

## Targeted Code Cleanup

Cleanup is part of the package work only where it creates a needed boundary:

- extract curriculum normalization from the existing parser and study service
- extract reusable question rules and validation policies from the large question pipeline
- keep offline templates and runtime assets out of React route components
- move FRM allocation configuration into one typed policy module
- remove duplicate package-specific code after callers are migrated and behavior is covered

Do not perform cosmetic whole-file rewrites. Do not delete existing hosted features until the package
equivalent is implemented, tested, and manually verified. Unrelated type debt remains outside this
feature unless it blocks a changed file.

## Testing Strategy

### Unit

Test curriculum normalization, concept merging, exact ten-card enforcement, FRM allocations,
difficulty and type allocation, deduplication fingerprints, semantic threshold decisions, source
reference checks, score calculations, manifest hashes, safe JSON embedding, HTML escaping, storage
namespacing, and timer state transitions.

### Integration

Use deterministic synthetic curriculum and sample-exam fixtures to create a small package end to end.
Verify durable checkpoint resume, individual regeneration, immutable completed versions, file
downloads, ZIP contents, and validation hard failures.

### Browser

Open every fixture HTML artifact directly through `file://` in a real browser. Assert zero network
requests, exercise every primary interaction, reload to prove persistence, import and export progress,
submit and grade an exam, verify pre-submit answer secrecy, and test mobile, tablet, and desktop
layouts.

### Release Gate

The repository gate remains `make check`. Package work adds an offline fixture-generation command and
a Playwright browser suite. A release candidate must pass both in addition to lint, type checks, unit
tests, integration tests, and the production frontend build.

## Delivery Sequence

The implementation is divided into independently verifiable increments:

1. Package schemas, migrations, repositories, and immutable version model.
2. Curriculum normalization and editable blueprint analysis.
3. Card, formula, question-spec, and candidate pipelines with hard validation.
4. Constrained exam assembly and cross-version deduplication.
5. Standalone renderers, package manifest, validation reports, and ZIP assembly.
6. Package APIs, durable orchestration, CLI commands, and partial regeneration.
7. Package-management UI and de-emphasized hosted study navigation.
8. Direct `file://` browser verification, documentation, and migration hardening.

Each increment must leave the existing application operational and include its matching tests and
manual surface verification before the next increment begins.

## Acceptance Contract

Implementation is complete only when all of these behaviors are verified:

1. A user can create a named package and upload multiple ordered curriculum PDFs.
2. A user can upload a sample exam PDF independently from curriculum materials.
3. The system extracts a source-linked curriculum hierarchy and permits corrections before generation.
4. The system analyzes the sample exam into an editable blueprint while identifying fallback values.
5. The system identifies normalized, source-grounded concepts and formulas.
6. Every included concept has exactly ten validated, pedagogically distinct cards.
7. The system creates one standalone flashcard HTML file per curriculum book.
8. Every flashcard file works directly through `file://`, with interactions and progress persistence.
9. The FRM Part I default produces three mock exams with 100 questions each.
10. All three exams satisfy configured domain, subtopic, type, difficulty, and timing constraints.
11. The generated exams contain no prohibited exact, semantic, numerical-reskin, or solution-template
    duplicates within the package or against prior completed package versions.
12. Generated questions are not copies, close paraphrases, or numerical reskins of the sample exam.
13. Every card and question contains verified curriculum source references.
14. Every mock exam works directly through `file://` without a server or network request.
15. Exam grading reports total, domain, subtopic, type, and difficulty performance.
16. Correct answers and explanations remain hidden until submission outside explicit practice mode.
17. The system creates a standalone Formula Review file.
18. The system creates a standalone Exam Blueprint file that distinguishes observations, guardrails,
    and generation decisions.
19. The system creates machine-readable and learner-readable validation reports.
20. Users can preview and download each generated file individually.
21. The system creates a complete versioned ZIP and package manifest with file hashes.
22. Durable generation jobs preserve completed work across partial failures and process restarts.
23. Users can regenerate one failed or selected output without changing accepted unaffected outputs.
24. Automated tests cover allocation, validation, deduplication, safe rendering, recovery, and offline
    interactions using deterministic fixtures.
25. Existing useful ingestion, retrieval, model-provider, quiz, and study behavior remains operational
    or is migrated behind an equivalent verified path.
26. Setup, package usage, migrations, output formats, troubleshooting, limitations, copyright-sensitive
    use, and future automation boundaries are documented.

Passing a build without generating and using an offline fixture package is not completion.
