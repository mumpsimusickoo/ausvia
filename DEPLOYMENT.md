# Deployment

This document covers what's needed to run AUSVIA on a real host (a
Render/Railway-style PaaS, Postgres, managed environment variables). It's
infrastructure only - no product behavior changes. Account setup on an
actual host is out of scope here.

## Serving the app

`flask run` / `python app.py` (Werkzeug's dev server) is not meant for real
traffic. Production serving is [gunicorn](https://gunicorn.org/), declared
in `requirements.txt` and started via the `Procfile`:

```
web: gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 3 --timeout 60
```

Most PaaS hosts (Render, Railway, Heroku-style) run this automatically from
the `Procfile` and inject `$PORT` themselves. Adjust `--workers` to the
host's CPU allocation (a common starting rule of thumb is `2 * cores + 1`).

**Use `wsgi:app`, not `app:app`.** The project has both an `app.py` file and
an `app/` package in the same directory - a plain `import app` (what a WSGI
server's `module:object` target does) resolves to the `app/` package, which
only exposes `create_app()`, not a `create_app()`-produced instance. `flask
run` never hits this because it loads `app.py` by file path, bypassing
normal import resolution - but `gunicorn app:app` fails outright with
`module 'app' has no attribute 'app'`. `wsgi.py` (new, at the repo root)
sidesteps this with a distinctly-named entrypoint:

```python
from app import create_app
app = create_app()
```

`gunicorn` cannot run on Windows at all (it imports the POSIX-only `fcntl`
module unconditionally) - this was verified by running it locally and
seeing that exact failure. Since the real host is Linux, this doesn't
matter for deployment; it just means gunicorn itself couldn't be exercised
end-to-end in this dev sandbox. `wsgi:app` was instead verified by serving
it through [Waitress](https://pypi.org/project/waitress/) (a cross-platform
WSGI server) and hitting real routes over HTTP - confirming the app factory
behaves correctly when driven by an external WSGI server, which was the
actual risk, not gunicorn's own worker/arbiter code.

## Environment variables

Grepped directly from `os.environ`/`os.environ.get()` usage in `config.py`
and `app/__init__.py` - nothing here is reconstructed from memory.

### Core / security

| Variable | Required? | Default | Notes |
|---|---|---|---|
| `FLASK_ENV` | Yes, in production | `development` | Must be exactly `development`, `production`, or `testing`. Any other value (including a typo) makes `create_app()` raise at startup rather than silently running in dev mode. |
| `SECRET_KEY` | **Required in production** | dev-only insecure fallback (dev only) | No fallback in production - `create_app()` raises at startup if unset. Flask session/CSRF signing key. |
| `TOKEN_ENCRYPTION_KEY` | No | none (falls back to a SECRET_KEY-derived key) | Encrypts stored Gmail OAuth tokens at rest with its own key, so rotating `SECRET_KEY` doesn't invalidate every stored Gmail connection. Safe to leave unset. |
| `SESSION_COOKIE_SECURE` | No | `false` | Only read in dev/testing config. **Production forces this (and `REMEMBER_COOKIE_SECURE`) to `True` unconditionally** - this var has no effect in production, kept only so a forgotten env var can't silently ship insecure cookies. |

### Database

| Variable | Required? | Default | Notes |
|---|---|---|---|
| `DATABASE_URL` | **Required in production** | local SQLite file under `instance/` (dev/test only) | A standard SQLAlchemy URL, e.g. `postgresql://user:pass@host:5432/dbname` - no code changes needed for Postgres, SQLAlchemy handles the dialect. **Production now fails loudly at startup if this is unset**, added during this pass: previously it would silently fall back to local SQLite, which starts up fine and appears to work, then loses all data on the next deploy/restart on any host with ephemeral disk (most of them). Run `flask db upgrade` against the real database before first traffic (creates/migrates all tables). |

### AI provider (`app/ai/provider.py`)

| Variable | Required? | Default | Notes |
|---|---|---|---|
| `AI_PROVIDER` | No | `mock` | `mock` \| `anthropic` \| `gemini`. Mock mode needs no credentials - every AI-assisted feature still works, with an honest "AI not configured" message instead of AI-written text. |
| `ANTHROPIC_API_KEY` | Only if `AI_PROVIDER=anthropic` | none | |
| `AI_MODEL` | No | `claude-opus-5` | Anthropic model name; only used by the Anthropic branch. |
| `GEMINI_API_KEY` | Only if `AI_PROVIDER=gemini` | none | |
| `GEMINI_MODEL` | No | `gemini-3.6-flash` | |
| `OPENAI_API_KEY` | No | none | Reserved for a future provider - no OpenAI implementation exists yet; setting this currently does nothing. |

### Storage provider (`app/documents/storage.py`, this pass)

| Variable | Required? | Default | Notes |
|---|---|---|---|
| `STORAGE_PROVIDER` | No | `local` | `local` \| `s3`. **Set to `s3` in production** on any host that wipes local disk on deploy/restart (most PaaS hosts) - `local` silently loses every uploaded document (CVs, diplomas, IDs) on the next redeploy otherwise. |
| `S3_BUCKET` | Only if `STORAGE_PROVIDER=s3` | none | |
| `S3_REGION` | No | boto3 default | Only needed for a specific AWS region. |
| `S3_ENDPOINT_URL` | No | AWS S3 | Set this for a non-AWS S3-compatible service (a PaaS's own object storage, MinIO, etc.). |
| `S3_ACCESS_KEY_ID` / `S3_SECRET_ACCESS_KEY` | No | boto3's default credential chain | Leave unset to use an IAM role or boto3's own env vars (`AWS_ACCESS_KEY_ID` etc.) instead - preferred where the host supports it. |
| `S3_PREFIX` | No | none | Optional key prefix inside the bucket (e.g. `prod/`), useful for sharing one bucket across environments. |
| `UPLOAD_DIR` | No | `<repo>/uploads` | Only relevant when `STORAGE_PROVIDER=local`. |
| `GENERATED_DIR` | No | `<repo>/generated` | **Always local disk regardless of `STORAGE_PROVIDER`** - generated application PDF packages are not yet routed through the storage abstraction (see "Known gaps" below). |

### Rate limiting

| Variable | Required? | Default | Notes |
|---|---|---|---|
| `RATELIMIT_STORAGE_URI` | No | `memory://` | **`memory://` is per-process.** With gunicorn's multiple workers, each worker has its own counter, so the effective limit becomes roughly `configured limit × worker count`, not the configured limit. Fine for a single-worker deployment; for multi-worker production where the exact limit matters, point this at a shared backend (e.g. `redis://...` - Flask-Limiter supports it, no code changes needed, just add a Redis add-on and set this var). |

### Gmail draft creation (optional feature - not env-var configured)

Not read from an environment variable at all: `app/integrations/gmail_oauth.py`
reads OAuth client config from a `credentials.json` file at a fixed path
relative to the repo root. See "Known gaps" below - this needs an
operational decision before Gmail features will work on most PaaS hosts.

## Health check

`GET /health` - returns `200 "ok"`, no auth, no DB check, no version/internal
info. Point the host's health check / readiness probe at this.

## Postgres compatibility

Verified:
- The SQLite foreign-key-enforcement listener (`app/__init__.py`,
  `_enable_sqlite_foreign_keys`) is already gated on `engine.dialect.name ==
  "sqlite"` and confirmed to stay a no-op when the engine's dialect is
  `postgresql`.
- No raw dialect-specific SQL anywhere in the app (grepped for `.execute(`,
  `PRAGMA`, etc.) - the one hand-written statement outside the ORM (the
  atomic invitation-code redemption `UPDATE` in `app/auth/routes.py`) is
  built with SQLAlchemy Core (`sa.update(...)`), not a raw string, and was
  compiled against the Postgres dialect directly to confirm it renders to
  valid SQL.
- All 33 tables across every model were compiled to `CREATE TABLE` DDL
  against the Postgres dialect (`sqlalchemy.dialects.postgresql`) with no
  errors - no SQLite-only column types anywhere (`db.JSON` columns map to
  Postgres's native `JSON` type fine).
- Migrations use Alembic's `batch_alter_table` throughout, which works on
  both dialects (it's SQLite's copy-and-swap workaround, but a harmless
  direct `ALTER TABLE` on Postgres).
- `psycopg2-binary` (added to `requirements.txt`) imports and is ready to
  use as the Postgres driver.

**Not verified: no live Postgres server was reachable in this sandbox** (no
Docker, no WSL, no native Postgres install, and no pip-installable embedded
Postgres binary compatible with this environment). The above is real
static/compile-time verification, not a substitute for actually running
`flask db upgrade` and the test suite against a real Postgres instance
before the first production deploy - recommended as the actual final check
once real hosting is set up.

## Known gaps / things to decide before going live

1. **Gmail `credentials.json` has no env-var path.** It's read from a fixed
   file path at the repo root, not from an environment variable - the
   standard "set env vars in the host's dashboard" deployment model can't
   supply it. Needs one of: (a) a small code change to also accept the
   credentials JSON via an env var, (b) a build/deploy hook that writes the
   file from a platform secret, or (c) accepting that Gmail draft creation
   stays unavailable in production until this is addressed. Not fixed in
   this pass - it's an existing feature's file-loading mechanism, out of
   this pass's "infrastructure only" scope, but it will block Gmail
   features specifically (nothing else) if left as-is.
2. **Generated PDF application packages stay on local disk even when
   `STORAGE_PROVIDER=s3`.** Only uploaded documents (CVs, diplomas, IDs) -
   the irreplaceable data - were routed through the storage abstraction.
   Generated packages are 100% deterministically reconstructable from data
   already in the database (the cover letter text + selected documents) by
   re-approving the application, so losing one on redeploy is a minor
   inconvenience, not data loss - a materially different risk profile from
   losing an original upload. Worth a small follow-up if it matters, not
   done here to avoid a much larger refactor (it would also touch the
   Gmail-draft-attachment code path) for a low-severity, self-healing gap.
3. **`RATELIMIT_STORAGE_URI` defaults to per-process memory.** See the
   table above - only matters if exact rate limits matter with multiple
   gunicorn workers.
4. **No live Postgres test.** See "Postgres compatibility" above.
