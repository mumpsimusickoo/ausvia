# Architecture — AUSVIA

See `DECISIONS.md` for *why* these choices were made.

## Stack

- **Backend:** Flask (application factory + blueprints), SQLAlchemy ORM,
  Flask-Migrate (Alembic), Flask-Login, Flask-WTF (CSRF), Flask-Limiter
- **Database:** SQLite by default (`instance/app.db`), swappable to
  PostgreSQL via `DATABASE_URL` with zero code changes (never exercised
  against a real Postgres instance yet - see `PROJECT_AUDIT.md`)
- **Storage:** local filesystem behind a `StorageProvider` abstraction
  (`app/documents/storage.py`) - swappable for cloud object storage later
- **AI:** provider-agnostic abstraction (`app/ai/provider.py`), see `AI.md`
- **Frontend:** server-rendered Jinja2 + Tailwind (CDN, JIT config in
  `base.html`) - no SPA framework, no build step
- **Background jobs:** none yet. Everything runs synchronously in the
  request/response cycle (flagged as technical debt once real AI calls or
  larger workloads make this too slow - see `PROJECT_AUDIT.md`)

## Directory structure

```
app/
  __init__.py          # application factory, blueprint registration
  extensions.py         # db, migrate, login_manager, csrf, limiter singletons
  models/                # SQLAlchemy models, grouped by domain
  auth/                  # registration, login, password reset
  main/                   # landing page, dashboard
  profile/                # candidate profile CRUD
  documents/               # document upload/library + StorageProvider
  jobs/                     # search, adapters, dedup, ingest, matching, manual import
    adapters/                  # JobSourceAdapter implementations
  applications/               # application CRM, cover letter/email/PDF workflow
  ai/                           # provider abstraction, matching engine, prompts
    providers/                     # MockAIProvider, AnthropicProvider
    prompts/                        # prompt-builder modules, one per feature
  integrations/                    # Gmail OAuth (per-user), drafts, reply tracking
  admin/                            # admin dashboard blueprint
  templates/                        # Jinja2 templates, mirrors blueprint structure
  utils/                             # decorators, logging, encryption (crypto.py)
migrations/                          # Alembic migration history
tests/                                 # pytest suite, one file per feature area
config.py                              # environment-driven config classes
app.py                                  # entrypoint (create_app() + run)
seed.py                                  # local dev bootstrap (admin + invite codes)
```

Legacy root-level scripts (`jobsearch.py`, `coverletter.py`, `pdfmerge.py`,
`gmail_client.py`) predate the `app/` package and are wrapped rather than
rewritten - see the "legacy prototype" note in `README.md` and the relevant
`DECISIONS.md` entries.

## Request flow (typical authenticated page)

```
Browser → Flask route (blueprint) → SQLAlchemy models → Jinja2 template → HTML
```

AI-assisted routes additionally call into `app/ai/*` (matching engine is
pure Python; generation routes call `get_provider()` from
`app/ai/provider_factory.py`, which returns `MockAIProvider` or
`AnthropicProvider` depending on config - callers never know which).

## Multi-tenancy / data isolation

Every user-owned resource (`Document`, `Application`, `JobMatch`,
`SavedJob`, profile sub-entities) is scoped by `user_id` and every route
that reads/writes one verifies `resource.user_id == current_user.id` before
proceeding, returning 404 (not 403) on mismatch to avoid leaking existence.
Enforced per-route, not via a global framework hook - see individual
blueprint route files for the `_owned_x_or_404` helper pattern used
throughout.

## Deployment status

Not deployed anywhere yet. Runs locally via `python app.py` against SQLite.
Production readiness (secrets management, real Postgres, HTTPS, background
jobs, monitoring) is explicitly Phase 10 in `ROADMAP.md`, not done.
