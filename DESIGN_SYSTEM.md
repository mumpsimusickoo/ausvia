# Design System — AUSVIA

Status: **Theme pass implemented**, 2026-08-25 — see "Theme architecture —
2026-08-25 pass" below. This supersedes the foundation-tokens pass's "fixed
dark surface, no toggle" decision: the app now has a real light/dark theme
toggle (Porzellan/Tinte), built on CSS custom properties. See
`DECISIONS.md` for the supersession entry.

Prior status, still accurate for everything it covers: **AUSVIA 2.0
foundation-tokens pass implemented**, 2026-08-25 — see the dated section
immediately below. This pass is colors/typography/spacing/radius/shadow/
focus only, extracted from the approved AUSVIA 2.0 mockup bundle's own
"Foundations" reference screen (audit bucket D — a style-guide screen, not
a real product page, but the authoritative token source). No screens,
components, or the logo changed. Everything below the new section is the
prior rev-1.0 record, kept for history; two of its subsections (Typography
decision, Color tokens) are explicitly superseded and say so at the top.

## Foundation tokens — 2026-08-25 pass

Source of truth for every value below: the 2.0 mockup bundle's `:root`
custom properties (light) and `[data-theme="dark"]` block (fixed ink
surface only — no toggle exists or was built). Values are transcribed
exactly, not approximated. Where the app needed a token the bundle didn't
define (the `brand-50..900` Tailwind ramp), the gap was resolved by
explicit user decision, recorded here and in `DECISIONS.md`, not guessed.

### Light-surface tokens

| Token | Hex | Role |
|---|---|---|
| `brand` | `#0B767D` (Tiefsee-Teal) | Primary action fill, link/tertiary text, brand-colored borders, focus outline, dark-on-tint text |
| `brand-hover` | `#075A61` | Hover/pressed state of `brand` |
| `tint` | `#EDF6F6` | Light wash fill — info-card and badge/pill backgrounds |
| `tint2` | `#D3EAEB` | Light wash border — info-card and badge borders, card hover-affordance borders |
| `paper` | `#F2F5F6` | Page background (was `#FAF8F5`) |
| `ok` / `ok-tint` | `#14713F` / `#E9F2ED` | Success semantic — **defined, not yet wired in** (see note below) |
| `warn` / `warn-tint` | `#8A6008` / `#FAF3E4` | Warning semantic — defined, not yet wired in |
| `err` / `err-tint` | `#AE3227` / `#FAEDEB` | Error semantic — defined, not yet wired in |
| `info` / `info-tint` | `#2C6E9B` / `#EAF1F7` | Informational semantic — new role, defined, not yet wired in |

**Semantic colors are defined but not migrated this pass.** The app's
existing `green-600`/`amber-600`/`red-600` usage (match-quality tiers,
validation states) is untouched — `DECISIONS.md`'s 2026-08-11 entry already
settled on reusing Tailwind's default semantic scale, and revisiting that
wasn't part of this pass's brief. `ok`/`warn`/`err`/`info` are available in
the Tailwind config for a future pass that explicitly revisits it.

### Light-surface neutrals (Porzellan)

**Added after the initial pass, on review** — the first cut of this pass
defined the full ink neutral scale but left the app's light-surface body
text, borders, and secondary surfaces on Tailwind's default `slate`, on the
reasoning that a full neutral-scale migration was a bigger retheme than a
token swap. That reasoning didn't hold up: `slate` is measurably blue-tinted
against the bundle's cool-neutral "Porzellan" scale, not an approximation of
it — `t1` (`#101619`) vs `slate-900` (`#0F172A`) differ by 17 units on the
blue channel alone, visible across a full page of body text. Migrated in
full, same role-mapping method as `brand` below.

| Token | Hex | Role |
|---|---|---|
| `raised` | `#FAFBFB` | Subtle nested-surface fill (was `slate-50`) |
| `line` | `#E3E8EA` | Default border / divider; also reused as a light background fill (was `slate-100`/`slate-200`) |
| `line2` | `#CFD4D6` | Stronger border — form-field/input borders specifically (was `slate-300`) |
| `t1` | `#101619` | Primary text — headings, body copy (was `slate-900`/`slate-800`) |
| `t2` | `#55636D` | Secondary text — labels, muted body copy (was `slate-600`/`slate-700`) |
| `t3` | `#8A96A0` | Tertiary text — **defined, not wired into any live element** (fails AA — see Accessibility below, same reasoning as `ink-t3`) |

`card` (`#FFFFFF`) needed no new token — it's already exactly Tailwind's
`white`, already used everywhere a card surface appears.

### Neutral-scale role mapping (mechanical swap, 31 templates)

Every `slate-NNN` call site (384 occurrences, 16 distinct prefix+shade
combinations) was grepped, read in its real template context, and assigned
to a role below — not picked by nearest-lightness hex. Two judgment calls
worth stating explicitly rather than leaving implicit:

- **`border-slate-100` and `border-slate-200` both collapse to `line`.** The
  bundle only defines one light-surface border token, not a three-tier
  hierarchy; the app's pre-existing two-tier distinction between them wasn't
  meaningful enough to invent a token the bundle doesn't have.
- **`bg-slate-100` reuses `line` as a background fill**, not a separate
  token — the bundle's own light block does the same (its border and
  "subtle fill" custom properties are the same value), so this isn't the
  app inventing a shortcut.

| Old class(es) | New class(es) | Role / note |
|---|---|---|
| `text-slate-900`, `text-slate-800` | `text-t1` | Primary text — headings, values |
| `text-slate-700`, `text-slate-600` | `text-t2` | Secondary text — labels, muted body copy |
| `text-slate-500`, `text-slate-400` | `text-t2` | **Not `text-t3`** — see the Accessibility note below; a real AA failure was caught and fixed within this pass, same treatment as `ink-t3` |
| `border-slate-100`, `border-slate-200` | `border-line` | Default border / divider (two old tiers collapse to one) |
| `border-slate-300` | `border-line2` | Form-field/input border specifically — this is the bundle's own documented role for this exact value |
| `divide-slate-100` | `divide-line` | List/table row dividers |
| `bg-slate-50` | `bg-raised` | Subtle nested-surface fill |
| `bg-slate-100` | `bg-line` | Light background fill (status pills, table zebra) — reuses the border token, matching the bundle |

