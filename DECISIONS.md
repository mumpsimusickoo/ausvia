# Decision Log — AUSVIA

Each entry: decision, reason, alternatives considered, consequences. Newest
first. Don't reopen a settled decision without new evidence — see entry
format below for what was actually weighed.

---

## 2026-08-13 — Phase 8 D6(a): optional dedicated Gmail token encryption key

**Decision:** Added `TOKEN_ENCRYPTION_KEY` as an optional env var
(`config.py`). When set, `app/utils/crypto.py` encrypts new Gmail tokens
with it instead of a `SECRET_KEY`-derived key; when unset, behavior is
identical to before this change. `decrypt_text()` additionally falls back
to the legacy `SECRET_KEY`-derived key whenever `TOKEN_ENCRYPTION_KEY` is
set, so already-encrypted tokens keep decrypting even if the variable is
introduced on a live deployment - no forced reconnect.

**Reason:** Requested as Phase 8 D6 option (a) specifically: real
improvement (a compromised/rotated `SECRET_KEY` no longer also exposes or
invalidates every stored Gmail token) with zero migration burden, unlike
option (b) below.

**Alternatives considered:** Option (b) - require `TOKEN_ENCRYPTION_KEY` in
production and force reconnection for tokens encrypted under the old
derivation, mirroring the `SECRET_KEY`-required-in-production check added
earlier in Phase 8. Explicitly deferred - designing the forced-migration/
reconnect flow is real scope that needs its own deliberate pass, not
something to fold into the same change as the optional opt-in version.

**Consequences:** `SECURITY.md`'s D6 gap entry updated to reflect the new
optional capability while keeping option (b) documented as still open.

---

## 2026-08-12 — Phase 6 scope: background jobs get one real call site, not a full retrofit

**Decision:** Built real background-task infrastructure
(`app/tasks/runner.py`, `BackgroundTask` model) and applied it to exactly
one operation - Gmail reply checking - rather than also retrofitting PDF
assembly and AI generation (cover letter/email/narrative/reply-suggestion/
company-insight) in the same pass, even though `ROADMAP.md`'s Phase 6
description named all three.

**Reason:** each of those operations has a different UX shape today. Gmail
reply checking is already a manual, fire-and-forget "click a button, check
back" interaction - moving it to a background task changes nothing about
how the user experiences it, just removes the wait. AI generation and PDF
assembly are different: the UI currently expects the result inline,
immediately, for the user to review/edit in the same view (a generated
cover letter appears in an editable textarea right after the button
click). Backgrounding those would require a genuine UX redesign (a
pending state, a way to know when it's done, probably polling or a
refresh prompt) - real product design work, not just an infrastructure
swap. Scoping this pass to the one call site where backgrounding is a
clean drop-in, and leaving the UX-design-required ones for a dedicated
pass, produces a real, honest improvement instead of a rushed one.

**Alternatives considered:** Retrofitting all three - rejected as
overreach for one pass; would have meant either half-finishing the UX for
AI generation/PDF assembly, or spending most of this phase's effort on
that instead of the other three Phase 6 items (company pages, document
extraction, live-verification recheck). Not building the infrastructure at
all until all three call sites could be done together - rejected; the
infrastructure itself (the DB row shape, the runner) doesn't get easier to
build later, and Gmail checking benefits from it today.

**Consequences:** `PROJECT_AUDIT.md`'s "Partially implemented" section
tracks this explicitly so it isn't mistaken for complete. The next
candidate for backgrounding, if picked up, is PDF assembly (approve
application) - closer to Gmail-checking's shape (a distinct build step
with a clear "done" signal) than AI generation is.

---

## 2026-08-12 — Background-task runner has no broker; runs eagerly (synchronously) under TESTING

**Decision:** `app/tasks/runner.py` is a `BackgroundTask` DB row plus an
in-process `ThreadPoolExecutor` - no Celery, no RQ, no Redis. Under
`TESTING`, `submit_task()` runs the target function synchronously instead
of submitting it to the executor.

