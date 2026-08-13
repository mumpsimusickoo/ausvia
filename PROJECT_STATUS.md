# Project Status — AUSVIA

Snapshot date: 2026-08-13, after Phase 8 + the Post-Phase-8 v1 cleanup pass
(see `ROADMAP.md`). For phase-by-phase detail see `ROADMAP.md`; for the
original working/partial/broken/mocked/missing category audit see
`PROJECT_AUDIT.md`; for the Phase 7 QA findings and their fixes see
`QA_REPORT.md` and `PHASE7_REMEDIATION.md`. This file is the "where are we,
what's next" summary.

## Where things stand

AUSVIA is a Flask-based, invitation-only platform that takes a candidate
from profile → job discovery → transparent match scoring → AI-assisted
application prep → human-approved send → Gmail reply tracking → AI-assisted
reply drafting, plus company profile pages, document AI extraction, and a
strengthened manual-import path (bulk paste + browser bookmarklet) for
sources that can't be reached programmatically. Phases 1 through 8, the
Phase 7 Remediation follow-up, and a small Post-Phase-8 v1 cleanup pass are
all complete, tested (189 passing pytest tests), and committed. Nothing is
faked or silently mocked - every feature either does the real thing or
honestly says it can't (see `AI.md`'s deterministic-first principle).

Three things remain explicitly **not yet verified against live external
services** in this environment: the Anthropic AI provider (no API key
configured), the entire Gmail stack (no `credentials.json` configured), and
the Arbeitsagentur Jobsuche endpoint - the last of which is now understood
to be an unofficial, reverse-engineered interface (not a registered
developer API) that appears to deliberately block non-browser access,
tested live from two structurally different networks with identical
results. All three are real, tested against faked services where
applicable, and unverified live - not broken, not stubbed. See
`JOB_SOURCES.md` for the Arbeitsagentur diagnosis in full.

## Architecture summary

- **Backend:** Flask application factory + blueprints (auth, main, profile,
  documents, jobs, applications, integrations, companies, admin),
  SQLAlchemy ORM, Flask-Migrate/Alembic, Flask-Login, Flask-WTF (CSRF),
  Flask-Limiter.
- **Database:** SQLite (`instance/app.db`) in dev, Postgres-ready via
  `DATABASE_URL` (never exercised against real Postgres). SQLite
  foreign-key enforcement is explicitly turned on (Phase 7 Remediation).
- **AI:** provider-agnostic abstraction (`MockAIProvider` default,
  `AnthropicProvider` real but unverified live) - every AI feature computes
  its core output deterministically first; AI only adds polish, except
  reply classification/suggestion which has no deterministic fallback by
  design (see `AI.md`). Cover-letter/application-email generation now also
  incorporates real linked-`Company` data (industry/website/description)
  when available, not just the job posting's own text.
- **Frontend:** server-rendered Jinja2 + Tailwind (CDN, no build step), no
  SPA framework. A real mobile navigation (hamburger + drawer) exists below
  the `md` breakpoint (Phase 7 Remediation) - see `DESIGN_SYSTEM.md` for
  the full component breakdown.
- **Security headers:** CSP, `X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy`, and HSTS on every response (`app/security_headers.py`,
  Phase 8) - a manual `after_request` hook rather than a new dependency,
  using a per-request nonce for the app's own inline `<script>` blocks.
- **Background jobs:** minimal - a `BackgroundTask` DB row +
  `ThreadPoolExecutor`, no broker (Phase 6). One real call site (Gmail
  reply checking); PDF assembly and AI generation remain synchronous, an
  explicit scope decision (see `DECISIONS.md`).
- **Multi-tenancy:** every user-owned resource is scoped by `user_id` and
  checked per-route (`_owned_x_or_404` pattern), returning 404 rather than
  403 on mismatch.

Full detail: `ARCHITECTURE.md`. Full schema: `DATABASE.md`. Full decision
history: `DECISIONS.md`.

## Manual job import - now the primary working path for sources that block automated access

Since the Arbeitsagentur endpoint is confirmed blocked (see above),
`app/jobs/manual_import.py` and its two convenience layers added in the
Post-Phase-8 cleanup are the actual load-bearing path for getting real job
data into the product today, not just a fallback:

