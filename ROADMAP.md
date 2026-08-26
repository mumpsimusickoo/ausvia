# Roadmap — AUSVIA

Original build phases (1-4, complete - see `PROJECT_AUDIT.md`), now
continuing under the phase structure below.

## Phase 4.5 — Audit + Brand Integration (complete)

- [x] `PROJECT_AUDIT.md` - honest working/partial/broken/mocked/missing audit
- [x] AUSVIA brand: colors, typography (Inter), logo wordmark, landing page
- [x] Design system pass across existing templates (no functional changes)
- [x] `DECISIONS.md` + documentation set (`PRODUCT.md`, `ARCHITECTURE.md`,
      `DESIGN_SYSTEM.md`, `DATABASE.md`, `AI.md`, `JOB_SOURCES.md`,
      `SECURITY.md`, this file)

## Phase 5 — Product Completion (complete)

- [x] **Gmail OAuth redesign** - real per-user web OAuth flow
      (`app/integrations/gmail_oauth.py`), encrypted per-user token storage
      (`GmailConnection`), connect/disconnect UI at `/integrations/gmail`.
      Application draft creation now goes through each user's own connection.
- [x] **Gmail reply tracking** - manual "Check for replies" action
      (`app/integrations/gmail_reply_tracking.py`) searches the connected
      inbox for messages from the application's contact email (there's no
      thread to track from creation, since AUSVIA never sends the original
      email itself - see `DECISIONS.md`), extracts full message bodies,
      dedupes, logs a timeline event.
- [x] **AI reply suggestions** - `app/ai/reply_ai.py` classifies intent
      (6 categories + high/medium/low confidence) and drafts a contextual
      reply grounded in candidate facts + the company's message; reply
      drafts are created in-thread via Gmail's `threadId` +
      `In-Reply-To`/`References` headers, never sent automatically.
- [x] **Per-category match breakdown UI** - `MatchResult.category_scores`
      (skills/language/education/location/start_date, each 0-100, absent
      rather than zero when not evaluable) now renders as percentage bars
      on the job detail page.
- [x] **Rate limiting on AI-calling routes** - 30/hour/IP on cover letter,
      email, narrative, improvement-tips, reply-classification, and
      reply-suggestion generation.

**Known limitation carried forward:** nothing Gmail-related (OAuth, reply
search, draft creation) has been exercised against real Google
infrastructure in this environment - no `credentials.json` is configured.
The code follows the documented API precisely and is unit-tested against a
faked Gmail API service, but live behavior is unverified. See
`PROJECT_AUDIT.md`.

## Phase 5.5 — Product/Design Checkpoint (complete)

A pause between Phase 5 and Phase 6 to review the brand/UI direction before
adding more surface area, per explicit request. No functional or visual
code changes - documentation and one text-only correction only.

- [x] Brand casing corrected to **AUSVIA** (all caps) everywhere - wordmark,
      page titles, docs. See `DECISIONS.md`.
- [x] `DESIGN_SYSTEM.md` rewritten as an honest target-vs-actual comparison
      against the brand direction (deep navy/ink foundation, blue primary,
      warm off-white background, green/amber semantics, restrained motion,
      no purple/gradient/glassmorphism). Three concrete gaps identified:
      background is cool-toned not warm, zero shadow usage anywhere
      (border-only), ink/navy used only on the landing hero rather than as
      a foundation element. Also inventoried every reusable UI pattern
      currently in use but not yet extracted into shared components.
- [x] `PROJECT_STATUS.md` created as a standing current-state reference.
- [x] This file refreshed to fold the checkpoint's findings into Phase 6/9
      scope below.

**Decision on when to act on the design findings:** deferred to an
explicitly-scoped visual-refinement pass, not bundled automatically into
Phase 6. See `DESIGN_SYSTEM.md`'s "what would actually change" list.

## Phase 6 — Integration (complete for the scope taken on)

- [x] **Company profile pages** (`app/companies/`) - real `Company` fields
      (name, industry, location, website, description, all sourced only
      from job postings) plus the list of known Ausbildung positions at
      that company. Linked from job detail and application detail pages.
- [x] **Company AI fit insight** (`app/companies/insights.py`) - "why this
      company might fit you," dual-honesty pattern like reply
      classification (no deterministic core, mock mode declines plainly,
      real mode explicitly told to say company facts are thin rather than
      invent culture/benefits/headcount). Cached per (user, company), same
      staleness rule as `JobMatch`.