**Reason:** no Docker/Redis is available in this development environment
(the same constraint that's shaped every other infra choice in this
project - SQLite not Postgres, local filesystem not S3). A DB row plus a
thread pool achieves the actual goal stated in `ROADMAP.md` ("stop
blocking the request/response cycle") without new infrastructure. The
TESTING-eager behavior isn't just a convenience: the test suite's SQLite
database is `sqlite:///:memory:`, which is connection-scoped - a real
background thread opening its own connection would see an empty database,
not the test's data. Running eagerly under TESTING sidesteps that
entirely, and as a second, independent benefit, means tests assert on
real outcomes immediately with no sleep/poll for a thread that might not
have finished yet. This mirrors Celery's own `task_always_eager` testing
pattern - a well-established solution to the same class of problem, not a
project-specific workaround.

**Alternatives considered:** A real broker (Celery/RQ + Redis) - rejected,
not available in this environment, and would be premature infrastructure
for the app's current scale (see the same reasoning already applied to
SQLite/local storage elsewhere). Mocking the background thread entirely in
tests instead of an eager-execution mode - rejected; that would test the
mock, not the real `target_fn` logic, weakening exactly the tests meant to
catch real bugs in the retrofitted route.

**Consequences:** The row shape (`task_type`, `status`, JSON `context`,
result/error text) is deliberately broker-agnostic, so swapping in
Celery/RQ later is a runner-module change, not a schema or call-site
change. Real (non-test) background tasks are not durable across a process
restart (in-memory `ThreadPoolExecutor`) - acceptable for a manually-
triggered "check for replies" action today, would need revisiting before
anything higher-stakes (e.g. a paid action) is backgrounded this way.

---

## 2026-08-12 — Document type suggestion is a keyword heuristic, not an AI call

**Decision:** `app/documents/extraction.py` suggests a document's likely
type by scanning its own extracted PDF text for known German/English
keywords per type (e.g. "Lebenslauf" → cv, "Abschlusszeugnis" → diploma) -
it never calls the configured AI provider, not even optionally.

**Reason:** this is the one place in the codebase where routing through an
AI provider would be a worse fit than the deterministic approach, not just
an unnecessary one. Detecting "does this document contain the word
Zeugnis" doesn't benefit from a language model's reasoning - a keyword
match is free, instant, and 100% reproducible, which the project's own
deterministic-first principle already treats as the ideal, not just an
acceptable fallback. Every other "AI-optional" feature in the app (match
narrative, cover letter, company insight) has a deterministic core *and*
an optional AI layer for polish; this feature is deterministic-only
because there's no meaningful polish an LLM would add to "which
checkbox was probably right."

**Alternatives considered:** Routing extraction through the AI provider
with a heuristic fallback in mock mode (matching the pattern used
everywhere else) - rejected specifically because it would be slower, cost
real tokens in production, and be *less* reproducible than the heuristic
for zero accuracy benefit on this particular task. Full OCR for scanned
documents - rejected as out of scope; no OCR library is available in this
environment, and this is disclosed honestly (`PROJECT_AUDIT.md`) rather
than silently limited to PDFs with a real text layer.

**Consequences:** Image uploads (JPG/PNG) and scanned PDFs with no text
layer get no suggestion at all - correctly absent, not a wrong guess.
`AI.md` documents this as the intentional exception to the project's
usual "deterministic core + optional AI layer" shape.

---

## 2026-08-12 — Correction pass: hardcoded exact values instead of ratio-derived ones for the three signature details

**Decision:** Replaced ratio/proportion-derived implementations of the
three visual-direction signature details with the exact literal values
from an approved correction reference, applied verbatim: hero route as a
filled counterform cut (not a stroked line), bar shear as a hardcoded 12px
at 14px bar height with a 28px fill min-width (not `bar-height × ratio`),
and the application-status current-marker as a 24px/4px-ring/10px-dot
combination that differs from other states in size, ring weight, and fill
together (not ring weight alone).

