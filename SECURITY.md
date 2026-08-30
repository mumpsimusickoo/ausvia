# Security — AUSVIA

This is a running account of what's implemented and what's flagged, not a
one-time checklist. See `PROJECT_AUDIT.md` for the fuller "needs security
review" list with reasoning; this file is the security-specific summary.

## Implemented

- **Auth:** Werkzeug password hashing (never plaintext), Flask-Login
  sessions, rate limiting on login/register/password-reset endpoints,
  secure cookie flags (`HttpOnly`, `SameSite=Lax`, `Secure` in production
  config).
- **Password reset never exposes the reset token/link in an HTTP
  response** (fixed 2026-08-30, was a real production vulnerability - see
  `DECISIONS.md`'s "Urgent security fix" entry): the request-reset route
  used to render the real, working reset link directly on the page,
  gated behind a config key (`MAIL_PROVIDER_CONFIGURED`) that was never
  actually defined anywhere, so that gate was always open - anyone who
  submitted a registered user's email got a valid reset link handed to
  their own browser, no access to the victim's inbox required. Now
  returns one identical generic message regardless of whether the
  account exists (closing the email-enumeration side channel too), and
  never renders the token anywhere under any config state. **Real email
  delivery added the same day** (`app/mail.py`, via Resend): the token
  now reaches the user in an actual email, never in the HTTP response -
  the reset flow is safe and usable again, not just safe. Graceful
  degradation mirrors every other optional provider in this app: an
  unconfigured or failing mail provider logs internally and shows the
  same generic message, never falls back toward exposing the link.
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

1. **Gmail token encryption key can be a dedicated secret (`TOKEN_ENCRYPTION_KEY`),
   but still falls back to `SECRET_KEY`-derivation if that env var is
   unset** (Phase 8, D6a). No production requirement to set it yet, and no
   forced-reconnect migration exists if it's introduced later on a live
   deployment - see `app/utils/crypto.py`'s docstring for the fallback
   details. Requiring it in production (rather than leaving it optional) is
   still a Phase 8/10 revisit (D6b), deliberately not done yet.
2. **No accessibility audit yet** - see `DESIGN_SYSTEM.md`.
3. **No secrets-management story beyond `.env`** - fine for local dev, not
   evaluated for a real deployment target yet (Phase 10 concern).
4. **No background job system** - a slow AI or Gmail API call blocks the
   request cycle. Availability concern more than a security one, but worth
   tracking here since it affects how much load the auth/session layer needs
   to tolerate per request.
5. ~~No real email delivery mechanism exists anywhere in this app~~ -
   **resolved 2026-08-30**: `app/mail.py` sends real password reset
   emails via Resend when `RESEND_API_KEY` is configured (see the
   "Password reset never exposes..." entry above). Still the only place
   this app sends real email - nothing else (application confirmations,
   digest notifications, etc.) goes through it.

## What's explicitly out of scope for now

Payment processing (not implemented, per product directive - manual/off-
platform only). Data export / account deletion (privacy features, listed as
missing in `PROJECT_AUDIT.md`, not yet built).
