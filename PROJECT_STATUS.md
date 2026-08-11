# Project Status — AUSVIA

Snapshot date: 2026-08-11, after Phase 5 + a Phase 5.5 product/design
checkpoint (this document). For the detailed working/partial/broken/mocked/
missing breakdown, see `PROJECT_AUDIT.md` — this file is the higher-level
"where are we, what's next" summary.

## Where things stand

AUSVIA is a Flask-based, invitation-only platform that takes a candidate
from profile → job discovery → transparent match scoring → AI-assisted
application prep → human-approved send → Gmail reply tracking → AI-assisted
reply drafting. Phases 1 through 5 are complete, tested (96 passing pytest
tests), and committed. Nothing is faked or silently mocked — every feature
either does the real thing or honestly says it can't (see `AI.md`'s
deterministic-first principle).

Two things are explicitly **not yet verified against live external
services** in this environment: the Anthropic AI provider (no API key
configured) and the entire Gmail stack (no `credentials.json` configured).
Both are real, tested against faked services, and unverified live — not
broken, not stubbed. See `PROJECT_AUDIT.md` → "Needs testing."

## Architecture summary

- **Backend:** Flask application factory + blueprints (auth, main, profile,
  documents, jobs, applications, integrations, admin), SQLAlchemy ORM,
  Flask-Migrate/Alembic, Flask-Login, Flask-WTF (CSRF), Flask-Limiter.
- **Database:** SQLite (`instance/app.db`) in dev, Postgres-ready via
  `DATABASE_URL` (never exercised against real Postgres).
- **AI:** provider-agnostic abstraction (`MockAIProvider` default,
  `AnthropicProvider` real but unverified live) — every AI feature computes
  its core output deterministically first; AI only adds polish, except
  reply classification/suggestion which has no deterministic fallback by
  design (see `AI.md`).
- **Frontend:** server-rendered Jinja2 + Tailwind (CDN, no build step), no
  SPA framework, no shared component library beyond two form macros — see
  `DESIGN_SYSTEM.md` for the full breakdown.
- **Background jobs:** none. Everything (AI calls, PDF assembly, Gmail
  reply checking) runs synchronously in the request/response cycle —
  flagged for Phase 6.
- **Multi-tenancy:** every user-owned resource is scoped by `user_id` and
  checked per-route (`_owned_x_or_404` pattern), returning 404 rather than
  403 on mismatch.

Full detail: `ARCHITECTURE.md`. Full schema: `DATABASE.md`. Full decision
history: `DECISIONS.md`.

## What Phase 5 added

1. **Gmail OAuth redesign** — real per-user web OAuth flow replacing the
   old single-shared-token desktop flow. Encrypted per-user token storage.
2. **Gmail reply tracking** — search-based reply detection (no thread to
   track from creation, since AUSVIA never sends the original email),
   full-body extraction, dedup, timeline logging.
3. **AI reply classification + suggestions** — 6 intents + high/medium/low
   confidence, contextual reply drafts threaded in-Gmail. First feature
   with no deterministic fallback (mock mode honestly declines).
4. **Per-category match breakdown** — `MatchResult.category_scores`
   rendered as percentage bars on the job detail page.
5. **AI-route rate limiting** — 30/hour/IP on every AI-calling route.

96 tests passing (up from 70 after Phase 4). Committed as `9bb2ef8`.

## What this checkpoint (post-Phase 5, pre-Phase 6) added

- Brand casing corrected to **AUSVIA** (all caps) everywhere — wordmark,
  page titles, documentation. Text-only change, no layout/component impact.
  See `DECISIONS.md`.
