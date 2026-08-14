# AUSVIA

**Your path to Ausbildung.**

A private, invitation-only AI-assisted platform that helps people find and
apply for Ausbildung (apprenticeship) opportunities in Germany - discover,
match, prepare, apply, and track, with AI drafting and the user always in
control of what actually gets sent. This is being built in phases; see
`PROJECT_AUDIT.md` for an honest account of what's implemented, mocked, or
missing, and `ROADMAP.md` for what's next.

## Architecture

- **Backend:** Flask (application factory + blueprints), SQLAlchemy ORM, Flask-Migrate (Alembic)
- **Auth:** Flask-Login sessions, Werkzeug password hashing, access-code-gated registration, CSRF via Flask-WTF, rate limiting via Flask-Limiter
- **Database:** SQLite by default (`instance/app.db`), swappable to PostgreSQL via `DATABASE_URL` with zero code changes
- **Storage:** `StorageProvider` abstraction (`app/documents/storage.py`) — local filesystem by default, or S3-compatible object storage in production (`STORAGE_PROVIDER=s3`, see `DEPLOYMENT.md`)
- **AI:** provider-agnostic abstraction (`app/ai/provider.py`) with a mock implementation (default) plus real Anthropic and Gemini implementations — set `AI_PROVIDER=anthropic` + `ANTHROPIC_API_KEY`, or `AI_PROVIDER=gemini` + `GEMINI_API_KEY`, to enable one; otherwise the app runs fully rule-based with no credentials
- **Frontend:** server-rendered Jinja2 + Tailwind (CDN)

The legacy prototype scripts are now wrapped rather than replaced:
`jobsearch.py` by `app/jobs/adapters/arbeitsagentur.py` and `pdfmerge.py`'s
text-to-PDF rendering by `app/applications/pdf_package.py`. `gmail_client.py`
has been fully superseded by `app/integrations/gmail_oauth.py` +
`gmail_drafts.py` (real per-user OAuth, not a single shared token - see
`DECISIONS.md`) and is kept only as a standalone reference. `coverletter.py`
itself is superseded by
`app/ai/cover_letter.py` (same idea - a real template-based generator - but
built against the actual `CandidateProfile`/`Job` models) and kept only as a
standalone reference.

## Job discovery (Phase 2, expanded in the job-source integration pass)

- **`JobSourceAdapter`** interface (`app/jobs/adapters/base.py`): `search()`,
  `get_job()`, `normalize()`, `check_availability()`. Three real providers
  implement it - Bundesagentur für Arbeit (Jobsuche), Adzuna, and Jooble -
  normalizing into the same `NormalizedJob`/`Job` shape regardless of source.
  Sources can be enabled or disabled independently by an admin at
  `/admin/job-sources` with no code changes, and one source failing never
  blocks the others (see `app/jobs/ingest.py`). Adzuna/Jooble are only added
  to the search rotation once their credentials are configured (see
  `.env.example`) - absent otherwise, not an error.
- **Manual import** (`/jobs/import`): paste a URL, get a best-effort readable-text
  extraction to review and correct — or paste job text directly if a site blocks
  automated access. Nothing here bypasses logins, paywalls, CAPTCHAs, or bot
  protection; a blocked/unreachable site just falls back to manual entry.
- **Duplicate detection** (`app/jobs/dedupe.py`): the same posting from multiple
  sources is grouped under one canonical `Job` - matched either by an identical
  canonical/original URL across sources, or by normalized company/title/
  location/start-date - rather than shown as duplicates or silently dropped.
- **Per-query caching** (`app/jobs/ingest.py`, `ProviderQueryCache`): a repeated
  identical search doesn't re-hit a metered provider (Adzuna/Jooble) within a
  15-minute window, since the search route calls providers synchronously on
  every request - protects daily/monthly API quotas without needing a
  scheduler or background rewrite.
- **Known limitations - see `JOB_SOURCES.md` for full detail:**
  - Bundesagentur's search endpoint (bumped v4→v6 this pass) returned real
    data from this project's dev network at time of writing, after two
    separate real bugs were found and fixed (a stale response-field mapping,
    and a missing base64-encoding step for job detail lookups) - but the
    same endpoint was confirmed *blocked* (403) from multiple networks in
    earlier sessions, so this is not treated as durably fixed everywhere;
    re-verify from your own production environment before relying on it.
  - Adzuna's free API access is a **14-day trial only** per its Terms of
    Service, not indefinite free use - see `JOB_SOURCES.md` before relying
    on it in production past the trial window.
  - Neither Adzuna nor Jooble guarantee apprenticeship-specific results for
    German "Ausbildung"-style keyword searches the way Arbeitsagentur's
    `angebotsart=4` filter does - see `JOB_SOURCES.md` for the live-tested
    finding on real result quality.

