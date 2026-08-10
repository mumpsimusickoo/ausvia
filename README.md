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

The legacy prototype scripts (`coverletter.py`, `pdfmerge.py`, `gmail_client.py`)
still work standalone and contain real, working integrations (Gmail draft
creation, PDF merging). They'll be wrapped into the AI-generation architecture
in a later phase rather than rewritten from scratch. `jobsearch.py` is now
wrapped by `app/jobs/adapters/arbeitsagentur.py` as the first `JobSourceAdapter`.

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
multiple profile/job scenarios, and AI provider selection/fallback/error
handling (a fake provider is injected in tests — no test calls the real
Anthropic API or the real Jobsuche API).

## 6. (Optional) Gmail draft creation

Used by the existing `gmail_client.py` module (wired into the UI in a later
phase). Google requires this to come from your own account.

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
