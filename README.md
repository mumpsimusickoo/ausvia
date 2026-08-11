# Ausbildung Career Agent

An AI-assisted platform to help international applicants find, prepare for, and
track Ausbildung (apprenticeship) applications in Germany. This is being built
in phases; see `PROJECT_STATUS.md` (created after each phase) for what's live.

## Architecture

- **Backend:** Flask (application factory + blueprints), SQLAlchemy ORM, Flask-Migrate (Alembic)
- **Auth:** Flask-Login sessions, Werkzeug password hashing, access-code-gated registration, CSRF via Flask-WTF, rate limiting via Flask-Limiter
- **Database:** SQLite by default (`instance/app.db`), swappable to PostgreSQL via `DATABASE_URL` with zero code changes
- **Storage:** local filesystem behind a `StorageProvider` abstraction (`app/documents/storage.py`) — swappable for cloud object storage later
- **AI:** provider-agnostic abstraction (`app/ai/provider.py`) with a mock implementation (default) and a real Anthropic implementation — set `AI_PROVIDER=anthropic` + `ANTHROPIC_API_KEY` to enable it, otherwise the app runs fully rule-based with no credentials
- **Frontend:** server-rendered Jinja2 + Tailwind (CDN)

The legacy prototype scripts are now wrapped rather than replaced:
`jobsearch.py` by `app/jobs/adapters/arbeitsagentur.py`, `pdfmerge.py`'s
text-to-PDF rendering by `app/applications/pdf_package.py`, and
`gmail_client.py` directly by the optional Gmail-draft action in
`app/applications/routes.py`. `coverletter.py` itself is superseded by
`app/ai/cover_letter.py` (same idea - a real template-based generator - but
built against the actual `CandidateProfile`/`Job` models) and kept only as a
standalone reference.

## Job discovery (Phase 2)

- **`JobSourceAdapter`** interface (`app/jobs/adapters/base.py`): `search()`,
  `get_job()`, `normalize()`, `check_availability()`. The Bundesagentur für
  Arbeit Jobsuche API is the first implementation; sources can be enabled or
  disabled independently by an admin at `/admin/job-sources` with no code
  changes, and one source failing never blocks the others (see `app/jobs/ingest.py`).
- **Manual import** (`/jobs/import`): paste a URL, get a best-effort readable-text
  extraction to review and correct — or paste job text directly if a site blocks
  automated access. Nothing here bypasses logins, paywalls, CAPTCHAs, or bot
  protection; a blocked/unreachable site just falls back to manual entry.
- **Duplicate detection** (`app/jobs/dedupe.py`): the same posting from multiple
  sources is grouped under one canonical `Job` (normalized company/title/
  location/start-date match) rather than shown as duplicates or silently dropped.
- **Known limitation:** the public Jobsuche API returned `403` from this
  project's dev sandbox network (likely bot-protection on datacenter IPs, not
  a broken key) — the adapter's field-name mapping is based on the shape used
  by the previously-working prototype but is unverified against a live
  response from this environment. If search results come back empty on a
  normal network, check the raw response shape and adjust
  `app/jobs/adapters/arbeitsagentur.py`. Manual import doesn't depend on this
  and was verified working end-to-end.

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
  action (draft only, via the existing `gmail_client.py` - can never send or
  read email) follows after the user has reviewed everything.
- **Application CRM**: `Application` status lifecycle (preparing → ready →
  sent → follow_up/interview/offer/... ), auto-logged `ApplicationEvent`
  timeline, and a status/notes/interview-date/follow-up-date update form.

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
multiple profile/job scenarios, AI provider selection/fallback/error handling,
and the full application workflow (cover letter/email generation and
validation, document selection, PDF package assembly including a corrupt-file
regression test, the human-approval gate, and cross-user ownership). No test
calls the real Anthropic API or the real Jobsuche API.

## 6. (Optional) Gmail draft creation

Used by the "Create Gmail draft" action on an approved application (only
appears once an application is ready). Google requires this to come from
your own account - without it, use "I sent this myself" / download the PDF
package and send however you like.

1. Go to https://console.cloud.google.com/ and create a new project.
2. **APIs & Services → Library** → enable "Gmail API".
3. **APIs & Services → OAuth consent screen** → External, add yourself as a test user.
4. **APIs & Services → Credentials → Create Credentials → OAuth client ID** → **Desktop app** → download the JSON.
5. Rename it to `credentials.json` and put it in the project root.

The app only ever requests the `gmail.compose` scope — it can create drafts
but can never send email or read your inbox.

## Notes

- Everything (database, uploaded documents, generated files) stays local on
  your machine under `instance/`, `uploads/`, and `generated/`.
- `uploads/` and `generated/` are per-user-scoped on disk (`uploads/<user_id>/...`)
  and every document route checks ownership server-side — a user can't reach
  another user's document by guessing an ID.
- Uploaded files are validated by both extension and content signature (magic
  bytes), not just filename, and capped at 15 MB.
