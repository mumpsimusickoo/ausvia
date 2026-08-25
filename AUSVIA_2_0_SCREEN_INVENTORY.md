# AUSVIA 2.0 — Screen Inventory

Two parts. **Part 1** is a verification pass against the live repo, done
2026-08-25. **Part 2** is the original inventory exactly as submitted —
unmodified, so you can see what the corrections above are correcting.

Do not treat this file as a work order. It is a map, same as the original.

---

# Part 1 — Verification pass (2026-08-25)

Every A/B/C/D call in Part 2 was made against the project docs, not the
live repo. This pass checked each one directly against the current code
(routes, models, templates, forms) as of commit `d109c66`. Only items that
needed a correction or a materially different note are listed below —
anything not mentioned here was checked and confirmed accurate as written.

## The four direct questions

**1. Does `manual_import.py` already cover URL import, or is a fetch/parse
path genuinely missing?**

It's already built. `app/jobs/manual_import.py:fetch_and_extract_text()`
does a real `requests.get()` (10s timeout, 3MB cap, User-Agent set),
handles 401/403/429 and non-200/non-HTML responses with specific
messages, strips script/style/nav/footer/header tags, extracts readable
text via BeautifulSoup, and returns `{page_title, text}` capped at 20k
chars. `ManualImportUrlForm` (`app/jobs/forms.py`) already accepts one or
more URLs, one per line.

→ Screen 4's "Anzeige per URL importieren" item is **not C, it's A**.
Full fetch/parse/review-form prefill already exists and is shipped.

**2. Which of the ten application statuses exist in the enum today?**

All ten. `Application.APPLICATION_STATUSES`
(`app/models/application.py:4-15`) is exactly `preparing, ready, sent,
follow_up, interview, offer, accepted, rejected, withdrawn, expired` —
a 1:1 match with the bundle's list.

→ Section 0.2 is **not B/C, it's A**. The status schema work is done.

One nuance worth keeping distinct from the enum question: the *visual*
journey component on Application Detail (`STATION_ORDER` in
`app/applications/status_route.py:13`) deliberately shows only 6 of the
10 as linear stations (`preparing, ready, sent, follow_up, interview,
offer`) — `accepted/rejected/withdrawn/expired` are treated as terminal
exits, not stations, by design. That's a real, already-made UX decision,
not a gap in the enum. It's why Screen 6's note ("Reply is not one of
today's 6 `STATION_ORDER` stations") is accurate as written.

**3. Is `GmailMessage.classification_confidence` really the only
confidence/reliability field anywhere in the models?**

Confirmed — yes. A case-insensitive grep for `confidence` across the
entire `app/` tree returns only that column (`app/models/integration.py:58`,
a string `"high"|"medium"|"low"`) and its own call sites
(`app/ai/reply_ai.py`, the classification prompt, one template line).
Nothing else in `app/models/` has a reliability-style field.

→ Section 0.3's "same small schema addition seven more times" (8
Intelligence surfaces, 1 already has the field) is accurate as stated.

**4. Does nothing track whether AI text was later hand-edited?**

Partly wrong. `edited_at` (nullable `DateTime`) already exists and is
already wired up for **2 of the 5** named features:

- Cover letter — `GeneratedDocument.edited_at`, set in `save_cover_letter`
  (`app/applications/routes.py:183`)
- Application email — `GeneratedEmail.edited_at`, set in `save_email`
  (`app/applications/routes.py:228`)

(Same pattern also already covers a 6th AI-content type not in the
inventory's list of five: follow-up email —
`FollowUpEmail.edited_at`, `app/applications/routes.py:274`.)

For the other 3 of 5, the original claim holds, with different sizes:

- **Interview prep** (`InterviewPrep`) — no `edited_at` column, and no
  save/edit route at all. Generate-only today (`generate_interview_prep_route`).
- **CV profile statement** (`CvProfileStatement`) — same: no column, no
  edit route, generate-only.
- **Reply suggestion** (`GmailMessage.ai_suggested_reply`) — a plain
  `Text` column with no edited-tracking sibling. The reply route
  (`app/applications/routes.py:592`) already reads
  `request.form.get("reply_text") or message.ai_suggested_reply`, i.e.
  there's already an editable textarea in the flow — it just never
  writes back whether the user changed it.

