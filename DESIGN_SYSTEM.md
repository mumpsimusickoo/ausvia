# Design System — AUSVIA

Status: **rev 1.0 implemented**, 2026-08-11. The Phase 5.5 checkpoint left
this document as a target-vs-actual gap analysis with nothing implemented.
This pass implements the approved logo (`LOGO.md`) and closes all three
gaps flagged then (background warmth, shadow usage, ink navy's footprint).
This is still a design-system checkpoint, not Phase 6 — no product features
changed, only brand/visual foundation.

Updated again the same day with a scoped visual-direction pass (Counterform
+ Wayfinding, see "Signature construction: the 63.4° shear" and
"Application status: Wayfinding" below) — still a design-system checkpoint,
not Phase 6.

**Correction pass, 2026-08-12:** the first visual-direction pass shipped
all three signature details technically correct in code but visually
imperceptible or under-emphasized — a 3-4px clip-path shear on 6-8px bars,
a stroked hero line instead of a true counterform cut, and a current-station
ring too close in weight to the completed markers. All three are corrected
below with exact, hardcoded values (not re-derived from a ratio) — see the
per-section notes and the two new `DECISIONS.md` entries dated 2026-08-12.

## Visual direction: Counterform (1a), scoped exception for status (1c)

Three directions were explored (Counterform, Record, Wayfinding — see the
design-exploration PDF referenced in `DECISIONS.md`). **Counterform (1a) is
the product's direction everywhere**, except the application-status
component, which uses **Wayfinding's (1c)** station/marker approach
instead. Record (1b) is not used anywhere. This is a deliberate scoped
exception, not an inconsistency: Counterform's signature (the mark's
counterform cut, extended into a process-flow graphic and a bar-fill
shear) is about the *product's construction language*; Wayfinding's
signature (named stations, a marker for where you are) is about *reducing
anxiety for someone navigating an unfamiliar process*, which is exactly
what the application-status view's job is. Two directions, applied to two
different problems, not two houses styles competing on one page.

### Landing hero + process flow (1a)

The five-stage sequence ("Discover → Match → Prepare → Apply → Track") is a
**filled compound path** (`fill-rule="evenodd"`, `fill="#0B1220"`) — subpath
1 is a solid ink rectangle spanning the full graphic band, subpath 2 is the
route, cut out as the hole. The route is never a drawn/stroked line (the
first version of this pass used a 3px stroke, which read as "a line on a
dark background," not as an opening cut through solid material — corrected
2026-08-12). The band is full-bleed (breaks out of the centered content
column) and sits on the app's `paper` background color, so the counterform
cut reveals the page surface through it — literally the same construction
as the logo mark, at hero scale. Path data in
`app/templates/landing.html` is copied verbatim from the approved
correction and must not be re-derived or approximated. Labels are
percentage-positioned over an `aspect-ratio`-locked container (not SVG
`<text>` this time — see the correction's judgment-call note in
`DECISIONS.md` for why). No motion on this graphic — only bars animate.

### Signature construction: the shear is a fixed 12px, not a ratio

The logo symbol's leg is a 1:2 rise (63.4° from horizontal — see `LOGO.md`
section 02) — that ratio is where the shear idea comes from, but **the
implementation is a hardcoded 12px `clip-path` offset**, not a CSS custom
property derived from bar height. The first version of this pass computed
the offset as `bar-height × 0.5`, which at the product's actual 6-8px bar
heights produced an imperceptible 3-4px notch — technically present,
invisible in practice. Corrected 2026-08-12: bar height is now **14px**
everywhere this is used (was 6-8px), the shear is a **literal 12px**
(`.ausvia-bar-fill` in `app/templates/base.html`), and every fill carries
**`min-width: 28px`** so a low score (e.g. 25%) still renders a complete,
legible shear instead of a clipped sliver. A bar at exactly 0% renders no
fill element at all (track only) rather than a misleading 28px-wide nub.
Motion changed from a `width` keyframe to `transform: scaleX(0→1)`
(`transform-origin: left`), 500ms ease-out, 60ms stagger — `scaleX` doesn't
fight the `clip-path` calculation the way animating `width` did, so the
sheared edge holds its angle steadily through the animation instead of
recomputing (and briefly distorting) every frame.

