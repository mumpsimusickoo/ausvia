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
      self-serve signup). **Live and working (2026-08-29)**: the earlier
      403s were a domain-key mismatch (a key issued for `jooble.org`
      doesn't work on that domain either - Jooble issues keys per
      regional domain; a `de.jooble.org` key fixed it), not an
      account-side block. Because Jooble's free tier turned out to be a
      500-request *lifetime* cap (no reset, only a new key), it's
      deliberately **admin-only** rather than opened to general search
      traffic - `ADMIN_ONLY_SOURCES` in `app/jobs/adapters/manager.py`,
      enforced at both real call sites plus the public landing footer.
      A persistent per-source request counter tracks cumulative spend
      and a hard stop (5 requests short of the true cap, to absorb a
      non-atomic check-then-increment) refuses further calls outright
      once reached - a counter that only warns doesn't protect a
      non-renewing budget, so this isn't optional polish. See
      `DECISIONS.md`'s two 2026-08-29 Jooble entries and `JOB_SOURCES.md`.
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
- [x] **Extraction retry (2026-08-29)** - a transient failure (rate limit,
      timeout, malformed response) on the one-shot extraction above used to
      strand a job with `skills == None` forever, since it only ever fired
      once, chained off `enrich_job_detail()`'s one-time `True` return.
      Added `requirements_extraction_attempts` +
      `requirements_extraction_last_attempted_at` on `Job` to distinguish
      never-attempted / failed-and-retriable / gave-up-permanently: not a
      bare boolean, since a retry cap needs a count. Retry check
      (`should_retry_requirements_extraction()`) is OR'd into the existing
      view-triggered condition in `detail()` - no new scheduler. 1-hour
      backoff, 3-attempt cap; see `DECISIONS.md`'s 2026-08-29 entry for the
      full reasoning and the scope boundary found while implementing
      (deliberately does not trigger a *first* attempt outside the
      enrichment moment - that's `enrich_job_detail()`'s own, separate gap).
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
- **i18n pass - English default with a language switcher** (reserved
      space for it already sits beside the theme toggle). **Supersedes
      the bundle's own bilingual rule** (English labels over
      permanently-German prose, `AUSVIA_2_0_SCREEN_INVENTORY.md`'s
      section 0.1) - that rule is not the target here, see `DECISIONS.md`.
      AI-generated content language is a separate, per-feature axis, not
      tied to the UI language toggle: cover letter/application email/
      reply suggestions stay German always (real German-employer-facing
      text); match explanation/company insight/profile coaching/interview
      prep/CV profile statement follow the UI language; job posting data
      (titles/descriptions/requirements) is never translated, since it
      comes from the source verbatim. Split into three passes since a
      half-extracted set of templates is recoverable but a
      half-configured Babel setup is not:
  - [x] **Pass 1: infrastructure + switcher, 2026-08-28** - Flask-Babel
        wired up (`app/i18n.py`, `babel.cfg`, `translations/de/`), locale
        selection in priority order (an explicit choice, persisted >
        Accept-Language on first visit > English), the `language_switcher()`
        component (`_components.html`, beside `theme_toggle()`) at all
        three chrome call sites (desktop top bar, mobile topbar, landing
        header), and locale-aware `format_local_date()`/
        `format_local_currency()` helpers. Proof of concept only: the
        sidebar/drawer nav labels (7 strings) are the one template
        extraction this pass did; `format_local_date()` was wired into
        two real call sites (Job Detail's deadline, Application Detail's
        "applied since") plus `format_local_currency()` demonstrated at
        `/admin/components` with a literal value (no numeric currency
        field exists anywhere in the schema - `Job.salary` is a
        pre-formatted string from each source adapter, not a number).
        `User.locale` needed no migration - it's existed, unused, since
        the very first migration. Full detail: `DECISIONS.md`'s
        2026-08-28 "i18n pass 1" entry, `DEPLOYMENT.md`'s Translations
        section.
  - [x] **Pass 2: mass string extraction, 2026-08-28** - every in-scope
        template and Python module wrapped in `_()`/`_l()`/`ngettext()`,
        German catalog filled in group by group (shared components, auth,
        dashboard/digest, jobs, applications, profile/documents, company,
        landing, errors, integrations, admin), each followed by its own
        extract/translate/compile cycle. `format_local_date()`/
        `format_local_datetime()` mass-applied to every remaining date/
        time call site beyond pass 1's two proof-of-concept ones (no new
        `format_local_currency()` call sites - still no numeric currency
        field in the schema, unchanged from pass 1). Deliberately still
        untranslated: `app/ai/prompts/*` and AI-generated content itself
        (pass 3's job), job posting data (source-verbatim rule, unchanged),
        internal audit-log/diagnostic content (`log_event()` messages,
        `admin/components.html`, the temporary CORS diagnostic route).
        One deterministic-content fix landed outside its originally-
        assumed scope: `app/ai/matching.py`'s five scorer functions build
        plain-Python match-summary sentences (never an LLM call) that a
        first pass through the file mistakenly deferred as "AI content" -
        corrected once live German verification showed English gap
        sentences on every Find Ausbildung result card. Full detail:
        `DECISIONS.md`'s 2026-08-28 "i18n pass 2" entry, `DEPLOYMENT.md`'s
        Translations section (including a real stale-`.mo`-in-a-running-
        process gotcha found this pass).
  - [x] **Pass 3: AI prompt language, 2026-08-29** - the per-feature split
        wired into the real prompt builders. Cover letter/application
        email/reply suggestions confirmed already unconditionally German
        (no code change needed, verified live). Match explanation/
        improvement tips, company insight, profile coaching, interview
        prep, and CV profile statement now take an explicit `locale`
        (from `app/i18n.py`'s `get_locale()`, called inside each
        orchestration function - no route/call-site changes needed) and
        carry a new `generated_locale`/`narrative_locale`/
        `improvement_tips_locale` column (migration `d0a13f3299ee`) so a
        cached response is treated as stale when the session's locale no
        longer matches it, not just when the profile changes. CV profile
        statement moved buckets - it used to hardcode German
        unconditionally, now follows the UI language, since (confirmed in
        its own docstring) it's never submitted anywhere by AUSVIA, only
        copied into the candidate's own CV. Two real bugs found by this
        pass's own required verification/test run, not by inspection: the
        match-explanation functions were the only AI feature that never
        special-cased mock mode, silently falling through to a shared,
        hardcoded-English decline message regardless of locale; and a
        `lazy_gettext()` value can't bind directly to a SQLite column
        (the same class of bug pass 2 found once already, recurring in
        four more sibling "not configured" messages this pass closed).
        Verified via live generation against the real configured provider
        (Gemini) in both locales for all eight features, full pytest
        suite. Full detail: `DECISIONS.md`'s 2026-08-29 "i18n pass 3"
        entry.
  - [x] **Pass 3 resolve, 2026-08-29** - closed the one item pass 3's own
        report left open: `dashboard_insight.py`/`process_qa.py`, flagged
        as "structurally follows-UI-language but not named," confirmed
        genuinely candidate-facing by tracing their actual call chains
        (rendered on the Dashboard and Candidate Profile screens via the
        same `intelligence_surface()` component as their siblings) and
        wired the same way as the original five (migration `b00ad196d445`).
        A full sweep for the `LazyString`-can't-bind-to-SQLite pattern
        found zero further instances beyond the two closed here. Reply
        suggestion's live re-verification was attempted with a synthetic
        Gmail reply against the real provider and blocked by a real,
        account-wide daily quota exhaustion (not a code issue) - the
        fixed-system-prompt equality test and existing orchestration
        tests are what stand in its place. Full detail: `DECISIONS.md`'s
        2026-08-29 "i18n pass 3 resolve" entry.
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
      pass work). Migration `5b4fe35a6528`, applied to production via
      Railway's console, 2026-08-26. Full pytest suite: 452 passed / 3
      skipped (9 new tests). Full detail:
      `DECISIONS.md`'s two 2026-08-26 schema-pass entries,
      `DESIGN_SYSTEM.md`'s "Reliability - where the value comes from".
