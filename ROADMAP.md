# Roadmap — Ausvia

Original build phases (1-4, complete - see `PROJECT_AUDIT.md`), now
continuing under the phase structure below.

## Phase 4.5 — Audit + Brand Integration (this phase)

- [x] `PROJECT_AUDIT.md` - honest working/partial/broken/mocked/missing audit
- [x] Ausvia brand: colors, typography (Inter), logo wordmark, landing page
- [x] Design system pass across existing templates (no functional changes)
- [x] `DECISIONS.md` + documentation set (`PRODUCT.md`, `ARCHITECTURE.md`,
      `DESIGN_SYSTEM.md`, `DATABASE.md`, `AI.md`, `JOB_SOURCES.md`,
      `SECURITY.md`, this file)

## Phase 5 — Product Completion (next)

Priority order, based on the audit's "Missing" and "Needs redesign" lists:

1. **Gmail OAuth redesign** (top priority - currently the single biggest
   gap between "works for one developer locally" and "real multi-user
   feature"). Per-user web OAuth flow (authorization URL → callback route),
   encrypted per-user token storage (new `GmailConnection` model), connect/
   disconnect UI, connection status on the dashboard.
2. **Gmail reply tracking** - associate inbox threads with `Application`
   records, AI-classify reply intent (interview invite / rejection /
   document request / offer / unclear) with a visible confidence + easy
   user correction, never silently overwrite a status the user set manually.
3. **AI reply suggestions** - drafted from the company's reply + application
   context, created as a Gmail draft, never auto-sent (same approval-gate
   pattern as application generation).
4. **Per-category match breakdown UI** - surface the matching engine's
   existing per-category data (skills/language/education/location/timing)
   as the visual breakdown the product spec describes, not just the
   aggregate score + flat strengths/gaps list it shows today. Mostly a
   template/presentation change - the underlying data already exists.
5. **Rate limiting on AI-calling routes** (security gap, cheap to fix).

## Phase 6 — Integration

Connect the pieces built across Phases 1-5 that currently exist but aren't
fully cross-linked: company profile pages (real `Company` data + clearly-
labeled AI interpretation, never invented facts), document AI extraction
(auto-classify/extract on upload, always shown to the user for confirmation
before being trusted), background job system (Celery/RQ or similar) once
real AI calls or larger workloads make synchronous requests too slow.

## Phase 7 — QA

Full workflow test per the product directive's "final quality bar" scenario
(access code → account → profile → search → match → prepare → Gmail draft →
send → reply → AI response → timeline). Expand test coverage into the Phase
5/6 features as they land.

## Phase 8 — Security

Re-run the `SECURITY.md` gap list once Phase 5's Gmail OAuth redesign lands;
add rate limiting; review secrets management for a real deployment target.

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