- [x] **Document AI extraction** (`app/documents/extraction.py`) - a
      keyword heuristic over each uploaded PDF's own text suggests a
      doc_type when it disagrees with the user's choice, shown as an
      explicit confirm/dismiss action, never auto-applied. Deliberately
      *not* AI-provider-based - see `AI.md` for why a heuristic is the
      better fit here. PDF-only (no OCR available in this environment).
- [x] **Background job infrastructure** (`app/tasks/runner.py`) - a
      `BackgroundTask` DB row + in-process `ThreadPoolExecutor`, no broker
      (matches the project's "no new infra beyond SQLite" pattern - no
      Docker/Redis available). One real call site: Gmail reply checking no
      longer blocks the request. PDF assembly and AI generation were *not*
      retrofitted this pass - explicit scope decision, see `DECISIONS.md`.
- [x] **Live verification recheck** - Arbeitsagentur endpoint retested
      directly against the exact URL/key `jobsearch.py` uses; still 403,
      same bot-protection diagnosis as Phase 2. Anthropic/Gmail remain
      unconfigured in this environment (no key, no `credentials.json`) -
      unchanged from Phase 5, not re-attempted without new credentials.

**Sequencing note from the Phase 5.5 checkpoint, revisited:** the
background-job groundwork *did* land before this phase's new AI-calling
features went live (company insight generation is the newest one, and
runs synchronously - it wasn't a background-job candidate the way Gmail
checking was, since its result needs to render inline immediately after
the button click, same as narrative/cover-letter generation). The
"extract UI patterns before adding more pages" note was *not* acted on
this pass - company/document-extraction UI reused the existing per-
template utility-class patterns rather than pausing to build a component
library first, a scope trade-off worth revisiting before Phase 7 adds
more surface area.

## Phase 7 — QA (complete)

Full workflow test per the product directive's "final quality bar" scenario,
end to end against the live dev server with a real (non-`:memory:`)
database. Found 3 Blocking + 9 Worth Fixing Now issues; see `QA_REPORT.md`.

- [x] **Phase 7 Remediation** (`PHASE7_REMEDIATION.md`) - all 3 Blocking and
      all 9 Worth Fixing Now findings fixed the same day: document-deletion
      cascade + SQLite FK enforcement, mobile navigation (hamburger +
      drawer), invitation-code redemption race, leaked exception detail,
      color-only status/flash indicators, unlabeled form fields, unlinked
      validation errors, AI-prompt delimiting. Full mobile-overflow audit
      across every authenticated page, all clean; `scripts/
      check_mobile_overflow.py` added as a reusable regression check.
- [x] **B3 correction** - the landing-page mobile-overflow finding was
      re-examined after its "fixed" claim didn't match the actual diff
      (`landing.html` had zero changes). Live re-verification found no
      overflow on the unmodified page; the original finding was most likely
      a measurement artifact from an unreliable CLI screenshot method
      discovered during this same pass, not a real defect. Corrected in
      both `QA_REPORT.md` and `PHASE7_REMEDIATION.md` rather than left
      standing - see either for the full writeup.

## Phase 8 — Security (complete)

Full audit-then-fix pass (classify every finding as Fix now / Needs a
decision / Defer *before* touching code, same discipline as Phase 7's QA
pass) - see `QA_REPORT.md`'s Defer table for where this started.

