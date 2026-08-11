# Design System — AUSVIA

Audit date: 2026-08-11 (post-Phase 5 design checkpoint). This document has
two jobs: (1) state the target brand direction, and (2) honestly compare it
against what's actually implemented today, so gaps are visible rather than
assumed away. No UI changes were made as part of this pass — see
`PROJECT_STATUS.md` for why.

## Brand

- **Name:** AUSVIA (all caps everywhere — wordmark, page titles, docs;
  corrected 2026-08-11, see `DECISIONS.md`)
- **Tagline:** Your path to Ausbildung.
- **Personality:** premium European career-tech. Intelligent, trustworthy,
  calm, precise. Explicitly **not**: generic "AI startup" purple/gradient
  aesthetics, glassmorphism, chatbot-bubble styling, neon accents, clutter.
- **Logo:** `app/templates/_logo.html` — two macros, `mark()` (an abstract
  route/path icon on a rounded `brand-600` badge — deliberately not a
  graduation cap, briefcase, flag, or sparkle) and `wordmark()` (now
  "AUSVIA", all caps). Always imported and used together.

## Target color direction (brand spec)

| Role | Direction |
|---|---|
| Foundation | Deep navy / ink |
| Primary action | Blue |
| Background | Warm off-white |
| Success / good match | Green |
| Warning / gaps | Amber |
| Error | Red (implied, not explicitly specified) |

## Current implementation vs. target

Defined in `app/templates/base.html`'s Tailwind runtime config — everything
else in the app is plain Tailwind utility classes, no custom component CSS.

- **Brand blue** (`brand-50`…`brand-900`) — matches Tailwind's `blue-500`/
  `blue-600` almost exactly. **Aligned with target.** Used consistently for
  primary buttons, links, active nav state, the logo badge, focus rings.
