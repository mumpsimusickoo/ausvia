import os

from flask import Flask, render_template
from werkzeug.middleware.proxy_fix import ProxyFix

from config import config_by_name
from app.extensions import db, migrate, login_manager, csrf, limiter, babel


def create_app(config_name=None):
    # Phase 8 security audit (2.1): FLASK_ENV left unset is a normal, safe
    # local-dev default - but FLASK_ENV *set to something unrecognized* (a
    # typo like "produciton") used to silently fall back to development too,
    # which means DEBUG=True (Werkzeug's interactive debugger - a known RCE
    # vector) plus the insecure hardcoded SECRET_KEY fallback in a deployment
    # someone believed was configured for production. Fail loudly instead.
    if config_name is None:
        # `or`, not get()'s default arg: FLASK_ENV present-but-blank in a
        # real .env should mean the same thing as unset (use development),
        # not get treated as an unrecognized value and rejected below -
        # see config.py's matching fix for the same "blank isn't absent"
        # class of bug.
        config_name = os.environ.get("FLASK_ENV") or "development"
    if config_name not in config_by_name:
        raise RuntimeError(
            f"Unrecognized FLASK_ENV={config_name!r} - refusing to silently fall back to "
            f"'development' config (DEBUG=True + an insecure fallback SECRET_KEY). "
            f"Valid values: {', '.join(sorted(config_by_name))}."
        )
    app = Flask(__name__)
    app.config.from_object(config_by_name[config_name])

    # Gmail OAuth bug fix, deployment-specific: Railway (like Heroku/Render)
    # terminates TLS at its edge proxy and forwards to this container over
    # plain HTTP internally, so without help Flask sees every request as
    # http:// even though the site is genuinely served over https:// -
    # url_for(..., _external=True) (Gmail's OAuth redirect_uri, see
    # app/integrations/gmail_oauth.py's _callback_url()) then generates an
    # http:// URL, which Google's OAuth flow rejects outright
    # (redirect_uri_mismatch). ProxyFix reads the X-Forwarded-Proto/-Host
    # headers Railway's edge proxy sets on every request and corrects what
    # Flask reports accordingly.
    #
    # Scoped to production only, not applied unconditionally: trusting
    # X-Forwarded-* headers is only safe when a real proxy in front of the
    # app is what sets them, overwriting/stripping any client-supplied copy
    # before forwarding - true for Railway's edge (the only path into this
    # container), not true for local dev, where there is no proxy and
    # nothing should trust a client-supplied X-Forwarded-* header for
    # anything (x_host=1 in particular also feeds url_for(_external=True)
    # generally, not just this one callback URL). Development/testing have
    # no proxy to trust in the first place, so scoping this out costs
    # nothing there and keeps the trust boundary honest.
    if config_name == "production":
        app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

    # ProductionConfig deliberately has no insecure SECRET_KEY fallback (only
    # DevelopmentConfig does), so an operator who forgets to set it in a real
    # deployment would otherwise only find out when Flask raises deep inside
    # the first request that touches the session - surface it at startup
    # instead, before the app ever accepts traffic.
    if config_name == "production" and not app.config.get("SECRET_KEY"):
        raise RuntimeError(
            "SECRET_KEY is not set. Production requires it to be set via the "
            "environment - there is no insecure fallback for this config."
        )

    # Deployment readiness pass: unlike SECRET_KEY, SQLALCHEMY_DATABASE_URI
    # always has *some* value - config.py falls back to a local SQLite file
    # when DATABASE_URL is unset, which is the right dev/test default but a
    # silent, easy-to-miss footgun in production: the app would start up
    # fine and appear to work, then lose all data on the next
    # deploy/restart on any host that wipes local disk (which is most of
    # them). Checked against the raw env var, not app.config - the config
    # value itself can never be falsy here, only the real cause can.
    if config_name == "production" and not os.environ.get("DATABASE_URL"):
        raise RuntimeError(
            "DATABASE_URL is not set. Production requires a real Postgres URL - "
            "without it, the app would silently fall back to a local SQLite "
            "file that most hosts wipe on every deploy/restart."
        )

    os.makedirs(os.path.join(app.root_path, "..", "instance"), exist_ok=True)
    os.makedirs(app.config["UPLOAD_DIR"], exist_ok=True)
    os.makedirs(app.config["GENERATED_DIR"], exist_ok=True)

    from app.security_headers import init_security_headers

    init_security_headers(app)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    from app.i18n import get_locale, format_local_date, format_local_datetime, format_local_currency

    babel.init_app(app, locale_selector=get_locale)
    # get_locale here is app.i18n's own callback, not flask_babel's Locale-
    # object one - templates need "which of the two supported codes is
    # active" (for the switcher's active-state styling), not a Locale
    # object. flask_babel's own _/gettext/ngettext/format_* globals are
    # already auto-registered by babel.init_app() above - these are the
    # only additions this app needs on top of that.
    app.jinja_env.globals["get_locale"] = get_locale
    app.jinja_env.globals["format_local_date"] = format_local_date
    app.jinja_env.globals["format_local_datetime"] = format_local_datetime
    app.jinja_env.globals["format_local_currency"] = format_local_currency

    from app.models.application import APPLICATION_STATUS_LABELS
    from app.models.document import DOCUMENT_TYPE_LABELS
    from app.models.integration import REPLY_INTENT_LABELS
    from app.jobs.matching import _CATEGORY_DISPLAY_NAMES

    app.jinja_env.globals["application_status_labels"] = APPLICATION_STATUS_LABELS
    app.jinja_env.globals["document_type_labels"] = DOCUMENT_TYPE_LABELS
    app.jinja_env.globals["reply_intent_labels"] = REPLY_INTENT_LABELS
    app.jinja_env.globals["category_display_names"] = _CATEGORY_DISPLAY_NAMES

    with app.app_context():
        _enable_sqlite_foreign_keys(db.engine)

    from app.models.user import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    from app.auth.routes import bp as auth_bp
    from app.main.routes import bp as main_bp
    from app.profile.routes import bp as profile_bp
    from app.documents.routes import bp as documents_bp
    from app.jobs.routes import bp as jobs_bp
    from app.applications.routes import bp as applications_bp
    from app.integrations.routes import bp as integrations_bp
    from app.admin.routes import bp as admin_bp
    from app.companies.routes import bp as companies_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(documents_bp)
    app.register_blueprint(jobs_bp)
    app.register_blueprint(applications_bp)
    app.register_blueprint(integrations_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(companies_bp)

    # Plans page + access expiry pass (2026-08-30): the mid-session
    # checkpoint - app-wide, not blueprint-scoped, since an expired
    # session must be cut off no matter which page the next request hits.
    # See app/access_expiry.py's own docstring for the two-checkpoint
    # design (this one, plus a login-time check in app/auth/routes.py).
    from app.access_expiry import enforce_access_expiry

    app.before_request(enforce_access_expiry)

    register_error_handlers(app)
    register_cli(app)

    return app


def _enable_sqlite_foreign_keys(engine):
    """Phase 7 remediation (QA finding W2): SQLite does not enforce foreign
    keys unless a connection explicitly turns it on - without this, an
    orphaned FK reference (see B1) fails silently instead of being rejected.
    No-op for any other database backend (e.g. Postgres in production)."""
    if engine.dialect.name != "sqlite":
        return

    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def register_error_handlers(app):
    @app.errorhandler(403)
    def forbidden(e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(413)
    def too_large(e):
        return render_template("errors/413.html"), 413

    @app.errorhandler(500)
    def server_error(e):
        # Never leak stack traces to the user; details go to server logs only.
        app.logger.exception("Unhandled server error")
        return render_template("errors/500.html"), 500


def register_cli(app):
    @app.cli.command("seed")
    def seed_command():
        """Seeds a first admin user + admin invitation code for local development."""
        from seed import run_seed

        run_seed()
        print("Seed complete.")