→ The schema/UI gap is real for 3 of 5, not 5 of 5, and two of those
three (interview prep, CV statement) need a save route built from
scratch, not just a column — bigger than "add edited_at" implies. Reply
suggestion is the smallest of the three: the edit surface already
exists, only the tracking column is missing.

## Section 0 corrections

- **0.2** — corrected to **A** (all ten statuses exist; see Q2 above).
- **0.3** — confidence-field claim confirmed accurate (1 of 8). Edited-
  tracking claim corrected: gap is 3 of 5, not 5 of 5 (see Q4 above).
- **0.6 shadow count** — corrected. `shadow-sm` currently appears **59
  times across 24 templates**, not "45 across 20." (Counted fresh this
  pass; the foundation-tokens and logo passes earlier in this session
  touched some but not all of these call sites, so the number moved.)
- **0.1 (bilingual)** — not touched. Per instruction, this file preserves
  the original's characterization of the *bundle's* own rule (German
  body / English labels) without correcting it toward the actual product
  decision (English default, switcher). That correction belongs to the
  i18n pass, not this one.

## Screen-by-screen corrections

**2. Landing** — the real `landing.html` today is a materially different
build from what the bundle assumes already exists:
- "So funktioniert es" secondary CTA: marked **B?**, corrected to **A**.
  A `#how-it-works` anchor + section already exists (`landing.html:68-81`,
  labelled "See how it works") — copy/restyle only.
- 8-station journey strip: today's version has only **5** stages
  (Discover → Match → Prepare → Apply → Track). Reply/Interview/Offer
  don't exist on landing at all yet. **D** bucket still right, but "3 of
  8 stations missing" is bigger than the original note implies.
- Mini search-result preview / mini application-status preview:
  confirmed genuinely absent from landing.html today — not a restyle of
  something present-but-different. A/B still reasonable since the
  underlying data exists elsewhere in the app.
- Footer: **B** confirmed right, but today's footer is only a copyright
  line + one CTA link — no source list, no Datenschutz/Impressum at all
  (not "hardcoded," just not there). More net-new UI than "generate
  instead of hardcode" implies.

**3. Dashboard**
- Staleness computation: marked **C (small)**, corrected to **B**.
  `compute_priority_digest()` (`app/priority_digest.py:65-68`) already
  computes `days_since_activity` from `Application.updated_at` and
  produces a "No activity for N days" reason. The signal exists; only
  the "Als nächstes" hero card's presentation of it is new.
- Applications table (4 active · 1 rejected) with status pills: marked
  **A**, corrected to **B**. `dashboard.html` today has no applications
  table — only 4 stat tiles + 3 link-out teaser cards. The real
  status-pill table lives on the separate Applications list page
  (`applications/list.html`). Pulling it onto the dashboard is real
  template work, though no new data.
- Stat tiles: confirmed accurate — "Follow-ups due" is still hardcoded
  `"0"` at `dashboard.html:27`, with `priority_digest.py` already able to
  detect it but not wired in. Also confirmed: today's dashboard has only
  **4** stat tiles, not 5 — "Gespeicherte Stellen" is a separate teaser
  card, not a stat tile, today.
- Priority digest inline: confirmed exactly as written — today's
  dashboard shows only a teaser card linking to `/digest`, no inline rows.
- Job radar copy: confirmed **already shipped** exactly as claimed, and
  already rendered on the dashboard (`dashboard.html:43-75`) with the
  explicit "manual check" copy the note asks for. No correction.

**4. Find Ausbildung**
- URL import: corrected **C? → A** (see Q1 above).
- Filter chips: confirmed accurate — `SearchForm`
  (`app/jobs/forms.py:6-8`) has exactly `keywords` + `location`. **C**
  confirmed.
- Sort by match score: confirmed accurate — search orders by
  `Job.discovered_at.desc()` (`app/jobs/routes.py:45`), no score-based
  ordering exists. **C** confirmed.
- Result count / duplicates merged: confirmed **B** right — `dedup_key`
  and `Job.listings` (`app/models/job.py`) already group duplicate
  postings; only a query/template surfacing the count is needed.

