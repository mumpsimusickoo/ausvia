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

### Job source adapters (`app/jobs/adapters/`, job-source integration pass)

| Variable | Required? | Default | Notes |
|---|---|---|---|
| `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` | No | none | Both required together to enable Adzuna - absent otherwise, not an error. Self-serve signup at developer.adzuna.com. **Free access is a 14-day trial only per Adzuna's Terms of Service** - see `JOB_SOURCES.md` before relying on this past the trial window in production. |
| `ADZUNA_COUNTRY` | No | `de` | Adzuna's country-code path segment. |
| `JOOBLE_API_KEY` | No | none | Enables Jooble. Manually issued after submitting a request form at jooble.org/api/about (name/role/email/website) - not instant, allow lead time. |

Arbeitsagentur (Bundesagentur für Arbeit Jobsuche) needs no credentials -
see `JOB_SOURCES.md` for its current reliability status, which is more
nuanced than a simple working/broken flag.

### Gmail draft creation (optional feature)

| Variable | Required? | Default | Notes |
|---|---|---|---|
| `GOOGLE_CREDENTIALS_JSON` | No | none (falls back to `credentials.json` on disk) | The **entire contents** of the OAuth client's `credentials.json` file, as a JSON string - not a file path. Get it from Google Cloud Console → APIs & Services → Credentials → your OAuth client → Download JSON, then paste the full file content as this var's value. Either this or a `credentials.json` file at the repo root works; if both are somehow present, the env var wins. This is what makes Gmail draft creation work on hosts where you can only set env vars (Railway, Render, etc.) and can't place an arbitrary file at a fixed repo-relative path. |

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

## Pre-deploy checklist

**Tailwind build pass, 2026-08-26** (see `DECISIONS.md`): the app no longer
loads Tailwind from a CDN at runtime. `app/static/css/tailwind.css` is a
compiled, purged, committed static file - Railway's deploy is still pure
Python and never runs Node, so this file has to already be correct and
committed *before* you push, not generated during deploy. The tradeoff
this creates is real: the compiled CSS can go stale (out of sync with
`tailwind.config.js`, `assets/css/input.css`, or a class name used in a
template) exactly the way the 2026-08-25 migration gap happened - the code
is correct, but a required local step wasn't run before pushing.

**Before every push that touches a template, `tailwind.config.js`, or
`assets/css/input.css`:**

1. Run `npm run build:css` to regenerate `app/static/css/tailwind.css`.
2. Run `npm run check:css` to confirm it - this rebuilds into a scratch
   file and diffs it against what's actually committed, so staleness is
   *detected*, not just hoped against. A clean `git status` on the CSS
   file after step 1 is the same signal, but the check script is the one
   to actually run (and the one safe to wire into CI later, if this
   project ever gets one) since it doesn't depend on remembering to look.
3. Commit the rebuilt `app/static/css/tailwind.css` alongside whatever
   template/config change prompted it - it's a real source file for
   deploy purposes, not a build artifact to gitignore.

If step 2 fails on a branch you didn't expect to touch CSS on, that's the
check doing its job - something (a class name, a token, a purge-relevant
template edit) changed since the last commit of the compiled file.

## Translations (i18n)

**i18n pass 1, 2026-08-28** (`app/i18n.py`, `babel.cfg`, `translations/`):
Flask-Babel wires up locale selection and message catalogs. Same
committed-compiled-artifact discipline as the Tailwind build above and for
the same reason - Railway's deploy is pure Python with no build step, so
`translations/de/LC_MESSAGES/messages.mo` (the binary catalog the app
actually reads at runtime) has to already be correct and committed before
you push, not regenerated during deploy.

**English is the source language, not a translated one** - every `_()`-
wrapped string's English text is its own `msgid`, so English needs no
catalog at all; only `translations/de/` exists. This supersedes the
AUSVIA 2.0 bundle's own bilingual rule (English labels over permanently-
German prose) - see `DECISIONS.md`. A translated locale's AI-generated
content (cover letters, etc.) is a separate, per-feature concern scoped to
i18n pass 3, not this mechanism.