- [x] **Fix now, implemented:** `InvitationCode.generate_code()` moved from
      stdlib `random` to `secrets` (D1); `FLASK_ENV` set to an unrecognized
      value now fails loudly at startup instead of silently running in dev
      mode with `DEBUG=True`; `ProductionConfig` now forces
      `SESSION_COOKIE_SECURE`/`REMEMBER_COOKIE_SECURE` rather than relying
      on an env var that could be forgotten, and production with no
      `SECRET_KEY` now fails at startup rather than deep inside the first
      request; full CSP/`X-Content-Type-Options`/`X-Frame-Options`/
      `Referrer-Policy`/HSTS response headers added
      (`app/security_headers.py`, live-verified via DevTools that the CSP
      doesn't break the Tailwind/Google Fonts CDN loading it has to
      coexist with); 4 sites where a raw exception was flashed to the user
      fixed in the Gmail integration surface (same class of bug as Phase
      7's W3, which only reached background-task errors); `pypdf` upgraded
      4.3.1 → 6.15.0 (the one dependency finding with an actually-reachable
      attack surface - user-uploaded PDFs, parsed synchronously - not just
      the one with the most CVEs), with dedicated new tests inspecting real
      assembled-PDF output, not just "the suite is green."
- [x] **D6(a) implemented:** optional dedicated `TOKEN_ENCRYPTION_KEY` env
      var for Gmail token encryption, falling back to the original
      `SECRET_KEY`-derived behavior when unset - opt-in, and proven
      backward-compatible (a token encrypted before the key is introduced
      keeps decrypting after, no forced reconnection). D6(b) - requiring it
      in production with a forced-migration/reconnect path - stays
      deliberately deferred; that's real migration-design scope, not
      folded into the opt-in version.
- [x] **Audited, confirmed clean, no fix needed:** privilege escalation
      (the race-protected invitation-code flow is the only path to
      `role=admin`); Gmail OAuth state-parameter CSRF protection and scope
      minimality.
- [x] **Needs a decision, presented, not implemented:** D3 (rate limiter
      keys by IP not user) - deferred per the recommendation, since
      AI-cost abuse is already bounded by the account-level plan-limit
      system independent of the rate limiter. Stopping the Tailwind CDN
      dependency at runtime - deferred, real build-step infrastructure
      change, not a header tweak. `flask`/`cryptography`/`pytest`/
      `python-dotenv` version bumps - deferred, none currently exploitable
      in this app's actual configuration per the reachability analysis.

## Post-Phase-8 small fixes (v1 cleanup, complete)

Independent small passes closing out v1 - not a new phase, no new product
surface.

- [x] **Real company data in generation** - `format_job_facts()` only ever
      read `Job` fields; a job's linked `Company` row's industry/website/
      description (real, Phase-6-populated data) never reached cover-letter
      or application-email generation. Now wired in via a new
      `format_company_facts()`, gracefully absent when there's no linked
      company or it has no populated fields. Mock-mode template output
      confirmed unaffected.
- [x] **Manual import strengthened** (`JOB_SOURCES.md`) - bulk paste (up to
      10 URLs at once, each fetched independently, stepped through the same
      single-item review one at a time) and a browser bookmarklet (reads
      the current page's own title/URL/text directly from the DOM, hands
      it to AUSVIA via a URL fragment - never a request of AUSVIA's own,
      never sent to any server, never bypassing CSRF). Both live-verified
      via Chrome DevTools Protocol against real pages, not just pytest.
- [x] **Arbeitsagentur re-diagnosis** - tested live from a genuinely
      different network (not just re-asserted the Phase 2 finding). Still
      blocked, but the diagnosis changed: confirmed this was never an
      official API, and the block looks like anti-automation hardening on
      the endpoint itself, not IP reputation. `JOB_SOURCES.md` and
      `jobsearch.py` corrected accordingly.
- [x] **`.env` actually loads now** - nothing called `load_dotenv()` despite
      `python-dotenv` being a dependency and the README instructing
      `cp .env.example .env`; a fresh clone's `.env` was silently ignored,
      only real OS environment variables were ever read. Fixed in
      `config.py`, before any `Config` class reads `os.environ`. Verified
      via a subprocess-based test (in-process re-import can't prove this,
      since `config.py` is already loaded by the time any test runs) that a
      value set only in `.env` is actually picked up, and that a real OS
      environment variable still wins over one.
- [x] **`requests` bumped** 2.32.4 → 2.33.0 - a newer advisory existed but
      wasn't reachable in this app (the vulnerable function is never
      called); patched anyway since it's a zero-risk one-line bump.

## AI Feature Expansion (complete)