- `DESIGN_SYSTEM.md` rewritten as an honest target-vs-actual comparison
  (brand direction vs. what's implemented), not just a description of
  current state. Identifies concrete gaps (background warmth, shadow usage,
  ink/navy's limited footprint) and a prioritized "what would actually
  change" list — none of it executed yet, by instruction.
- This file, `PROJECT_STATUS.md`, created as a standing "current state"
  reference separate from `PROJECT_AUDIT.md`'s category-by-category detail.
- `ROADMAP.md` refreshed to reflect Phase 5 completion and fold this
  checkpoint's design findings into Phase 6/9 scope.

No functional or visual code changes were made in this checkpoint beyond
the brand casing text change — per explicit instruction to hold on UI
changes and Phase 6 implementation pending review.

## What Phase 6 will implement (planned, not started)

Per `ROADMAP.md`:

- **Company profile pages** — real `Company` data (already exists as a
  model, sourced from job postings) presented on a dedicated page, with
  clearly-labeled AI interpretation layered on top — never invented facts.
- **Document AI extraction** — auto-classify/extract on upload (e.g. detect
  document type, pull key fields), always shown to the user for
  confirmation before being trusted, never silently auto-filled.
- **Background job system** (Celery/RQ or similar) — so AI generation, PDF
  assembly, and Gmail reply checking stop blocking the request/response
  cycle. This is also a prerequisite for any future auto-polling reply
  checker (today's "Check for replies" is manual-only).
- **Live verification pass** — when a non-blocked network is available,
  confirm the Arbeitsagentur adapter's field mapping, the Anthropic
  provider, and the full Gmail stack against real external services rather
  than faked ones.

## Current UI/design status

Functionally complete and internally consistent — the same handful of
Tailwind utility patterns (card, button tiers, status pill, progress bar)
are reused correctly across all ~25 templates with no visual drift. Brand
colors (blue primary, green/amber semantic) already match the target spec.

Three concrete gaps against the full brand direction, none blocking, all
cheap to address whenever a visual pass is scoped:

1. Background is a cool off-white (`slate-50`), not the warm off-white the
   brand direction specifies.
2. No shadows anywhere — fully flat, border-only. Brand direction calls for
   subtle borders *and* shadows.
3. Ink/navy exists only on the landing page hero, not as a foundation
   element anywhere in the authenticated app shell.

There is also no shared component library beyond two form-rendering
macros — every card/button/badge/pill is a repeated (but consistent)
utility-class pattern, not a reusable macro or component. Not urgent today,
but worth addressing before Phase 6 adds more pages, so the pattern doesn't
have to be copy-pasted a third and fourth time.

Full detail on all of the above: `DESIGN_SYSTEM.md`.

## Architectural concerns to consider before Phase 6

- **Synchronous everything.** No background job system yet. Phase 6 adds
  document AI extraction and (potentially) company-page AI synthesis on
  top of an already-synchronous cover letter/email/narrative/reply-
  classification stack — worth deciding whether background jobs land
  *before* or *alongside* Phase 6's new AI features, since adding more
  synchronous AI calls to the request cycle makes the eventual migration
  larger later, not smaller.
- **No component library.** Same reasoning as above but for the frontend:
  Phase 6's new pages (company profiles, document extraction UI) are a
  natural moment to extract the "ready to formalize" patterns from
  `DESIGN_SYSTEM.md` *before* writing three more copies of the same card/
  badge markup, rather than after.
- **Gmail token encryption key is derived from `SECRET_KEY`**, not a
  dedicated secret. Flagged in `SECURITY.md` for Phase 8, not urgent, but
  worth remembering it exists before any real deployment planning starts.
- **Nothing has been verified against live external services** (Anthropic,
  Arbeitsagentur, Gmail). This isn't a code-quality concern, but it is a
  real unknown — Phase 6's "live verification pass" item should be treated
  as genuinely load-bearing, not a formality, since three separate external
  integrations have never actually run end-to-end.

## Test coverage

96 pytest tests passing across auth, profile, documents, admin, job
search/import/dedup/matching, AI provider selection, application generation
(cover letter/email/PDF/approval), Gmail OAuth/reply-tracking/AI-reply
(faked services), token encryption, and rate limiting. No test calls a real
external API (Anthropic, Jobsuche, Gmail).

## Recommended next step

Hold here per instruction. When ready to proceed, the two live options are:
(a) start Phase 6 implementation as scoped in `ROADMAP.md`, or (b) scope a
short, explicit visual-refinement pass against `DESIGN_SYSTEM.md`'s
"what would actually change" list first. Given the architectural concerns
above, doing a small background-job groundwork step before or alongside
Phase 6's new AI-calling features (rather than after) is also worth
explicit consideration rather than defaulting to feature-first.
