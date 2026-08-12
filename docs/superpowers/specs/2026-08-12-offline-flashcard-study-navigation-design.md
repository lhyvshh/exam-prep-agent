# Offline Flashcard Study Navigation Design

## Status

Approved in conversation on 2026-08-12. This specification narrows and supersedes the
student-facing flashcard artifact rules in the broader offline study-package design. It does not
change mock-exam generation or completed-exam import behavior.

## Goal

Make each generated flashcard HTML file feel like a focused exam-prep application rather than a
long sequential deck. A student must be able to find descriptive learning objectives, combine
multiple objectives into a custom session, jump directly to any card in that session, and continue
studying without an internet connection or the producer application.

## Student Artifact Boundary

A study-card package contains only learner-facing flashcard artifacts:

- one self-contained flashcard HTML file per selected book; and
- one ZIP containing exactly those flashcard HTML files.

The study-card package does not emit or list a package manifest, validation HTML, validation JSON,
formula-review file, exam blueprint, or other producer metadata. Hard validation still runs before
release and remains stored in the producer application's database. Removing reports from the
download cannot weaken the quality gate.

Mock-exam and complete-package artifact policies remain outside this change.

## Learning Objective Contract

The renderer receives explicit learning-objective groups rather than reconstructing groups from
card strings. Each group contains:

- a stable group key;
- the LO code, such as `LO 43.d`;
- a descriptive title from the normalized curriculum concept;
- an ordered list of card IDs; and
- total and rated-card counts calculated in the browser.

The visible label uses `LO code · Descriptive title`. A code-only label is not acceptable when a
descriptive concept title exists. Cards retain their source page, source reference, type,
difficulty, and stable identity.

## Study Workflow

### Initial State

On first open, the first available LO is selected so the file is immediately usable without
showing a thousand-card queue. Returning students restore their selected LOs, card position,
ratings, and reveal state from local storage. Imported progress follows the same normalized state
contract.

### LO Navigator

The navigator is searchable and supports multiple selection. Every row includes a checkbox, the LO
code, descriptive title, card count, and rated progress. Students can:

- select or clear individual LOs;
- select all currently visible search results;
- clear the current selection;
- choose one LO through a direct `Study this LO` action; and
- begin or resume the custom batch made from all selected LOs.

Changing the LO search does not silently remove prior selections. Empty selection shows a clear
prompt to choose at least one LO.

### Card Queue

The active batch has a scrollable, clickable queue grouped under descriptive LO headings. Each
queue row shows its position, prompt text, and recall status without revealing the answer. Clicking
a row jumps directly to that card, resets the answer to hidden, moves focus to the study card, and
announces the new position to assistive technology.

Previous and next controls wrap only within the active batch. Existing shuffle, search by card
content, card type, difficulty, answer reveal, recall rating, fullscreen, progress export/import,
reset, and keyboard navigation remain available. Filter and batch changes always clamp the current
position to a valid card.

## Responsive Layout

Desktop uses a two-column study workspace:

- a bounded left navigator for LO selection and batch controls; and
- a main study region with the active card and a bounded card queue.

The page itself remains normally scrollable. Internal navigator and queue regions have stable
heights and independent scrolling so headers and study controls remain reachable.

Below the mobile breakpoint, LO selection becomes a native disclosure panel above the study card.
The card queue follows the card as a full-width section. No essential action depends on hover,
dragging, or a desktop-sized viewport.

## Accessibility and Clarity

- Provide a skip link to the active study card.
- Use semantic `nav`, `fieldset`, `legend`, `main`, `article`, and live-status elements.
- Associate every checkbox and filter with a visible label.
- Keep interactive targets at least 44 by 44 CSS pixels.
- Provide visible keyboard focus and current-card styling that does not rely on color alone.
- Announce batch size, empty results, direct jumps, answer visibility, and saved recall ratings.
- Preserve logical focus when filters, LO selections, or card jumps change the view.
- Support left/right navigation and answer reveal shortcuts without intercepting typing in controls.
- Respect `prefers-reduced-motion` and maintain readable contrast and line length.
- Use plain student-facing language and keep producer terminology out of the file.

## Data and Persistence

The generated file remains fully self-contained: embedded CSS, embedded JavaScript, inert escaped
JSON payload, and no network requests. State remains namespaced by package, file, and version.

The saved state adds selected LO keys and queue position while preserving ratings by card ID.
Loading older state without selected LO keys chooses the first LO and retains all compatible
ratings. Import rejects malformed state instead of leaving the page unusable.

## Failure Behavior

- No LO groups: show a readable unavailable state; do not render broken controls.
- Selected LO no longer present: drop that key and select the first available LO.
- No cards match secondary filters: keep the LO selection and explain which filters to clear.
- Imported progress is invalid: keep current progress and show an inline alert.
- Fullscreen is unavailable: leave the study workflow unchanged.

## Verification

Automated tests must prove:

- study-card ZIPs contain only flashcard HTML files;
- producer-only artifacts are neither written nor listed for study-card packages;
- each rendered deck embeds descriptive LO group metadata;
- multiple LO selection creates the expected ordered batch;
- selecting visible results does not clear hidden selections;
- direct queue clicks jump to the intended card and hide its answer;
- legacy saved progress migrates safely;
- keyboard navigation ignores focused form controls;
- the file contains no network dependencies; and
- the existing quality gate still blocks invalid packages.

Browser QA covers desktop, tablet, and mobile widths, plus keyboard-only use, visible focus,
multi-select batch creation, queue scrolling and direct jumps, answer reveal, rating persistence,
progress export/import, and opening the generated HTML from a downloaded ZIP.