**Reason:** the previous pass's ratio-based approach was *technically*
correct (the shear ratio genuinely was 1:2, matching the logo's own leg
angle) but produced values too small to actually see at the sizes the
product uses (3-4px shear on 6-8px bars; a ring-weight-only difference
that read as noise). Correctness of the underlying math didn't survive
contact with real pixel sizes. The fix is to stop re-deriving the shear
from a ratio at every call site and instead hardcode the values that were
verified to actually render visibly, once.

**Alternatives considered:** Keeping the ratio-based token and just
tuning the ratio itself upward - rejected; a ratio still recomputes
differently at every bar height, which is exactly the fragility that
caused the original bug once bar height itself also needed to change (6-8px
→ 14px). A single hardcoded value that's independent of bar height is more
robust for a "signature detail" that's meant to be uniform across the
product, not proportional to whatever container it's in.

**Consequences:** `--ausvia-shear-ratio` and the per-element `--bar-h`
custom property are removed entirely from `base.html` - `.ausvia-bar-fill`
now has no configurable inputs at all, which is deliberate (see
`DESIGN_SYSTEM.md`). Two judgment calls made while implementing this
pass, not explicitly covered by the reference:

1. **Hero labels use percentage-based absolute positioning, not SVG
   `<text>`.** The reference's own markup uses absolutely-positioned HTML
   divs at fixed pixel coordinates, sized for its 1240px-wide demo
   sheet - not directly usable on the product's fluid-width hero.
   Converted the same relative positions to percentages of an
   `aspect-ratio`-locked container (so they scale in lockstep with the
   SVG at any viewport width) rather than switching to SVG `<text>`
   nodes (which the *previous* pass had used successfully) - staying
   closer to the reference's literal technique since the correction
   explicitly asks not to re-derive/approximate this section.
2. **The match-score category bars keep their existing green/amber/red/
   blue semantic-threshold coloring**, even though the reference's own
   illustrative example (using AUSVIA's real seeded data: Skills 25%,
   Location 50%, Start date 100%) renders every bar in flat Signal Blue
   regardless of score. Read the reference's uniform blue as a
   simplification for demonstrating the shear mechanic specifically, not
   an instruction to remove an existing, working, documented color
   system - both correction documents state this is "a values
   correction, not a new redesign" and that colors don't change. Did
   *not* extend this same reasoning to darkening the "Compatibility with
   your profile" card background (the reference's section-02 demo wraps
   its bars in a dark `#0B1220` card) - kept it white, for the same
   "colors/cards don't change" reason, since section 03's demo of the
   *same* kind of card renders it white, confirming section 02's dark
   backdrop was a spec-sheet presentation choice, not a product
   instruction.

---

## 2026-08-11 — Visual direction: Counterform (1a) everywhere, Wayfinding (1c) for application status only