### Application status: Wayfinding (1c)

`app/templates/applications/detail.html`'s old status `<select>` +
separate timeline list is now a single vertical route
(`app/applications/status_route.py` computes it): six fixed stations
(Preparing/Ready/Sent/Follow-up/Interview/Offer, matching
`Application.APPLICATION_STATUSES` — the four terminal exception statuses
accepted/rejected/withdrawn/expired surface as a small badge instead of a
seventh/eighth station, since they're exits from the route, not stops on
it). Every marker state and one-line description is computed from data
that already existed (status, `ApplicationEvent` log, contact/interview/
follow-up fields) — a display change, not a new data source. Skipped
stations (e.g. Follow-up, when a reply arrives before the reminder date)
still render with an explanatory line, never hidden.

**Marker sizing, corrected 2026-08-12:** the first version distinguished
the current station from completed ones by ring weight alone
(`ring-4 ring-brand-100`, a pale tint), which read as noise, not emphasis,
at a glance. Corrected to differ by size, ring weight, *and* fill
simultaneously, so it can't be missed or mistaken for a color-only cue:
current = **24px** circle, **4px solid ink ring**, **10px Signal Blue core
dot** (15.9:1 against white); completed = 14px solid Signal Blue, no ring;
skipped = 14px white fill with a 2px Signal Blue ring; not-yet-reached =
14px white fill with a 2px `ink/20%` ring. No pale brand-tint rings
anywhere in this component. The connecting rail is a CSS grid row (24px
marker column + content column, `align-items: stretch`), so its length
auto-matches however tall each row's description actually renders,
instead of a hand-tuned absolute-positioned guess.

**Not a clean 1:1 swap — flagged per the design brief's own request:** the
old form combined status editing with contact/interview/follow-up-date/
notes fields. Only the status dropdown competed visually with the new
route (the other fields are just data entry, not status *display*), so
only the dropdown was extracted — into a collapsed `<details>` "Manually
correct status" disclosure at the end of the (renamed) "Contact & tracking
details" form. This keeps manual correction possible (e.g. marking
withdrawn/rejected, fixing a mistake) without it visually competing with
the route component above it.

## Brand

- **Name:** AUSVIA in running text, page titles, and documentation (all
  caps — a standing correction, see `DECISIONS.md`). The **logotype**
  itself (the graphic wordmark) is set lowercase "ausvia" per the approved
  logo spec — this is a deliberate, common distinction (compare Sony,
  IKEA, adidas: stylized logotype vs. normal-case brand references in
  prose) and not an inconsistency. When in doubt: if it's the SVG mark,
  it's lowercase; if it's text you're writing, it's AUSVIA.
- **Tagline:** Your path to Ausbildung.
- **Personality:** premium European career-tech. Intelligent, trustworthy,
  calm, precise. Explicitly **not**: generic "AI startup" purple/gradient
  aesthetics, glassmorphism, chatbot-bubble styling, neon accents, clutter.
- **Logo:** Aperture, rev 1.0, approved — full construction spec, ratios,
  and rationale in `LOGO.md`. Implemented as real production assets
  (`app/static/brand/*.svg`) and Jinja macros (`app/templates/_logo.html`:
  `symbol()`, `wordmark()`, `lockup()`). The wordmark is a true outlined
  path extracted from the licensed Sora SemiBold font (fontTools, not
  hand-approximated, not live text in a substitute face) — see `LOGO.md`
  section on typography for why and how.

## Typography decision: Sora is wordmark-only (Option A)

The logo spec sets the wordmark in Sora SemiBold; the existing design
system uses Inter for all UI/body text. **Decision: Sora is scoped to the
logotype only. Inter remains the UI/body/data typeface everywhere else,
unchanged.**