**5. Job Detail**
- Weighting disclosure line: confirmed accurate, not rendered today. **B**.
- Strengths/Gaps "nicht bewertet" state: note upgrade, not a bucket
  change — `jobs/detail.html:104-117` already has a third icon branch
  (`unknown()`) for gap statuses beyond required/preferred-missing, and
  `match.skipped_categories` is already surfaced as a "Not evaluated"
  line above the bars. Closer to already-built than the A/B call
  suggests — likely just needs per-item label text.
- Requirement tags from posting: confirmed accurate exactly as written —
  `Job.skills` (JSON, `models/job.py:46`) is populated but never rendered
  anywhere in `jobs/detail.html`. **B** confirmed.
- Apply rail deadline countdown: note correction — `job.application_deadline`
  is not rendered anywhere on this page today (confirmed via full read
  of `jobs/detail.html`); it's used elsewhere (`priority_digest.py`) but
  the row needs to be built from scratch here, not reformatted.
- Company summary rail / Source & dedup disclosure: confirmed accurate,
  neither rendered today despite the underlying data existing. **B**.
- Intelligence block / reliability badge: confirmed **A + C** exactly
  right — `narrative_provider` is shown, no reliability field exists.

**6. Application Detail**
- 8-station journey: confirmed exactly accurate — `STATION_ORDER`
  (`status_route.py:13`) has exactly 6 stations, Reply genuinely isn't
  one of them. **C (small)** confirmed.
- Tab bar: confirmed accurate — no tab markup anywhere in
  `applications/detail.html` (grepped for `role="tab"` and similar,
  nothing); the page uses stacked sections with plain headings. **B**
  confirmed.
- "VON DIR BEARBEITET" badge + edit timestamp: corrected from a flat
  **C** to **split B/C** — `edited_at` already exists and is already set
  for cover letter and email (2 of 5); those two need only the badge UI
  (**B**). Interview prep, CV statement, and reply suggestion genuinely
  need new tracking (**C**), sized differently as detailed in Q4 above.
- Reply card confidence badge: confirmed accurate, already **A**
  (`applications/detail.html:330` already renders
  `msg.classification_confidence`).

**7. Candidate Profile**
- CV export / profile coaching: both confirmed **A**, resolved/shipped
  exactly as claimed.
- Completeness panel as a checklist: note correction — there is
  currently **no completeness panel at all on the Candidate Profile
  page**. The % bar exists only on the Dashboard. **B** still right (the
  underlying computation exists in `main/routes.py`), but the Profile
  page needs the panel added for the first time, not upgraded in place.

**8. Documents**
- Usage count ("in 4 Bewerbungen verwendet"): confirmed accurate —
  `ApplicationDocument` join exists (`models/application.py:162-178`)
  but nothing in `documents/list.html` renders a usage count today. **B**
  confirmed.
- Type suggestion inline: not re-verified this pass (no grep run for
  `suggest_doc_type` specifically) — flagged for a quick follow-up
  check rather than corrected outright.

**9. Company Detail**
- Header with initials avatar: `Company`
  (`app/models/job.py`) has no `employee_count`/`founded_year`/`revenue`
  columns at all, and `companies/detail.html` shows plain text today
  (industry · location · website link), no avatar element. Minor either
  way — **A** still reasonable for the restyle.
- "Belegte Angaben" facts panel: corrected **A → B** — no structured
  facts panel exists in `companies/detail.html` today, only prose header
  fields. Needs building as new UI, though no schema change is required
  — the three "absent" facts aren't columns on `Company` at all, so the
  honesty line can be hardcoded rather than computed.
- Confidence badge on company insight / open positions list: both
  confirmed accurate as originally bucketed.

**10. Mobile** — not independently re-verified (would need live browser
testing at real breakpoints, out of scope for this pass). **B** is
reasonable on its face.

**Addendum §12 Component layer** — confirmed accurate: exactly two
macros exist (`render_field`, `render_checkbox` in `_macros.html`), no
button/pill/chip component macros exist anywhere. One correction: the
input focus-ring spec (2px solid outline, 2px offset) described in the
bundle is **already implemented** in `_macros.html` — done during the
foundation-tokens pass, not net-new work.

## What this pass did not check

Sections 0.4 (motion tokens) and 0.5 (breakpoints), and most of §12's
component micro-specs (button variants, chip states, notice copy), are
descriptions of the *bundle's* design spec rather than claims about
current app state — there's nothing in the repo to verify them against
until the component layer is actually built. They're carried into Part 2
unchanged.