**Decision:** Of three explored directions (Counterform, Record,
Wayfinding — "Design exploration directions.pdf"), Counterform (1a) is the
product's direction: the ascending-staircase process-flow graphic on the
landing hero, and the 63.4° shear (the logo mark's own leg angle) applied
as a reusable token to every progress-bar fill. The application-status
component is the one deliberate exception, using Wayfinding's (1c)
station/marker route instead of Counterform's bar-shear treatment. Record
(1b) is not used anywhere.

**Reason:** explicit product direction. The two directions solve different
problems on purpose: Counterform's signature is about the product's own
construction language (the mark's counterform cut, echoed at other
scales); Wayfinding's signature is about legibility for someone anxious
and unfamiliar with the process, which is specifically what the
application-status view needs to do. Applying Wayfinding narrowly (one
component) rather than blending both directions' hero/landing treatments
keeps each direction doing the one job it's actually good at, rather than
producing a diluted hybrid.

**Alternatives considered:** Using 1a's shear treatment on the status
timeline too, for full visual consistency — rejected per the explicit
brief; a shear-cut progress bar doesn't communicate "which of six named
stations am I on" as directly as discrete markers do. Using Record (1b)'s
ledger aesthetic anywhere - not selected, reference only.

**Consequences:** Two distinct visual signatures now coexist in the
product, each scoped to what it's good at. This is intentional and
documented here specifically so it isn't "fixed" into one direction later
by someone who doesn't know it was deliberate. See `DESIGN_SYSTEM.md`'s
"Visual direction" section for the implementation detail of each.

---

## 2026-08-11 — Application status: extracting the terminal states (accepted/rejected/withdrawn/expired) from the Wayfinding route

**Decision:** The Wayfinding route (`app/applications/status_route.py`)
shows exactly six stations, matching the sequential part of
`Application.APPLICATION_STATUSES`. The four non-sequential terminal
statuses (`accepted`, `rejected`, `withdrawn`, `expired`) are not
stations — `accepted` is treated as having completed the full route (all
six reached, none "current"); the other three infer how far the route
actually got from real evidence (events, `interview_date`) since the
status string alone doesn't say where the process stopped, and are shown
as a small badge next to the section heading rather than a seventh/eighth
marker.

**Reason:** the design brief specified six stations "matching the existing
status lifecycle" but didn't address the other four values, which aren't
sequential steps forward — they're exits (a rejection can happen at any
point; withdrawing is a choice, not a stage). Inventing station markers
for them would misrepresent the route as having more sequential stages
than the product actually models.

**Alternatives considered:** Showing all ten statuses as stations in
lifecycle-declaration order — rejected, would render nonsensically (e.g.
"Rejected" appearing as a station between "Offer" and nothing, implying
it's always the last forward step, when rejection can happen right after
"Sent"). Hiding terminal-status applications' progress entirely - rejected,
loses real information the user has about how far they got.

**Consequences:** For a `rejected`/`withdrawn`/`expired` application, which
stations show as "reached" depends on inference (event log presence, not
just the status string) — documented in `status_route.py`'s docstrings so
this isn't mistaken for a bug if the inferred cutoff looks slightly off in
an edge case (e.g. an application rejected the same day it was marked
sent, before any other event logged).

---

## 2026-08-11 — Resolved: Signal Blue (not Ink Navy) is the logo symbol's default fill on light backgrounds

**Decision:** The symbol's default fill on light backgrounds is **Signal
Blue** (`#2563EB`), not Ink Navy. Ink Navy governs the wordmark text and
surfaces, not the mark's default color. `app/templates/_logo.html`'s
`symbol()`/`lockup()` macro defaults, and the corresponding static assets
(`ausvia-lockup-primary-light.svg`, `ausvia-lockup-stacked.svg`,
`ausvia-lockup-tagline.svg`), were updated accordingly.

**Reason:** this reverses the previous session's implementation, which
followed section 09's asset-filename table literally
(`ausvia-symbol-ink.svg` = "default, light backgrounds") and explicitly
flagged that reading as reversible. Asked to re-examine against the
spec's actual color-role language rather than file names: the earlier
"Brand identity with logo.pdf" (v1.0) states outright — "**Signal Blue:**
Primary actions, **the mark on light**" and "**Bright Blue:** Dark mode
only — **the mark on ink**." That is an explicit, unambiguous pairing of
background context to symbol color, naming Signal Blue for light and
Bright Blue for dark. Rev 1.0's own section 08 is consistent with this:
"the dark version **steps up to** Bright Blue" only makes sense as a
description of moving away from a Signal-Blue baseline. And the rendered
primary-lockup reference art in all three logo PDFs produced across this
project (8-concept exploration, v1.0 identity, rev 1.0 spec) consistently
shows the symbol in blue on light backgrounds, never ink.

**Alternatives considered:** Keeping the ink-default reading exactly as
previously implemented, since it wasn't demonstrably *wrong*, just
under-evidenced - rejected because it directly contradicts the explicit
"the mark on light" / "the mark on ink" sentence once weighed against it;
that sentence is the single clearest piece of textual evidence in either
direction and it says the opposite of what was implemented.

