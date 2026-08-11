# Security — Ausvia

This is a running account of what's implemented and what's flagged, not a
one-time checklist. See `PROJECT_AUDIT.md` for the fuller "needs security
review" list with reasoning; this file is the security-specific summary.

## Implemented

- **Auth:** Werkzeug password hashing (never plaintext), Flask-Login
  sessions, rate limiting on login/register/password-reset endpoints,
  secure cookie flags (`HttpOnly`, `SameSite=Lax`, `Secure` in production
  config).
- **CSRF:** Flask-WTF CSRF protection app-wide, on every state-changing
  route (both WTForms-rendered and manual forms include the token).
- **Authorization / data isolation:** every user-owned resource
  (documents, applications, matches, profile sub-entities) is scoped by
  `user_id` with an explicit ownership check in the route layer, returning
  404 (not 403) on mismatch so a guessed ID doesn't even confirm the
  resource exists. Verified by tests across every phase (cross-user access
  attempts return 404).
- **File uploads:** extension allowlist + magic-byte content verification
  (rejects a renamed non-PDF/image), 15MB cap, UUID-named storage (no
  path traversal via filename), originals never modified by any downstream
  processing (PDF merge reads, never writes back to uploaded files).
- **Access codes:** cryptographically random generation (`secrets`-backed),
  never logged, admin-only creation/revocation, expiry + max-use
  enforcement.
- **Logging:** `SystemLog` deliberately takes only a short message string
  (no arbitrary object dumping) - structurally prevents accidentally
  logging a password, access code, or document content. AI token-usage
  logging (`AIUsage`) stores counts only, never prompt/response content.
- **AI provider errors:** never surfaced with raw exception detail to the
  end user; caught and shown as a plain, actionable message. API keys are
  server-side config only, never sent to the frontend.
- **Prompt injection defense:** external job/company content is treated as
  untrusted data in every AI system prompt that touches it; narrative/tips
  generation doesn't even receive raw scraped text, only already-normalized
  structured facts (see `AI.md`).

## Known gaps (tracked, not hidden)

1. **Gmail OAuth token storage is the most serious open item.** A single
   shared `token.json` file, not per-user, not encrypted, not database-
   backed. Unacceptable for multi-user use as-is. See `PROJECT_AUDIT.md` and
   the relevant `DECISIONS.md` entry - fix is scoped for Phase 5/6 alongside
   the rest of the Gmail feature work, not deferred indefinitely.
2. **No rate limiting on AI-calling routes** (cover letter/email/narrative
   generation) - only auth endpoints are currently limited. Low risk today
   (mock provider has no cost), but must be added before a real AI provider
   key is used in anything beyond a trusted personal deployment.
3. **No accessibility audit yet** - see `DESIGN_SYSTEM.md`.
4. **No secrets-management story beyond `.env`** - fine for local dev, not
   evaluated for a real deployment target yet (Phase 10 concern).

## What's explicitly out of scope for now

Payment processing (not implemented, per product directive - manual/off-
platform only). Data export / account deletion (privacy features, listed as
missing in `PROJECT_AUDIT.md`, not yet built).