- **Bulk paste** - up to 10 URLs pasted at once, each fetched independently
  (one blocked URL never stops the others), stepped through the same
  single-item human review form one at a time.
- **Browser bookmarklet** - reads the current page's own title/URL/visible
  text directly out of the DOM (no request of AUSVIA's own, so there's
  nothing for a site to block), hands it to AUSVIA via a URL fragment
  (never sent to any server), lands on the same CSRF-protected review form
  as every other import path. Nothing saves without an explicit submit.

Both are user-initiated, one-posting-reviewed-by-a-human-at-a-time, and
never bypass a login wall, paywall, or bot protection - same discipline as
everywhere else in the product.

## Security posture

- Response headers (CSP/X-Frame-Options/etc.), fail-loud config
  (unrecognized `FLASK_ENV`, missing production `SECRET_KEY`), and
  cryptographically-random invitation codes all landed in Phase 8.
- Gmail token encryption can use a dedicated `TOKEN_ENCRYPTION_KEY`
  (optional, falls back to the original `SECRET_KEY`-derived behavior when
  unset - see `SECURITY.md`). Not yet required in production; that's a
  deliberately deferred follow-up (D6b) since it needs a real forced-
  reconnect migration path designed first, not just a config flag.
- `.env` is now actually loaded (`config.py` calls `load_dotenv()` before
  any `Config` class reads `os.environ`) - previously silently ignored
  despite the README instructing `cp .env.example .env`.
- Dependency versions: `pypdf` upgraded to 6.15.0 (the one dependency
  finding with an actually-reachable attack surface) and `requests` to
  2.33.0 (patch bump, not currently reachable but zero-risk to take).
  `flask`/`cryptography`/`pytest`/`python-dotenv` version bumps remain
  deliberately deferred pending a "needs a decision" review of their
  breaking-change risk - see `ROADMAP.md`'s Phase 8 entry.
- Rate limiter still keys by IP, not by user (D3) - deliberately deferred,
  since AI-cost abuse is already bounded by the account-level plan-limit
  system independent of the rate limiter.

Full detail: `SECURITY.md`.

## Current UI/design status

Functionally complete and internally consistent - the same handful of
Tailwind utility patterns (card, button tiers, status pill, progress bar)
are reused correctly across all templates with no visual drift. Brand
colors (Signal Blue primary, Ink Navy foundation, warm off-white
background, green/amber semantics) match the target spec, including on
mobile navigation surfaces added in Phase 7 Remediation.

There is still no shared component library beyond a couple of form-
rendering macros - every card/button/badge/pill is a repeated (but
consistent) utility-class pattern, not a reusable macro or component. Not
urgent, but worth addressing whenever Phase 9 (UX Polish) adds more
surface area, so the pattern doesn't get copy-pasted further.

Full detail on the brand direction and any remaining gaps: `DESIGN_SYSTEM.md`.

## Test coverage

189 pytest tests passing across auth, profile, documents, admin, job
search/import/dedup/matching, manual-import bulk-paste and bookmarklet
flows, AI provider selection, application generation (cover letter/email/
PDF assembly/approval, including real Company-data-in-generation
coverage), Gmail OAuth/reply-tracking/AI-reply (faked services), token
encryption (including the D6a dedicated-key backward-compatibility
transition), rate limiting, mobile navigation markup, accessibility
(labels, flash messages, status markers), AI prompt-injection fencing,
security-hardening config behavior (fail-loud `FLASK_ENV`, forced
production cookie/secret settings), PDF-assembly output correctness (real
page counts/extracted text, not just "no exception"), and `.env` loading
(subprocess-verified, since the effect can only be proven from a cold
interpreter start). No test calls a real external API (Anthropic,
Jobsuche, Gmail).

## Recommended next step

Phase 7, 7-Remediation, 8, and the v1 cleanup pass are done - this closes
out v1 per explicit instruction; no further phase is scheduled without a
separate prompt. When work resumes, the live options per `ROADMAP.md` are:
(a) Phase 9 (UX Polish - accessibility audit, loading/empty/error states,
a notification system), or (b) Phase 10 (Production Readiness - real
Postgres, deployment pipeline, monitoring). Both remain genuinely
unscoped in detail; neither has been started.