**Consequences:** `ausvia-symbol-ink.svg` remains a valid, real asset
(genuine use for print/monochrome-adjacent editorial contexts) but is no
longer implied as the default anywhere live. Also fixed while auditing
this: form focus rings (`_macros.html`) used Bright Blue's hex on light-
surface white inputs (`ring-brand-500`), which violates "Bright Blue is
dark-background-only" - changed to `brand-600` (Signal Blue) in both
field-rendering macros. Full reasoning and the exact quotes: `LOGO.md`
"Signal Blue vs. Ink Navy."

---

## 2026-08-11 — Logo rev 1.0 implemented: outlined Sora wordmark, ink-default symbol, Sora scoped to logotype only

**Decision:** Implement the approved Aperture logo spec exactly, with four
judgment calls where the spec didn't fully pin things down: (1) extract the
real Sora SemiBold wordmark as a static vector outline via `fontTools`
rather than loading Sora as a live webfont; (2) follow the spec's file
table literally — Ink Navy is the symbol's default fill for light/editorial
contexts, Signal Blue is reserved for the favicon/app-icon/accent role; (3)
the wordmark *graphic* stays lowercase "ausvia" per the spec, while plain-
text brand mentions (titles, docs, prose) stay "AUSVIA" uppercase per the
standing Phase 5.5 correction — two different rules for two different
things, not a contradiction; (4) Sora is scoped to the logotype only
(Option A) — Inter remains the sole UI/body typeface.

