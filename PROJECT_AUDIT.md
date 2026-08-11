# Project Audit — AUSVIA

Audit date: 2026-08-11, after Phase 5 (originally written after Phase 4, now
updated). This is an honest snapshot, not aspirational. Nothing below is
claimed as done unless it's been exercised (unit-tested and/or
live-smoke-tested against the running app).

## Already working (real, exercised)

- **Auth & access codes** — registration gated by invitation code (trial/
  standard/premium/admin types, max-uses, expiry, admin revocation), login/
  logout, Werkzeug password hashing, CSRF everywhere, rate limiting on auth
  endpoints. Password reset works but has no email transport configured (see
  "Needs redesign").
- **Candidate profile** — personal info, education, experience, skills,
  languages, preferences. Full CRUD, ownership-enforced.
- **Document library** — real local-filesystem storage, magic-byte content
  validation (not just extension), 15MB cap, primary-CV/diploma/cert flags,
  strict per-user ownership (cross-user access returns 404).
- **Job discovery** — `JobSourceAdapter` interface; `ArbeitsagenturAdapter`
  wraps a real API client (`jobsearch.py`); manual URL import does a real
  permitted GET + readable-text extraction (verified live against a real
  page), with manual-paste fallback on any failure. Duplicate detection
  (company/title/location/start-date normalization) is real and tested.
- **AI matching engine** (`app/ai/matching.py`) — fully real, deterministic,
  zero AI dependency. Score/strengths/gaps computed from actual profile vs.
  job data every time, now including a **per-category breakdown**
  (skills/language/education/location/start-date, each shown as its own
  percentage bar on the job detail page - added Phase 5).
- **AI provider abstraction** — real `MockAIProvider` (honest, labeled) and
  real `AnthropicProvider` (real SDK integration code). See "Needs testing"
  below — the Anthropic path has never been exercised against a live API key
  in this environment.
- **Cover letter & email generation** — real template-based generators
  (used whenever no AI provider is configured — not stubs, genuinely usable
  German business letters/emails built from actual profile+job data) plus
  real AI-generation code paths. Second-pass validation: deterministic
  sanity check (template mode) or AI self-correction (AI mode).
- **PDF package assembly** — real, merges generated cover letter + selected
  documents (PDF/JPG/PNG) in spec order. A corrupt-file edge case was found
  via live testing and fixed (graceful error, not a 500) with a regression test.
- **Application CRM** — status lifecycle, auto-logged timeline, notes/
  interview/follow-up date fields, mandatory human-approval gate before a
  package is built, separate explicit "mark sent" action.
- **Admin dashboard** — users (activate/deactivate), invitation codes,
  job-source enable/disable + diagnostics, AI usage/token log.
- **Gmail OAuth (per-user, redesigned in Phase 5)** — real authorization-code
  web flow (`app/integrations/gmail_oauth.py`): connect/disconnect UI,
  encrypted per-user token storage (`GmailConnection`, Fernet-encrypted via
  `app/utils/crypto.py`, key derived from `SECRET_KEY`), automatic token
  refresh. Replaces the old single-shared-`token.json` desktop-app flow -
  see `DECISIONS.md`. Draft creation now goes through each user's own
  connection. **Never exercised against a live Google OAuth consent screen**
  in this environment (no `credentials.json` configured) - the code follows
  the documented `google-auth-oauthlib` API precisely, but its live behavior
  is unverified, same honesty standard applied to the Anthropic provider and
  the Arbeitsagentur adapter.