## AI matching (Phase 3)

- **The match score is never an AI guess.** `app/ai/matching.py` computes it
  deterministically in plain Python from the candidate profile vs. the job's
  actual listed skills/language requirements/education/location/start date —
  the same score, strengths, and gaps display identically whether or not any
  AI provider is configured. This is intentional per the product's core rule:
  AI explains and suggests, it never invents or decides the facts.
- **AI provider abstraction** (`app/ai/provider.py` + `app/ai/providers/`):
  `MockAIProvider` (default, zero cost/credentials, returns an honest "AI
  narrative not available" message rather than faking one) and
  `AnthropicProvider` (real, only active when `AI_PROVIDER=anthropic` and
  `ANTHROPIC_API_KEY` are set). Optional AI-written narrative explanations and
  "how to improve your fit" tips are generated only from the already-computed
  structured match data (`app/ai/prompts/narrative.py`) — never from raw
  scraped job text — which also keeps prompt-injection surface minimal.
- **Caching + cost tracking:** match results are cached per (user, job) and
  only recomputed when the candidate profile changes since (`JobMatch` model);
  AI narrative/tips are generated once and cached alongside it. Every real
  (non-mock) AI call's token usage is logged to `AIUsage` and visible at
  `/admin/ai-usage` — mock calls are never logged, since they cost nothing.

## Application generation (Phase 4)

- **Cover letter (Anschreiben) generation** (`app/ai/cover_letter.py`): AI path
  (personalized, grounded only in `app/ai/facts.py`'s fact block - never raw
  job HTML) when a real provider is configured, or a genuinely usable
  template-based German business-letter generator otherwise - not a stub,
  the same dual-path philosophy as Phase 3's matching engine. A second AI
  validation pass checks the letter against the source facts and
  self-corrects (spec: never trust one AI pass); in template/mock mode a
  deterministic sanity check confirms the job title/company/candidate name
  actually appear in the output.
- **Application email generation** (`app/ai/email_gen.py`): same AI/template
  dual path, short and distinct from the cover letter.
- **Salutation logic** (`app/ai/salutation.py`): uses a named contact only
  when the source data already encodes gender (a stored "Frau"/"Herr"
  prefix) - never guesses from a first name; falls back to the standard
  neutral "Sehr geehrte Damen und Herren" otherwise.
- **PDF package assembly** (`app/applications/pdf_package.py`): cover letter
  first, then the user's selected documents (PDFs and JPG/PNG, auto-converted
  to a PDF page) in spec-suggested order (CV → diplomas/certs → other).
  Original uploaded files are never modified. A corrupted/unparseable
  document fails the build with a clear, specific error rather than a 500 -
  the upload step's magic-byte check only verifies a file *starts with* a
  valid signature, not full structural validity, so this failure mode is
  real and was caught by live testing, not just unit tests.
- **Human approval is mandatory** (spec section 47): nothing is ever sent
  automatically. "Approve application" is the one action that builds the
  final PDF; a separate explicit "mark as sent" or optional Gmail-draft
  action (draft only, can never send or read email) follows after the user
  has reviewed everything.
- **Application CRM**: `Application` status lifecycle (preparing → ready →
  sent → follow_up/interview/offer/... ), auto-logged `ApplicationEvent`
  timeline, and a status/notes/interview-date/follow-up-date update form.

## Gmail integration + reply tracking (Phase 5)

- **Per-user Gmail OAuth** (`app/integrations/gmail_oauth.py`): a real
  authorization-code web flow, not the earlier single-machine desktop-app
  flow - each user connects their own account at `/integrations/gmail`,
  tokens are stored per-user and encrypted at rest (`app/utils/crypto.py`).
  See `DECISIONS.md` for why this replaced the original prototype's
  shared-token approach.
- **Reply detection** (`app/integrations/gmail_reply_tracking.py`): a manual
  "Check for replies" action searches the connected inbox for messages from
  an application's contact email. AUSVIA never sends the original
  application email itself, so there's no thread to track from creation -
  this is the best available detection approach without controlling the
  send step (see `DECISIONS.md`).
- **AI reply classification + suggestions** (`app/ai/reply_ai.py`): classifies
  a detected reply's intent (interview invitation / rejection / document
  request / offer / acknowledgement / unclear) with a plain high/medium/low
  confidence - never a fake precise percentage - and can draft a contextual
  reply grounded in your profile and the company's actual message. Reply
  drafts thread correctly in Gmail (`In-Reply-To`/`References` headers +
  `threadId`). Mock mode (no AI provider configured) is honest about not
  being able to classify or draft contextual replies, rather than guessing.