**Reason:** (1) avoids a font-loading dependency for the logo entirely,
and is strictly more faithful to "outline the wordmark... do not re-set it
in a substitute typeface" than live text would be. (2) is the literal,
unambiguous reading of the spec's own file-naming table, safer to follow
than to guess at pixel colors from a rendered PDF thumbnail. (3) both
rules are independently sourced from explicit instructions (the approved
logo spec; the user's standing casing correction) and apply to different
things (a graphic vs. running text) — real brands draw this same
distinction routinely. (4) the wordmark no longer needs Sora as a webfont
(see 1), so adding it as a second UI typeface would be pure added
complexity for a stylistic change nobody asked for — the spec scopes Sora
to "wordmark" (section 03), not to UI type generally.

**Alternatives considered:** Hand-approximating Sora's letterforms with
bezier curves - rejected outright, would not actually be Sora, directly
contradicts the spec. Using Signal Blue as the default symbol fill
everywhere (matching the visual pattern across earlier exploration PDFs) -
plausible alternate reading, explicitly flagged as reversible in `LOGO.md`
rather than silently chosen. Loading Sora everywhere as the new UI display
face (Option B) - rejected as unrequested scope creep once outlining made
it unnecessary for the logo itself.

**Consequences:** `app/static/brand/` holds the full production asset set
(symbol/wordmark/lockup variants, app icon, favicon + PNG fallbacks, the
bundled Sora OFL license). `app/templates/_logo.html` was rewritten with
three macros (`symbol()`, `wordmark()`, `lockup()`) using the exact spec
geometry, not an approximation. If judgment call (2) turns out backwards
(blue should be the default, not ink), it's a one-line fill swap, not a
rebuild - see `LOGO.md` for the exact reasoning to revisit.

---

## 2026-08-11 — Closed the three Phase 5.5 design-system gaps: warm background, card shadows, ink navy as sidebar foundation

**Decision:** `bg-slate-50` → `bg-paper` (`#FAF8F5`) site-wide; `shadow-sm`
added to every instance of the shared card pattern (45 occurrences across
20 templates); the authenticated sidebar changed from white to solid
`bg-ink`, with nav text/hover/active states redesigned for a dark surface
(default `text-slate-300`, hover `hover:bg-white/5 hover:text-white`,
active `bg-white/10 text-white`) and the logo lockup switched to the
"reversed on ink" bright-blue + white variant inside it.

**Reason:** these were the three gaps `DESIGN_SYSTEM.md` flagged (but
deliberately did not fix) in the Phase 5.5 checkpoint; this session's
brief explicitly asked to close them alongside the logo implementation.

**Alternatives considered:** Leaving the sidebar white and only using ink
on the landing hero (status quo) - rejected, explicitly called out as
insufficient ("not just the landing hero") in this session's brief.
Applying ink to the main content background instead of the sidebar -
rejected, would fight with white cards and hurt readability across many
long-form pages (profile, applications); the sidebar is a bounded,
persistent, non-text-heavy surface, a much safer place for a saturated
dark fill.

**Consequences:** any future new authenticated page inherits the dark
sidebar automatically (it's in `base.html`, not per-template). Contrast on
the new dark surface was spot-checked visually (screenshotted against the
live dev server) but not yet measured formally against WCAG AA - carried
into the existing Phase 9 accessibility-audit item in `ROADMAP.md`, not
newly introduced by this change.

---

## 2026-08-11 — Brand casing corrected to "AUSVIA" (all caps) everywhere

**Decision:** Display the brand name in all caps, "AUSVIA", in the wordmark
(`app/templates/_logo.html`), every page `<title>`, and all documentation -
replacing the earlier mixed-case "Ausvia" and the wordmark's lowercase
"ausvia".

**Reason:** Explicit product-owner correction.

**Consequences:** Purely a text/copy change (wordmark macro + page titles +
docs) - no layout, component, or functional changes. Repo folder name,
Python package (`app.*`), and database remain unchanged, consistent with
the original rebrand decision below.

---

## 2026-08-11 — Gmail OAuth: real per-user web flow, token encryption keyed from SECRET_KEY

**Decision:** Replace the prototype's single-machine `InstalledAppFlow.
run_local_server()` + shared `token.json` with a standard authorization-code
web flow (`google_auth_oauthlib.flow.Flow`, not `InstalledAppFlow`):
redirect to Google → user consents → Google redirects back to our own
`/integrations/gmail/callback` route. Tokens are stored per-user
(`GmailConnection`, unique on `user_id`), encrypted at rest via Fernet
symmetric encryption with a key derived from `SECRET_KEY`
(`app/utils/crypto.py`).

**Reason:** The old flow doesn't work for more than one user - it opens a
browser and blocks on the *server's own machine*, and the resulting token
is shared globally. Flagged as the top priority gap in `PROJECT_AUDIT.md`
after Phase 4.5.

**Alternatives considered:** A dedicated encryption key (separate from
`SECRET_KEY`) with its own env var and rotation story - rejected for now as
more infrastructure than this app's current scale needs; noted as a Phase
8/10 revisit in `SECURITY.md` rather than silently accepted. Storing tokens
in plaintext - rejected outright, tokens are credentials.

**Consequences:** Reusing the same `credentials.json` a "Desktop app"-type
Google Cloud OAuth client produces still works locally, because Google's
loopback exception for that client type accepts `http://127.0.0.1:<port>/...`
redirect URIs without pre-registration - which matches how this app runs
(`python app.py` binds `127.0.0.1`). A real (non-localhost) deployment needs
a "Web application"-type client with the callback URL registered in Google
Cloud Console instead - documented in README.md. Never exercised against a
live Google OAuth consent screen in this environment (no `credentials.json`
configured) - same honesty standard as the Anthropic provider and the
Arbeitsagentur adapter: the code follows the documented API, but its live
behavior is unverified.

---

## 2026-08-11 — Gmail reply detection is search-based, not thread-tracked from creation

**Decision:** `app/integrations/gmail_reply_tracking.py` detects replies by
searching the connected inbox for messages from the application's contact
email (`from:<contact_email>`, optionally scoped to after the application
was marked sent) - not by tracking a specific Gmail thread ID from the
moment the application email was created.

**Reason:** AUSVIA never sends the original application email itself (spec:
the user always sends manually via the created draft). The Gmail thread
doesn't exist until the user actually sends - there is nothing to track a
thread ID *of* until after that point, which AUSVIA has no visibility into.
Searching by contact email is the best available signal without controlling
the send step.

**Alternatives considered:** Waiting for the user to paste back the sent
message's thread ID or manually link a thread - rejected as extra manual
work that defeats the point of automatic tracking. Requesting
`gmail.send`/`gmail.modify` scope to send *and* track directly - rejected
outright, contradicts the core "user always sends, AI never does" product
rule (spec sections 30/58).

**Consequences:** Reply detection can miss a reply if the company replies
from a different address than the one stored as `contact_email`, or
mis-attribute a message if multiple applications share a contact email at
the same company. Acceptable v1 tradeoff, upgradable later (e.g. once a
thread's `threadId` is known from a first detected reply, subsequent checks
could also search by that thread ID directly - not yet implemented).
Detection is manual (a "Check for replies" button), not backgrounded - see
the background-jobs gap in `ARCHITECTURE.md`.

---

## 2026-08-11 — Rebrand to "AUSVIA"

**Decision:** Rename the product from the working title "Ausbildung Career
Agent" to **AUSVIA**, with tagline "Your path to Ausbildung." Apply the new
brand across user-facing surfaces (page titles, nav, landing page, logo)
without renaming the repository, Python package structure, or database.

**Reason:** Explicit product/brand directive.

**Alternatives considered:** Renaming the repo folder and Python import
paths (`app.*`) to match — rejected as high-risk, zero functional benefit
churn touching every file's imports, and the directive itself says "do not
delete, restart, replace, or rebuild."

**Consequences:** All template titles, nav branding, and landing copy now
say AUSVIA. `app.py`, the `app/` package, `requirements.txt`, and the git
history still reference the original working name in places (e.g. the repo
folder name `ausbildung-finder/`) - this is cosmetic-only and intentional.

---

## 2026-08-11 — Brand palette reuses the existing Tailwind slate/blue scale

**Decision:** Adopt the new brand's exact neutral colors (`#F7F8FA`,
`#E2E8F0`, `#0F172A`, `#64748B`, `#94A3B8`) and semantic colors (`#16A34A`,
`#D97706`, `#DC2626`) as-is, without introducing new custom Tailwind tokens
for them, because they are pixel-identical or near-identical to Tailwind's
built-in `slate` and `green-600`/`amber-600`/`red-600` - which the app's
templates already used throughout Phases 1-4. Only the primary "brand" blue
scale was refined to the exact spec hex (`#2563EB`/`#3B82F6`, which are
themselves exactly Tailwind's `blue-600`/`blue-500`).

**Reason:** Avoid introducing redundant design tokens for values already
~99% in use; matches the directive's own "do not overengineer" principle.

**Alternatives considered:** Defining a fully custom neutral/semantic scale
from scratch and re-theming every template to reference it explicitly -
rejected as unnecessary churn with no visible difference.

**Consequences:** The rebrand touched `base.html`'s Tailwind config, the new
logo, and copy - not a page-by-page re-theme, since the existing utility
classes already matched the new spec almost exactly.

---

## 2026-08-11 — Gmail OAuth flagged as needing redesign, not fixed in Phase 4.5

**Decision:** Document the single-user OAuth flow (`gmail_client.py`'s
`run_local_server()` + shared `token.json`) as a known architectural gap in
`PROJECT_AUDIT.md` rather than redesigning it during the brand/audit phase.

**Reason:** Phase 4.5 was scoped to audit + brand/design system per the
directive's own phase breakdown; a proper per-user OAuth web flow (auth URL
→ callback route → encrypted per-user token storage) is a substantial
feature change that belongs in Phase 5/6 alongside the rest of the Gmail
reply-tracking work, not bundled into a rebrand.

**Alternatives considered:** Fixing it immediately since it's flagged as a
security concern - considered, but doing it properly requires new DB models
(`GmailConnection` with per-user encrypted tokens) and new routes, which is
feature work, not brand/audit work; bundling it would blur the phase
boundary the directive itself asks to respect.

**Consequences:** Gmail draft creation remains usable only in a single-
developer local setup until this is addressed. Flagged prominently in the
audit so it isn't silently forgotten.

---

## 2026-08-10 — Evolve the existing Flask app rather than rewrite in Next.js/Postgres

**Decision:** Build out the platform on the existing Python/Flask codebase
(SQLAlchemy + SQLite, upgradeable to Postgres via `DATABASE_URL`) instead of
the master spec's literal default recommendation of a Next.js/TypeScript/
Postgres stack.

**Reason:** The existing repo already had working, real integrations
(Bundesagentur Jobsuche API client, Gmail OAuth draft creation, PDF merge);
the dev machine had no Docker/Postgres available; a full rewrite would
discard working code for no functional gain. User deferred the choice to
this judgment call.

**Alternatives considered:** Next.js + TypeScript + Postgres (the spec's
literal default) - rejected per the reasoning above.

**Consequences:** Server-rendered Jinja2 + Tailwind CDN frontend rather than
a SPA. This is the foundational decision everything since Phase 1 builds on.

---

## 2026-08-10/11 — AI features are deterministic-first, AI-optional

**Decision:** Every AI-assisted feature (match scoring, cover letter/email
generation) computes its core output deterministically in plain Python
first; a configured AI provider only adds narrative polish or personalized
prose on top of already-computed, real facts. The app is fully functional
with zero AI credentials configured (`AI_PROVIDER=mock` default).

**Reason:** Spec's explicit anti-hallucination and "never present an AI
guess as a guaranteed fact" requirements; also means the app never depends
on a paid API key to be useful, and match scores are always explainable and
reproducible.

**Alternatives considered:** Asking an LLM directly for a match score or
letting cover letter generation be AI-only with a "coming soon" mock state -
rejected as both less trustworthy and less honest about what's real.

**Consequences:** `app/ai/matching.py` and `app/ai/cover_letter.py`
(template path) are real, tested, working code paths - not stubs. The real
`AnthropicProvider` path exists and is architecturally sound but has never
been exercised against a live API key in this environment (see
`PROJECT_AUDIT.md`).

---

## 2026-08-10 — Job source architecture: adapter pattern, manual import as universal fallback

**Decision:** All job sources implement a common `JobSourceAdapter`
interface (`search`/`get_job`/`normalize`/`check_availability`); manual URL/
text import is a permanent, source-independent fallback, not a stopgap.

**Reason:** Spec requirement that the product never depend on any single
external source being available; the Bundesagentur API turned out to be
blocked from this dev sandbox's network, which validated the design (search
degrades gracefully, manual import still works fully).