---

# Part 2 — Original inventory, as submitted (unmodified)

# AUSVIA 2.0 — Screen Inventory

Read directly from `AUSVIA_2_0_standalone.html`, 2026-08-25. Every item below
appears in the bundle. Categories:

- **A** — exists in the app today, 2.0 restyles it
- **B** — new UI over data/logic that already exists (query + template work)
- **C** — new feature needing real backend work
- **D** — prototype-only, not a product surface

Bucket calls marked **?** are my read against the project docs, not against the
live repo — verify before sizing.

---

## 0. Cross-cutting decisions

These are not per-screen. They affect everything and none of them are in the
foundation-tokens prompt.

### 0.1 Bilingual by rule — C, large

The brief: *"Beschriftungen bleiben in der Sprache der Anwendung, Fließtext ist
deutsch."* Labels, navigation, status names and column headers stay English;
all prose is German.

Observed throughout: page heading `Candidate profile` over German body copy;
`START DATE` next to `VERGÜTUNG`; statuses rendered `Sent` / `Interview` /
`Preparing`; sidebar items `Dashboard`, `Find Ausbildung`, `Saved Jobs`,
`Applications`, `Candidate Profile`, `Documents`, `Gmail`.

This touches every user-facing string plus every AI prompt that produces prose.
It is the single largest undiscussed item in the bundle.

### 0.2 Ten application statuses — B/C

Foundations lists all ten explicitly: `Preparing`, `Ready`, `Sent`,
`Follow-up`, `Interview`, `Offer`, `Accepted`, `Rejected`, `Withdrawn`,
`Expired`. Check this against the app's current status enum — any missing value
is schema work, not styling.

Rule attached: *"Zustand nie nur über Farbe"* — dot, label and position on the
journey route carry the state together. This aligns with the Phase 7 remediation
that removed colour-only indicators; keep it.

### 0.3 Intelligence surface anatomy — C, repeated

Every AI-generated block carries the same three marks:

1. A 3px teal edge on the left, radius on the right only — same rake as the logo.
2. The word "Intelligence" plus the **real provider and model** (`GEMINI-2.5-FLASH`
   in the mock), never a product name without the model.
3. A provenance line: what it drew on, when, and a reliability rating of
   **hoch / mittel / niedrig**.

Four stated rules:

- It only explains what the calculation produced. Scores never originate in AI.
- Every generated surface carries origin, timestamp and reliability — never an
  invented percentage.
- With no provider configured, it says so plainly: *"KI-Text nicht verfügbar,
  weil kein Provider konfiguriert ist."* No placeholder, no apology.
- **Once you edit the text, the surface loses its tint** — the edge goes neutral
  and the provenance line disappears. The text is yours now.

The eight places Intelligence appears, per the bundle: match explanation
(job detail), improvement tips (job detail, on request), company insight,
cover letter, application email, reply classification, reply suggestion,
profile coaching.

Backend consequence: a **reliability field** on every AI-backed model. Today
only `GmailMessage.classification_confidence` has one. That is the single
largest concentrated chunk of backend work in the mockup — the same small
schema addition seven more times.

Second consequence: **edited-by-you tracking** on five features (cover letter,
email, interview prep, CV statement, reply suggestion). No model tracks this
today; it needs a column or a hash comparison.

### 0.4 Motion tokens — not in the tokens prompt

140ms hover · 180ms tabs and dropdowns · 240ms drawer (0.98 → 1) · 520ms match
band, once · 420ms score fades in, **does not count up**. Under
`prefers-reduced-motion`, every animation drops.

### 0.5 Breakpoints

- 375–430: one column, score above the title, actions pinned to the bottom,
  tables become row cards
- 768: two columns for facts, rail moves below content
- 1024: rail right at 300px, sidebar collapsed
- 1280–1440+: content 1100px, rail 330px, sidebar permanent, extra space stays
  whitespace

### 0.6 Structural principle

*"Gruppen entstehen zuerst durch Abstand, dann durch eine Linie, erst zuletzt
durch eine Fläche."* Spacing first, then a hairline, a filled surface only last.
Exactly two shadows, both functional. **In ink, nothing carries shadow — only
lines.**