**Why:** the wordmark is now a pre-outlined vector path (see `LOGO.md`) —
it doesn't need Sora loaded as a webfont at all, anywhere, to render
correctly. Introducing Sora as a second UI typeface would add a font-
loading dependency and a second type system to maintain, for a stylistic
gain that isn't what was actually requested (the spec scopes Sora to
section 03, "wordmark," not to body/display type generally). Inter already
satisfies "clean, modern, highly readable" for UI copy, and Phase 4.5
already established it with zero complaints. Keeping two systems cleanly
separated — Sora as a fixed, outlined brand mark; Inter as the living,
webfont-loaded UI face — is simpler and lower-risk than blending them.
**Consequence:** nowhere in the live app does `<link>`-load Sora; only the
outlined path data (baked into `_logo.html` and the static SVGs) uses its
letterforms. The `ausvia-lockup-tagline.svg` reference asset (for
print/social use outside the app) does render live tagline text in Sora
Regular for visual consistency with the mark in that specific standalone
context — this is the one exception, and it's an asset file, not the
running app.

## Color tokens (confirmed, from the approved logo spec section 08)

Defined in `app/templates/base.html`'s Tailwind runtime config.

| Token | Hex | Role |
|---|---|---|
| `ink` | `#0B1220` | Foundation surface (sidebar), wordmark/text color on **light** surfaces, high-contrast backgrounds |
| `brand-600` (Signal Blue) | `#2563EB` | Primary actions, links, focus rings, **and the logo symbol's default fill on light surfaces** — 5.17:1 on white, AA-safe. See "Signal Blue vs. Ink Navy" below — this was an open question in the last checkpoint, now resolved. |
| `bright` (Bright Blue) | `#3B82F6` | The logo symbol's fill (and general accent) on **dark/ink** surfaces only — 5.4:1 on Ink Navy. Numerically equal to `brand-500` but named explicitly so any use on a dark surface is intentional, not accidental copy-paste of the light-surface blue |
| `paper` | `#FAF8F5` | Page background — warm off-white, replaces the old `slate-50` (which had a cool/blue cast, flagged as a gap in the last checkpoint) |

### Signal Blue vs. Ink Navy: resolved

The last checkpoint flagged this as an open reading (implemented "literally" from an asset-filename table, explicitly noted as reversible). Re-examined against the spec's actual color-role language and the rendered reference art (not just file names) — **Signal Blue is the symbol's default fill on light backgrounds; Ink Navy is the text/wordmark and surface color, not a default mark color.** Full reasoning, the exact spec quotes that settle it, and what changed as a result: `LOGO.md`'s "Signal Blue vs. Ink Navy" section. Short version: the earlier identity doc states "Signal Blue: ... the mark on light" and "Bright Blue: ... the mark on ink" explicitly; rev 1.0's contrast note ("the dark version steps up to Bright Blue") only makes sense if Signal Blue is the light-context baseline it's stepping up from; and the reference art in all three logo PDFs in this project shows the primary lockup's symbol in blue, consistently.

**Separately confirmed:** Signal Blue already drives every primary CTA and link across the app (grep-verified). One real inconsistency was found and fixed: form focus rings used Bright Blue's hex (`ring-brand-500`) on light-surface white inputs, violating "dark-only" — changed to `brand-600` in `_macros.html`'s two field-rendering macros, the single centralized definition.
| `green-600`/`green-100` | Tailwind default | Success / good match |
| `amber-600`/`amber-100` | Tailwind default | Warning / gaps |
| `red-600` | Tailwind default | Error / destructive |
| `slate-*` | Tailwind default | Neutrals: borders, secondary text, card backgrounds stay white |

**Rule that must not be broken:** Signal Blue (`brand-600`) is for light
surfaces; Bright Blue (`bright`) is for dark surfaces. Using Signal Blue as
text/icon color directly on `bg-ink` drops to 2.9:1 contrast — fails AA.
This is why the sidebar's active-nav-item text and the logo's "on ink"
variant both use `bright`, never `brand-600`.

### Role mapping

| UI role | Token |
|---|---|
| Page background | `bg-paper` |
| Cards / panels | `bg-white` + `border-slate-200` + `shadow-sm` |
| Sidebar / authenticated app shell | `bg-ink` (see "Ink Navy as foundation" below) |
| Primary CTA button | `bg-brand-600` (light surfaces) |
| Links, tertiary actions | `text-brand-700` |
| Focus rings | `ring-brand-500` |
| Active nav item (on `bg-ink` sidebar) | `text-white` + `bg-white/10` |
| Success / good match | `green-600` / `green-100` |
| Warning / gaps | `amber-600` / `amber-100` |
| Error / destructive | `red-600` |

