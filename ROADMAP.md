# Roadmap — Ausvia

Original build phases (1-4, complete - see `PROJECT_AUDIT.md`), now
continuing under the phase structure below.

## Phase 4.5 — Audit + Brand Integration (complete)

- [x] `PROJECT_AUDIT.md` - honest working/partial/broken/mocked/missing audit
- [x] Ausvia brand: colors, typography (Inter), logo wordmark, landing page
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
      thread to track from creation, since Ausvia never sends the original
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

## Phase 6 — Integration

Connect the pieces built across Phases 1-5 that currently exist but aren't
fully cross-linked: company profile pages (real `Company` data + clearly-
labeled AI interpretation, never invented facts), document AI extraction
(auto-classify/extract on upload, always shown to the user for confirmation
before being trusted), background job system (Celery/RQ or similar) so AI
generation, PDF assembly, and Gmail reply checking stop blocking the
request/response cycle, and - when a real network allows it - live
verification of the Arbeitsagentur adapter, the Anthropic provider, and the
whole Gmail stack against real external services.

## Phase 7 — QA

Full workflow test per the product directive's "final quality bar" scenario
(access code → account → profile → search → match → prepare → Gmail draft →
send → reply → AI response → timeline). Expand test coverage into the Phase
5/6 features as they land.

## Phase 8 — Security

Re-run the `SECURITY.md` gap list (Gmail OAuth redesign and AI-route rate
limiting landed in Phase 5); review secrets management, including moving the
Gmail token-encryption key off `SECRET_KEY` onto its own dedicated secret,
for a real deployment target.

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
