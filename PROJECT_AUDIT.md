# Project Audit — Ausvia (formerly "Ausbildung Career Agent")

Audit date: 2026-08-11, after Phases 1–4. This is an honest snapshot, not
aspirational. Nothing below is claimed as done unless it's been exercised
(unit-tested and/or live-smoke-tested against the running app).

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
  job data every time.
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
- **Gmail draft creation** — real integration code (`gmail_client.py`,
  pre-existing) wired into the application-approval flow. See "Needs
  redesign" — the OAuth architecture underneath it does not fit a multi-user
  web app.

## Partially implemented

- **Gmail integration** — draft creation is wired and uses real Gmail API
  calls, but the OAuth flow it depends on (`gmail_client.get_gmail_service`)
  is a single-machine "desktop app" flow: `InstalledAppFlow.run_local_server()`
  opens a browser and blocks waiting for a redirect on the same machine the
  Flask process runs on, and the resulting token is a single shared
  `token.json` file at the project root — not per-user, not database-backed.
  This works only when one person runs the app on their own laptop. It does
  **not** work for more than one user, or for any real deployment. This needs
  a real per-user OAuth web flow (authorization URL → callback route →
  encrypted per-user token storage) before Gmail can be considered a genuine
  multi-user feature. Flagged as the top priority for Phase 5/6.
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

## Broken

- Nothing currently fails in the app's own test suite or live smoke tests.
  The one architectural item that would break in a real multi-user
  deployment is the Gmail OAuth flow above — listed there rather than here
  since it "works" for the single-developer local case it was written for.

## Mocked (and clearly labeled as such — never presented as real)

- `MockAIProvider` — the default when no `ANTHROPIC_API_KEY` is configured.
  Returns an honest "AI narrative not available, here's why" message rather
  than fabricated AI-sounding text. No fake job data, fake company data, or
  fake match scores exist anywhere in the app — every job comes from a real
  source (Arbeitsagentur API or the user's own manual import), and match
  scores are always computed from real profile/job data, never invented.

## Missing (not started)

- Gmail reply tracking / thread-to-application association
- AI email-reply classification and AI-drafted reply suggestions
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
- Per-category match breakdown UI (education/skills/language/location as
  separate percentage bars) — current UI shows one overall score + a
  strengths/gaps list, which is the same underlying data but not broken out
  visually per category
- Saved searches / automatic job radar
- Application analytics/statistics
- Account data export / account deletion (privacy)
- Centralized reusable component library beyond the two current Jinja macros
  (`render_field`, `render_checkbox`) — styling is currently consistent but
  applied ad hoc per template, not via shared components

## Needs redesign

- **Visual identity** — this is what Phase 4.5 addresses: rebrand to Ausvia
  (name, color system, typography, logo wordmark, landing page copy).
- **Gmail OAuth architecture** — see "Partially implemented" above.
- **Match breakdown UI** — add the per-category percentage view.

## Needs security review

- **Gmail token storage is the most serious open item.** A single
  `token.json` on disk, shared across all users, is unacceptable for a
  multi-user app — whoever's browser most recently completed the OAuth flow
  effectively "owns" Gmail access for the whole app. Must become per-user,
  database-backed (or at minimum per-user file), and the refresh/access
  tokens should not be logged or exposed. No user-facing Gmail feature
  should ship broadly until this is fixed.
- **Rate limiting** currently covers only auth endpoints. AI-calling routes
  (cover letter/email/narrative generation) have no per-user rate limit,
  so a compromised or careless account could run up real API costs once a
  real provider is configured. Worth adding before enabling a real API key
  in anything beyond a personal/trusted deployment.
- File upload validation, CSRF, session cookie flags, and cross-user
  ownership checks were reviewed in Phases 1–4 and are solid.

## Needs testing

- `AnthropicProvider`'s live behavior (by design — no test should burn real
  API credits or require a key in CI; this is an accepted coverage gap, not
  an oversight, but should be manually verified once a key is available).
- Gmail draft creation route has no test coverage (no test mocks
  `gmail_client` and exercises `create_gmail_draft`).

## Technical debt

- `coverletter.py` (root-level legacy script) is now fully superseded by
  `app/ai/cover_letter.py` and is effectively dead code, kept only as a
  standalone reference per the original phase decision. Worth removing once
  confirmed nobody depends on it standalone.
- All "long-running" work (AI generation, PDF assembly) currently runs
  synchronously inside the request/response cycle. Fine for template-mode
  and fast API calls; will need a background job system once real AI calls
  or larger workloads make requests slow (spec explicitly anticipates this
  in Phase 6+).
- SQLite in dev; Postgres migration path exists (`DATABASE_URL` env var,
  zero code changes needed) but has never been exercised against a real
  Postgres instance.

## Phase status

| Phase | Status |
|---|---|
| 1 — Foundation | Complete, tested, solid |
| 2 — Job Discovery | Complete; Arbeitsagentur adapter unverified live (sandbox network block, documented); manual import fully verified |
| 3 — AI Matching | Complete; deterministic engine solid; AI narrative path unverified live (no API key configured) |
| 4 — Application Generation | Complete and tested; Gmail draft wired but built on a single-user OAuth architecture that needs redesign before real multi-user use |