**Consequences:** Adding a second real source later (e.g. an official
company-careers feed, if one exists) is a new adapter class, not a rewrite.

---

## 2026-08-10 — Duplicate detection: simple normalized-match heuristic, not fuzzy/embedding-based

**Decision:** `app/jobs/dedupe.py` groups postings under one canonical `Job`
via exact matching on normalized company name (legal-suffix-stripped),
title (noise-stripped), location, and start date - not fuzzy string
matching or embeddings.

**Reason:** Simple, fully deterministic, explainable, and sufficient for the
one real source currently integrated. Avoids the complexity and cost of an
embedding-based approach before there's a second/third source to actually
need it for.

**Consequences:** Postings that are the same job but described with
different location strings or missing a start date won't currently be
merged. Documented as a v1 heuristic in the module docstring, upgradeable
without touching callers.

---

## 2026-08-10 — Human approval is mandatory before any application "package" is built

**Decision:** The `Application.status` can only become `ready` via an
explicit user "Approve application" action; nothing is ever auto-sent.
Gmail integration only ever creates drafts, never sends.

**Reason:** Explicit, repeated spec requirement (sections 47/58/28 across
both the original and AUSVIA directives).

**Consequences:** Every AI-assisted generation step (cover letter, email)
is followed by a review/edit step before the approval gate; this shaped the
whole `app/applications` route design.
