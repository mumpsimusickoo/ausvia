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
  structured facts (see `AI.md`). Extended in Phase 5 to inbound Gmail reply
  content - a company's reply is data to classify/respond to, never
  instructions to follow.
- **Gmail OAuth (Phase 5):** real per-user web OAuth flow, replacing the
  single-shared-token desktop-app flow. Tokens are per-user
  (`GmailConnection`, one row per user, unique on `user_id`) and encrypted
  at rest (`app/utils/crypto.py`, Fernet symmetric encryption keyed from
  `SECRET_KEY`) rather than stored as plaintext or in a shared file. The
  OAuth `state` parameter is verified server-side via the session to prevent
  CSRF on the callback. See `DECISIONS.md` for the full reasoning.
- **AI-route rate limiting (Phase 5):** cover letter/email/narrative/
  improvement-tips/reply-classification/reply-suggestion generation are all
  now rate-limited (30/hour/IP) via Flask-Limiter, closing the gap flagged
  after Phase 4.5.

## Known gaps (tracked, not hidden)

1. **Gmail token encryption key is derived from `SECRET_KEY`**, not a
   separate dedicated secret with its own rotation story. Adequate for
   current scale; worth revisiting for a real production deployment (Phase
   10 concern) - see `app/utils/crypto.py`'s docstring.
2. **No accessibility audit yet** - see `DESIGN_SYSTEM.md`.
3. **No secrets-management story beyond `.env`** - fine for local dev, not
   evaluated for a real deployment target yet (Phase 10 concern).
4. **No background job system** - a slow AI or Gmail API call blocks the
   request cycle. Availability concern more than a security one, but worth
   tracking here since it affects how much load the auth/session layer needs
   to tolerate per request.

## What's explicitly out of scope for now

Payment processing (not implemented, per product directive - manual/off-
platform only). Data export / account deletion (privacy features, listed as
missing in `PROJECT_AUDIT.md`, not yet built).