This conflicts with the current app, where `shadow-sm` sits on 45 card instances
across 20 templates. Not a token swap; a component-pass decision.

---

## 1. Foundations — D

A style-guide reference screen, not a product page. Sections 01–06 plus 09.
Source of truth for tokens, logo construction, type scale, radius roles,
shadows, motion, breakpoints, component states.

Nothing to build. Everything to read.

---

## 2. Landing

| Element | Bucket | Note |
|---|---|---|
| Access-code gate, log in | A | `access_code.py`, `landing.html` |
| Headline "Dein Weg zur Ausbildung." + promise copy | A | Copy change only |
| `NUR MIT ZUGANGSCODE` badge | A | |
| "So funktioniert es" secondary CTA | B? | Anchor or section — verify one exists |
| Mini search-result preview (3 job cards with scores) | A/B | Real data shape, new presentation |
| Mini application-status preview | A/B | Same |
| 8-station journey strip: Discover → Match → Prepare → Apply → Track → Reply → Interview → Offer | D | Decorative here; becomes a real ask on Application Detail |
| Three value blocks: Transparent / Vorbereitet / In deiner Hand | A | Copy |
| Closing CTA with code field | A | |
| Footer: sources named (Bundesagentur, Adzuna, Jooble), Datenschutz · Impressum | B | Source list should be generated from enabled adapters, not hardcoded |

---

## 3. Dashboard

| Element | Bucket | Note |
|---|---|---|
| Greeting + one-line situation summary + date | A | |
| **"Als nächstes" hero card** | C (small) | New: single highest-priority item, promoted above the digest. Carries a staleness marker `SEIT 3 TAGEN UNVERÄNDERT` and two actions: `Paket öffnen`, `Als gesendet markieren` |
| Staleness computation ("seit 3 Tagen unverändert") | C (small) | Needs a last-transition timestamp comparison |
| Priority digest inline, "3 Vorgänge mit echtem Anlass" | B | `compute_priority_digest()` already returns this; today it lives on `/digest` |
| Digest rows with per-row reason and per-row action link | B | Reasons in the mock: approved-not-sent, deadline in 5 days, strong match with no application started |
| Applications table (4 active · 1 rejected) with status pills and relative dates | A | |
| Profile completeness % + what's missing + link | A | |
| Stat tiles: In Vorbereitung, Gesendet, Interviews, **Follow-ups fällig**, Gespeicherte Stellen | A / C (small) | Follow-ups is hardcoded `0` in `dashboard.html:23-28` today; `priority_digest.py` already detects it, just needs wiring |
| **Cross-application Intelligence insight** | C | Genuinely new. Aggregates across all applications: *"Drei deiner vier offenen Bewerbungen liegen im Bereich Elektrotechnik…"* Nothing aggregates across applications today |
| "Neue Treffer · heute geprüft · 6 neue Anzeigen" | B | **Resolved** — shipped as the on-demand radar (`app/jobs/radar.py`, `POST /jobs/check-now`). Copy must stay explicit that this is a manual check, not autonomous monitoring |

---

## 4. Find Ausbildung

| Element | Bucket | Note |
|---|---|---|
| Keyword + location search, result cards, Save/Saved toggle | A | |
| Intro line naming which sources are searched | B | Generate from enabled adapters |
| **"Anzeige per URL importieren"** | C? | Audit called this a new fetch/parse path. But `app/jobs/manual_import.py` plus bulk-paste and a bookmarklet already exist. **Verify** whether the gap is URL-fetch specifically vs. the paste flow that's already built — this may be much smaller than the audit sized it |
| **Filter chips**: radius (+50 km), year range, German level, category, source toggle, min-score | C | `SearchForm` (`app/jobs/forms.py:6-8`) has keywords + location only |
| Removable chip UI (`Nur Passung ≥ 60 ✕`) | C | Part of the above |
| **Sort by match score** | C | Search orders by `discovered_at`; needs scores computed for all results up front, not lazily |
| Result count line: "18 Treffer · 3 Quellen · **2 Duplikate zusammengeführt**" | B | `JobListing` rows already carry this; query only |
| Per-card score + label + five weighted segments | B | `compute_match` already produces this; the card doesn't render it |
| Per-card one-line strengths/gaps summary | B | Same source |
| Per-card meta chips: START, salary, SOURCE, **FRIST** | A/B | Deadline chip incl. the honest `KEINE FRIST ANGEGEBEN` variant |

