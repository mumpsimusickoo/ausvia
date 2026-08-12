import os

from flask import Flask, render_template

from config import config_by_name
from app.extensions import db, migrate, login_manager, csrf, limiter


def create_app(config_name=None):
    # Phase 8 security audit (2.1): FLASK_ENV left unset is a normal, safe
    # local-dev default - but FLASK_ENV *set to something unrecognized* (a
    # typo like "produciton") used to silently fall back to development too,
    # which means DEBUG=True (Werkzeug's interactive debugger - a known RCE
    # vector) plus the insecure hardcoded SECRET_KEY fallback in a deployment
    # someone believed was configured for production. Fail loudly instead.
    if config_name is None:
        config_name = os.environ.get("FLASK_ENV", "development")
    if config_name not in config_by_name:
        raise RuntimeError(
            f"Unrecognized FLASK_ENV={config_name!r} - refusing to silently fall back to "
            f"'development' config (DEBUG=True + an insecure fallback SECRET_KEY). "
            f"Valid values: {', '.join(sorted(config_by_name))}."
        )
    app = Flask(__name__)
    app.config.from_object(config_by_name[config_name])

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
