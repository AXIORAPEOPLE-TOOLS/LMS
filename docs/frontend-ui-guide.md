# Frontend UI guide — theme, components, motion, words

The UI follows the deck: calm deep green, a warm gold for the one action that matters on dark panels,
serif headings, plain words, one big button per screen. **Nothing looks "AI-generated"**: no sparkle
icons, no purple gradients, no "AI" / "AI-assisted" badges or labels. Assistant features are presented
as ordinary product features ("Draft from a document", "Suggestions", "Ask").

## 1. Colour tokens (Tailwind v4 `@theme` in `src/index.css`)
| Token | Hex | Use |
|---|---|---|
| `forest-950` | `#123A31` | darkest panel, hover on dark |
| `forest-900` | `#17463C` | dark panels (next-step card, sidebars, hub top bar) |
| `forest-700` | `#1F5C4E` | **primary** buttons, links, selected states |
| `forest-600` | `#2C6E5F` | active nav pill on dark |
| `forest-100` | `#E8F0EC` | chips, soft info panels |
| `forest-50`  | `#F1F6F3` | selected row |
| `gold-500`   | `#B8860B` | the primary CTA **on dark panels**, badges, rank 1–3 |
| `canvas`     | `#F4F6F5` | page background |
| `surface`    | `#FFFFFF` | cards |
| `line`       | `#DDE3E0` | borders |
| `ink-900`    | `#1F2A33` | headings/body text |
| `ink-600`    | `#5B6670` | secondary text |
| `ink-400`    | `#8A949C` | hints |
| `ok-600` / `ok-50` | `#2E8B57` / `#E6F4EA` | done, verified, on time |
| `warn-600` / `warn-50` | `#B7791F` / `#FDF3E1` | due soon |
| `bad-600` / `bad-50` | `#C0392B` / `#FBE7E5` | overdue, flags |
| `info-600` / `info-50` | `#2F5DA8` / `#E8EFFA` | to approve, revisions |

Contrast: body text on canvas ≥ 7:1; buttons ≥ 4.5:1 (WCAG 2.1 AA). Status is never shown by colour
alone — always with a word ("Overdue", "Verified").

## 2. Type
- Headings: **Source Serif 4** (variable, 600–700). Body/UI: **Source Sans 3** (variable). Self-hosted via `@fontsource-variable/*` (no external calls).
- Scale (mobile → desktop): page title 26→34, section 18→20, body 15→16, small 13. Line height 1.5 body.
- Hindi: Noto Sans Devanagari loaded when the language is Hindi.

## 3. Layout
- **Mobile first** (designed at 360 px). Learner gets a **bottom tab bar** (Home, My path, Learn, Rank, Knowledge); ≥ 1024 px switches to a left rail.
- Manager: 4 tabs (Team, Skills, Approvals, Rank). Admin: 6 sections in a dark sidebar.
- Knowledge Hub is a **separate app shell**: dark top bar (Home, Library, My items, Dashboard, Admin) and an app switcher.
- Spacing scale 4/8/12/16/24/32. Cards: radius 14, 1 px `line` border, no heavy shadows. Max content width 1200.

## 4. Components (`src/components/ui`)
| Component | Notes |
|---|---|
| `Button` | variants `primary` (forest), `gold` (on dark), `outline`, `ghost`, `danger`; sizes `md`, `lg` (full-width on mobile). Only **one** primary per screen. |
| `Card`, `Panel` | `Panel tone="dark"` = forest-900 next-step panel. |
| `Badge` / `StatusPill` | status words with tone. |
| `ProgressBar` | animated width; label always visible. |
| `Stat` | big serif number + label + optional ▲/▼ change. |
| `Toggle`, `Field`, `Input`, `Select`, `Textarea` | label above, hint below, error in words. |
| `Dialog`, `Sheet` | confirmations and previews ("Preview before sending"). |
| `EmptyState` | always offers the next action (no dead ends). |
| `Toast` with **Undo** | bulk sends show "Sent to 14 people · Undo" for 10 minutes. |
| `DegradedBanner` | from `/api/health`: calm "Some features are in limited mode" with details. |
| `Skeleton` | loading placeholders shaped like the content. |

## 5. Motion (Motion for React, `motion/react`)
- Purpose only: orientation (page transitions), feedback (button press, progress), continuity (list items).
- Durations: 150 ms (press), 220 ms (fade/slide), 320 ms (page), 600 ms (progress bars). Easing `[0.22, 1, 0.36, 1]`.
- Page transition: fade + 8 px rise. Lists: stagger 40 ms, max 8 items animated. Numbers: count-up on dashboards.
- `prefers-reduced-motion`: all motion reduced to opacity only (use `useReducedMotion`).
- **Splash screen** on first open per session: brand mark + product name on forest-900, gold underline drawing in, ≤ 1.4 s, skipped on reduced motion and on return visits within the session.

## 5b. The monitoring page (admin only)
The one deliberately "instrument panel" screen: very dark forest background (`#0b1d18`) with a faint grid,
glass-like panels with a thin gold top edge, monospace numbers, radial gauges (CPU/memory/disk), area
sparklines (requests, latency, errors), per-queue stacked bars and pulsing status lights
(green `#3ddc97` healthy, amber `#f2b84b` fallback, red `#ff6b5e` down). It stays useful first: every
number has a label and a threshold colour, breakers can be reset by hand, errors show request ids.
Still no "AI" styling (no purple gradients or sparkles).

## 6. Words
- Plain verbs: "Start learning", "Continue", "Send invitations", "Still correct". Never "Initiate", "Leverage", "Utilise".
- Numbers with context: "62% of Wave 1 done", "Overdue 12 days", "Top 25% of 36 people tested".
- Errors say what to do: "That email and password do not match." Backend messages are already plain; show them as-is.
- Every string goes through `t()` (English + Hindi files in `src/i18n`).

## 7. Accessibility
Keyboard reachable, visible focus ring (2 px gold on dark, forest on light), labels on every input,
`aria-live` for toasts and timers, tap targets ≥ 44 px, charts have a text/table alternative.

## 7b. Layout rules learned from testing
- Grid children get `min-width: 0` (global rule in `index.css`) so wide tables scroll inside their card and the page never scrolls sideways at 360 px. E2E checks this.
- `Field` wraps its control in the `<label>` when no `htmlFor` is given, so every input has an accessible name.
- Forms that start from server data mount a keyed child with initial state (no `setState` in effects).

## 8. Data and state
TanStack Query for all server data (`src/api/*.ts` typed clients); mutations invalidate the affected
queries. Optimistic updates only where undo exists. Persisted query cache (localStorage) so the app shows
the last data while offline/degraded.