- **Gmail reply tracking** (`app/integrations/gmail_reply_tracking.py`) —
  real Gmail API search/read code (`gmail.readonly` scope), extracts the
  full plain-text body (not just the short snippet), deduplicates against
  already-seen messages, logs a timeline event. Manually triggered ("Check
  for replies" button) - no background polling yet. Unverified live for the
  same credentials.json reason as above; unit-tested against a fake Gmail
  service object that mimics the real API's response shape.
- **AI reply classification + suggested replies**
  (`app/ai/reply_ai.py`) — real dual-path code (mock: honestly says
  AI isn't configured, no fake classification; real: AI classifies
  intent + confidence and can draft a contextual reply), reply drafts are
  created in-thread (`In-Reply-To`/`References` headers + Gmail `threadId`)
  via `app/integrations/gmail_drafts.py`. Same untrusted-external-content
  framing as cover letter generation - the company's message is data to
  respond to, never instructions to follow.
- **AI-route rate limiting** — cover letter/email/narrative/reply-suggestion
  generation are now rate-limited (30/hour/IP), closing the gap flagged
  after Phase 4.5. Verified with a dedicated test that forces the limiter on
  and confirms a 429 actually fires.

## Partially implemented

- **AI-generated content** — the architecture is real and dual-path (never
  mocked-and-labeled-as-real), but the Anthropic path has literally never
  run against a live API key in this environment (none was configured). The
  code is real; its live behavior is unverified.
- **Arbeitsagentur job data** — the adapter's field-name mapping is a
  best-effort port of the previously-working prototype's field names,
  unverified against a live response, because this project's sandbox network
  gets HTTP 403 from that API (likely bot-protection on datacenter IPs, not
  a broken key — confirmed general internet connectivity works). Documented
  in README since Phase 2.
- **Gmail (OAuth + reply tracking + AI replies)** — see above: the code is
  real and unit-tested against faked API responses, but nothing Gmail-related
  has been exercised against real Google infrastructure in this environment.

## Broken

- Nothing currently fails in the app's own test suite or live smoke tests.

## Mocked (and clearly labeled as such — never presented as real)

- `MockAIProvider` — the default when no `ANTHROPIC_API_KEY` is configured.
  Returns an honest "AI narrative not available, here's why" message rather
  than fabricated AI-sounding text. Same honesty pattern extended in Phase 5
  to reply classification and reply suggestions - mock mode never guesses an
  intent or fakes a contextual reply. No fake job data, fake company data,
  or fake match scores exist anywhere in the app.

## Missing (not started)

- Interview preparation (question generation, mock interview)
- Persistent AI Assistant / chat interface
- In-app notification system
- Document AI extraction/classification (documents are currently typed
  manually by the user on upload; no OCR/text-extraction auto-fill)
- Dedicated company profile/analysis page (a `Company` record exists with
  real fields sourced from job postings, but there's no page presenting it,
  and no AI synthesis of "why this company might fit you")
- Structured first-time onboarding wizard (users currently just land on
  their profile page and fill it in organically)
- Background job system - reply checking, AI generation, and PDF assembly
  are all still synchronous in the request cycle
- Saved searches / automatic job radar
- Application analytics/statistics
- Account data export / account deletion (privacy)
- Centralized reusable component library beyond the two current Jinja macros
  (`render_field`, `render_checkbox`) — styling is currently consistent but
  applied ad hoc per template, not via shared components

## Needs redesign

- Nothing currently flagged. (Visual identity was addressed in Phase 4.5;
  Gmail OAuth architecture was addressed in Phase 5; per-category match
  breakdown was addressed in Phase 5.)

## Needs security review

- **Gmail token encryption uses a key derived from `SECRET_KEY`**, not a
  separate dedicated secret. Adequate for this app's current scale and
  threat model (protects against casual DB file exposure), but a real
  production deployment should consider a dedicated encryption key with its
  own rotation story, independent of the session-signing key. Noted in
  `app/utils/crypto.py`'s docstring.
- **No background job system** means a slow AI provider or Gmail API call
  blocks the request/response cycle - not a security issue per se, but a
  potential availability one worth addressing before higher traffic.
- File upload validation, CSRF, session cookie flags, cross-user ownership
  checks, and AI-route rate limiting were reviewed and are solid.

## Needs testing

- `AnthropicProvider`'s live behavior (by design — no test should burn real
  API credits or require a key in CI; this is an accepted coverage gap, not
  an oversight, but should be manually verified once a key is available).
- The entire Gmail OAuth/reply-tracking/reply-suggestion stack's live
  behavior against real Google infrastructure (same reasoning as above -
  unit tests use a faked Gmail API service object that mirrors the
  documented response shape, but nothing has hit the real API).

## Technical debt

- `coverletter.py` and `gmail_client.py` (root-level legacy scripts) are now
  fully superseded by `app/ai/cover_letter.py` and
  `app/integrations/gmail_oauth.py`/`gmail_drafts.py` respectively, and are
  effectively dead code, kept only as standalone reference per the original
  phase decisions. Worth removing once confirmed nobody depends on them
  standalone.
- All "long-running" work (AI generation, PDF assembly, Gmail reply
  checking) currently runs synchronously inside the request/response cycle.
  Fine at today's scale; will need a background job system as usage grows.
- SQLite in dev; Postgres migration path exists (`DATABASE_URL` env var,
  zero code changes needed) but has never been exercised against a real
  Postgres instance.

## Phase status

| Phase | Status |
|---|---|
| 1 — Foundation | Complete, tested, solid |
| 2 — Job Discovery | Complete; Arbeitsagentur adapter unverified live (sandbox network block, documented); manual import fully verified |
| 3 — AI Matching | Complete; deterministic engine solid; AI narrative path unverified live (no API key configured) |
| 4 — Application Generation | Complete and tested |
| 4.5 — Audit + Brand | Complete: AUSVIA rebrand, full documentation set |
| 5 — Product Completion | Complete: per-user Gmail OAuth, reply tracking, AI reply suggestions, per-category match UI, AI-route rate limiting. Gmail stack unverified against real Google infrastructure (no credentials.json in this environment) |