---

## 5. Job Detail

| Element | Bucket | Note |
|---|---|---|
| Breadcrumb, title, company, Save / Start application | A | |
| Fact tiles: start date, salary, duration, source | A | |
| Score + label + narrative + five category bars | A | |
| **Weighting disclosure line** | B | *"Segmentbreite = Gewichtung: Skills 30 · Language 25 · Education 20 · Location 15 · Start 10. Füllung = erreichter Anteil."* Weights are already fixed in `matching.py`; surface them |
| "Aufschlüsselung anzeigen ▾" expander | B | |
| Strengths / Gaps lists, incl. **"nicht bewertet"** entries | A/B | The mock shows a third state: *"Führerschein — in der Anzeige nicht genannt, nicht bewertet."* Honest non-evaluation, distinct from a gap |
| **Requirement tags from the posting** | B | `Job.skills` already extracted and stored, never rendered |
| Intelligence block with provider, **reliability badge**, "Neu erzeugen" | A + C | The generation exists; the reliability field does not |
| Apply rail with deadline countdown ("Frist 30.09.2026 · in 40 Tagen") | A/B | |
| Company summary rail + link | B | Same data, also rendered here |
| **Source & dedup disclosure** | B | *"Eine zweite Fassung derselben Anzeige wurde automatisch zusammengeführt"* + link to the original posting |

---

## 6. Application Detail

| Element | Bucket | Note |
|---|---|---|
| Header, status pill, link to job posting | A | |
| **8-station journey** with real dates: Discovered · Matched · Prepared · Approved · Sent · **Reply** · Interview · Offer | C (small) | Discovered/Matched timestamps exist; Prepared/Approved/Sent/Interview/Offer reuse existing event inference; **Reply is not one of today's 6 `STATION_ORDER` stations** and needs new logic |
| Journey header line: next event + countdown ("Interview am 27.08., 10:00 — in 6 Tagen") | B | |
| Tab bar: Anschreiben · E-Mail · Dokumente (3) · Antworten (2) · Interview-Vorbereitung | B | All five features exist; the tabbed container is new UI |
| Cover letter editor with Neu erzeugen / Speichern | A | |
| **"VON DIR BEARBEITET" badge + edit timestamp** | C | No model tracks whether AI text was later hand-edited. Needed on 5 features |
| **Tint drops when edited** | C | The visual consequence of the above |
| Character count + grounding note | B | |
| Gmail panel: connection state, last-checked time | A | |
| Reply card with classification + **confidence badge** | A | The one place the mock's confidence pattern already matches real data (`classification_confidence`) |
| Reply suggestion + "In Gmail öffnen" | A | |
| PDF package card (pages, size, date, download) | A | |
| Contained-documents list with type tags | A | |
| Contacts & dates rail (Ansprechpartnerin, interview, follow-up) | A/B | |
| "Nächster Schritt" card | B | Derivable from status + digest logic |

---

## 7. Candidate Profile

| Element | Bucket | Note |
|---|---|---|
| Personal info, education, experience, skills, languages | A | Feeds `matching.py`'s scorers |
| Grounding statement: *"Was hier nicht steht, wird nicht erfunden."* | A | Copy |
| Per-section "Eintrag hinzufügen" / "Bearbeiten" | A | |
| Language rows with proof state ("Goethe-Zertifikat vorhanden" vs "kein Nachweis") | A/B | |
| **"Als CV exportieren"** | A | **Resolved and shipped** — `app/profile/cv_export.py`, `GET /profile/cv.pdf`, deterministic reportlab, no AI |
| Completeness panel as a **checklist**, not just a % | B | Four explicit lines incl. what's missing |
| Intelligence coaching block | A | `ProfileCoaching` |
| Ausbildung preferences panel (fields, locations, relocation, min German) | A | |

---

## 8. Documents

