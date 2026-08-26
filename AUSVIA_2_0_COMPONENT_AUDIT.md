# AUSVIA 2.0 — Component Audit

Read-only pass, 2026-08-26. Catalogues every repeated presentational pattern
already in `app/templates/` — grepped and read directly, not inferred —
then compares each against `AUSVIA_2_0_SCREEN_INVENTORY.md`'s component-layer
section (§12: buttons, inputs, status pills, chips, notices, composite rows,
Intelligence surface). Purpose: the component-layer build (inventory's
revised-sequencing step 5) should start from what's actually load-bearing in
the app today, not rediscover it mid-build. No templates were touched to
produce this — every count below is a real grep/read result, not an estimate.

---

## 1. Card / panel shapes

**64 occurrences, 6 distinct shapes.** One shape accounts for 57 of them
(89%) — the other five are deliberate, low-frequency variants, not drift.

| Shape | Class string (core) | Occurrences | Where |
|---|---|---|---|
| **Default card** | `rounded-xl border border-line bg-card shadow-sm` (+ p-4/5/6, mt-N) | **57** | Every screen — the app's one real "card" today |
| Tinted CTA banner | `rounded-xl border border-tint2 bg-tint p-6` | 2 | `applications/detail.html:162` (Review & approve), `main/dashboard.html:8` (profile completeness) |
| Muted nested panel | `rounded-xl border border-line bg-raised/60 p-5` | 2 | `applications/detail.html:266,293` (Gmail replies, Status & history) |
| Danger card | `rounded-xl border border-err/40 bg-card shadow-sm p-6` | 1 | `applications/detail.html:368` (Delete this application) |
| Plain info box | `rounded-xl border border-line bg-raised p-4` | 1 | `jobs/import.html:22` (bookmarklet install steps) |
| Dashed dropzone | `rounded-xl border border-dashed border-line2 bg-raised p-6` | 1 | `jobs/import.html:77` |

**Read:** the default card is genuinely one shape, used consistently — a
clean macro candidate as-is. The other five are real, semantically distinct
uses (highlight, de-emphasis, danger, plain, dropzone) that happen to be
rare — worth keeping as *variants of one macro* (a `tone=` or `variant=`
param), not as five separate one-off classes and not collapsed into the
default.

## 2. Badges and pills

**~24 occurrences across 5 distinct treatments** (excluding the 4 station-
tracker dots, a different sub-genre — see §6).

| Treatment | Class string | Occurrences | Note |
|---|---|---|---|
| Neutral pill | `rounded-full bg-line px-N py-N text-xs font-medium text-t2` | 10 | Application status pills, message-intent pill, inactive/disabled states. **No per-status color anywhere** — confirmed deliberate (Phase 7 remediation removed colour-only indicators); this is the same pill for every status today |
| Affirmative pill | `rounded-full bg-ok-tint px-2 py-0.5 text-xs text-ok` | 6 | "Active"/"Enabled"/"Primary CV" etc. — the one place a semantic color *is* already used on a pill |
| Fixed-ink badge | `rounded-full bg-white/10 px-3 py-1 text-xs font-semibold text-bright` | 1 | Landing hero only, not reusable off the fixed-ink surface |
| 4-state score badge | conditional `bg-ok-tint`/`bg-tint`/`bg-warn-tint`/`bg-line` | 1 call site | `jobs/search.html:48` — one site, four possible renders, all inline-conditional (not a shared macro) |
| Skill/language chip | `rounded-full border border-line bg-raised px-3 py-1 text-sm` + inline `×` remove button | 2 call sites (loops) | `profile/view.html:104,127` — the closest existing thing to a bundle "attribute chip," but always removable and undifferentiated by type |

**Read:** two real reusable pill shapes exist (neutral, affirmative) — no
warn/err-toned pill exists anywhere yet, despite the tokens (`warn`, `err`)
being available and already used for text/borders elsewhere. That's a real
gap, not an oversight to preserve.

## 3. Buttons

**~78 occurrences across 5 tiers**, matching the bundle's own five-tier
button spec closely in *count* of tiers, less closely in *shape*.