- [x] **Screens pass 1: Job Detail** - 2026-08-27, `jobs/detail.html`
      rebuilt on the component layer (bundle structure, English copy).
      Replaced the five stacked score bars with `match_band()`; added the
      requirement-tag cloud from `Job.skills` (extracted, never rendered
      before); added the third "not evaluated" state to Strengths/Gaps
      (distinct from a real gap); added the deadline countdown and
      source/dedup disclosure (both from data that already existed,
      never surfaced); wrapped the match narrative and improvement tips
      in `intelligence_surface()`, reliability badge confirmed hidden on
      null. `chip_attribute`/`chip_coverage` gained real variants in the
      process (see `DESIGN_SYSTEM.md`). One real bug caught by the 375px
      mobile check and fixed: `match_band()`'s segment labels lacked
      `truncate`. 12 new tests. Full detail: `DECISIONS.md`'s 2026-08-27
      entry, `DESIGN_SYSTEM.md`'s "Job Detail - 2026-08-27 pass".
- [x] **Screens pass 2: Application Detail** - 2026-08-27, densest screen
      in the bundle. Extended the vertical Wayfinding journey from six
      stations to eight (Discovered/Matched new leading stations, Reply
      genuinely new - dates from the earliest tracked Gmail reply, shows
      an honest "Skipped." when the route passed it with none); added
      the header line naming the next event with a countdown; built an
      accessible tab bar (real ARIA tabs, keyboard-navigable - a new
      interaction pattern for this app) for Cover letter/Email/Documents/
      Replies/Interview prep, matching the bundle's own five exactly;
      wired the three save routes the schema pass had flagged as missing
      (interview prep, CV statement, reply suggestion - all straightforward,
      mirroring cover letter/email's existing mechanism); confirmed
      `classification_confidence` is the one reliability badge in the app
      that renders a real value today. `intelligence_surface()` gained an
      editable `{% call %}` body slot to carry all five editable AI
      features on one component. Two real 375px overflow bugs caught and
      fixed (one copied forward into `jobs/detail.html` too - see
      `DECISIONS.md`). 23 new tests. Full detail: `DECISIONS.md`'s second
      2026-08-27 entry, `DESIGN_SYSTEM.md`'s "Application Detail -
      2026-08-27 pass".
- [x] **Screens pass 3: Dashboard** - 2026-08-27, `main/dashboard.html`
      rebuilt on the component layer (bundle structure, English copy);
      first screen most users see, brand-new-account empty states treated
      as the main case throughout, not an afterthought. Fixed "Follow-ups
      due" (was hardcoded `"0"`); built the new "Next up" hero card
      (single highest-priority digest item, own construction rather than
      `intelligence_surface()`, staleness dated from a new public
      `latest_transition_at()` helper reading real `ApplicationEvent`
      transitions rather than a new schema column); made the priority
      digest inline (dot-colored rows, no longer a teaser link to the
      identical standalone `/digest` page); added the applications table
      (didn't exist on the dashboard before, `status_pill()` + relative
      dates); built the cross-application insight (new `DashboardInsight`
      model + migration, grounded in real per-application facts, gated at
      2+ applications, verified against the real configured AI provider
      in dev, not just mock mode). Dropped the pre-existing bottom
      three-card row (not part of the bundle's Dashboard; every
      destination already lives in the sidebar). 13 new tests. Full
      detail: `DECISIONS.md`'s third 2026-08-27 entry, `DESIGN_SYSTEM.md`'s
      "Dashboard - 2026-08-27 pass". **Deploy note:** migration
      `4bbab0dec59b` (dashboard_insights table) is applied locally but
      not yet run against production - needs `flask db upgrade` on next
      deploy, same as the job_radar_status precedent.
- [x] **Screens pass 4: Find Ausbildung** - 2026-08-28, `jobs/search.html`
      rebuilt on the component layer - the biggest remaining feature, and
      mostly real backend work rather than layout. Sort-by-score shipped
      via a new batched `get_or_compute_matches()` (`app/jobs/matching.py`)
      that scores an entire result set in one query + one commit instead
      of per-card N+1 (measured ~8x/~26x faster cold/warm on this app's
      real data - see `DECISIONS.md`), reusing the existing `JobMatch`
      cache rather than a new schema or a precompute-on-discovery
      pipeline. Radius, category, and (caught mid-implementation, after
      first reporting it as real - a wrong measurement) German level were
      all dropped: no real data backs any of them today, checked against
      this app's own dev DB, not estimated - category needed and got an
      explicit stop-and-ask per the task's own instruction. Year range and
      minimum-score filters shipped (76% and, once scoring was unblocked,
      fully real respectively); source toggle generated from
      `get_enabled_adapter_names()`. Result cards gained real score +
      label + compact `match_band()` segments, a one-line strengths/gaps
      summary built from category names (not raw strength strings), and
      honest meta chips (deadline's dashed "NO DEADLINE GIVEN" variant is
      the common case - only 2.5% of jobs have one). Result count line
      ("N results · N sources · N duplicates merged") is a query over the
      existing `JobListing` relationship, no schema change. Found and
      fixed a real bug during required Playwright verification: a wholly
      blank profile could still show a fabricated 100/100 "Strong match"
      via `_score_location()`'s "no preference = open to anywhere"
      default - a new `_profile_has_scorable_data()` check overrides
      display (never the underlying score) to "Not scored" when nothing
      real was entered. 14 new tests. Full detail: `DECISIONS.md`'s
      2026-08-28 entry, `DESIGN_SYSTEM.md`'s "Find Ausbildung - 2026-08-28
      pass".
- [x] **Screens pass 5: Candidate Profile + Documents** - 2026-08-28, both
      `profile/view.html` and `documents/list.html` rebuilt on the
      component layer - two screens in one pass, both mostly restyling
      over data that already existed. Personal info and Ausbildung
      preferences became summary-card-plus-`<details>`-toggle sections
      (avatar initials, computed age, a real meta line) matching the
      bundle's compact read-only constructions, replacing the pre-existing
      always-open forms. Completeness became a real per-item checklist
      (dot + done/missing sentence, one row per one of
      `completeness_checklist()`'s eight checks) - reusing the Dashboard
      pass's *data*, not its single-summary-sentence UI, since the bundle
      draws this screen's panel as an actual list. Language rows gained a
      proof-state caption, scoped honestly to German only (the one
      language this schema actually tracks certificate evidence for, via
      `Document.is_primary_german_cert`) rather than fabricating "no
      evidence" for languages with no tracking at all. Documents gained
      "Used in N applications" / "Not used in any application" per
      document (a query over the existing `ApplicationDocument` join, no
      new plumbing) and its zero-documents empty state. 11 new tests. Full
      detail: `DECISIONS.md`'s 2026-08-28 entry, `DESIGN_SYSTEM.md`'s
      "Candidate Profile + Documents - 2026-08-28 pass".
- [x] **Screens pass 6: Company Detail** - 2026-08-28, `companies/detail.html`
      rebuilt on the component layer - small screen, mostly restyling.
      New "Facts on file" panel (industry, location, listings on file,
      first seen) plus its unusual, deliberately-kept honest-blank note
      ("Employee count, founding year, and revenue aren't available, so
      they stay blank rather than being estimated"). Per-position match
      scores reuse Find Ausbildung's batched `get_or_compute_matches()`
      (per the task's own instruction, avoiding the N+1 pattern that pass
      fixed) and picked up its `_profile_has_scorable_data()` guard too -
      a wholly blank profile can no longer fabricate a passing score on
      a company's positions either, the same underlying bug applied
      proactively rather than rediscovered. "Listings on file" is
      deliberately the raw `JobListing` count, not the position count -
      a genuinely different number whenever postings were merged from
      more than one source, same reasoning as Find Ausbildung's "N
      duplicates merged" line. Company fit insight wrapped in
      `intelligence_surface`; its grounding was verified by reading
      `app/ai/prompts/company.py`'s prompt builder directly (five company
      fields + job titles, nothing else, wrapped as untrusted external
      text) and confirmed live against the real configured provider - the
      generated note stayed inside the facts panel's own data and
      explicitly flagged the company facts as thin rather than inventing
      around it. 9 new tests. Full detail: `DECISIONS.md`'s 2026-08-28
      entry, `DESIGN_SYSTEM.md`'s "Company Detail - 2026-08-28 pass".
- [x] **Screens pass 7: Landing** - 2026-08-28, `landing.html`, last screen
      in the named inventory (`AUSVIA_2_0_SCREEN_INVENTORY.md`'s ten). A
      mini search-result preview + mini application-status preview (real
      `match_band`/`status_pill` components, deliberately non-flattering
      scores 82/64/45), an 8-station decorative journey strip (the real,
      functioning one is Application Detail's Wayfinding route,
      unrelated), and a footer with a source list generated from
      `get_enabled_adapter_names()` - today just "Bundesagentur für Arbeit
      (Jobsuche)", not the bundle's hardcoded three, since Adzuna's trial
      was never started and Jooble's key returns 403. The closing CTA's
      access-code field is real (posts straight to the existing
      `auth.register` endpoint, zero auth-logic changes), not decorative.
      Privacy/Impressum links are deliberately omitted, not stubbed - see
      the pre-launch blocker below. Also fixed a pre-existing dark-mode bug
      found via this pass's own required dark screenshot: the header logo
      wordmark was invisible in dark mode (hardcoded ink hex on a
      theme-aware background). 13 new tests. Full detail: `DECISIONS.md`'s
      2026-08-28 entry. **Superseded same-day by the widen pass directly
      below** - this pass kept the pre-2.0 counterform hero, which turned
      out to be an overly-literal scope reading, not a decision that held.
- [x] **Landing widen pass** - 2026-08-28, same day, corrects the scope
      reading above. Rebuilds the hero as the bundle's actual two-column
      composition (eyebrow/headline/promise/buttons left, the preview
      panel - reused, not rebuilt - right), removes the pre-2.0
      counterform staircase graphic entirely (no bundle equivalent ever
      existed), moves the access-code badge and "See how it works" into
      the header (matching the bundle), and widens every content section
      to a single-sourced 1600px (`max-w-content`, `tailwind.config.js`)
      while making the header itself genuinely full-width/edge-to-edge -
      the bundle's 1180px was judged too narrow on large monitors. Found
      and fixed a real clipping bug via its own required 1920px screenshot
      (the reused overlap card's `-mt-7` ate into the third listing's own
      score label; fixed with matching `pb-7` clearance). 5 new tests.
      Full detail: `DECISIONS.md`'s "Landing widen pass" entry,
      `DESIGN_SYSTEM.md`'s "Landing - 2026-08-28 widen pass".
- [x] **Landing toggle-fix pass** - 2026-08-28, same day. The theme
      toggle appeared missing from the rebuilt header; checked git history
      first per explicit instruction and found it was never actually
      reachable from `landing.html` - `theme_toggle()` was defined only
      inside `base.html`'s authenticated branch, not dropped by the
      rebuild. Moved the macro to `_components.html` as a genuinely shared,
      importable component (both of `base.html`'s existing call sites
      unchanged) and added a third call site in the landing header, with
      room reserved beside it for the language switcher. Verified live via
      Playwright, not just structurally: clicked the button and read
      `data-theme`/`localStorage` directly, both directions, at 1920 and
      375px, plus the persistence-through-login requirement end-to-end. 2
      new tests. Full detail: `DECISIONS.md`'s "Landing toggle-fix pass"
      entry, `DESIGN_SYSTEM.md`'s "Landing - 2026-08-28 toggle-fix pass".
- [ ] **Screens pass 8+** - the remaining ~110 existing card/badge/button/
      empty-state occurrences across every other screen, plus the
      remaining per-screen re-layouts beyond tokens/logo/theme/components/
      the ten named-inventory screens (all ten now done as of pass 7). Not
      yet scoped or started. The named token layer
      (`text-display`/`text-title`/`text-section`/etc., `rounded-panel`,
      `shadow-hairline`/`shadow-overlay`) is available for it; adopting
      those tokens on existing headings/cards site-wide is itself part of
      this not-yet-started work.

## Plans page + real access expiry (complete)

- [x] **Public `/plans` pricing page** - three plans by max simultaneous
      users per code (1/2/5, 150/250/500 DH/month), a yearly option at
      exactly 10x monthly (not 12x - "2 months free" is a checked
      consequence of that ratio, not a separate claim), one toggle
      switching all three cards at once. Built within the existing design
      system only (Tiefsee Teal tokens, existing `_components.html`
      macros, `btn()` extended with optional `target`/`rel` for the
      external WhatsApp links) - checked Context7's current Tailwind v3
      docs for toggle-switch patterns before building (per explicit
      instruction), landed on a real `role="switch"` button + vanilla JS
      rather than a CSS-only `peer-checked` construction, since the
      latter can't reach descendants of later siblings (three separate
      cards), only true siblings of the checkbox. Each card's CTA is a
      plan- and billing-period-specific pre-filled WhatsApp link
      (`app/plans.py`), not a generic one. Landing page gained a second
      "Request access" CTA next to the existing "Enter access code" one,
      linking here. Fully bilingual from the start (no fourth
      string-sweep gap).
- [x] **Real automatic access expiry** - `User.access_expires_at`
      (nullable, None = unaffected) computed at redemption time from a
      new `InvitationCode.access_duration_months` (nullable, backward-
      compatible default) via `dateutil.relativedelta` calendar-month
      arithmetic, not a flat day count - verified directly that a Jan 31
      redemption + 1 month lands on Feb 28, and on Feb 29 in a leap year,
      never an error or a March rollover. Two enforcement checkpoints, no
      scheduler (same check-at-request-time architecture as the job
      radar/priority digest elsewhere in this app): a login-time refusal
      with a WhatsApp-renewal message, and an app-wide `before_request`
      hook (`app/access_expiry.py`) that ends an already-authenticated
      session on its very next request once expiry passes, not just at
      the next login attempt. Both live-verified via Playwright against a
      real dev account, not just unit-tested. Admin code-creation form
      gained a "Plan" convenience selector (JS-fills Type/Max uses/Access
      duration from six presets) - a UI-only convenience, not a bound
      form field, so the underlying raw fields stay directly editable for
      trial/admin/custom codes exactly as before.
- [ ] **Explicitly not done, flagged so it isn't mistaken for finished:**
      the 1000-generation AI limit (`PLAN_AI_LIMITS`,
      `app/models/access_code.py`) is still completely unenforced - this
      pass added *time*-based expiry only, never touched *usage*-count
      expiry. Two unrelated mechanisms that happen to both hang off the
      same `plan` field. See `DECISIONS.md`'s 2026-08-30 entry for full
      reasoning throughout, including two real process gaps found while
      shipping this (a `pybabel update` fuzzy-flag trap that silently
      dropped 9 translations from the compiled catalog, and a Tailwind
      CSS purge staleness this project's own `npm run check:css` would
      have caught proactively but wasn't run until after the bug showed
      up live).

## Manual import: real AI field extraction (complete)

- [x] **Grounded field extraction on manual import** -
      `/jobs/import` used to prefill only a raw `<title>` tag and an
      unfiltered full-page text dump (company/location/start date always
      blank). A new AI pass (`app/ai/manual_import_extraction.py`,
      `app/ai/prompts/manual_import_extraction.py`) extracts a clean
      title, company, location, and start date (null unless genuinely
      stated - never guessed), plus a chrome-filtered description.
      Grounded the usual way for the scalar fields (literal,
      case-insensitive substring of the source); the description is
      grounded **by construction** - the AI cites 1-based line numbers
      to remove rather than composing or copying text, so fabricated
      description content is structurally impossible, not just checked
      for. Least-trusted input in the app (arbitrary third-party scraped
      text), fenced via the existing `wrap_untrusted_external_text()`.
      Runs lazily (only the batch item on screen) and caches onto that
      item so revisiting never burns a second AI call. Same mock-mode/
      `AIProviderError`/rate-limit degradation as every other AI
      feature - any hiccup falls back to exactly the old raw-title/
      raw-text baseline.
- [x] **Two bugs found only by testing real pages, not canned
      responses** - see `DECISIONS.md`'s 2026-08-30 entry for the full
      story: (1) Gemini wraps JSON replies in a markdown code fence even
      when told not to, silently collapsing every real call to the
      fallback; (2) the original "copy excluded lines back out verbatim"
      design blew past `max_tokens` on a real 176-line chrome-heavy page
      and truncated mid-JSON - same silent-fallback symptom, only caught
      by dumping the raw response directly. Fixed by stripping the
      fence and switching to line-number citation (truncation-resistant
      and equally grounded); `MAX_EXCLUDED_FRACTION`'s original 0.6 cap
      (assumed chrome is a page minority) was also raised to 0.95 after
      the same live test showed a real cookie-consent-heavy corporate
      page can legitimately be ~78% chrome. Both silent-fallback paths
      were logging nothing at all (`logger.warning()`, console-only) -
      swapped for `log_event(..., level="warning")` so a real failure is
      now visible in `/admin`, matching
      `job_requirements_extraction.py`'s convention.
- [x] **Live-verified against two real, messy postings** - Festo
      (`jobs.festo.com`) and TE Connectivity (`careers.te.com`), not
      mocked. TE Connectivity's page correctly left start date blank
      (its only date field is the ad's publish date, not an
      apprenticeship start date - the extraction did not conflate the
      two). Caching confirmed via `/admin/ai-usage`'s flat call count
      across repeat visits. Full suite: 688 passed, 3 skipped.
- [x] **Follow-up pass: whitespace-normalized grounding, plus a
      small-business/third-party-portal re-test and a forced-failure
      fallback check** - see `DECISIONS.md`'s second 2026-08-30 entry.
      A real small-business posting on `ausbildung.de` (portal template
      chrome, not a corporate ATS) extracted correctly, including
      resolving the actual operator name ("EDEKA Serbes") over the
      portal's more prominent franchise-umbrella label ("EDEKA
      Verbund"). `_grounded()`'s literal substring check was silently
      rejecting genuinely correct, non-fabricated extractions whenever
      whitespace was reformatted (non-breaking spaces, a title joined
      across source lines, doubled internal spacing) - fixed with
      whitespace normalization on both sides of the check, confirmed a
      genuine fabrication is still rejected after the fix. Fallback UI
      itself (not just its logging) live-verified by forcing a real
      Gemini rejection (invalid API key via process env, not `.env`) -
      review form came back exactly as the pre-extraction baseline.
      Full suite: 693 passed, 3 skipped.

## Password reset: real email delivery (complete)

- [x] **Real Resend delivery wired into the reset flow** - `app/mail.py`'s
      `send_password_reset_email()` actually emails the reset link at the
      exact point `request_reset()` (`app/auth/routes.py`) used to only
      generate the token and log the request internally. `ausvia.org` is
      verified with Resend (DKIM/SPF); from address is the hardcoded
      `AUSVIA <noreply@ausvia.org>`. The generic, enumeration-safe message
      is unchanged either way - a real send happening in the background
      never shows up in the response. Content is built in the account's
      own stored `User.locale` (`flask_babel.force_locale()`), not the
      anonymous requester's browser locale.
- [x] **Same graceful-degradation discipline as every other optional
      provider** (AI/storage/job-source adapters) - unset
      `RESEND_API_KEY`, a real `ResendError`, or any other unexpected
      exception all degrade to "log internally, send nothing," never to
      an error or a fallback toward exposing the link (which would undo
      the earlier security fix two entries below). Confirmed the route's
      existing `@limiter.limit("10 per hour")` actually covers real-send
      abuse specifically, not just redemption-style limits elsewhere -
      it's a real route decoration (unlike manual import extraction's
      internally-caught limit), so Flask-Limiter returns a genuine 429
      once exceeded.
- [x] **A real regression, self-caught before it shipped** - see
      `DECISIONS.md`'s full account: the first i18n extraction pass for
      this feature's 5 new strings omitted this project's own documented
      `-k lazy_gettext -k _l` flags, which silently dropped ~140
      unrelated, already-translated strings (every WTForms field label
      uses the `_l` alias, not `_`) out of the catalog. Caught by the
      full pytest run before anything was committed, fixed by discarding
      the corrupted catalog and re-running the extraction correctly.
- [x] **Live end-to-end verification, both languages, a real inbox** -
      graceful degradation confirmed first (forced-empty key via process
      env). With the real key: a real send through the actual form to a
      real Gmail inbox produced no failure log, and a direct Resend API
      call confirmed genuine acceptance (a real email ID, real Resend
      rate-limit headers) for both an English and a German copy. The
      reset link's own mechanism was separately verified end-to-end by
      reconstructing the identical token and completing a real password
      change, then logging in with the new password to confirm it was
      genuinely active. Full suite: 700 passed, 3 skipped.

## Adzuna off-by-default fix (complete)

- [x] **A real, pre-existing gap, confirmed not a false alarm** - real
      `ADZUNA_APP_ID`/`ADZUNA_APP_KEY` credentials found already present
      in `.env` would have activated Adzuna for real, non-admin user
      search traffic with zero deliberate admin action. The `is_enabled`
      *check* was already correct wherever it ran; the actual gap was two
      layers up: `ensure_source_settings_seeded()` seeded every source,
      Adzuna included, `is_enabled=True` by default, and this dev DB's
      row had been seeded that way before any Adzuna credentials existed.
      A second, more fundamental layer of the same gap:
      `ensure_source_settings_seeded()` only runs when an admin visits
      `/admin/job-sources` - a fresh deployment with real credentials
      could run real search traffic before that ever happens, with no
      settings row for any source at all, and the old fallback (no row ->
      treat as enabled, correct and intentional for Arbeitsagentur) was
      silently applying to Adzuna too.
- [x] **Fixed, both layers, reusing existing infrastructure only** - no
      new admin-only scoping needed (Adzuna's limits reset daily/weekly/
      monthly, not Jooble's lifetime cap). A new
      `SEED_DISABLED_SOURCES = {"adzuna"}` drives both the seed default
      and the no-row fallback so they can't disagree. A new data-only
      migration (`df88254c4f2c`) flips any already-seeded `adzuna` row
      back to disabled once - portable to any already-deployed database,
      not just this dev DB. `/admin/job-sources`'s existing generic
      toggle needed no changes - an admin can still enable it exactly as
      before, deliberately.
- [x] **Live-verified, non-admin user, real credentials, both
      directions** - with real credentials configured but disabled,
      neither the public landing footer nor a logged-in non-admin's
      `/jobs/` search page mentioned Adzuna. An admin toggling it on via
      the real `/admin/job-sources` UI made it appear on both
      immediately, no restart - then toggled back off to leave the dev
      environment in the correct default state. See `DECISIONS.md` for
      full detail. Full suite: 707 passed, 3 skipped.

## Manual import: extraction from pasted text (complete)

- [x] **The same AI field extraction now runs on the failed-fetch/
      paste path too, not just fetch-success** - `import_save()` in
      app/jobs/routes.py intercepts the first Save on a failed item that
      has pasted description text, runs the same
      `extract_manual_import_fields()` (same grounding, same
      log_event/record_usage discipline, cached onto the item the same
      way), merges results into whatever fields the user left blank
      (never overwrites what they actually typed), and re-shows the
      review form for confirmation rather than saving immediately - same
      "never silently commit an AI value the user hasn't seen"
      discipline as the fetch path. Only intercepts when extraction
      actually adds something new (a blank field gets filled, or the
      description gets chrome-cleaned) - found via a real test failure
      that intercepting unconditionally forced a pointless extra
      confirmation click even when the user had already typed everything
      themselves.
- [x] **A real bug only a live browser could catch, not the test
      suite** - the title/company HTML5 `required` attribute (WTForms'
      default for a `DataRequired` field) blocked the browser from ever
      submitting the form when those fields were deliberately left blank
      for extraction to fill in - the exact case this feature exists
      for. All 13 new pytest tests passed regardless, since a test
      client's POST never goes through real client-side HTML5
      validation. Fixed with `formnovalidate` on the Save button,
      matching an existing precedent on the "Skip this one" button in
      the same template; server-side validation remains the real,
      unchanged authoritative check.
- [x] **Live-verified with real pasted text and a genuine bot-blocked
      fetch failure** - a real Indeed URL rejected by Indeed's own bot
      protection, then real posting text copied from a genuine LinkedIn
      Siemens Mechatroniker listing pasted into the description field.
      Extraction correctly populated title/company/location and
      correctly left start date blank for a genuinely ambiguous
      DD/MM-vs-MM/DD date format in the source rather than guessing which
      reading was right. Confirming Save created the real job record and
      burned exactly one AI call total, confirmed via `/admin/ai-usage`.
      See `DECISIONS.md` for full detail. Full suite: 713 passed, 3
      skipped.

## Manual import salary + API-sourced salary investigation (complete)

- [x] **Salary added to manual import extraction, same grounded
      discipline as start date** - `app/ai/manual_import_extraction.py`
      and `ManualImportReviewForm` (`app/jobs/forms.py`) gained a
      `salary` field, wired through `_store_extraction_result()`,
      `_render_batch_review()`, and `import_save()` the same way as the
      other extracted fields. Never converts currencies, never averages
      a range, never invents a figure from company reputation - null
      when the source genuinely never states one, which is the common
      case for Ausbildung roles on fixed collective-bargaining pay
      scales. See `DECISIONS.md` for the two real bugs found and fixed
      via live testing (response truncation on a large real page, and a
      prompt gap around multi-line per-training-year salary tables).
- [x] **API-sourced jobs (Arbeitsagentur/Adzuna/Jooble) investigated,
      not fixed** - queried the dev DB for every job currently showing
      no salary per source and checked whether description text (or, for
      Arbeitsagentur, the raw API snapshot itself) contains a salary
      figure the structured field missed. Found no evidence of a real
      gap worth building a fix for - see `DECISIONS.md` for the full
      finding and reasoning.
- [x] Full suite: 718 passed, 3 skipped.

## Contact info: four independent causes fixed (complete)

Implementation pass following the same-day investigation that found
four distinct, confirmed reasons cover letter/application email/
follow-up email generation kept falling back to a fully generic
salutation even when a job posting named a real contact.

- [x] **Manual import** - `contact_person`/`contact_email` added to
      extraction (`app/ai/manual_import_extraction.py`) and
      `ManualImportReviewForm`, exact mirror of the salary fix, reusing
      `app/applications/forms.py`'s existing field labels/translations.
- [x] **`extract_contact_section()`'s documented "known v1
      limitation"** (a contact block stated as a dense run-on sentence
      with no heading) fixed via an email-address detection signal -
      re-verified directly against the real motivating case,
      Arbeitsagentur job id 119 (CASISOFT MindWare GmbH):
      `extract_contact_section()` now returns `found=True` with the real
      name/email instead of the placeholder.
- [x] **`_grounded_contact_value()` whitespace-normalization gap** -
      same bug shape, same fix, as manual import's own `_grounded()`
      fixed during the salary pass. Re-verified against the exact two
      synthetic cases found in investigation (non-breaking space, a name
      split across lines) - both now ground correctly.
- [x] **`build_salutation()` required a literal "Frau "/"Herr "
      prefix** - the highest-impact fix, since it silently capped the
      other three regardless of extraction quality. A title-less name
      (increasingly common in informal postings - real examples this
      session: ALDI Nord, CASISOFT) now gets a genuine, standard,
      gender-neutral opener ("Guten Tag [Name]") instead of either
      fabricating a title or falling back to the fully generic greeting.
      Directly tested against all three consumers, and live-verified
      end-to-end through the real app: a real manually-imported CASISOFT
      posting -> saved job -> started application -> real AI-generated
      cover letter opening "Sehr geehrte Frau Hubbes,".
- [x] Reply suggestions confirmed unchanged (deliberately doesn't use
      `contact_person`/`contact_email`/`build_salutation()` - left as an
      open design question, not fixed on this pass's own judgment).
- [x] Secondary consequence confirmed resolved too:
      `Application.contact_email` (the real address the Gmail draft/
      reply flow uses) is seeded from `Job.contact_email` at Application
      creation - verified via a new test and live in the browser.
- [x] Full suite: see `DECISIONS.md` for the final count.

## Before any public launch (not yet scheduled)

- [ ] **Real Impressum + privacy policy** - no privacy or Impressum
      route/page exists anywhere in the app today; the Landing pass
      (2026-08-28) deliberately left the footer's legal links out rather
      than stub them - see `DECISIONS.md`'s 2026-08-28 entry for exactly
      what the privacy policy needs to cover (Gmail OAuth scopes/storage,
      uploaded document retention, what's sent to the AI provider, which
      job source APIs are queried) and why an Impressum needs the user's
      real legal identity, not something to improvise mid-pass. Currently
      low-urgency only because AUSVIA is invite-only with no public
      signup - this becomes a hard blocker the moment that changes.

## Explicitly not scheduled

Payment processing (product directive: manual/off-platform only, not V1),
public registration (private/invite-only is a deliberate product choice,
not a temporary limitation), mobile native apps.