| Element | Bucket | Note |
|---|---|---|
| Drag-and-drop upload zone with constraints stated | A/B | "PDF, JPG oder PNG bis 15 MB" |
| Type selector + file picker | A | |
| Document table: file, type, size, uploaded, primary flag | A | |
| **"in 4 Bewerbungen verwendet" usage count** | B | `ApplicationDocument` join already has the relationship; query + template |
| **"nicht verwendet"** state | B | Same |
| Type suggestion inline: *"Intelligence schlägt vor: Training certificate"* + "prüfen" | A | `suggest_doc_type` + confirm/dismiss routes exist |
| Grounding note: originals never modified, PDFs built from copies | A | Copy |
| Empty state: "Noch keine Unterlagen" + guidance + action | B | |

---

## 9. Company Detail

| Element | Bucket | Note |
|---|---|---|
| Header with initials avatar, industry, location, website | A | Matches `companies/detail.html` closely |
| About text + provenance note ("aus den vorliegenden Stellenanzeigen … keine Fremddatenbank") | A | |
| Intelligence company-fit block | A | `CompanyInsight` |
| **Confidence badge on that insight** | C | Same gap as job detail |
| Open positions list with per-row score and Details link | B | |
| "Belegte Angaben" facts panel | A | |
| **Explicit absence statement** | B | *"Mitarbeiterzahl, Gründungsjahr und Umsatz liegen nicht vor — sie bleiben leer, statt geschätzt zu werden."* Strong honesty pattern; worth keeping verbatim |
| "Deine Bewerbung hier" cross-link | B | |

---

## 10. Mobile — B

Explicitly a re-layout, not new functionality: *"Nicht geschrumpft, neu geordnet."*

Existing structure stays: ink topbar with logo and menu, drawer from the left,
same destinations. What changes inside the content:

- Score moves **above** the title
- Actions pin to the bottom edge
- Tables become row cards
- Touch targets ≥ 44px, no horizontal scroll

Three mobile screens are drawn: Dashboard, Drawer (marked unchanged), Find
Ausbildung, and Job Detail with fixed actions.

---

## Rough sequencing

Not effort estimates — dependency order.

1. **Tokens** (in progress)
2. **Logo replacement** — the Aperture mark is retired; new two-track mark,
   full asset regeneration, favicon and app icon. Wordmark spec unchanged, so
   the existing outlined Sora path survives
3. **Component layer** — buttons, inputs, status pills, chips, cards, the
   Intelligence surface, empty states, notices. No shared component library
   exists today beyond two form macros; every card/badge/pill is a repeated
   utility-class pattern
4. **Reliability field ×7 + edited-by-you ×5** — the schema work that unlocks
   most of the Intelligence surface
5. **Screen re-layouts**, in dependency order: Job Detail and Application Detail
   first (they carry the most new surface), then Dashboard, Find, Profile,
   Documents, Company
6. **Search filters + sort by score** — the largest single feature
7. **Bilingual pass** — can run in parallel from step 3 onward, but every screen
   touched before it will need revisiting, so consider pulling it earlier

## Open questions worth resolving before step 3

- **Language:** is German-body/English-label confirmed as the product direction,
  or is the bundle simply drawn for a German audience? Everything downstream
  depends on the answer.
- **URL import:** does `manual_import.py` already cover this, or is a real
  fetch/parse path genuinely missing?
- **Status enum:** which of the ten statuses exist today?
- **Shadows:** the "hairline before surface" principle contradicts 45 existing
  `shadow-sm` card instances. Adopt the principle, or keep the current pattern?

---

# Addendum — theme architecture and the component layer

Added 2026-08-25 after re-reading the bundle and confirming against
rendered screenshots of both modes.

## 11. Two themes, not one theme plus a dark surface

**Confirmed visually in both modes.** The sidebar is `background: var(--card)`
— white in Porzellan, `#12171B` in Tinte. It is **not** a permanently dark
surface.

This matters because the app's current sidebar is permanently ink, and the
tokens pass treated `ink` as a fixed surface with a toggle out of scope.
In 2.0 that concept doesn't exist: every surface follows the theme. It also
explains why `ink-card`, `ink-raised`, `ink-line`, `ink-line2`, `ink-t1/t2/t3`,
`ink-tint`, `ink-tint2` and the four ink semantics were all defined with "no
current consumer" — they were waiting for this.

The bundle's own words: *"Tinte ist ein vollwertiger Modus, nicht ein
invertiertes Nachspiel."*

