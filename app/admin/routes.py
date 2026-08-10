from datetime import datetime, time

from flask import Blueprint, render_template, redirect, url_for, flash, abort
from flask_login import login_required, current_user

from app.extensions import db
from app.models import User, InvitationCode, SystemLog, Document, Job, JobSourceSetting
from app.models.access_code import generate_code
from app.utils.logging import log_event
from app.admin.forms import CreateCodeForm
from app.jobs.adapters.manager import ensure_source_settings_seeded

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.before_request
@login_required
def _guard():
    # Runs before every route in this blueprint; login_required above handles
    # "not logged in", this handles "logged in but not an admin".
    if not current_user.is_admin:
        abort(403)


@bp.route("/")
def overview():
    stats = {
        "total_users": User.query.count(),
        "active_users": User.query.filter_by(is_active=True).count(),
        "active_codes": InvitationCode.query.filter_by(is_active=True).count(),
        "documents_stored": Document.query.count(),
        "jobs_indexed": Job.query.count(),
    }
    recent_logs = SystemLog.query.order_by(SystemLog.created_at.desc()).limit(20).all()
    return render_template("admin/overview.html", stats=stats, recent_logs=recent_logs)


@bp.route("/users")
def users():
    all_users = User.query.order_by(User.created_at.desc()).all()
    return render_template("admin/users.html", users=all_users)


@bp.route("/users/<int:user_id>/toggle-active", methods=["POST"])
def toggle_user_active(user_id):
    user = db.get_or_404(User, user_id)
    if user.id == current_user.id:
        flash("You can't deactivate your own account.", "error")
        return redirect(url_for("admin.users"))
    user.is_active = not user.is_active
    db.session.commit()
    log_event(
        "admin",
        f"Admin {'activated' if user.is_active else 'deactivated'} a user account.",
        user_id=current_user.id,
    )
    flash(f"User {'activated' if user.is_active else 'deactivated'}.", "success")
    return redirect(url_for("admin.users"))


@bp.route("/codes", methods=["GET", "POST"])
def codes():
    form = CreateCodeForm()
    if form.validate_on_submit():
        code_value = generate_code()
        while InvitationCode.query.filter_by(code=code_value).first():
            code_value = generate_code()

        expires_at = None
        if form.expires_at.data:
            expires_at = datetime.combine(form.expires_at.data, time.max)

        code = InvitationCode(
            code=code_value,
            code_type=form.code_type.data,
            max_uses=form.max_uses.data,
            expires_at=expires_at,
            notes=form.notes.data or None,
            created_by_id=current_user.id,
        )
        db.session.add(code)
        db.session.commit()
        log_event("admin", f"Invitation code created (type={code.code_type}).", user_id=current_user.id)
        flash(f"Code created: {code_value}", "success")
        return redirect(url_for("admin.codes"))

    all_codes = InvitationCode.query.order_by(InvitationCode.created_at.desc()).all()
    return render_template("admin/codes.html", form=form, codes=all_codes)


@bp.route("/codes/<int:code_id>/revoke", methods=["POST"])
def revoke_code(code_id):
    code = db.get_or_404(InvitationCode, code_id)
    code.is_active = False
    db.session.commit()
    log_event("admin", "Invitation code revoked.", user_id=current_user.id)
    flash("Code revoked.", "info")
    return redirect(url_for("admin.codes"))


@bp.route("/job-sources")
def job_sources():
    ensure_source_settings_seeded()
    settings = JobSourceSetting.query.order_by(JobSourceSetting.source_name).all()
    return render_template("admin/job_sources.html", settings=settings)


@bp.route("/job-sources/<int:setting_id>/toggle", methods=["POST"])
def toggle_job_source(setting_id):
    setting = db.get_or_404(JobSourceSetting, setting_id)
    setting.is_enabled = not setting.is_enabled
    db.session.commit()
    log_event(
        "admin",
        f"Job source '{setting.source_name}' {'enabled' if setting.is_enabled else 'disabled'}.",
        user_id=current_user.id,
    )
    flash(f"{setting.display_name} {'enabled' if setting.is_enabled else 'disabled'}.", "success")
    return redirect(url_for("admin.job_sources"))
