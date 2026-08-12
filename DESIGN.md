# Exam Prep Agent Design System

## 1. Atmosphere & Identity

Exam Prep Agent should feel like a quiet study terminal for high-stakes exam preparation: focused, trustworthy, and fast to scan. The signature is a warm paper workspace with precise teal actions, restrained borders, and compact surfaces that keep the learner close to the material instead of turning the app into a marketing page.

## 2. Color

### Palette

| Role | Token | Light | Dark | Usage |
| --- | --- | --- | --- | --- |
| Canvas | `--background` | `#f7f5ef` | not used | App background |
| Page background | `--page-bg` | `#f7f5ef` | not used | Full-page shell |
| Surface/default | `--surface` | `rgba(255, 255, 255, 0.88)` | not used | Panels and cards |
| Surface/strong | `--surface-strong` | `#fffefb` | not used | Modals, floating windows |
| Surface/muted | `--surface-muted` | `#f1eee6` | not used | Subtle contrast blocks |
| Text/primary | `--text` | `#20242a` | not used | Headings and body |
| Text/secondary | `--muted` | `#65717d` | not used | Captions and metadata |
| Border/default | `--border` | `rgba(32, 36, 42, 0.11)` | not used | Cards and controls |
| Border/strong | `--border-strong` | `rgba(32, 36, 42, 0.18)` | not used | Active surfaces |
| Accent/primary | `--accent` | `#16645d` | not used | Primary actions and links |
| Accent/soft | `--accent-soft` | `rgba(22, 100, 93, 0.10)` | not used | Selected states |
| Accent/strong | `--accent-strong` | `#0f4f49` | not used | Hover and pressed actions |
| Warning/background | `--warning-soft` | `rgba(184, 111, 18, 0.12)` | not used | Caution states |
| Warning/text | `--warning-text` | `#8f5a12` | not used | Caution text |
| Danger/background | `--danger-soft` | `rgba(177, 48, 48, 0.12)` | not used | Error states |
| Danger/text | `--danger-text` | `#8f2424` | not used | Error text |

### Rules

- Accent teal is reserved for primary actions, active states, and source links.
- Large backgrounds stay warm neutral. No purple/blue AI gradients.
- Add a token here before adding any new reusable color.

## 3. Typography

### Scale

| Level | Size | Weight | Line Height | Tracking | Usage |
| --- | --- | --- | --- | --- | --- |
| Display | `clamp(2rem, 3.2vw, 2.8rem)` | 800 | 1.04 | 0 | Course library title |
| H1 | `clamp(1.35rem, 1.8vw, 1.8rem)` | 800 | 1.08 | 0 | Workspace title |
| H2 | `1.35rem` | 750 | 1.2 | 0 | Modal and page section headers |
| H3 | `1rem` | 750 | 1.3 | 0 | Card titles |
| Body | `0.95rem` | 400 | 1.55 | 0 | Default copy |
| Body/sm | `0.86rem` | 500 | 1.45 | 0 | Secondary info |
| Caption | `0.76rem` | 700 | 1.35 | `0.06em` | Eyebrows and metadata |

### Font Stack

- Primary: `"Avenir Next", "SF Pro Display", "Helvetica Neue", Arial, sans-serif`
- Mono: `"SF Mono", "Menlo", "Consolas", monospace`

### Rules

- Use sentence case for labels unless a source title requires otherwise.
- Numeric metrics use tabular figures.
- Body text must stay readable inside dense cards; do not go below `0.84rem`.

## 4. Spacing & Layout

### Base Unit

Spacing derives from a 4px base.

| Token | Value | Usage |
| --- | --- | --- |
| `--space-1` | `4px` | Tight icon-to-label spacing |
| `--space-2` | `8px` | Compact chips and inline groups |
| `--space-3` | `12px` | Control padding |
| `--space-4` | `16px` | Card inner spacing |
| `--space-5` | `20px` | Modal headers and dense sections |
| `--space-6` | `24px` | Page section rhythm |
| `--space-8` | `32px` | Major workspace gaps |
| `--space-12` | `48px` | Page bottom breathing room |

### Grid

- Max content width: `1180px` for learner workspaces, `1240px` for source-heavy views.
- Breakpoints: mobile under `720px`, desktop above `1024px`.
- Dense operational screens prioritize scan paths over decorative symmetry.

### Rules

- Cards and fixed-format panes use stable min/max sizes to avoid layout shift.
- Floating study/source/quiz windows must remain resizable on desktop and full-width on mobile.

## 5. Components

### Primary button

- **Structure**: `button` or `a` with `.primary-button`.
- **Variants**: primary and compact.
- **Spacing**: `12px 18px`, compact `8px 12px`.
- **States**: hover darkens, active lowers by 1px, focus shows teal ring, disabled lowers opacity.
- **Accessibility**: button elements for actions, anchors for navigation.
- **Motion**: transform and background only.

### Secondary button

- **Structure**: `.secondary-button`.
- **Variants**: neutral action and compact action.
- **States**: hover border/accent fill, active lower, focus ring.

### Course card

- **Structure**: code/name block, metric chips, primary navigation.
- **Spacing**: `22px` desktop, `18px` mobile.
- **States**: hover raises subtly with accent border.
- **Accessibility**: primary link remains visible and keyboard reachable.

### Floating window

- **Structure**: titlebar, action row, scrollable body.
- **States**: active border and shadow, minimized dock button.
- **Accessibility**: titlebar remains visible, actions are real buttons, mobile disables resize.

### Offline package workspace

- **Structure**: compact page introduction, one package command band, generation status rows, validation findings, and a download list.
- **Primary action**: the current next action is visually dominant: create, build, validate, or download the ZIP.
- **Progress**: report persisted backend counts and stages only; never animate invented progress.
- **Downloads**: the ZIP is first and prominent. Individual HTML and JSON files remain available as secondary links.
- **States**: draft, queued, running, failed, complete, empty, and API-unavailable states each have a concise recovery action.
- **Responsive behavior**: status rows collapse from columns into labeled blocks below `720px`; controls remain full-width and keyboard reachable.
- **Accessibility**: progress uses `progress`, asynchronous updates use polite live regions, and errors use alert semantics.

## 6. Motion & Interaction

| Type | Duration | Easing | Usage |
| --- | --- | --- | --- |
| Micro | `140ms` | `ease-out` | Button press |
| Standard | `220ms` | `ease` | Hover and panel state |
| Emphasis | `360ms` | `cubic-bezier(0.16, 1, 0.3, 1)` | Modal and floating surface entry |

### Rules

- Animate only `transform`, `opacity`, background, border, and box-shadow.
- Every interactive element needs hover, active, and visible focus states.
- Respect `prefers-reduced-motion`.

## 7. Depth & Surface

### Strategy

Mixed, with borders as the default and very soft shadows only for modal/floating layers.

| Level | Value | Usage |
| --- | --- | --- |
| Resting | `0 1px 2px rgba(32, 36, 42, 0.035)` | Cards |
| Floating | `0 18px 48px rgba(32, 36, 42, 0.13)` | Sticky headers and docks |
| Modal | `0 28px 80px rgba(20, 25, 31, 0.22)` | Modal and floating windows |

### Rules

- Avoid stacked card-in-card treatment unless the inner card is a repeated item.
- Large surfaces use borders and tonal shifts, not heavy elevation.