Mechanism: values swap under `[data-theme="dark"]` on `:root`. Class names
never change. Tailwind's `dark:` variant strategy would instead add a second
class to ~500 existing call sites — avoid it.

Toggle placement: top right of the app chrome, labelled `PORZELLAN` /
`TINTE` in the prototype's own switcher. The language switcher goes beside it.

## 12. Component layer — the missing middle

The app has no shared component library beyond two form macros. Every card,
badge, pill and chip is a repeated utility-class string. The bundle specifies
a real component set, and building it is what makes the screen passes
affordable rather than another 500-call-site migration each time.

### Buttons — height 36 (compact 30), radius 8

| Variant | Fill | Text | Border |
|---|---|---|---|
| Primary | `brand` | `#FFFFFF` | `brand` |
| Secondary | `card` | `t1` | `line2` |
| Tertiary / text | transparent | `brand` | none |
| Destructive | transparent | `err` | `line` |
| Disabled | `page` | `t3` | `line` |
| Focus | as primary | — | + 2px outline, 2px offset |

### Inputs — radius 8, 2px focus ring

States drawn: default, focused, select/dropdown, and **error with an
explanatory message beneath** (*"Unvollständige Adresse — ohne sie können
keine Antworten erkannt werden."*). The error state carries a reason, not
just a red border.

### Status pills — all ten, each with a dot

| Status | Fill | Text |
|---|---|---|
| Preparing | `page` | `t3` |
| Ready | `tint` | `brand` |
| Sent | `ok-tint` | `ok` |
| Follow-up | `warn-tint` | `warn` |
| Interview | `info-tint` | `info` |
| Offer | `ok` | `#FFFFFF` |
| Accepted | `brand` | `#FFFFFF` |
| Rejected | — | (semantic err pair) |
| Withdrawn | transparent | `t3`, **dashed** border |
| Expired | transparent | `t3`, **dashed** border |

Rule: *"Zustand nie nur über Farbe"* — dot, label and position on the journey
route carry the state together. Withdrawn and Expired use a dashed border so
the terminal-but-not-negative states are distinguishable without colour.

### Chips

- **Source chips** — `ARBEITSAGENTUR`, `ADZUNA`, `MANUAL IMPORT`: Plex Mono,
  +0.1em tracking, `t2` on `line2` border, radius 4
- **Attribute chips** — `Primary CV`, `SPS · fortgeschritten`, `Deutsch · B2`
- **Coverage chips** — four states: `Erfüllt` / `Teilweise` / `Fehlt` /
  **`Nicht bewertet`**. That fourth state is the honesty pattern again —
  distinct from "missing," it means the posting never asked

### Notices and empty states

- Success notice: *"Deine Bewerbung ist freigegeben. Das PDF-Paket liegt bereit."*
- **Partial-failure notice**: *"Zwei Quellen waren nicht erreichbar. Jooble:
  Zeitüberschreitung."* — names which source failed and why. Worth building
  as a real component; the app currently has no per-source failure surface
- Empty state: heading, one line of guidance, one action

### Composite rows

Three repeated row types are specified as components rather than one-offs:
**job card**, **document row**, **application row**. Plus a **progress bar**
(profile completeness) and the **match band** (five weighted segments).

### Intelligence surface

3px `brand` edge on the left, radius on the right only. Tinted fill that
**drops to neutral once the user edits the text**. Header carries the word
"Intelligence" plus the real provider/model, and a reliability badge
(hoch/mittel/niedrig). Footer carries the provenance line.

## Revised sequencing

1. ~~Tokens~~ — done (`1b0b1db`)
2. ~~Logo~~ — done (`d109c66`)
3. **Theme** — light/dark as real modes, toggle top right
4. **i18n** — English default, switcher beside the theme toggle;
   employer-facing AI output stays German always
5. **Component layer** — the table above; this is what makes 6 affordable
6. **Schema for Intelligence** — reliability field ×7, edited-by-you ×5
7. **Screen re-layouts** — Job Detail and Application Detail first
8. **Search filters + sort by score** — the largest single feature

## What still needs repo verification

The A/B/C calls throughout this document are read against the project docs,
not against the live codebase. Before sequencing work from them, have them
checked against the real repo — particularly the four open questions in the
section above, and every item marked C, since those carry the schema cost.