| Tier | Class string (core) | Occurrences |
|---|---|---|
| Primary (filled) | `rounded-lg bg-brand px-N py-N text-sm font-semibold text-on-fill hover:bg-brand-hover` | **27** |
| Secondary (outline) | `rounded-lg border border-line2 [bg-card] text-t2 hover:bg-raised` | 4, + 1 dynamic two-state (`jobs/detail.html:21`, Save/Saved toggle) |
| Tertiary (text-link) | `text-sm`/`text-xs font-medium text-brand hover:underline`, no border/bg/height at all | **35+** |
| Destructive (text-link) | `text-xs font-medium text-err hover:underline` | 5 |
| Destructive (bordered) | `rounded-lg border border-err/50 px-4 py-2 text-sm font-semibold text-err hover:bg-err-tint` | 2 (identical, both in `applications/detail.html`) |
| Disabled | — | **0 found anywhere** |

**Read:** Primary is a real, consistent macro candidate (27 identical-shape
sites, only label/width varying) — same conclusion the earlier Tailwind
build pass reached independently when it swept these for `text-on-fill`.
Tertiary is the single most-used interactive pattern in the app by a wide
margin, but it's a **bare text link with zero button chrome** — no height,
no padding-as-button, no border. The bundle spec's Tertiary is a real
button (height 36, `radius 8`, just filled transparent) sized the same as
Primary/Secondary. These are not the same shape today; reconciling them is
a real design decision, not a rename. Destructive is inconsistent between
its two existing forms (text-link vs. bordered) — the component layer
should pick one, not keep both. **No disabled button exists anywhere to
check against the bundle's disabled spec** — either it's never been needed
yet, or disabled state is handled via the bare HTML `disabled` attribute
with no custom styling (unverified either way; worth a quick check before
the build, not a blocking gap).

## 4. Empty states

**20 occurrences, one shape, no exceptions.** Every empty state in the app
is:

```html
<p class="text-sm text-t2 [mb-3]">No {thing} yet[. {inline link}]</p>
```

Two of the twenty sit inside a `<td colspan="N">` instead of a bare `<p>`
(table contexts: `admin/codes.html:54`, `admin/ai_usage.html:35`), same
text treatment either way.

**Read:** completely consistent — there's no drift to clean up. But it's
also **far more minimal than the bundle's spec** (heading + one line of
guidance + one action button). Today it's one muted sentence, sometimes
with an inline text link folded into the sentence rather than a separate
action. This is a real gap to design for, not a "just wire it up" job —
every one of the 20 sites needs a decision on whether it gets the fuller
treatment or stays minimal.

## 5. Form field wrappers beyond `render_field()`

