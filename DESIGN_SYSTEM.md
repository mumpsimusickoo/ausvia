# Design System — Ausvia

## Brand

- **Name:** Ausvia (lowercase "ausvia" in the wordmark)
- **Tagline:** Your path to Ausbildung.
- **Personality:** intelligent, trustworthy, calm, modern, European,
  transparent. Explicitly not: chatbot-styled, cluttered, neon/gradient-
  heavy, glassmorphism, generic "AI sparkle" aesthetics.
- **Logo:** `app/templates/_logo.html` - two macros, `mark()` (an abstract
  route/path icon on a rounded `brand-600` badge - not a graduation cap,
  briefcase, flag, or sparkle) and `wordmark()` (lowercase "ausvia" text).
  Import both together wherever the logo appears (sidebar, landing header).

## Color system

Defined in `app/templates/base.html`'s Tailwind runtime config.

- **Brand blue** (`brand-50`...`brand-900`): matches Tailwind's own
  `blue-500`/`blue-600` scale exactly - primary actions, active nav state,
  links, the logo badge.
- **Ink** (`bg-ink` / `text-ink`, `#0B1220`): used sparingly for high-
  contrast surfaces (currently only the landing-page hero).
- **Neutrals:** plain Tailwind `slate-*` throughout (background, borders,
  text) - deliberately not a custom token set, since the brand spec's exact
  neutral hex values are ~99% identical to Tailwind's slate scale already in
  use. See the relevant `DECISIONS.md` entry.
- **Semantic:** plain Tailwind `green-600`/`amber-600`/`red-600` (+ `-100`
  soft backgrounds) for success/warning/error - also exact-match with the
  brand spec's semantic hex values. Green = positive match/completed state,
  amber = gaps/attention needed, red = errors/destructive only.

## Typography

**Inter**, loaded via Google Fonts in `base.html` and set as the Tailwind
`font-sans` default. No decorative fonts. Hierarchy is currently expressed
directly via Tailwind text-size utilities per template (`text-2xl font-bold`
for H1, etc.) rather than named component classes - see "Known gaps" below.

## Spacing & shape

- Cards: `rounded-xl` (12px), `border border-slate-200`, `bg-white`, no
  shadow by default (shadows are intentionally rare, per the "avoid clutter"
  brand principle) - consistent across every card-style section in the app.
- Buttons: `rounded-lg` (8px), solid `bg-brand-600` for primary actions,
  bordered/neutral for secondary actions.
- Transitions: `transition-colors duration-150` on interactive nav/hover
  states - short, intentional, never game-like, per the motion principle.

## Reusable components (what actually exists)

- `app/templates/_macros.html` — `render_field()`, `render_checkbox()`
  (WTForms field rendering)
- `app/templates/_logo.html` — `mark()`, `wordmark()`
- `app/templates/_flashes.html` — flash message rendering

## Known gaps vs. the full design-system ambition

There is no centralized Button/Badge/Card/Modal/Table/Tabs/Toast component
library yet - styling is consistent (same Tailwind utility patterns reused
per template) but applied per-template, not via shared Jinja macros or
components beyond the three listed above. Match-score display, application-
status badges, and document cards are currently each hand-styled per
template rather than shared components. Listed as a real gap in
`PROJECT_AUDIT.md`, not hidden.

## Accessibility

Not yet audited. Semantic HTML is used throughout (proper `<label>`/`<form>`
elements via WTForms rendering, `<table>` for tabular data), but keyboard
navigation, focus states, contrast, and reduced-motion support have not been
explicitly reviewed. Flagged for Phase 9 in `ROADMAP.md`.