Signal Blue and the success/warning semantics never collide: green and
amber are reserved exclusively for status (match quality, validation
state), blue is reserved exclusively for actions/navigation/brand — a
green "success" badge and a blue "primary button" never compete for the
same meaning in the same view.

## Gap closure (from the Phase 5.5 checkpoint)

All three flagged gaps are now closed:

1. **Warm off-white background** — `bg-slate-50` → `bg-paper`
   (`#FAF8F5`) in `base.html`'s `<body>`. One-line token change, every
   card stays white, so contrast/hierarchy is unaffected — only the page
   ground shifted from a cool to a warm neutral.
2. **Shadow usage alongside borders** — every instance of the shared card
   pattern (`rounded-xl border border-slate-200 bg-white`) across all 20
   templates that use it now also carries `shadow-sm`. Mechanical,
   uniform, applied via a single find/replace across the codebase so
   there's zero drift between templates.
3. **Ink Navy as a real foundation element** — the authenticated app
   shell's sidebar (`base.html`'s `<aside>`) is now solid `bg-ink`, not
   white. Nav item text/hover states, the admin section divider, and the
   logo lockup inside it were all updated together (nav default
   `text-slate-300`, hover `hover:bg-white/5 hover:text-white`, active
   `bg-white/10 text-white`) so the whole surface reads as one consistent
   dark panel rather than a white sidebar with one dark accent. The
   landing hero keeps its existing `bg-ink` section — ink now appears in
   exactly two places, both structural (hero, sidebar), not decorative.

Verified live (screenshot-checked against the running dev server, not just
read from the template source) on the dashboard, landing page, documents,
profile, and Gmail status pages.

## Spacing & whitespace

Unchanged from the last checkpoint: cards/sections use `p-5`/`p-6`
internally, `mt-6`/`space-y-6` between sections, content capped at
`max-w-5xl`. Still tidy rather than spacious — not addressed in this pass
(it wasn't one of the three flagged gaps); a candidate for a future
polish pass, not urgent.

## Shape, borders & shadows

- **Cards:** `rounded-xl`, `border border-slate-200`, `bg-white`,
  **`shadow-sm`** (new, see gap closure above).
- **Buttons:** `rounded-lg`. Primary = solid `bg-brand-600` + white text;
  secondary = `border border-slate-300` + `text-slate-700`; tertiary/link
  = `text-brand-700 hover:underline`. Unchanged, still the strongest
  ready-to-formalize pattern.

## Motion

Unchanged: `transition-colors duration-150` on interactive states only.
Still fully aligned with "restrained animation" — not revisited here.

## Reusable components — what actually exists today

- `app/templates/_macros.html` — `render_field()`, `render_checkbox()`
- `app/templates/_logo.html` — `symbol()`, `wordmark()`, `lockup()` (real
  production geometry, see `LOGO.md`)
- `app/templates/_flashes.html` — flash message banner

## Patterns in active use, still ready to formalize

Unchanged from the last checkpoint — extracting these into real macros
was explicitly deferred to whenever Phase 6 actually needs a third/fourth
call site, per the sequencing note in `ROADMAP.md`:

- Card/section container, status/count pill, stat tile, button tiers,
  per-category progress bar, `<details>` accordion.

## Components that don't exist yet

Unchanged: modal/dialog, toast, tabs, empty-state component, table
component. Still deferred to when Phase 6 features actually need them.

## Iconography & imagery

Not covered by the logo spec (that's the mark only). See `BRAND_VOICE.md`
for the product's iconography stance — kept in the voice doc rather than
here since it's as much a content decision (what to show, what not to)
as a visual one.

## Accessibility

Not yet audited. Unchanged from the last checkpoint — still scheduled for
Phase 9. One new item to check then: text contrast on the new `bg-ink`
sidebar (`text-slate-300`/`text-slate-400`/`text-slate-500` against
`#0B1220`) — spot-checked visually during this pass and reads clearly,
but not measured against WCAG AA formally yet.

## What's next

Per `DESIGN_SYSTEM.md`'s own prior recommendation and `ROADMAP.md`'s
sequencing note: extract the "ready to formalize" patterns into real
components when Phase 6's new pages (company profiles, document
extraction UI) need a third call site, rather than before. No further
visual work is scoped here — see `PROJECT_STATUS.md` for what's next.