**A second, real accessibility catch, not a restatement of the first:**
mapping `text-slate-500`/`text-slate-400` to `text-t3` (the "obviously
correct" nearest-role match) was tried first and computed at **2.76:1 on
`paper`, 3.02:1 on `white`** — both fail WCAG AA's 4.5:1 normal-text
threshold, at 98 call sites, almost none of them large enough to qualify
for the 3:1 large-text exception (mostly `text-xs`/`text-sm` helper text,
table headers, timestamps — genuinely read, not decorative). The class this
replaced (`slate-500`/`slate-400`) measured 4.35–4.76:1 in the same
positions — borderline-passing — so shipping `text-t3` here would have been
a real regression, not a wash. Remapped to `text-t2` instead (5.65–6.19:1,
comfortably passing) before this pass was considered done; `t3` stays
defined in the token set (it's a real bundle value) but wired into zero
live call sites, exactly matching how `ink-t3` was already handled. One
minor, honest cost: `applications/detail.html`'s Wayfinding station
description line had a `{% if s.reached %}text-t3{% else %}text-t2{% endif
%}`-shaped conditional that collapsed to identical branches once `t3` left;
simplified to a single class rather than ship a dead conditional — the
reached/not-reached distinction is still carried by the label line above it
and the connector color, just no longer double-encoded on the description
line too.

**Superseded 2026-08-25 (theme pass, same day) for the sidebar; still
accurate for the landing hero.** The paragraph below described the
sidebar and landing hero as both using "a fixed dark surface, not a
toggleable dark mode." That's no longer true for the sidebar — see "Theme
architecture" below: the sidebar now follows the theme (confirmed
directly against the bundle's own markup, `background: var(--card)`). The
landing hero remains fixed, by explicit decision (also in that section) —
the bundle has no themed version of it to model one on. The table
immediately below is otherwise unchanged and is now the *dark theme's*
value set (via `[data-theme="dark"]`), not a second fixed palette.

| Token | Hex | Role |
|---|---|---|
| `ink` | `#0C1013` | Fixed dark foundation surface (sidebar, hero) — was `#0B1220` |
| `ink-card` | `#12171B` | Nested card surface on ink — defined, no current consumer |
| `ink-raised` | `#171E23` | Second nested level on ink — defined, no current consumer |
| `ink-line` | `#222A30` | Border on ink surfaces — defined, no current consumer (sidebar dividers still use `border-white/10`) |
| `ink-line2` | `#303B42` | Secondary border on ink — defined, no current consumer |
| `ink-t1` | `#E9EFF1` | Primary text on ink — defined; plain `white` is used instead on active nav states for maximum contrast |
| `ink-t2` | `#9DABB3` | Secondary text on ink — sidebar nav default text, logout link, email line, admin section label |
| `ink-t3` | `#6E7C85` | Tertiary text on ink — **defined but not used anywhere live** (fails AA at normal text size — see Accessibility) |
| `ink-tint` / `ink-tint2` | `#0E2327` / `#123337` | Light-wash fill/border on ink — the ink analogue of `tint`/`tint2` above. Defined, no current consumer (no tinted panel exists on ink yet) |
| `ink-ok` / `ink-ok-tint` | `#4BBE7E` / `#0F2419` | Success semantic on ink — defined, no current consumer |
| `ink-warn` / `ink-warn-tint` | `#D9A22B` / `#241C0B` | Warning semantic on ink — defined, no current consumer |
| `ink-err` / `ink-err-tint` | `#E4665A` / `#251311` | Error semantic on ink — defined, no current consumer |
| `ink-info` / `ink-info-tint` | `#5FA6D6` / `#0E1D26` | Informational semantic on ink — defined, no current consumer |
| `bright` | `#4FC3C9` | Accent text/icon on ink — nav-active accent, hero badge text (was `#3B82F6`) |
| `bright-action` | `#12949B` | Primary action **fill** specifically on ink surfaces (new — fixes a real bug, see role-mapping table below) |
| `bright-action-hover` | `#3FBFC4` | Hover state of `bright-action` |

**This table is now the complete bundle dark block**, not a
sidebar-sized subset of it — every one of the bundle's
`[data-theme="dark"]` custom properties (`page`/`card`/`raised`/`line`/
`line2`/`t1`/`t2`/`t3`/`brand`/`brand-h`/`tint`/`tint2`/`cyan`/`ok`/
`okt`/`warn`/`warnt`/`err`/`errt`/`info`/`infot`/`sh`/`sh2`) has a named
token above, per the explicit instruction that ink is a full mode, not
an inverted afterthought half-defined down to whatever the sidebar
happens to use. The bundle's dark `--sh` is literally `none` — no
ink-surface hairline shadow token exists, on purpose, matching that. Its
`--sh2` is defined as `ink-overlay` (see Shadows below).

**Superseded 2026-08-25 (theme pass, same day):** "still no toggle" is no
longer accurate — this table's values are exactly what
`:root[data-theme="dark"]` now sets at runtime for
`page`/`card`/`raised`/`line`/`line2`/`t1`/`t2`/`t3`/`brand`/`brand-hover`/
`tint`/`tint2`/`ok`/`warn`/`err`/`info` (+ tints). The `ink`/`ink-t2`/
`bright` family named here stays exactly as described — a real, separate,
non-toggling fixed palette — but it's no longer *all* the app has for dark
surfaces; see "Theme architecture" below for which is which.

`bright` is the direct analogue of the pre-existing `brand`/`bright` split
this project already established (Signal Blue for light, Bright Blue for
dark — see the 2026-08-11 "Signal Blue vs. Ink Navy" entry below): one
token pair per surface, never the light-surface token used directly on
ink. `bright-action` is a new addition to that pattern, not a break from
it — the bundle's dark mode has two distinct dark-surface roles (a
text/icon accent and a separate, lower-contrast action-fill color), and
the pre-2.0 app conflated them into one `bright` value.

### Typography

`fontFamily.sans` (body/UI text) → **IBM Plex Sans**, replacing Inter.
Inter's `<link>` is removed from `base.html`; nothing references it
anymore, so nothing was left half-loaded. Two new families added:
`fontFamily.display` → **Sora**, `fontFamily.mono` → **IBM Plex Mono**.

**This directly supersedes** the "Sora is wordmark-only (Option A)"
decision below — see the superseded-notice at that section and the new
`DECISIONS.md` entry for the full reasoning and the honest loading-cost
consequence.

Role rule (must not drift — write it down once, here, so nobody re-derives
it differently later):

- **Sora 600** → titles, section headings, values, numbers (`tabular-nums`
  pairs with it well). Never body text.
- **IBM Plex Sans 400** → everything read as running language — paragraphs,
  button labels, form text. The default `font-sans` face.
- **IBM Plex Mono 500** → labels and source attributions **only** (e.g. a
  document's source tag, a field's uppercase micro-label). Never body copy.

New named `fontSize` tokens, exact bundle values (font family/weight is a
separate class, e.g. `font-display font-semibold`):

| Token | Size / line-height / tracking | Face + weight (bundle) |
|---|---|---|
| `text-display` | 52px / 1.04 / −0.035em | Sora 600 |
| `text-title` | 28px / 1.2 | Sora 600 |
| `text-section` | 19px / 1.35 | Sora 600 |
| `text-body` | 15px / 1.62 | Plex Sans 400 |
| `text-label` | 11px / 1.4 / +0.1em | Plex Mono 500 |

**Defined, not migrated.** Per explicit scope decision: existing
`text-3xl`/`text-xl`/etc. headings across every template keep their
current Tailwind default sizes this pass. Adopting the named scale
site-wide is a real per-template retype, deliberately left for a future
pass — this one is a token swap, not a retheme.

### Radius & spacing — no config changes needed

Tailwind's own default scale already matches the bundle almost exactly,
because both use the same base units (4px spacing, and a radius scale
that happens to land on Tailwind's existing named steps):

- `rounded-lg` (8px) = bundle's control radius — already used everywhere buttons/inputs are.
- `rounded-xl` (12px) = bundle's card radius — already used everywhere cards are.
- `rounded-full` (pill) = bundle's status-pill radius — already used for status pills.
- `p-6` (24px) = bundle's card-inner padding.
- `gap-8` / `space-y-8` (32px) = bundle's block gap.
- `mt-14` / `space-y-14` (56px) = bundle's section gap.

None of these needed a config change or a template edit — the tokens
already existed under Tailwind's own names. One true gap: the bundle's
20px "panel" radius has no matching Tailwind default (`rounded-2xl` is
16px, `rounded-3xl` is 24px) — added as `rounded-panel` (20px), available,
currently unused (no panel-type component exists in the app yet).

Adopting `mt-14`/`space-y-14` between major page sections (current
templates mostly use `mt-6`) is the natural next spacing-polish step this
pass deliberately didn't take — flagged as "still tidy rather than
spacious" since the Phase 5.5 checkpoint, unchanged; the tokens needed for
it now already exist as Tailwind defaults.

### Shadows

Tailwind's built-in `shadow-sm` — `0 1px 2px 0 rgb(0 0 0 / 0.05)` — already
closely matches the bundle's `--sh` — `0 1px 2px rgba(12,16,19,.05)` — the
only difference is near-black vs. ink-tinted black at the same 5% opacity,
imperceptible in practice. Left as-is; it's already applied at 154 call
sites across 27 templates and re-deriving all of them for a difference
nobody would see is not a good trade. Added the bundle's exact values as
two new named tokens for precision when they're actually needed:
`shadow-hairline` (`--sh`) and `shadow-overlay` (`--sh2`, `0 12px 32px
-10px rgba(12,16,19,.18)`) — available, currently unused (no modal,
dropdown, or popover exists in the app yet to need the overlay tier).
The bundle's dark-surface shadow pair was also captured: `--sh` is
literally `none` in dark mode (no token — a hairline shadow doesn't read
against ink), and `--sh2` is `shadow-ink-overlay` (`0 16px 40px -12px
rgba(0,0,0,.6)`) — defined, no current consumer, same as the rest of the
completed ink structural set above.

### Focus states

`_macros.html`'s `render_field()`/`render_checkbox()` — the single
centralized definition every form field and checkbox in the app draws
from — switched from a 1px inset ring (`focus:ring-1
focus:ring-brand-600`) to the bundle's actual spec: a real 2px solid
outline, 2px offset (`focus:outline focus:outline-2
focus:outline-offset-2 focus:outline-brand`), plus `focus:border-brand` on
text fields (border darkens to `brand` at the same time the outline
appears, matching the bundle's own focused-input example).

The sidebar nav links, admin nav links, the logout link, and the mobile
nav toggle/close buttons gained the ink-surface equivalent
(`focus:outline focus:outline-2 focus:outline-offset-2
focus:outline-bright`) — previously **none of these had any custom focus
style at all**, relying entirely on the browser default outline against
the dark sidebar, unverified. See Accessibility for the measured numbers
on both.

### Brand-shade role mapping (mechanical swap, ~24 templates)

The bundle defines the teal accent as two raw values (`brand`,
`brand-hover`) plus two light washes (`tint`, `tint2`) — it does not
define a Tailwind `50`–`900` shade ramp, because the 2.0 system doesn't
have one; `tint`/`tint2` **are** the 2.0 answer to "light badge fill and
border," not a smaller version of a bigger ramp. Per explicit decision,
every `brand-NNN` call site was greppped, read in its real template
context, and assigned to a role below — never picked by nearest-lightness
hex, which can put a fill color in a text role. One row needed a real
functional fix, not just a rename (see its note).

| Old class(es) | New class(es) | Role / note |
|---|---|---|
| `bg-brand-600` (solid fills: buttons, progress-bar fills, status-route markers) | `bg-brand` | Primary action background |
| `hover:bg-brand-700` | `hover:bg-brand-hover` | Primary action hover |
| `text-brand-600`, `text-brand-700`, `hover:text-brand-700` | `text-brand`, `hover:text-brand` | Link / tertiary action text (the single largest group — ~90 call sites: "Regenerate," "View job posting →," badge text, etc.) |
| `border-brand-600` (outline-button borders, focus borders, status-route ring markers) | `border-brand` | Brand-colored border on an actionable/interactive element |
| `border-brand-400` (bookmarklet drag-hint border) | `border-brand` | Same reasoning as `border-brand-600` — it's an interactive drag affordance, not a passive divider |
| `text-brand-800`, `text-brand-900` (heading/body text inside `tint`-colored info cards) | `text-brand` | Dark-on-tint brand text |
| `bg-brand-50`, `hover:bg-brand-50` | `bg-tint`, `hover:bg-tint` | Light wash fill — info cards, badge/pill backgrounds, outline-button hover fill |
| `border-brand-200`, `border-brand-300`, `hover:border-brand-300` | `border-tint2`, `hover:border-tint2` | Light wash border — info-card borders, badge borders, whole-card hover-affordance borders |
| `focus:border-brand-600 focus:ring-brand-600` / `focus:ring-brand-600` | see Focus states above | Ring→outline mechanism change, not a rename |
| `bg-brand-600 hover:bg-brand-500` (landing hero primary CTA, `class="rounded-lg bg-brand-600 ... hover:bg-brand-500"`) | `bg-bright-action hover:bg-bright-action-hover text-ink` (was `text-white`) | **This one was a real, pre-existing bug, not just a token rename.** The button sits on the ink hero but was using the *light-surface* brand token directly on dark — exactly the mistake the project's own "Signal Blue is light-only, Bright Blue is dark-only" rule (2026-08-11 entry below) was written to prevent, just missed for a fill color instead of a text color. Its inverted hover (lightening instead of darkening) turns out to have been a manual, undocumented patch for the resulting low contrast, not a mistake — moving to the real ink-surface action pair (which lightens on hover by design, matching the bundle) replaces that patch with a principled token. The white label text also failed AA here (3.66:1 against `#12949B`, computed — see Accessibility); switching the label to `ink`-colored text fixes it to 5.22:1, passing, at zero cost to the hover state (8.60:1). |

### Accessibility — measured, not assumed (2026-08-25)

Every pairing below is computed via the standard WCAG relative-luminance
formula, not eyeballed. Two of them were cross-checked against numbers
supplied independently during scoping and matched exactly (8.11:1 and
9.08:1), which is worth recording as a sanity check on the rest.

| Pairing | Ratio | WCAG AA (normal text 4.5:1 / large or UI 3:1) |
|---|---|---|
| Body text (`t1`, was `slate-900`) on page (`paper`, new `#F2F5F6`) | **16.66:1** | Pass (AAA) |
| Body text (`t1`) on card (`white`) | **18.25:1** | Pass (AAA) |
| Secondary text (`t2`, was `slate-600`/`700`/`500`/`400`) on page (`paper`) | **5.65:1** | Pass |
| Secondary text (`t2`) on card (`white`) | **6.19:1** | Pass |
| `t3` on `paper`/`white` (**not used anywhere**) | 2.76:1 / 3.02:1 | **Fails** for normal text — defined as a token (it's a real bundle value) but wired into zero live call sites, same reasoning as `ink-t3` below. See "Neutral-scale role mapping" above for the regression this avoided. |
| Primary button label (`white`) on `brand` fill | **5.39:1** | Pass |
| Primary button label (`white`) on `brand-hover` fill | **7.95:1** | Pass (AAA) |
| `text-brand` link/badge text on `white` | **5.39:1** | Pass |
| `text-brand` link/badge text on `paper` | **4.92:1** | Pass |
| `text-brand` heading/body inside a `tint` info card | **4.90:1** | Pass (narrow) |
| Focus outline (`brand`) against `white`/`paper` | 5.39:1 / 4.92:1 | Pass (needs 3:1) |
| Focus outline (`bright`) against `ink` | **9.08:1** | Pass (AAA) — matches the number supplied at scoping |
| Sidebar nav default text (`ink-t2`) on `ink` | **8.11:1** | Pass (AAA) — matches the number supplied at scoping |
| `ink-t3` on `ink` (not used anywhere) | 4.44:1 | **Fails** for normal text — this is exactly why `ink-t3` is defined but not wired into any live element this pass |
| White button label on `bright-action` fill (the landing CTA's *original* plan) | **3.66:1** | **Fails** — caught before shipping, see the role-mapping table's note; fixed by using `ink`-colored text instead (5.22:1, passes) |
| `bright-action` fill against `ink` page (button-vs-background, non-text) | **5.22:1** | Pass (needs 3:1) |

**Pre-existing, unaffected by this pass, noted for completeness:** input
borders (`border-line2`, was `border-slate-300`) measure **1.50:1** against
`white` — well under the 3:1 WCAG 1.4.11 non-text-contrast guideline for
UI-component boundaries. This is not a regression: `slate-300` measured an
almost identical 1.49:1 in the same position before this pass. It's a
genuine pre-existing gap, tracked under the separate Phase 9 accessibility
backlog, not new debt from this token swap.

**One real, new finding, not a restatement of the existing Phase 9 backlog
item:** the landing hero CTA would have shipped a genuine WCAG AA failure
(white text at 3.66:1) if the ink-surface action token had been applied
mechanically without checking text-on-fill separately from
fill-on-background. Caught and fixed within this pass — see the
role-mapping table above. No new failing pairing ships as a result of this
pass; `ink-t3` is defined but deliberately left unused precisely because
it fails at normal text size and nothing in the app has a large-text-only
use for it yet.

## Theme architecture — 2026-08-25 pass

Reverses the foundation-tokens pass's decision to treat `ink` as a fixed
surface with a toggle explicitly out of scope (see the superseded-notices
above, and `DECISIONS.md`). Product direction changed: AUSVIA now has a
real Porzellan/Tinte theme toggle, matching the bundle's own architecture.

### The bundle was verified directly, not inferred

The bundle (`AUSVIA 2.0 standalone.html`) is a self-extracting artifact
bundle — its real markup isn't visible by opening the file in a text
editor, only by running it. Unpacked it directly (its
`__bundler/template` payload is a JSON string containing the actual HTML)
rather than assuming from screenshots or prior notes. Two things this
settled that would otherwise have been guesses:

- **The sidebar is `background: var(--card)`** in the bundle's own
  markup — white in light, `#12171B` in dark. Not a fixed dark surface.
  This is the one reversal from the foundation-tokens pass: the desktop
  `<aside>` in `base.html` was `bg-ink`, now `bg-card`.
- **The mobile topbar and drawer are genuinely fixed**, not theme-following
  — confirmed two ways, not one: every mobile-frame topbar/drawer in the
  bundle's own Mobile screen hardcodes `background:#0C1013` (not
  `var(--page)`), and the bundle's own copy says so outright: *"Die
  bestehende mobile Struktur bleibt: Ink-Topbar mit Logo und Menü, Drawer
  von links, dieselben Ziele"* — "stays," not "adapts." Nothing changed
  here; today's app already matched this before the theme pass.

**The landing hero has no themed equivalent in the bundle to model one
on.** The bundle's own landing page is fully theme-following — plain
`var(--page)` background, `var(--t1)` headline, no full-bleed dark
section, no counterform graphic at all. The app's hero (the ink section
with the counterform SVG cutout) has no bundle design to convert to. By
explicit decision: **the hero stays fixed-ink**, deliberately rather than
by omission — its `bg-ink`/`text-ink-t2`/`bright-action` classes and its
one necessarily-raw SVG `fill="#0C1013"` (a `<path>` fill can't reference
a Tailwind class, so it's a literal kept in sync with the `ink` token by
comment, unchanged from the logo pass) already pinned it to the fixed ink
palette rather than a raw hex, so this pass didn't need to retokenize
anything there — it verified the pinning was already real, not
incidental. Revisit when the landing screen re-layout pass runs (per
`AUSVIA_2_0_SCREEN_INVENTORY.md`'s sequencing) — that pass has an actual
bundle spec to build the light version from; this one didn't.

Everything else in the app — every card, every page background, the new
desktop top bar, and the sidebar as of this pass — follows the theme,
matching the bundle's own "every surface follows the theme" position
(section 11 of the inventory): *"Tinte ist ein vollwertiger Modus, nicht
ein invertiertes Nachspiel"* — Tinte is a full mode, not an inverted
afterthought.

### Mechanism: CSS custom properties, not Tailwind `dark:`

`base.html` defines the full light/dark value set as CSS custom
properties, `:root { --page: ...; }` and `:root[data-theme="dark"] {
--page: ...; }`, and `tailwind.config`'s `colors` block points every
theme-following role at the matching `var(--x)` instead of a hex literal.
**No class name in any template changed as a result** — `bg-paper`,
`text-t1`, `border-line`, `bg-brand` all keep working exactly as before,
in both themes, because only the variable's *value* swaps under
`[data-theme="dark"]` on `<html>`. The alternative — Tailwind's
`darkMode: 'class'` with `dark:` variants — was explicitly rejected: it
would have added a second class at every one of the ~500 existing
color-class call sites (and every future one), where this approach adds
none. All values are unchanged from the foundation-tokens pass — this
restructures *how* they're referenced, not what they are; verified
byte-identical against the bundle's own light `:root` and
`[data-theme="dark"]` blocks (see table below).

| Token | Light | Dark | Was (foundation-tokens pass) |
|---|---|---|---|
| `paper` (page bg) | `#F2F5F6` | `#0C1013` | light-only; dark value = old fixed `ink` |
| `card` | `#FFFFFF` | `#12171B` | **new token** — was bare Tailwind `white`; dark value = old fixed `ink-card` |
| `raised` | `#FAFBFB` | `#171E23` | light-only; dark value = old fixed `ink-raised` |
| `line` / `line2` | `#E3E8EA` / `#CFD4D6` | `#222A30` / `#303B42` | light-only; dark values = old fixed `ink-line`/`ink-line2` |
| `t1` / `t2` / `t3` | `#101619` / `#55636D` / `#8A96A0` | `#E9EFF1` / `#9DABB3` / `#6E7C85` | light-only; dark values = old fixed `ink-t1`/`ink-t2`/`ink-t3` |
| `brand` / `brand-hover` | `#0B767D` / `#075A61` | `#12949B` / `#3FBFC4` | light-only; dark values = old fixed `bright-action`/`bright-action-hover` |
| `tint` / `tint2` | `#EDF6F6` / `#D3EAEB` | `#0E2327` / `#123337` | light-only; dark values = old fixed `ink-tint`/`ink-tint2` |
| `ok`/`warn`/`err`/`info` (+`-tint`) | as before | old fixed `ink-ok`/`ink-warn`/`ink-err`/`ink-info` (+`-tint`) values | light-only, undefined in dark |
| `on-fill` | `#FFFFFF` | `#0C1013` (ink) | **new, derived this pass** — see below, not a bundle value |

`ink`, `ink-card`, `ink-raised`, `ink-line`, `ink-line2`, `ink-t1`,
`ink-t2`, `ink-t3`, `ink-tint`/`ink-tint2`, `ink-ok`/`ink-warn`/`ink-err`/
`ink-info` (+ tints), `bright`, `bright-action`, `bright-action-hover`
**stay exactly as literal hex, not `var()`-based** — they're the
genuinely-fixed palette, now used only by: the mobile topbar/drawer, the
landing hero, and the `bg-ink/20` divider trick in the application-detail
station tracker (a fixed-black-at-opacity effect, not a themed surface —
making it `var()`-based would have inverted it into a near-invisible
light-gray-on-light-gray in light mode).

### `on-fill` — a derived token, not a bundle value

Measuring before migrating (not after) caught a real problem: a fixed
`text-white` button label, which was correct on every LIGHT fill, fails
AA against several of the DARK fills — not just on hover, at rest:

| Fill (dark value) | White label | Ink (`#0C1013`) label |
|---|---|---|
| `brand` `#12949B` | 3.66:1 — **fail** | 5.22:1 — pass |
| `ok` `#4BBE7E` | 2.34:1 — **fail** | 8.16:1 — pass |
| `warn` `#D9A22B` | 2.29:1 — **fail** | 8.33:1 — pass |
| `err` `#E4665A` | 3.31:1 — **fail** | 5.77:1 — pass |
| `info` `#5FA6D6` | 2.65:1 — **fail** | 7.20:1 — pass |

(All five LIGHT fills pass with white at 5.38–6.39:1 — ink also passes
there, just isn't needed.) Same flip every time — white in light, ink in
dark — so this is one shared variable (`on-fill`), not five separate
`on-brand`/`on-ok`/`on-warn`/`on-err`/`on-info` tokens. Migrated the 27
`text-white` sites paired with `bg-brand` (every primary button in the
app) to `text-on-fill`. `ok`/`warn`/`err`/`info` have no filled-pill
consumer yet (status pills are still the neutral `bg-line`/`text-t2`
treatment from the Phase 7 remediation — see
`AUSVIA_2_0_SCREEN_INVENTORY.md`), so this table is also the reference for
whoever builds the bundle's filled Offer (`ok` fill) and Accepted (`brand`
fill) status pills later: their label needs `on-fill`, not a fixed white,
from the start.

### Hardcoded-color hunt

Two categories of "hardcoded value that stays wrong in dark mode," found
by grepping for exactly that pattern and fixed in this pass:

- **`bg-white` card panels → `bg-card`.** 68 sites across 24 templates,
  every one in the `border-line bg-white shadow-sm`-shaped card pattern —
  checked directly, not assumed: `bg-white/NN` opacity overlays (33 sites,
  mostly `base.html`'s mobile chrome and the landing hero) were excluded
  from the sweep and stay literal, since those sit on the surfaces that
  remain fixed-ink; none of the 68 card sites were inside those surfaces.
- **Tailwind's stock semantic literals → `ok`/`warn`/`err`/`info` (+
  `-tint`).** 62 individual class occurrences across 18 templates —
  match-score bands and category-bar fills, validated/needs-review text,
  flash-message categories, admin/document status badges, destructive
  buttons, warning callouts. These were never migrated when
  `ok`/`warn`/`err`/`info` were first defined (foundation-tokens pass, "not
  yet wired in"). Measured before migrating, not after: Tailwind's
  `green-700`/`amber-700`/`red-600` all pass AA against a **light** card
  (4.83–5.02:1) but drop to **3.59–3.74:1** — a real AA failure — against
  the new **dark** card, since they were tuned for white backgrounds only.
  The tokens they replaced them with measure 5.31–7.86:1 in dark and
  5.06–6.39:1 in light — equal-or-better in both themes, not a regression
  anywhere. No pairing was migrated where the new value measured worse
  than the old one.

### The toggle

Icon-only (sun/moon, `_icons.html`), real `aria-label` that updates with
state ("Switch to dark theme" / "Switch to light theme"), keyboard
reachable with the same `focus:outline-brand` 2px ring as everything else.
Two placements sharing one `theme_toggle()` macro in `base.html`:

- **Mobile** — added to the existing fixed-ink topbar, left of the
  hamburger button. Styled for that fixed surface (`text-ink-t2`,
  `outline-bright`), not theme-var-based, since that bar doesn't follow
  the theme.
- **Desktop** — a new slim top bar above `<main>` (desktop had no
  persistent chrome at all before this pass). Deliberately minimal: the
  toggle and reserved space for the language switcher the i18n pass adds
  beside it, nothing else — no title, breadcrumb, or search. Checked
  against the bundle before inventing this: the bundle's own top bar (with
  screen tabs and a `PORZELLAN`/`TINTE` text button) is its screen-switcher
  demo chrome, not product UI — confirmed by its tab list matching the ten
  mockup screens exactly and its hardcoded, non-`var()` colors sitting
  outside the bundle's own `data-theme` wrapper entirely. None of the real
  screens render a top bar. So this bar's styling (`bg-card`,
  `border-line`) is an original minimal treatment using existing theme
  tokens, not a bundle-sourced pattern.

Persistence and no-flash, both in `base.html`:

- **Persistence**: `localStorage['ausvia-theme']`, written on toggle.
- **First visit** (nothing stored): `prefers-color-scheme` decides.
- **No flash**: a synchronous inline `<script nonce="{{ csp_nonce }}">` at
  the very top of `<head>`, before the Tailwind CDN script, sets
  `data-theme` on `<html>` before first paint. It carries the nonce
  because `script-src` has no `'unsafe-inline'` (see `SECURITY.md`/
  `app/security_headers.py`) — an un-nonced script here would be silently
  CSP-blocked, which produces exactly the flash this exists to prevent,
  just a different one (stuck on the light default until the next
  toggle). The `<style>` block defining the CSS variables needs no nonce —
  `style-src` already carries `'unsafe-inline'`, unavoidably, because the
  Tailwind CDN injects its own runtime `<style>` tag that this app's code
  can't attach a nonce to.

### Sidebar rework

`nav_links()` (shared by the desktop sidebar and the mobile drawer, per
the Phase 7 "never drift" reasoning for why it's one macro at all) took a
`surface` argument (`'themed'` | `'fixed-ink'`, default `'fixed-ink'` so
the drawer's call site didn't need to change) rather than being split in
two — the nav *item list* stays single-sourced; only the color classes
branch. The themed surface's active-item treatment (`bg-tint` fill,
`t1`/`t2` text split, an inset `brand` left border) isn't invented — it's
read directly from the bundle's own nav-item rendering logic
(`background: on ? var(--tint) : transparent`, `color: var(--t1)` /
`var(--t2)`, `box-shadow: inset 2px 0 0 var(--brand)` on the active item).

### Contrast — measured for both themes

| Pairing | Light | Dark |
|---|---|---|
| Body text (`t1`) on `page` | 16.66:1 | 16.45:1 |
| Body text (`t1`) on `card` | 18.25:1 | 15.53:1 |
| Secondary text (`t2`) on `page` | 5.65:1 | 8.11:1 |
| Secondary text (`t2`) on `card` | 6.19:1 | 7.65:1 |
| `t3` on `card` (**not used for text, either theme**) | 3.02:1 — fails | 4.20:1 — fails |
| Primary button label (`on-fill`) on `brand` | 5.38:1 | 5.22:1 |
| Focus ring (`brand`) on `page` | 4.91:1 | 5.22:1 |
| Sidebar nav text (`t2`/`t1` on `card`, new pairing) | 6.19:1 / 18.25:1 | 7.65:1 / 15.53:1 |
| `ok` on `ok-tint` / on `card` | 5.31:1 / 6.06:1 | 6.97:1 / 7.70:1 |
| `warn` on `warn-tint` / on `card` | 5.06:1 / 5.59:1 | 7.35:1 / 7.86:1 |
| `err` on `err-tint` / on `card` | 5.59:1 / 6.39:1 | 5.38:1 / 5.45:1 |
| `info` on `info-tint` / on `card` | 4.83:1 / 5.51:1 | 6.47:1 / 6.80:1 |

Every pairing above passes AA (4.5:1) in both themes. `t3` fails at normal
text size in both light (3.02:1, already known from the foundation-tokens
pass) and dark (4.20:1, newly measured) — stays defined, deliberately
wired into zero live call sites in either theme, same reasoning as
`ink-t3` above: real bundle/derived values, known traps, not bugs to fix.

### Verification

Full pytest suite: 442 passed / 3 skipped, unchanged — this pass is
templates/CSS/JS only. Rendered both authenticated and public templates
through the app directly (dashboard, profile, documents, applications,
Gmail) to confirm no Jinja errors and that the new classes/markup are
actually present in the output. **Not independently verified in this
pass: an actual browser-rendered visual pass in both themes** — no
browser-automation tool was available in this environment to drive one.
The CSS variable values, the contrast math, and the template rendering
were all checked directly; the remaining risk is confined to things only
a rendered browser would catch (e.g. a genuinely missed call site that
still resolves visually wrong despite valid CSS). Flagged here rather than
silently claimed as done.

### Logo — Wegmarke replaces Aperture (implemented 2026-08-25)

**Aperture, rev 1.0, is retired.** The symbol is now **Wegmarke**
("waymark") — two parallel offset tracks at the same angle, the right one
leading, motion implied by position rather than a drawn arrow. This is
exactly what the previous pass's "flagged, not fixed" note above
predicted would eventually need doing; this pass is that follow-up,
implemented in full, not just documented.

**Construction**, transcribed exactly from the bundle's own Foundations
reference screen ("01 — MARKE, Offset — zwei Spuren, eine voraus"), not
approximated: 48-unit grid, bar width 8 (constant), the right track 6
units higher and 14 units ahead of the left one. Two flat, non-overlapping
shapes — no strokes, no cutout/evenodd construction (unlike Aperture,
which was a single counterform path). Exact path data:

```
M12 34 L20 12 L28 12 L20 34 Z
M26 28 L34 6 L42 6 L34 28 Z
```

**Below 22px the bundle switches to a wider-bar variant** (bar width 10,
not 8) so the gap between the two tracks stays legible at small sizes:

```
M11 35 L20 11 L30 11 L21 35 Z
M25 29 L34 5 L44 5 L35 29 Z
```

This switch is **automatic inside `_logo.html`'s `symbol()` and
`lockup()` macros** (keyed on the `size`/`height` param), not left to each
call site to remember — verified directly against the real macro output,
not just read from the source: rendering `symbol(size=21)` produces the
wide-bar variant, `symbol(size=22)` produces the standard variant, exactly
at the bundle's stated threshold.

**App icon** (viewBox `0 0 48 48`, new `app_icon()` macro): a rounded-rect
tile (`rx="11"`, ~23% of the grid) filled `brand`, with the standard-size
mark knocked out in the card color (`#FFFFFF`) rather than drawn on top —
matches the bundle's own "GRÖSSEN · APP-ICON" composited example exactly.
Nothing in the app currently calls this macro (no manifest or
apple-touch-icon exists in this repo to consume it — see "Static assets
regenerated" below) — it's available for when one is added.

**Color — one real discrepancy in the bundle, resolved in favor of the
shipped token, not guessed:** the bundle's own Foundations screen renders
the mark four different ways, and two of those hardcode `#0F7379` where
the other two use `var(--brand)` (`#0B767D` on light). These are two
different teals in the *same reference screen* — internally inconsistent,
not a deliberate second color. Resolved by using the token everywhere,
never the hardcoded value: `#0B767D` is what every other surface in this
app already renders as `brand` (buttons, links, focus rings — the entire
"single accent" system from the tokens pass), and `#0F7379` has no other
consumer anywhere in the app. Using it here would introduce a second,
undocumented teal for no reason beyond one inconsistent example in the
bundle's own art. Color roles:

| Context | Color | Token |
|---|---|---|
| Symbol on light surfaces | `#0B767D` | `brand` |
| Symbol on ink surfaces | `#4FC3C9` | `bright` |
| App icon tile fill | `#0B767D` | `brand` |
| App icon mark (knocked out) | `#FFFFFF` | `card` |

**The wordmark is unchanged — its spec was already correct and needed no
rework.** The bundle's own type section documents the wordmark exactly as
`_logo.html`'s `wordmark()`/`lockup()` macros already implement it:
**Sora SemiBold, lowercase "ausvia", −4% tracking.** The outlined vector
path baked into `_logo.html` (extracted from the real licensed Sora
SemiBold font via `fontTools`) stays exactly valid and was not touched —
only the symbol half of every lockup changed this pass. The wordmark's
own text color is `#0C1013` on light, `#FFFFFF` on dark, set via each
lockup call site's `wordmark_color` param.

**One real drift bug, caught and fixed, not just flagged:** the
light-surface default had been hardcoded as `#0B1220` — the *old*,
pre-tokens-pass `ink` surface hex. The tokens pass renamed the surface
token to `#0C1013` without updating this same hex's other historical use
as light-surface wordmark text (see the 2026-08-11 "Ink Navy as a real
foundation element" note), leaving a genuine leftover of the retired
value live in production. This pass initially flagged it as
out-of-scope ("symbol only") and left it; on review that was too
conservative for a one-line, zero-risk correction of an already-retired
literal — fixed in `_logo.html`'s `wordmark()`/`lockup()` macro defaults
and the four static SVGs that hardcoded it
(`ausvia-lockup-primary-light.svg`, `ausvia-lockup-stacked.svg`,
`ausvia-lockup-tagline.svg`, `ausvia-wordmark-ink.svg`). Confirmed zero
remaining live references via grep (the only two `#0B1220` occurrences
left in the codebase are accurate historical comments noting what the
value used to be, not live color). Live-verified against the running
dev server: the landing page's served HTML now renders the wordmark in
`#0C1013`.

**Clear space and minimum sizes**, transcribed from the bundle's
"FREIRAUM & MINDESTGRÖSSE" note: clear space is half the mark's height, on
every side; minimum sizes are 16px for the bare mark, 88px for the full
lockup (below that the wordmark's letterform detail stops being legible).
Both are call-site/usage rules, encoded in `_logo.html`'s header comment
and here — a macro can't enforce spacing or container sizing on its own.

**Static assets regenerated** (17 files under `app/static/brand/`,
existing filenames kept, per explicit instruction — geometry and, where
applicable, color updated in place):
`ausvia-symbol-{blue,bright,ink,white,black,currentcolor}.svg`,
`ausvia-lockup-{primary-light,primary-dark,mono-black,mono-white,stacked,
stacked-dark,tagline}.svg`, `ausvia-appicon-source.svg` (1024px canvas,
same construction scaled up: `rx="234.67"`, paths scaled ×21.3333),
`favicon.svg`, `favicon-32.png`, `favicon-16.png` (regenerated via Pillow
— no SVG rasterizer, e.g. cairosvg/Inkscape/ImageMagick, is available in
this environment, so these were redrawn from the exact same path
coordinates at 8× supersampling and downsampled with LANCZOS, not
approximated by eye). `favicon-32.png` uses the standard path variant,
`favicon-16.png` the 16px variant — visually confirmed side by side, not
just asserted (the 16px variant's wider bars and narrower gap are visibly
different at a glance). **Checked and confirmed absent, so nothing was
regenerated or invented for them:** no `.ico` file, no `apple-touch-icon`,
no web manifest exists anywhere in this repo.

**One filename/content mismatch worth flagging, not fixed this pass:**
`ausvia-symbol-blue.svg` now contains the mark in `brand` teal
(`#0B767D`), not blue — kept per the explicit instruction to preserve the
existing filename convention, but the name is now inaccurate. A future
asset-naming pass could rename it (nothing in the codebase references
these files by path — confirmed via grep — so it would be a safe,
zero-risk rename), not done here since renaming wasn't asked for and
wasn't necessary to complete this pass. `ausvia-symbol-ink.svg` was
updated to the *current* `ink` hex (`#0C1013`, not the pre-tokens-pass
`#0B1220`) since that file is purely about the symbol's fill color, which
is squarely in this pass's scope.

**`LOGO.md`** still documents Aperture's full historical construction
(artboard, counter span, leg angle, etc.) — left as-is, not rewritten,
since it's now a historical record, not the live spec; a short
superseded-notice was added at its top pointing here instead of deleting
or rewriting the history it documents.

---

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

**Superseded 2026-08-25** — see "Foundation tokens — 2026-08-25 pass" /
Typography above and the corresponding `DECISIONS.md` entry. Sora is now
loaded as a live webfont for titles/section headings/values/numbers
app-wide, not scoped to the outlined logotype only. Kept below for
history — the reasoning was sound for what the project needed *then*.

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

**Superseded 2026-08-25** — see "Foundation tokens — 2026-08-25 pass"
above for the current token set (`brand`/`bright`/`ink`/`paper` etc. now
hold different hex values) and `DECISIONS.md` for the palette-change
decision. The logo itself keeps the Signal-Blue/Bright-Blue colors
described below (frozen, out of scope) — flagged as a known
inconsistency above. Kept below for history and because the *role*
language (light-surface vs. dark-surface token pairing) it established
is still exactly the pattern the 2.0 tokens follow.

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
