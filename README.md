# Ausbildung Career Agent

An AI-assisted platform to help international applicants find, prepare for, and
track Ausbildung (apprenticeship) applications in Germany. This is being built
in phases; see `PROJECT_STATUS.md` (created after each phase) for what's live.

## Architecture

- **Backend:** Flask (application factory + blueprints), SQLAlchemy ORM, Flask-Migrate (Alembic)
- **Auth:** Flask-Login sessions, Werkzeug password hashing, access-code-gated registration, CSRF via Flask-WTF, rate limiting via Flask-Limiter
- **Database:** SQLite by default (`instance/app.db`), swappable to PostgreSQL via `DATABASE_URL` with zero code changes
- **Storage:** local filesystem behind a `StorageProvider` abstraction (`app/documents/storage.py`) — swappable for cloud object storage later
- **AI:** provider-agnostic abstraction (built out from Phase 3 onward) with a mock implementation so the app works with no API key configured
- **Frontend:** server-rendered Jinja2 + Tailwind (CDN)

The legacy prototype scripts (`jobsearch.py`, `coverletter.py`, `pdfmerge.py`,
`gmail_client.py`) still work standalone and contain real, working integrations
(Bundesagentur für Arbeit Jobsuche API, Gmail draft creation, PDF merging).
They'll be wrapped into the new job-source-adapter and AI-generation
architecture in later phases rather than rewritten from scratch.

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
cross-user access, and admin authorization boundaries.

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
