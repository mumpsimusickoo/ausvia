import os

from flask import Flask, render_template

from config import config_by_name
from app.extensions import db, migrate, login_manager, csrf, limiter


def create_app(config_name=None):
    config_name = config_name or os.environ.get("FLASK_ENV", "development")
    app = Flask(__name__)
    app.config.from_object(config_by_name.get(config_name, config_by_name["development"]))

    os.makedirs(os.path.join(app.root_path, "..", "instance"), exist_ok=True)
    os.makedirs(app.config["UPLOAD_DIR"], exist_ok=True)
    os.makedirs(app.config["GENERATED_DIR"], exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

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
    from app.admin.routes import bp as admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(documents_bp)
    app.register_blueprint(jobs_bp)
    app.register_blueprint(applications_bp)
    app.register_blueprint(admin_bp)

    register_error_handlers(app)
    register_cli(app)

    return app


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