**Workflow - three `pybabel` commands** (installed as part of
`Flask-Babel`, callable as `venv/Scripts/pybabel.exe` on this machine's
venv, or plain `pybabel` once the venv is activated):

1. **After adding or changing any `_('...')`-wrapped string** (in a
   `.py` file or a Jinja template - `babel.cfg` covers both), regenerate
   the template:
   ```
   pybabel extract -F babel.cfg -k lazy_gettext -k _l -o messages.pot .
   ```
   **Both `-k` flags are required, not redundant.** `flask_babel.lazy_gettext`
   (deferred translation - every WTForms field label/validator message,
   which is evaluated at class-body/module-import time, outside any
   request) is always imported under the alias `_l`
   (`from flask_babel import lazy_gettext as _l`) throughout this app's
   `forms.py` files. `pybabel extract` matches call sites by the literal
   identifier used at the call site, not by what it's imported *from* - a
   real bug hit during i18n pass 2 (2026-08-28): `-k lazy_gettext` alone
   silently extracted zero of the ~40 `_l(...)`-wrapped form field labels
   and validator messages, with no warning or error, because every call
   site in the source reads `_l(...)`, never `lazy_gettext(...)`. Caught
   by the pass's own extraction-completeness test, not by inspection - see
   `DECISIONS.md`. If a future session ever imports `lazy_gettext` under a
   *different* alias, that alias needs its own `-k` flag added here too.
2. **Update the German catalog against the new template** (preserves
   existing translations, marks changed/removed strings `#, fuzzy` for
   review, adds new ones as blank):
   ```
   pybabel update -i messages.pot -d translations -l de
   ```
   Then translate any new blank `msgstr ""` entries in
   `translations/de/LC_MESSAGES/messages.po` by hand - this project has no
   translation-management service, `.po` files are edited directly, the
   same way `.mo` compilation is a local step, not a service call.
3. **Compile before every commit that touches a `.po` file:**
   ```
   pybabel compile -d translations
   ```
   This regenerates `translations/de/LC_MESSAGES/messages.mo` - commit it
   alongside the `.po` source, same as the Tailwind CSS file above. A
   `.po` edit with no matching `pybabel compile` run is exactly the
   Tailwind-staleness trap in a different file: the source is correct, the
   compiled artifact the running app actually reads isn't.

**A first-time locale (there's only `de` today) needs `init`, not
`update`:**
```
pybabel init -i messages.pot -d translations -l <code>
```

**i18n pass 2, 2026-08-28: mass extraction complete** - every in-scope
template and Python module wraps its user-facing strings; only
`app/ai/prompts/*` (prompt builders), AI-generated content itself, job
posting data, and internal audit-log/diagnostic content remain
deliberately untranslated - see `DECISIONS.md`'s pass 2 entry for the
full scope list and reasoning.

**i18n pass 3, 2026-08-29: the AI content language split, done** - all
three i18n passes are now complete, nothing left scoped or pending.
Cover letter/application email/reply suggestions stay German
unconditionally (real German-employer-facing text). Match explanation/
improvement tips, company insight, profile coaching, interview prep, and
CV profile statement follow the session's UI locale, via `get_locale()`
called inside each feature's own orchestration function - no new
parameter threaded through any route. This added a `generated_locale`-
style column to five models (migration `d0a13f3299ee`) so a locale
switch invalidates a cached response the same way a profile edit already
does - **a fresh `flask db upgrade` is required after pulling this
change**, same as any other schema migration. See `DECISIONS.md`'s
2026-08-29 "i18n pass 3" entry for the two real bugs this pass found
(a shared mock-mode fallback that ignored locale; a recurrence of pass
2's `LazyString`-can't-bind-to-SQLite bug in four more places) and the
full verification method (live generation against the real configured
provider, both locales, all eight features).

**i18n pass 3 resolve, 2026-08-29:** `dashboard_insight.py`/`process_qa.py`
also confirmed candidate-facing and wired into the "follows UI language"
bucket - a second migration, `b00ad196d445`, adds `generated_locale` to
two more models. **Both migrations (`d0a13f3299ee` and `b00ad196d445`)
must be applied** (`flask db upgrade` picks up both in one run if neither
has been applied yet). See `DECISIONS.md`'s 2026-08-29 "i18n pass 3
resolve" entry for the full `LazyString` sweep result and why reply
suggestion's live re-verification was blocked (a real, account-wide daily
Gemini quota, not a code issue).