**8 raw form controls**, none going through `_macros.html`. All 8 already
converged on the same visual shape independently (confirmed during the
Tailwind build pass's inline-style/dark-mode sweep, re-verified here):

`rounded-lg border border-line2 bg-card text-t1 px-3 py-2 text-sm` (± `font-mono`, ± `rows-N`)

| Element | File | Note |
|---|---|---|
| Cover letter textarea | `applications/detail.html:37` | `font-mono`, `rows="16"` |
| Application email body | `applications/detail.html:58` | `rows="8"` |
| Follow-up email body | `applications/detail.html:85` | `rows="6"` |
| Reply-suggestion textarea | `applications/detail.html:358` | `rows="5"`, id includes message id |
| Delete-confirmation input | `applications/detail.html:396` | plain text input |
| Document type select | `documents/list.html:14` | the one raw `<select>` in the app |
| Document file input | `documents/list.html:22` | native picker, can't be fully restyled |
| Document description input | `documents/list.html:26` | plain text input |

**Read:** these already match `render_field()`'s own visual output almost
exactly (radius, border, focus ring) — they just lack its label/error
wrapper because none of them are WTForms fields. A `render_textarea()` /
raw-field variant of the same macro, rather than a new pattern, is the
low-risk move here.

## 6. Everything else repeated 3+ times

| Pattern | Occurrences | Note |
|---|---|---|
| **Stat tile** — `rounded-xl border border-line bg-card shadow-sm p-5` + uppercase label + `text-3xl font-bold text-t1` value | 3 call sites, 12 individual tiles | `main/dashboard.html` (4), `admin/overview.html` (5), `admin/ai_usage.html` (3) — byte-identical shape every time, looped from a label/value list. Clean macro candidate. |
| **Table shell + header row** — `<table class="w-full text-sm">` + `<tr class="border-b border-line text-left text-xs uppercase tracking-wide text-t2">` | 6 tables | `admin/ai_usage.html`, `admin/users.html`, `admin/job_sources.html`, `admin/overview.html`, `admin/codes.html`, `documents/list.html`. Wrapper + header shareable; row/cell structure differs per table so only those two parts generalize. |
| **"Generated by {{ provider }}."** AI-provenance line | 6 | `applications/detail.html` ×2, `companies/detail.html`, `profile/view.html` ×2, `jobs/detail.html`. Byte-identical modulo the variable — the primitive precursor to the bundle's Intelligence-surface provenance line. |
| **Uppercase eyebrow label** — `text-xs [font-medium\|font-semibold] uppercase tracking-wide text-t2` | 15+ | Table headers, stat-tile labels, section eyebrows, fact-tile labels. This reads as a typographic *token* wanting a name (the bundle's own `text-label` role) more than a component. |
| **Journey/station dot markers** — 4 states (`current`/`skipped`/`reached`/`unreached`), each a distinct `rounded-full` circle treatment | 4 states, 1 call site (`applications/detail.html:228-236`) | Not a pill — a small marker family, fixed-ink-aware (`border-ink`, `bg-ink/20`). Purpose-built for the station tracker; not obviously reusable elsewhere as-is. |
| **Match-score category bars** | 2 call sites, 5 bars each (job detail: one bar per category; dashboard: profile completeness, 1 bar) | Shares `.ausvia-bar-fill`/`.ausvia-bar-animated` (the 12px-shear construction, already verified bundle-accurate). Structurally: 5 *separate stacked full-width bars*, not one segmented band — see §7. |

---

## 7. Comparison against the bundle's component layer (§12)

### Clear existing counterpart

| Bundle component | Existing counterpart | Fit |
|---|---|---|
| **Inputs** (radius 8, 2px focus ring, error-with-message) | `_macros.html`'s `render_field()` | **Closest match of any component in this audit.** Already radius-8, already a real 2px solid outline focus ring, already renders the error message beneath the field. Essentially already built to spec. |
| **Primary button** | 27-site `bg-brand … text-on-fill` pattern | Same fill/radius logic already; just needs the macro extraction |
| **Progress bar** (profile completeness) | `.ausvia-bar-fill`/`.ausvia-bar-animated` | Already verified bundle-accurate (12px shear, exact construction) in an earlier pass — nothing to redesign |
| **Job card** (composite row) | `jobs/search.html`'s result card | Right shape (`border-line bg-card shadow-sm p-5`), missing the bundle's meta-chip row (today: plain text separated by `·`) |
| **Application row** (composite row) | `applications/list.html`'s link-card | Close match already |
| **Partial-failure notice** ("names which source failed and why") | `jobs/search.html:18-27`'s `ingest_errors` block | **Closer than it looks** — already loops `{% for source, message in ingest_errors %}` and prints exactly "source: message" per failed source. This is real logic already wired up; the bundle spec is a visual upgrade to existing data, not new plumbing. |
| **Success/error/info notice** | `_flashes.html` (3 categories, tinted, icon+text) | Direct counterpart for page-level flashes. The tinted CTA banners (`border-tint2 bg-tint`, 2 sites) are a second, inline-notice counterpart worth noting separately from flashes. |

### Genuinely new

| Bundle component | Why it's new |
|---|---|
| **Status pills — all ten, each with a dot** | Existing pills are one uniform neutral treatment with zero per-status color and no dot, by deliberate Phase 7 design. Ten distinct colored-fill states with a state-carrying dot is real, new build work — and revisits (compatibly, per the bundle's own "never color alone" rule) a decision Phase 7 made. |
| **Source chips** (ARBEITSAGENTUR / ADZUNA / MANUAL IMPORT, Plex Mono, tracked) | No mono-tracked chip exists anywhere. The Adzuna attribution macro is legally-mandated, differently shaped, and not reusable for this. The plain `bg-line` source label in `jobs/search.html` is a different visual language entirely (no mono, no tracking). |
| **Coverage chips** (Erfüllt/Teilweise/Fehlt/**Nicht bewertet**) | The *information* already exists — `jobs/detail.html`'s strengths/gaps list already has a fourth "not evaluated" state (the `unknown()` icon, distinct from required/preferred-missing) — but as inline list items with icons, never as chips. Converting is a real layout decision, not new data. |
| **Intelligence surface** (3px brand edge, left-only radius, provider+model+reliability header, tint-drops-on-edit) | Zero existing counterpart for the construction itself — grepped for any `border-l-[3px]`/left-accent-edge pattern anywhere in the app and found none. The "Generated by {{ provider }}" line (§6) is the only existing fragment; reliability badge, tinted-fill-that-clears-on-edit, and the left-edge construction are all net new. |

### Existing patterns with no bundle equivalent — need a decision

| Existing pattern | The decision |
|---|---|
| **Tertiary button as a bare text link** (35+ sites) | The bundle's Tertiary is a real button (height 36, radius 8, filled transparent) sized like Primary/Secondary. The existing pattern is un-buttoned inline text. Reconciling these changes the single most-used interactive element in the app — worth deciding deliberately, not silently, before the build starts. |
| **Two incompatible destructive-button shapes** (text-link ×5 vs. bordered ×2) | Pick one. Neither is wrong; having both is the drift. |
| **Minimal empty states** (20 sites, one muted sentence) | Bundle wants heading + guidance + action. Upgrading all 20 is real scope — worth sizing before the component pass claims "empty states" as done. |
| **Muted nested panel** (`bg-raised/60`, 2 sites) and **plain info box** / **dashed dropzone** (`jobs/import.html`, 2 sites) | These are real, deliberate card variants with no bundle-named equivalent. Fold them into the card macro as named variants, or leave as local one-offs — either is defensible, but it should be a choice. |
| **Match-score bars as 5 stacked full-width bars**, not one segmented band | The bundle's "match band" is a single bar with 5 adjacent segments, segment *width* = weight, *fill* = achievement. The existing pattern solves the same transparency goal differently (one full-width bar per category, stacked). This is a real structural difference, not a styling gap — worth flagging explicitly since it's easy to assume "match band exists" when what exists is a different design solving the same problem. |
| **Skill/language chips always carry a remove `×`** | The bundle's attribute chips (Primary CV, SPS · fortgeschritten) read as read-only display badges in some contexts. Existing chips are edit-affordance-first. Whether a read-only variant is needed alongside the removable one is a real question, not answered by what exists today. |

---

## Summary

- **6** card/panel shapes (1 dominant at 57 sites, 5 real variants at 1-2 each)
- **5** pill/badge treatments (~24 sites) — no warn/err-toned pill exists yet
- **5** button tiers (~78 sites) — Tertiary's shape diverges from the bundle spec; no disabled example exists anywhere
- **20** empty states, one consistent (but minimal) shape
- **8** raw form controls already converged on `render_field()`'s own visual language without sharing its macro
- Stat tiles, table shells, and the AI-provenance line are clean, low-risk macro extractions with zero design decisions attached
- Of the bundle's named components: **Inputs** is effectively already built; **Primary button**, **progress bar**, **job/application rows**, and the **partial-failure notice** have close existing counterparts; **status pills**, **source chips**, and the **Intelligence surface** construction are genuinely new; and five existing patterns (tertiary-button shape, the two destructive-button shapes, empty-state minimalism, the stacked-bars vs. segmented-band match visualization, and chip removability) need an explicit decision before the component layer can claim to "cover" what the bundle specifies.
