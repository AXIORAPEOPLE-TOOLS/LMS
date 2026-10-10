# Frontend UI guide — theme, components, motion, words

The UI follows the deck: calm mid-tone green (light, not dark), a warm gold for the one action that matters on dark panels,
serif headings, plain words, one big button per screen. **Nothing looks "AI-generated"**: no sparkle
icons, no purple gradients, no "AI" / "AI-assisted" badges or labels. Assistant features are presented
as ordinary product features ("Draft from a document", "Suggestions", "Ask").

## 1. Colour tokens (Tailwind v4 `@theme` in `src/index.css`)
| Token | Hex | Use |
|---|---|---|
| `forest-950`…`600` | `#1C6453`…`#3A9079` | mid greens: panels use a soft green gradient, primary buttons `forest-700` |
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
- **One top navigation on every screen**, in both apps (`layouts/TopNav.tsx`). No sidebar, no bottom tab bar. Links sit in a row; "My team" and "Admin" are menus in the same bar; on phones the bar collapses into a menu button.
- **One app, one bar.** Home, My path, Learn, Rank, then menus: Knowledge (Overview, Library, My items, Dashboard, Admin), My team and Admin (by role). The Knowledge menu is shown only to records staff: admin, knowledge admin, function heads, managers, and anyone who owns, backs up or heads part of the Hub (the server decides; `/me.can_open_knowledge`). Plain learners do not see it. Knowledge pages open inside the same layout, so the navigation never changes. Messages and the account menu sit at the right. There is no app switcher.
- Content uses the full width (max 1400 px, 16–32 px gutters). Screens with a main task and side information use two columns on desktop (Home, My path, course); no narrow single-column lists centred in empty space.
- **Uneven columns scroll, the page does not stretch.** When a list sits beside a shorter column, the list gets the `scroll-panel` class (max ≈ 620 px / 68vh, thin scrollbar) and the short column is `sticky`. Used on the profile skills, home "Coming up", leaderboard, Knowledge home side lists, admin home lists.
- Routes: `/` is the public landing page, `/home` is the signed-in home, `/login` and `/signup` share one layout.
- Spacing scale 4/8/12/16/24/32. Cards: radius 14, 1 px `line` border, no heavy shadows.

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
- **Splash screen** on first open per session: product name as plain centred text on a light background, ≤ 1 s, skipped on reduced motion and on return visits within the session.

## 5b. The monitoring page (admin only)
The one deliberately "instrument panel" screen: very dark forest background (`#0b1d18`) with a faint grid,
glass-like panels with a thin gold top edge, monospace numbers, radial gauges (CPU/memory/disk), area
sparklines (requests, latency, errors), per-queue stacked bars and pulsing status lights
(green `#3ddc97` healthy, amber `#f2b84b` fallback, red `#ff6b5e` down). It stays useful first: every
number has a label and a threshold colour, breakers can be reset by hand, errors show request ids.
Still no "AI" styling (no purple gradients or sparkles).

## 5c. Helpers and answers to check
- Helpers are called **Helpers**, never "AI", "agent" or "assistant" in the UI; no wand or sparkle icons (`ClipboardList`, `PenLine`).
- A run page is a numbered step list: grey dashed circle = not yet, spinning loader = working, green tick = done,
  dash = skipped, amber clock on an amber row = needs a person, red cross on a red row = stopped. Each step shows
  its detail in plain words (what it used, what it removed). The page polls while a run is working.
- The right column holds the one primary action: *Open the course*, *Assign to N people* (after the full list),
  *Follow progress*. Undo is a ghost button while the 10-minute window is open.
- Written quiz questions use a textarea with "A few lines in your own words. Spelling does not matter." When a
  person must check, the learner sees "Thanks, your answers are in", not a score.
- Glossary: Written case → written question (`kind = written`) · Points to look for → rubric.

## 6. Words
- **Glossary (what people see → what the code calls it):** Test → skill check / assessment · Course test → course quiz · Learning plan → pathway · Stage → wave · Take the course / Use it at work / Talk to an expert / Pass the test → learn / practise / connect / prove · Live class → session · Must do → mandatory · Records staff → knowledge roles.
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