Shipped 2026-08-13, immediately after the doc sync that produced the prior
version of this file - informally labeled "Phase 9 Wave 1" and "Phase 9
Wave 2" in commit history, but this is **not** the same thing as the
"Phase 9 — UX Polish" entry below (that phase's actual scope - accessibility
audit, loading states, a notification system - was never started; the
commit-message label was a naming collision from that session, not a
redefinition of this roadmap's Phase 9). Documented here under its own
heading to avoid perpetuating the collision.

- [x] **Wave 1 - five request-triggered AI features**, each grounded only
      in real stored data, honest mock-mode decline, and structural
      prompt-fencing: **Profile/CV coaching** (`app/ai/profile_coaching.py`,
      new `ProfileCoaching` model, independent of any job posting);
      **Interview prep** (`app/ai/interview_prep.py`, new `InterviewPrep`
      model, keyed per application, available at any status); **Follow-up
      email** (`app/ai/followup_email.py`, new `FollowUpEmail` model - the
      one Wave 1 feature with a genuine deterministic template fallback,
      not just an honest decline, offered only once an application is
      Sent/Follow-up); **Job posting explainer** (`app/ai/job_explainer.py`,
      new `JobExplainer` model, a plain-language summary of a posting
      calibrated to the candidate's own stated German level); **Process
      Q&A** (`app/ai/process_qa.py`, new `ProcessQAAnswer` model, 5 fixed
      common-question buttons, deliberately not open free-text chat).
      33 new tests; live-verified via Chrome DevTools Protocol against the
      running dev server, not just pytest.
- [x] **Wave 2 - on-demand priority digest** (`app/priority_digest.py`,
      `GET /digest`) - which saved jobs and active applications deserve
      attention this week, computed purely from existing deterministic
      signals (follow-ups due, upcoming interviews/deadlines, approved-
      but-unsent applications, stalled applications, strong-match unapplied
      saved jobs). No AI call anywhere in this feature. Deliberately
      request-triggered, not scheduled - this app has no scheduler (see
      Phase 6's background-job entry above) and building one was
      explicitly out of scope for this pass. 15 new tests.

## Job Source Integration & AI Provider Expansion (complete for the scope taken on)

Shipped 2026-08-14/15, building on the prior "Arbeitsagentur confirmed
blocked" diagnosis from the last doc-sync pass - which turned out to be
correctable, not permanent.

- [x] **Arbeitsagentur v4→v6 fix** - requested as a low-priority version
      bump, but live-testing found v6 returns real 200 responses with real
      data where v4 still 403s identically, on the same network/key,
      repeatably. Also found and fixed two real bugs this exposed:
      `get_job_detail()` never base64-encoded the reference number
      (silently 404'd), and `search_ausbildung()`'s pagination stopped one
      page early. `normalize()` rewritten against v6's actual field names.
      Re-verified live from a second, structurally different network - see
      `JOB_SOURCES.md`.
- [x] **Adzuna adapter** (`AdzunaAdapter`) - official API, full error
      handling, "Jobs by Adzuna" attribution per its ToS,
      `employment_type` deliberately not defaulted to "Ausbildung" (Adzuna's
      `contract_type` doesn't confirm an apprenticeship). Built and
      unit-tested; the 14-day free trial has not been started, so this is
      not live yet - a deliberate choice, not an oversight (starting the
      trial is a real, consequential clock).
- [x] **Jooble adapter** (`JoobleAdapter`) - official API, same
      error-handling/normalization discipline, manually-issued key (no
      self-serve signup). Built and unit-tested. A real API key was
      obtained since, but Jooble's API is currently rejecting it with a
      403 - actively being troubleshot, not resolved.
- [x] **Shared pipeline improvements** (not per-source special-casing):
      `dedupe.py` now checks a canonical/original-URL match before the
      existing company+title+location heuristic; `ingest.py` adds a
      15-minute per-(source, query) cache so a repeated search doesn't
      burn Adzuna's 250/day or Jooble's quota on every page load;
      `manager.py` builds Adzuna/Jooble lazily from `current_app.config`,
      simply absent (not an error) until credentials are set.
- [x] **Lazy Arbeitsagentur detail-fetch** on first job-detail view - fills
      description/education_requirements the first time a job is actually
      opened, not during search, avoiding an extra API call per result for
      listings nobody opens. Fixes the wrinkle this creates for cached
      `JobMatch` staleness (deletes cached matches once enrichment actually
      adds data).
- [x] **AI-assisted skills extraction** (`app/jobs/requirements_section.py`
      + `app/ai/job_requirements_extraction.py`) - deterministic isolation
      of a posting's real requirements section from curriculum/duties/
      benefits/application-info text, then a grounded AI call where every
      extracted skill must appear verbatim in the exact text shown to it or
      it's dropped. Validated against real live-fetched Arbeitsagentur
      descriptions, including real curriculum-vs-requirements traps.
      Deliberately does not write `job.language_requirements` (would
      silently break matching's language scoring - see commit for detail).
      Chained off `enrich_job_detail()` via the existing background-task
      infra, a second real call site alongside Gmail reply checking.
- [x] **AI-assisted contact person/email extraction** - extends the same
      extraction call and section-isolation engine with a second,
      independent contact-section isolator (so curriculum text still never
      reaches the AI for skills purposes), grounded the same way (extracted
      value must be a literal substring of the source text) plus a basic
      email-format sanity check as an extra safety net. Never overwrites a
      manually-entered `contact_person`/`contact_email`, per field.
- [x] **Gemini added as a second real AI provider** (`GeminiProvider`,
      `AI_PROVIDER=gemini`) - same `AIProvider` interface as
      `AnthropicProvider`. Two bugs found live once a real key existed:
      Gemini 3's invisible "thinking" tokens were eating the entire
      `max_tokens` budget before any visible answer (fixed via
      `thinking_level="minimal"`, the correct Gemini-3-series mechanism,
      not the Gemini-2.5-series `thinking_budget=0` the docs suggested);
      and `TestingConfig` never explicitly forced `AI_PROVIDER` to `mock`,
      so a real local `.env` with a real key silently made "mock mode is
      honest" tests call the live provider instead of testing mock
      behavior - caught by running the full suite after wiring up the real
      key. Live-verified end to end (profile coaching, real candidate
      data, correctly labeled "Generated by gemini"). 15 new tests +
      regression coverage for both bugs.
- [x] **Config-blank-vars bug found and fixed** - `os.environ.get(key,
      default)` only falls back when the key is fully *absent*, not
      *present-but-empty* - exactly what a freshly-copied `.env.example`
      ships for several vars. Found live (`DATABASE_URL=` broke every
      non-testing `create_app()` call). Fixed for every config var with a
      real default, with subprocess-based regression tests (config values
      are fixed at module-import time, so only a cold interpreter start
      actually proves this).

**Live-verification status after this pass:** Arbeitsagentur confirmed
working (no longer "blocked"); Adzuna/Jooble built but not live (see
above for why); Gemini confirmed live end-to-end; Anthropic still
unconfigured/unverified in this environment.

## Product follow-ups (complete)

Shipped 2026-08-15/19, independent small features and fixes found via real
usage of the live dev server, not part of a single planned pass.

- [x] **CV profile statement** (`app/ai/cv_profile_statement.py`, new
      `CvProfileStatement` model) - a short, per-application AI-generated
      "Kurzprofil" paragraph grounded in real profile/job facts, with the
      same generate-then-validate fabrication guard as cover-letter
      generation, since this text is meant to be copied into a real
      submitted CV (unlike interview prep). Also surfaces the
      already-computed `JobMatch.strengths` in the same card - read-only,
      no new AI call. Never inserted into `pdf_package.py`, never touches
      the uploaded CV document.
- [x] **Dedupe-remerge cache-invalidation bug, found and fixed** -
      `merge_missing_fields()` only fills empty fields, so a re-matched job
      can be a genuine no-op; unconditionally invalidating cached
      `JobMatch` rows there (unlike the two other call sites, which each
      fire at most once per job) was routinely wiping valid scores and
      generated narrative text for no reason. Now conditional on whether a
      changed field actually feeds `compute_match()`.
- [x] **Application deletion** - hard delete for every status (no
      soft-archive), confirmation strength tied to status: a plain
      `confirm()` for "preparing"/"ready" (pure draft work, nothing sent
      to anyone), a server-enforced typed-`DELETE` for anything from
      "sent" onward (real correspondence history - dates, notes, an actual
      outcome). Found and fixed two real cascade-orphaning risks while
      building this: `GmailMessage` and `InterviewPrep` both had a
      `NOT NULL` FK to `applications.id` but no cascade relationship
      declared on `Application`, unlike every other dependent table - with
      SQLite FK enforcement on, this would have crashed delete for exactly
      the applications most likely to have real history worth cleaning up.
      `JobMatch` deliberately left untouched (keyed by `(user_id, job_id)`,
      independent of whether/how the user applied).

## Gmail "Approve & Send" — investigated twice, rejected both times (complete, decision on record)

Not a shipped feature - a settled decision, recorded here so it's visible
from the roadmap, not just `DECISIONS.md`. Evaluated once during the
original Gmail OAuth scope decision (2026-08-11 - see that entry in
`DECISIONS.md`, which rejected requesting `gmail.send`/`gmail.modify`
alongside the "user always sends" rule), and again via a dedicated
re-investigation (2026-08-19) specifically to check whether the answer
should change now that draft creation, reply tracking, and AI reply
suggestions all exist. Both reached the same conclusion independently: the
two-step flow (approve in AUSVIA, send from a separately-opened Gmail tab)
gives a genuine second safety checkpoint before an irreversible action that
no in-app confirmation dialog can fully restore. `gmail.compose`/
`gmail.readonly` remain the only Gmail OAuth scopes. See `DECISIONS.md`'s
2026-08-11 and 2026-08-19 entries for the full reasoning, alternatives
considered, and one smaller not-rejected idea (verifying `mark_sent()` via
the Sent folder instead of trusting the manual click) kept on record for
later. Not implemented; don't re-propose without genuinely new evidence.

## Phase 9 — UX Polish

Accessibility audit (keyboard nav, focus states, contrast, reduced motion),
loading/empty/error states review across all pages, mobile layout pass
(deliberate mobile layouts, not just shrunk desktop - per the design
directive), notification system.

**Not started.** (Note: an unrelated body of AI-feature work shipped
2026-08-13 under an informal "Phase 9 Wave 1/2" label in commit history -
see "AI Feature Expansion" above. That work is unrelated to this phase's
actual scope and does not count toward it.)

## Phase 10 — Production Readiness

Real Postgres deployment, environment/secrets configuration for a real
host, background job worker, monitoring/observability, deployment
pipeline.

**Partially done** - a 2026-08-14 deployment-readiness pass (see
"Job Source Integration & AI Provider Expansion" above for the adjacent
work that shipped the same week) delivered:

- [x] gunicorn + Procfile for production serving, via a dedicated
      `wsgi.py` entrypoint (`gunicorn app:app` collided with the
      `app.py` file vs. `app/` package name clash - `flask run` never hit
      this since it loads `app.py` by file path).
- [x] S3-compatible document storage provider (`app/documents/storage.py`),
      selected via `STORAGE_PROVIDER`, tested against `moto` (mocked S3,
      not a live bucket).
- [x] Postgres compatibility verified by compiling the real schema DDL
      against the Postgres dialect and confirming the FK-enforcement
      listener stays a no-op - no live Postgres server available in this
      sandbox to test against directly.
- [x] `GET /health` for platform health checks.
- [x] Production now fails loudly if `DATABASE_URL` is unset, matching the
      existing `SECRET_KEY` check (previously silently fell back to local
      SQLite, which loses all data on redeploy on most hosts).
- [x] Gmail credentials can be supplied via `GOOGLE_CREDENTIALS_JSON` (full
      file content as an env var), not just a `credentials.json` file, for
      hosts that can't place an arbitrary file at a fixed repo-relative
      path.
- [x] A real production OAuth `redirect_uri` bug fixed via `ProxyFix`
      (Railway terminates TLS at its edge and forwards over plain HTTP
      internally; `url_for(..., _external=True)` was reporting `http://`
      instead of `https://`, which Google's OAuth flow rejected outright).

**Still not done:** exercising against a real live Postgres server, a real
background job worker beyond the existing in-process `ThreadPoolExecutor`
(deliberately unchanged - see Phase 6), monitoring/observability, and a
real CI/CD deployment pipeline. See `DEPLOYMENT.md` for the full env var
reference.

## AUSVIA 2.0 Redesign (in progress)

A full visual/product design brief ("AUSVIA Wegmarke") and a large
interactive HTML mockup ("AUSVIA 2.0", 9 screens + mobile) were provided
for a redesign pass, started 2026-08-24.

- [x] **Implementation audit** - every distinct design element across all
      9 screens plus mobile independently checked against the real repo
      (routes/models/templates, not assumptions) and categorized as
      existing functionality, new UI over existing data, a new feature
      needing real backend work, or a prototype-only interaction. Flagged
      two conflicts as blocking further work: an automatic "job radar"
      that conflicted with this app's deliberate no-scheduler architecture
      (see Phase 6/Phase 9-Wave-2 above), and an ambiguous "Als CV
      exportieren" button that matched neither the already-declined
      full-CV-generation idea nor the already-built `CvProfileStatement`.
- [x] **Job Radar decision resolved and built** - shipped as an on-demand
      "Check now" action (`app/jobs/radar.py`, `POST /jobs/check-now`,
      new `JobRadarStatus` model) - searches the user's saved preferences
      against the currently-enabled sources on request, surfaces genuinely
      new listings with match scores on the dashboard. No scheduler, cron,
      or background polling introduced; dashboard copy is explicit this is
      a manual check, never implying automatic background monitoring. The
      fully-automatic version stays explicitly deferred to a future
      infrastructure phase.
- [x] **"Als CV exportieren" decision resolved and built** - shipped as a
      real, deterministic PDF export (`app/profile/cv_export.py`,
      `GET /profile/cv.pdf`) built from the candidate's own stored profile
      data via reportlab - genuinely new document-rendering capability
      (`pdf_package.py` only ever merged existing PDFs), not a repurposing
      of `CvProfileStatement`. No AI call; empty sections omitted, nothing
      invented.
- [x] **Foundation-tokens pass** (colors, typography, spacing, radius,
      shadow, focus states only - no screens/components/logo/dark-mode
      changes), 2026-08-25 - values extracted directly from the approved
      2.0 mockup's own "Foundations" reference screen. Accent changed
      Signal Blue → Tiefsee-Teal (light) / a new distinct ink-surface
      action color (dark); page background and the fixed ink sidebar/hero
      surface both got new hex values; the retired `brand-50..900`
      Tailwind ramp was replaced role-by-role (not regenerated) across
      ~110 call sites in ~24 templates; Sora became a live UI webfont for
      titles/sections/values/numbers (superseding "wordmark-only"), IBM
      Plex Sans replaced Inter as the body face, IBM Plex Mono was added
      for labels; focus states became a real 2px outline everywhere,
      including the sidebar (which previously had none at all). The
      light-surface neutral scale (Tailwind `slate` → the bundle's
      Porzellan `t1`/`t2`/`t3`/`line`/`line2`/`raised`) was migrated in
      full too, same role-mapped method, across 384 call sites in 31
      templates - not left as "close enough" once the real RGB deltas
      turned out to be visible across a full page of body text. Two real
      accessibility regressions were caught and fixed before shipping, not
      after: a white-on-fill button label that measured 3.66:1 (fails AA),
      and a naive `slate-500/400` → `t3` mapping that measured
      2.76-3.02:1 at 98 call sites (`t3` stays defined, wired into zero
      live elements, same as `ink-t3`) - see `DESIGN_SYSTEM.md`
      Accessibility for the full measured numbers. Full detail:
      `DESIGN_SYSTEM.md` "Foundation tokens - 2026-08-25 pass",
      `DECISIONS.md`'s three entries dated 2026-08-25.
- [x] **Logo-replacement pass**, 2026-08-25 - retired Aperture (rev 1.0),
      implemented Wegmarke (two offset tracks, 48-grid, transcribed
      exactly from the bundle's own Foundations screen) as the AUSVIA
      symbol. Below 22px both `_logo.html` macros automatically switch to
      a wider-bar path variant so the gap stays visible - verified by
      rendering the real macro output on both sides of the threshold, not
      just reading the code. Symbol color follows the existing light/dark
      token split (`brand`/`bright`); one real discrepancy in the bundle
      itself (two of its four rendered examples hardcode a different teal,
      `#0F7379`, instead of its own `var(--brand)`) was resolved in favor
      of the shipped token, not the inconsistent hardcoded value. All 17
      static brand assets and the favicon (PNG raster regenerated via
      Pillow - no SVG rasterizer available in this environment) were
      regenerated to match; no `.ico`/apple-touch-icon/manifest exists in
      this repo, so none were invented. The wordmark's shape/spec (Sora
      SemiBold, lowercase, -4% tracking) is completely untouched - only
      the symbol changed. One drift bug caught and fixed within this
      pass: the wordmark's light-surface text color was still hardcoding
      the pre-tokens-pass `ink` hex (`#0B1220`), corrected to the current
      `#0C1013` in `_logo.html`'s macro defaults and the four static SVGs
      that hardcoded it - initially flagged as out-of-scope, folded in on
      review as a one-line, zero-risk fix rather than left for its own
      pass. Full detail: `DESIGN_SYSTEM.md` "Logo - Wegmarke replaces
      Aperture", `DECISIONS.md`'s 2026-08-25 entries.
- [x] **Screen inventory, verified against the repo** - an element-by-
      element read of all 10 bundle screens plus the theme/component-layer
      addendum, bucketed A (restyle)/B (new UI, existing data)/C (new
      backend)/D (prototype-only). Every bucket call checked against the
      live repo, not the project docs the inventory was originally read
      against - corrections filed alongside the original, not silently
      overwritten. Full detail: `AUSVIA_2_0_SCREEN_INVENTORY.md`.
- [x] **Theme pass** - real Porzellan/Tinte light/dark toggle, 2026-08-25,
      reversing the foundation-tokens pass's "ink is fixed, no toggle"
      decision. CSS custom properties under `[data-theme="dark"]` on
      `<html>`, not Tailwind `dark:` variants - no class name in any
      template changed, only the token values swap. Bundle verified
      directly (unpacked its self-extracting artifact payload, not
      inferred from screenshots): the sidebar follows the theme (was
      fixed-ink, now `bg-card`); the mobile topbar/drawer and the landing
      hero stay fixed-ink, confirmed against the bundle rather than
      assumed. Icon-only toggle (sun/moon), `localStorage` persistence,
      `prefers-color-scheme` on first visit, no flash of the wrong theme
      (nonce'd synchronous script ahead of first paint). Two real
      accessibility bugs caught by measuring before migrating, not after:
      a fixed white button-label text fails AA on several dark-mode fills
      at rest (not just on hover) - fixed with one new derived token
      (`on-fill`); Tailwind's stock semantic colors (never migrated when
      `ok`/`warn`/`err`/`info` were first defined) fail AA against the new
      dark card - migrated 62 occurrences across 18 templates, plus 68
      `bg-white`→`bg-card` card-panel sites and 27 `text-white`→
      `text-on-fill` button-label sites. Full detail: `DESIGN_SYSTEM.md`
      "Theme architecture - 2026-08-25 pass", `DECISIONS.md`'s 2026-08-25
      entry. One disclosed gap: no browser-automation tool was available
      to do a live rendered-in-both-themes visual pass this session -
      verified via CSS values, contrast math, and confirmed template
      rendering instead.
- [ ] **i18n pass** - English default with a language switcher (reserved
      space for it already sits beside the new theme toggle), German body
      copy for AI-generated prose per the bundle's own bilingual rule -
      not yet scoped or started.
- [x] **Component layer pass** - 2026-08-26, build-only: 11 macros
      (`btn`, `arrow_link`, `status_pill`, `chip_source`,
      `chip_attribute`, `chip_coverage`, `match_band`, `empty_state`,
      `notice`, `intelligence_surface`, `progress_bar`) in the new
      `app/templates/_components.html`, every value read from the
      bundle's own Foundations swatches, demonstrated at
      `/admin/components` (admin-only). No existing call site migrated -
      nothing in the live app changed appearance, by design. One real
      accessibility bug caught and fixed (Ready status pill's dark-mode
      text failed AA by a hair - see `DECISIONS.md`'s 2026-08-26 entry).
      Full detail: `DESIGN_SYSTEM.md` "Component layer - 2026-08-26 pass".
- [x] **Schema pass: reliability + edit tracking** - 2026-08-26,
      backend-only (no UI/screens/templates touched). Added a
      `reliability` column (`"high"`/`"medium"`/`"low"`, same type as
      `GmailMessage.classification_confidence`) to the six other
      AI-backed models feeding the Intelligence component
      (`JobMatch` x2, `CompanyInsight`, `GeneratedDocument`,
      `GeneratedEmail`, `GmailMessage`'s reply suggestion) - ships null on
      all seven by design, not a gap: only email classification has a
      real self-report mechanism, and none of the other six surfaces have
      a structured field to hang a rating on without restructuring their
      prompts for no real evidentiary gain. Added `edited_at` to
      `InterviewPrep`/`CvProfileStatement`/`GmailMessage` (reply
      suggestion), matching cover-letter/email's exact mechanism - all
      three ship unpopulated too, since none of those three features has
      a save/edit route yet (generate-only today; wiring that is screens-
      pass work). Migration `5b4fe35a6528` - **not yet applied to
      production**, pending manually via Railway's console. Full pytest
      suite: 452 passed / 3 skipped (9 new tests). Full detail:
      `DECISIONS.md`'s two 2026-08-26 schema-pass entries,
      `DESIGN_SYSTEM.md`'s "Reliability - where the value comes from".
- [ ] **Screens pass** - migrate the ~180 existing card/badge/button/
      empty-state/match-score occurrences onto the component-layer macros
      above, plus the remaining per-screen re-layouts beyond
      tokens/logo/theme/components. Not yet scoped or started. The named
      token layer (`text-display`/`text-title`/`text-section`/etc.,
      `rounded-panel`, `shadow-hairline`/`shadow-overlay`) is now
      available for it; adopting those tokens on existing headings/cards
      site-wide is itself part of this not-yet-started work.

## Explicitly not scheduled

Payment processing (product directive: manual/off-platform only, not V1),
public registration (private/invite-only is a deliberate product choice,
not a temporary limitation), mobile native apps.
