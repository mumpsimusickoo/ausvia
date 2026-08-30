import os

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Must run before any os.environ.get() call below - the Config classes read
# their values at class-definition time (i.e. the moment this module is
# first imported, which happens as a side effect of `from app import
# create_app` in app.py), so loading .env any later would be too late.
# Explicit path (not the default cwd-relative search) so this works
# regardless of the directory the process happens to be launched from.
# Real OS environment variables still win - load_dotenv() never overwrites
# a variable that's already set, only fills in ones that aren't.
load_dotenv(os.path.join(BASE_DIR, ".env"))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY")
    # Phase 8 security audit (D6): dedicated key for encrypting Gmail tokens
    # at rest (app/utils/crypto.py) - optional, falls back to SECRET_KEY-
    # derived behavior when unset. See crypto.py's docstring for the full
    # backward-compatibility story.
    TOKEN_ENCRYPTION_KEY = os.environ.get("TOKEN_ENCRYPTION_KEY")
    # `or` rather than os.environ.get(key, default): .env.example ships
    # DATABASE_URL= blank (there's no sensible literal default to write for
    # it), and a *present-but-empty* env var isn't caught by get()'s default
    # argument - only a fully-*absent* key is. Found via a real, reproduced
    # failure: creating .env from the template left DATABASE_URL="" in the
    # environment, which silently became SQLALCHEMY_DATABASE_URI="" instead
    # of falling back to the sqlite default, breaking every non-testing
    # create_app() call (TestingConfig overrides this var directly, which is
    # why the test suite's own DB was unaffected - only DevelopmentConfig/
    # ProductionConfig inherit this line unmodified).
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or (
        f"sqlite:///{os.path.join(BASE_DIR, 'instance', 'app.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    UPLOAD_DIR = os.environ.get("UPLOAD_DIR") or os.path.join(BASE_DIR, "uploads")
    GENERATED_DIR = os.environ.get("GENERATED_DIR") or os.path.join(BASE_DIR, "generated")
    MAX_CONTENT_LENGTH = 15 * 1024 * 1024  # 15 MB per request

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true"
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"

    WTF_CSRF_ENABLED = True

    # AI provider abstraction (see app/ai/provider.py). "mock" requires no credentials
    # and is used whenever a real key isn't configured, so the app is always usable.
    AI_PROVIDER = os.environ.get("AI_PROVIDER") or "mock"
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
    AI_MODEL = os.environ.get("AI_MODEL") or "claude-opus-5"
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
    # Separate from AI_MODEL on purpose - that var's default is an Anthropic
    # model name, and Gemini has its own model namespace (see
    # app/ai/provider_factory.py for why these can't share one var).
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
    GEMINI_MODEL = os.environ.get("GEMINI_MODEL") or "gemini-3.6-flash"

    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI") or "memory://"

    # Password reset email delivery (app/mail.py, 2026-08-30). Same
    # "absence is fine" pattern as AI_PROVIDER/STORAGE_PROVIDER above -
    # unset means the reset flow logs the attempt internally and sends
    # nothing, never an error and never a fallback to exposing the link.
    RESEND_API_KEY = os.environ.get("RESEND_API_KEY")

    # Storage provider abstraction (see app/documents/storage.py). "local"
    # writes to UPLOAD_DIR on disk and needs no credentials - the right
    # default for dev/test, and wrong for most real hosts (local disk is
    # wiped on every deploy/restart there). Set to "s3" plus S3_BUCKET to
    # persist uploaded documents to an S3-compatible bucket instead (AWS S3,
    # a PaaS host's own object storage, MinIO, etc.) - same
    # config-selected-at-runtime pattern as AI_PROVIDER above.
    STORAGE_PROVIDER = os.environ.get("STORAGE_PROVIDER") or "local"
    S3_BUCKET = os.environ.get("S3_BUCKET")
    # Optional: only needed for a non-AWS S3-compatible endpoint (MinIO, a
    # PaaS host's own object storage) or a specific AWS region. Access
    # key/secret are also optional - unset, boto3 falls back to its own
    # default credential chain (env vars it reads itself, an IAM role, etc.),
    # which is the preferred setup on any host that supports it.
    S3_REGION = os.environ.get("S3_REGION")
    S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL")
    S3_ACCESS_KEY_ID = os.environ.get("S3_ACCESS_KEY_ID")
    S3_SECRET_ACCESS_KEY = os.environ.get("S3_SECRET_ACCESS_KEY")
    S3_PREFIX = os.environ.get("S3_PREFIX")

    # Job source adapters (see app/jobs/adapters/manager.py). Arbeitsagentur
    # needs no config (public static key, see jobsearch.py) so it's always
    # registered; Adzuna/Jooble are only added to the search rotation when
    # their credentials are actually present - an unconfigured provider is
    # silently skipped, not an error, same "absence is fine" pattern as the
    # AI/storage providers above.
    #
    # Adzuna (developer.adzuna.com): free access is a 14-day trial only,
    # per Adzuna's own Terms of Service ("strictly for the purpose of
    # validating the general coverage and quality of the data... in
    # addition to usability testing") - ongoing use past the trial needs a
    # licence agreement directly with Adzuna. See JOB_SOURCES.md for the
    # trial-window tracking. ADZUNA_COUNTRY defaults to "de" since AUSVIA
    # is Germany-specific.
    ADZUNA_APP_ID = os.environ.get("ADZUNA_APP_ID")
    ADZUNA_APP_KEY = os.environ.get("ADZUNA_APP_KEY")
    ADZUNA_COUNTRY = os.environ.get("ADZUNA_COUNTRY") or "de"

    # Jooble (jooble.org/api/about): key is manually issued after
    # submitting a request form (name/role/email/website) - not instant
    # self-serve like Adzuna's, allow lead time.
    JOOBLE_API_KEY = os.environ.get("JOOBLE_API_KEY")

    # i18n pass 1 (see app/i18n.py, DECISIONS.md). English is the default,
    # not the bundle's own bilingual rule (superseded - see DECISIONS.md).
    # Not env-configurable - this is a fixed product decision, not a
    # per-deployment setting like AI_PROVIDER/STORAGE_PROVIDER above.
    LANGUAGES = {"en": "English", "de": "Deutsch"}
    BABEL_DEFAULT_LOCALE = "en"
    # Absolute, not the bare "translations" default Flask-Babel resolves
    # relative to *its own* app.root_path - which is app/ (the package
    # this Flask instance was constructed with __name__="app"), not the
    # repo root where translations/ actually lives (alongside babel.cfg).
    # A relative path here silently resolves to app/translations/ (never
    # created), which Flask-Babel treats as "no catalog found" and falls
    # back to returning every msgid verbatim - found live, not
    # theoretically: every _()-wrapped string rendered in English
    # regardless of locale until this was made absolute, same
    # BASE_DIR-relative pattern as UPLOAD_DIR/GENERATED_DIR above.
    BABEL_TRANSLATION_DIRECTORIES = os.path.join(BASE_DIR, "translations")


class DevelopmentConfig(Config):
    DEBUG = True
    if not Config.SECRET_KEY:
        SECRET_KEY = "dev-only-insecure-secret-key-change-me"


class ProductionConfig(Config):
    DEBUG = False
    # SECRET_KEY MUST be set via environment in production; no insecure fallback here.

    # Phase 8 security audit (2.1): don't rely on the SESSION_COOKIE_SECURE
    # env var being remembered in production - force it here so a forgotten
    # env var can't silently send session/remember-me cookies over plain HTTP.
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True


class TestingConfig(Config):
    TESTING = True
    SECRET_KEY = "test-secret-key"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False
    # Found live, not theoretically: the moment a real .env with a real
    # AI_PROVIDER + API key existed on this machine, 14 "mock mode is
    # honest" tests across every AI feature started actually calling the
    # real provider instead - this class never forced mock before, so
    # AI_PROVIDER/ANTHROPIC_API_KEY/GEMINI_API_KEY were inherited straight
    # from Config, i.e. from whatever a developer happens to have in their
    # local .env. Tests must never depend on, or spend, real API credits
    # regardless of local configuration - forced explicitly here rather
    # than relying on every test to remember to monkeypatch it away.
    AI_PROVIDER = "mock"
    ANTHROPIC_API_KEY = None
    GEMINI_API_KEY = None
    # Same class of bug, same fix: force local storage regardless of a
    # developer's real .env, so the test suite never attempts a real S3 call.
    STORAGE_PROVIDER = "local"
    # Same again: a real .env with Adzuna/Jooble credentials must never
    # make the test suite call the live APIs. Tests that specifically want
    # to exercise the "configured" path monkeypatch these back in.
    ADZUNA_APP_ID = None
    ADZUNA_APP_KEY = None
    JOOBLE_API_KEY = None
    # Same again: a real .env with a real RESEND_API_KEY must never make
    # the test suite send a real email. Tests that specifically want to
    # exercise the "configured" path monkeypatch this back in.
    RESEND_API_KEY = None


config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}


def get_config():
    env = os.environ.get("FLASK_ENV") or "development"
    return config_by_name.get(env, DevelopmentConfig)