- **Per-category match breakdown**: the job detail page now shows a
  percentage bar per category (skills/language/education/location/start
  date) alongside the overall score - same underlying deterministic data
  from Phase 3, just broken out visually.
- **Known limitation:** none of the Gmail-related code above has been
  exercised against real Google infrastructure in this environment (no
  `credentials.json` configured) - see `PROJECT_AUDIT.md`.

## 1. Install

```powershell
cd ausbildung-finder
python -m venv venv        # already present in this repo
venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Configure environment

```powershell
copy .env.example .env
```

Edit `.env` if needed — every value has a safe local-dev default. `SECRET_KEY`
must be set explicitly in production (there's no insecure fallback for that
config).

## 3. Set up the database

```powershell
$env:FLASK_APP = "app.py"
flask db upgrade      # creates instance/app.db and applies all migrations
flask seed            # creates a first admin account + invitation codes for local testing
```

`flask seed` prints the generated admin email/password and two invitation
codes (one `admin`, one `trial`) to the console — nowhere else. Change the
admin password after your first login.

## 4. Run it

```powershell
python app.py
```

Open http://127.0.0.1:5050. Use the printed access code to register, or log
in directly as the seeded admin.

## 5. Run tests

```powershell
pytest
```

Covers auth/access-code flows, profile CRUD and cross-user ownership checks,
document upload validation (content-sniffing, not just extension) and
cross-user access, admin authorization boundaries, duplicate-detection
heuristics, job search/import/save flows, deterministic match scoring across
multiple profile/job scenarios (including the per-category breakdown), AI
provider selection/fallback/error handling, the full application workflow
(cover letter/email generation and validation, document selection, PDF
package assembly including a corrupt-file regression test, the human-approval
gate, and cross-user ownership), token encryption (roundtrip + fails-closed
on tampering), the per-user Gmail OAuth connect/disconnect flow, reply
detection and body extraction (deduped, ownership-scoped), AI reply
classification/suggestion (including honest mock-mode behavior and
malformed-response fallback), and AI-route rate limiting (verified with a
dedicated fixture that forces the limiter on). No test calls the real
Anthropic API, the real Jobsuche API, or the real Gmail API — Gmail is
exercised against a faked service object, never live Google infrastructure.

## 6. (Optional) Gmail integration

Powers the "Gmail replies" section on an application's detail page: creating
the initial application draft, checking for and reading replies, and
creating in-thread reply drafts. Google requires this to come from each
user's own account — without it, use "I sent this myself" / download the PDF
package and send however you like, and reply manually in Gmail.

1. Go to https://console.cloud.google.com/ and create a new project.
2. **APIs & Services → Library** → enable "Gmail API".
3. **APIs & Services → OAuth consent screen** → External, add yourself as a test user.
4. **APIs & Services → Credentials → Create Credentials → OAuth client ID** → **Desktop app** → download the JSON.
5. Locally: rename it to `credentials.json` and put it in the project root.
   On a host where you can only set environment variables (Railway, Render,
   etc.): paste the full JSON file content as the `GOOGLE_CREDENTIALS_JSON`
   env var instead — see `DEPLOYMENT.md`. Either works; `is_configured()`
   accepts whichever is present, and the env var wins if both are.
6. Start the app, go to **Gmail** in the nav (`/integrations/gmail`), and
   click **Connect Gmail**. This is a real per-user OAuth flow — each user
   who wants Gmail features connects their own account; nothing is shared
   between users. Google's loopback exception for "Desktop app"-type clients
   accepts the `http://127.0.0.1:<port>/...` redirect this app uses without
   any redirect URI pre-registration, as long as it's run locally.

The app requests two scopes: `gmail.readonly` (to detect and read replies)
and `gmail.compose` (to create drafts). It can never send email on your
behalf, and only ever reads messages when you click "Check for replies" on
a specific application. Tokens are stored encrypted per-user
(`GmailConnection` — see `DATABASE.md`, `SECURITY.md`).

## Notes

- Everything (database, uploaded documents, generated files) stays local on
  your machine under `instance/`, `uploads/`, and `generated/`.
- `uploads/` and `generated/` are per-user-scoped on disk (`uploads/<user_id>/...`)
  and every document route checks ownership server-side — a user can't reach
  another user's document by guessing an ID.
- Uploaded files are validated by both extension and content signature (magic
  bytes), not just filename, and capped at 15 MB.