- **Ink navy** (`bg-ink` / `text-ink`, `#0B1220`) — exists as a token but is
  used in **exactly one place**: the landing-page hero section. The
  authenticated app (sidebar, headers, cards) never uses it. **Gap:** the
  brand direction calls for navy/ink as a *foundation*, not a single
  marketing accent — right now it reads as "the app has a dark landing
  page," not "the app has a navy foundation." Candidate treatment for a
  future pass: the sidebar (`base.html`'s `<aside>`) is the natural place to
  extend ink as a structural element, since it's the one persistent
  full-height surface in the authenticated layout — worth prototyping, not
  deciding here.
- **Background** — `bg-slate-50` (`#F8FAFC`), a cool-toned neutral.
  **Gap vs. target:** the brand direction specifies *warm* off-white;
  `slate-50` has a faint blue cast, not warm. A warm neutral (e.g. something
  closer to Tailwind's `stone-50`/`neutral-50`, or a custom near-white with
  a slight warm tint) would match the spec more precisely. Low-risk,
  high-visibility change — good first candidate for an actual visual pass.
- **Success (green) / warning (amber)** — plain Tailwind `green-600`/
  `amber-600` (+ `-100` soft backgrounds). **Aligned with target**, already
  used correctly and consistently: green for match scores ≥80 and "primary
  document set" badges, amber for gaps/needs-review states. Never used
  decoratively — always tied to a real status.
- **Error (red)** — plain Tailwind `red-600`, used only for destructive
  actions (delete document/entry) and form validation errors. Not part of
  the original brand spec's explicit palette but consistent with the rest
  of the semantic system.
- **No purple, no gradients, no glassmorphism anywhere in the codebase** —
  confirmed by inspection. This is already fully aligned with the "no
  generic AI aesthetic" requirement and should be actively preserved in any
  future component work, not just avoided by omission.

## Typography

**Inter**, loaded via Google Fonts in `base.html`, set as the Tailwind
`font-sans` default. No decorative or secondary fonts. **Aligned with
target** ("clean typography").

Hierarchy is expressed directly via Tailwind utilities per template
(`text-2xl font-bold` for H1, `font-semibold` for section headers, `text-xs
uppercase tracking-wide text-slate-500` for eyebrow/label text) rather than
named component classes or a documented type scale. Consistent in practice
across all ~25 templates inspected, but not centrally defined — see
"Known gaps" below.

## Spacing & whitespace

Cards/sections use `p-5`/`p-6` internally and `mt-6`/`space-y-6` between
sections; the main content column is capped at `max-w-5xl`. This reads as
tidy rather than spacious — **partially aligned** with "generous
whitespace": there's no clutter, but density could be relaxed further
(larger card padding, more breathing room around section headers) in a
future visual pass without any structural change.

## Shape, borders & shadows

- **Cards:** `rounded-xl` (12px), `border border-slate-200`, `bg-white`.
  Fully consistent across every card-style section in the app (dashboard
  stat tiles, job cards, application cards, profile sections, admin
  tables) — this is the single most reused pattern in the codebase.
- **Shadows:** **none used anywhere.** Every surface relies on a 1px border
  for separation; zero instances of `shadow-*` utilities in any template.
  **Gap vs. target:** the brand direction calls for "subtle borders/
  shadows" (both, used lightly) — today it's borders-only, fully flat. A
  very light `shadow-sm` on cards (or only on hover/elevated states like
  the Gmail-reply cards or modals-to-come) would move this closer to the
  "premium" feel without violating "restrained."
- **Buttons:** `rounded-lg` (8px). Primary = solid `bg-brand-600` +
  white text; secondary = `border border-slate-300` + `text-slate-700`;
  tertiary/link = `text-brand-700 hover:underline`, no border or fill.
  Three consistent tiers, reused everywhere — this is a strong, ready-to-
  formalize pattern.

## Motion

`transition-colors duration-150` on interactive nav/hover states only — no
page transitions, no entrance animations, no loading spinners with motion.
**Fully aligned** with "restrained animation."

## Reusable components — what actually exists today

- `app/templates/_macros.html` — `render_field()`, `render_checkbox()`
  (WTForms field rendering: label + input + inline error, consistent
  everywhere a form appears)
- `app/templates/_logo.html` — `mark()`, `wordmark()`
- `app/templates/_flashes.html` — flash message banner (error/success/info,
  color-coded)

That's the entire shared-component surface. Everything else below is a
**repeated Tailwind utility pattern**, not a shared macro — same look,
copy-pasted per template.

## Patterns in active use, ready to formalize (not yet shared components)

Identified by inspecting all ~25 templates. These are visually consistent
today (good sign — no ad hoc drift), which makes them low-risk to extract
into macros later without a visual change:

- **Card/section container** — `rounded-xl border border-slate-200 bg-white
  p-6` — used in essentially every template (job detail, application
  detail, profile sections, admin panels, Gmail status). The single highest-
  value extraction candidate.
- **Status/count pill** — `rounded-full bg-slate-100 px-3 py-1 text-xs
  font-medium text-slate-700` (application status), and its scored variant
  `rounded-full px-2 py-0.5 text-xs font-semibold` with green/blue/amber/
  slate backgrounds keyed to a score threshold (match-score pill, job
  search results). Same shape, three call sites, not shared.
- **Stat tile** — `rounded-xl border border-slate-200 bg-white p-5` with an
  uppercase label + large bold number (dashboard, admin overview). Two call
  sites, identical markup.
- **Primary / secondary / tertiary button** — see "Shape" above. Extremely
  consistent already; the best candidate for a first real macro since it
  has zero visual ambiguity to resolve.
- **Per-category / progress bar** — `h-1.5 w-full rounded-full bg-slate-100`
  track + colored fill sized by `style="width: X%"`, thresholded to green/
  brand/amber/red. Currently used for match category breakdown and profile
  completeness; same shape both places.
- **`<details>` accordion** — used for "Add education/experience/skill/
  language" forms on the profile page. Native HTML, no JS, works, but has
  no custom open/close styling (no chevron rotation, no transition).

## Components that don't exist yet (needed before Phase 6/9 UI work)

- **Modal / dialog** — nothing in the app currently uses one; destructive
  actions use a native `confirm()` (document delete) rather than a styled
  confirmation dialog.
- **Toast/inline notification beyond flash-on-reload** — flashes only
  appear after a full page redirect; no client-side toast for async
  actions.
- **Tabs** — not used anywhere yet; would matter if company profile pages
  or a future settings area need sub-navigation.
- **Empty state component** — every "no X yet" message is currently a
  hand-styled `<p class="text-sm text-slate-500">`, consistent in tone but
  not a shared component.
- **Table component** — documents list and admin tables both hand-roll
  `<table>` markup with the same header/row styling; not shared.

## Accessibility

Not yet audited. Semantic HTML is used throughout (real `<label>`/`<form>`
elements via WTForms rendering, real `<table>` for tabular data), but
keyboard navigation, focus-visible states, color contrast (particularly
`text-slate-400`/`text-slate-500` on white — likely borderline for small
text), and reduced-motion support have not been explicitly reviewed.
Remains scheduled for Phase 9 in `ROADMAP.md`.

## Summary: what would actually change in a real visual pass

In priority order, cheapest/highest-impact first:

1. Swap `bg-slate-50` → a warm off-white token (background only — every
   card stays white, so this is a one-line config change with broad visual
   effect).
2. Add a restrained `shadow-sm` to card containers (one shared pattern,
   touches every template but is mechanical).
3. Extend ink/navy beyond the landing hero into the authenticated shell
   (sidebar is the natural candidate) — this is a real design decision, not
   mechanical, and should be prototyped/reviewed before rolling out broadly.
4. Extract the patterns listed above ("ready to formalize") into real Jinja
   macros or a small component set — reduces drift risk as Phase 6 adds
   more pages (company profiles, document AI extraction UI).
5. Build the missing components (modal, toast, tabs, empty state, table) as
   Phase 6 features actually need them, rather than speculatively.

None of this was executed in this pass per instruction — this list is the
starting brief for whenever a visual-refinement pass is explicitly scoped.
