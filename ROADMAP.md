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

## Phase 9 — UX Polish

Accessibility audit (keyboard nav, focus states, contrast, reduced motion),
loading/empty/error states review across all pages, mobile layout pass
(deliberate mobile layouts, not just shrunk desktop - per the design
directive), notification system.

## Phase 10 — Production Readiness

Real Postgres deployment (never exercised yet, though the code path exists),
environment/secrets configuration for a real host, background job worker,
monitoring/observability, deployment pipeline.

## Explicitly not scheduled

Payment processing (product directive: manual/off-platform only, not V1),
public registration (private/invite-only is a deliberate product choice,
not a temporary limitation), mobile native apps.
