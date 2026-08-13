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
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'instance', 'app.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    UPLOAD_DIR = os.environ.get("UPLOAD_DIR", os.path.join(BASE_DIR, "uploads"))
    GENERATED_DIR = os.environ.get("GENERATED_DIR", os.path.join(BASE_DIR, "generated"))
    MAX_CONTENT_LENGTH = 15 * 1024 * 1024  # 15 MB per request

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true"
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"

    WTF_CSRF_ENABLED = True

    # AI provider abstraction (see app/ai/provider.py). "mock" requires no credentials
    # and is used whenever a real key isn't configured, so the app is always usable.
    AI_PROVIDER = os.environ.get("AI_PROVIDER", "mock")
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
    AI_MODEL = os.environ.get("AI_MODEL", "claude-opus-5")
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")


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


config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}


def get_config():
    env = os.environ.get("FLASK_ENV", "development")
    return config_by_name.get(env, DevelopmentConfig)
