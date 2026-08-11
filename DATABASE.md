# Database — Ausvia

SQLAlchemy models, SQLite by default (`instance/app.db`), Postgres-ready via
`DATABASE_URL` (untested against real Postgres). Migrations via Flask-
Migrate/Alembic in `migrations/versions/` - one migration per phase so far.

## Domain groups

### Identity & access (`app/models/user.py`, `app/models/access_code.py`)
- `User` — email, password hash, role (user/admin), plan, active flag
- `InvitationCode` — code, type (trial/standard/premium/admin), max_uses/
  use_count, expiry, active flag
- `CodeRedemption` — audit trail of which user redeemed which code

### Candidate profile (`app/models/profile.py`)
- `CandidateProfile` (1:1 with User) — personal info
- `Education`, `Experience`, `Skill`, `Language` (many per profile)
- `Preference` (1:1 with profile) — desired fields/locations/start date/
  min German level/relocation

### Documents (`app/models/document.py`)
- `Document` — type, original/stored filename, storage path, mime type,
  size, primary-CV/diploma/German-cert flags. Owned by `user_id`.

### Jobs (`app/models/job.py`)
- `Company` — name + normalized name (for dedup matching), industry,
  location, website, description
- `Job` — the canonical normalized opportunity (title, location, start
  date, requirements, skills, language_requirements JSON, etc.), a
  `dedup_key` for grouping
- `JobListing` — one row per source occurrence of a `Job` (source name,
  external ID, source URL, raw snapshot JSON) - multiple listings can point
  at one canonical `Job`
- `SavedJob` — user bookmark
- `JobSourceSetting` — admin enable/disable + last-run diagnostics per source

### AI (`app/models/ai.py`)
- `JobMatch` — cached deterministic match result per (user, job) + optional
  cached AI narrative/improvement-tips text
- `AIUsage` — token usage log per real (non-mock) AI call, for cost tracking

### Applications (`app/models/application.py`)
- `Application` — status lifecycle, contact info, package storage path
- `ApplicationEvent` — auto-logged timeline entries
- `GeneratedDocument` — the cover letter (one per application, source =
  ai/template/manual, validation status)
- `GeneratedEmail` — the application email (same source/validation pattern)
- `ApplicationDocument` — join table: which library `Document`s are
  selected for this application's PDF package, and in what order

### Diagnostics (`app/models/system_log.py`)
- `SystemLog` — admin-visible event log (auth, uploads, job sources, AI,
  application events). Never stores secrets, passwords, or raw access codes.

## Relationships worth knowing

- `Job` ←1:N— `JobListing` (dedup grouping)
- `Job` ←1:N— `JobMatch` per user, and ←1:N— `Application` per user
- `Application` ←1:1— `GeneratedDocument`, ←1:1— `GeneratedEmail` (one
  active cover letter/email per application; regenerating overwrites and
  logs a timeline event rather than keeping full history)
- Every user-owned table has a `user_id` foreign key and is queried with an
  explicit ownership check in the route layer (see `ARCHITECTURE.md`)

## Migration workflow

```powershell
flask db migrate -m "description"   # autogenerate from model changes
flask db upgrade                     # apply
```

One migration file per phase so far; each is additive (no destructive
schema changes have been needed yet).