**A compiled `.mo` catalog only loads once per process - a running
server must be restarted for a new `pybabel compile` to take effect,**
the same way it already needs a restart to pick up new Python code (but
unlike Jinja templates, which Flask's debug-mode autoreloader already
picks up per-request without a restart). Found during pass 2: a long-
running dev server kept serving an in-memory snapshot of the German
catalog from early in the session while `messages.po`/`messages.mo` were
recompiled several more times afterward, so some strings translated
correctly (whatever was cached at first load) and others - added in a
later cycle - silently rendered their English `msgid`, in the same
request, with no error. **On Railway, this means a deploy that changes
only `translations/de/LC_MESSAGES/messages.mo` still needs the dyno to
actually restart**, not just receive the new file - the same class of
"source correct, running process stale" trap the Tailwind CSS / compiled-
artifact discipline above exists to prevent, just triggered by a process
boundary instead of a missing build step. A plain `git push` to a
platform that hot-swaps files without restarting the process would ship
silently-stale translations.

## Post-deploy checklist

**Every push that includes a migration must be followed by these three
steps before the deploy is considered done — not just "code pushed":**

1. Run `flask db upgrade` against the production database (Railway's
   console/shell, or `railway run flask db upgrade` if using the CLI).
2. Confirm the migration actually applied: `flask db current` should show
   the new head revision, not the one before it.
3. Load the app's main authenticated screen (`/dashboard`) as a real
   logged-in user and confirm it renders - not just `GET /health` (which
   deliberately does no DB check, by design, so it stays green even when
   a table is missing) and not just a green CI run (the test suite runs
   against its own throwaway SQLite DB, created fresh via the *current*
   models on every run - it can never observe a stale *production*
   database missing a migration, because there's no such thing as a stale
   test database).

**Why this is a checklist and not a one-off note:** on 2026-08-25, the Job
Radar feature shipped with a migration (`job_radar_status` table) that
was never run against Railway's Postgres - the code was correct, tests
passed, the push succeeded, and the dashboard 500'd in production for an
unknown period because every dashboard load queried a table that didn't
exist. Nothing in the deploy path would have caught this automatically:
`/health` doesn't touch the DB, the test suite's DB is always fresh, and
the failure mode looked exactly like a code bug from the outside (a
generic 500, logged server-side, no user-facing detail) - it took
comparing Railway's Postgres revision against the repo's migration head
to actually find it. Full incident writeup: `DECISIONS.md`'s 2026-08-25
"Deploy gap" entry.

This matters more than it might look like from one incident: the
AUSVIA 2.0 reliability/edit-tracking schema pass (2026-08-26) added ten
columns across six models in one migration (`5b4fe35a6528`) - ten more
chances to repeat this exact failure. The checklist above is what closed
that gap this time: the user ran it against Railway the same day, per
`DECISIONS.md`'s 2026-08-26 entries.

## Known gaps / things to decide before going live

1. **Generated PDF application packages stay on local disk even when
   `STORAGE_PROVIDER=s3`.** Only uploaded documents (CVs, diplomas, IDs) -
   the irreplaceable data - were routed through the storage abstraction.
   Generated packages are 100% deterministically reconstructable from data
   already in the database (the cover letter text + selected documents) by
   re-approving the application, so losing one on redeploy is a minor
   inconvenience, not data loss - a materially different risk profile from
   losing an original upload. Worth a small follow-up if it matters, not
   done here to avoid a much larger refactor (it would also touch the
   Gmail-draft-attachment code path) for a low-severity, self-healing gap.
2. **`RATELIMIT_STORAGE_URI` defaults to per-process memory.** See the
   table above - only matters if exact rate limits matter with multiple
   gunicorn workers.
3. **No live Postgres test.** See "Postgres compatibility" above.
