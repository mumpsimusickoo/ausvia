from datetime import datetime, time

from flask import Blueprint, render_template, redirect, url_for, flash, abort
from flask_babel import gettext as _
from flask_login import login_required, current_user

from app.extensions import db
from app.jobs.adapters.jooble import JOOBLE_LIFETIME_BUDGET
from app.models import User, InvitationCode, SystemLog, Document, Job, JobSourceSetting, AIUsage
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
    # Jooble admin-only scoping pass (2026-08-29): its request budget is a
    # 500-request LIFETIME cap with no reset, so the running total needs
    # to be visible somewhere an admin will actually see it before it
    # runs out blind - see app/jobs/adapters/jooble.py's
    # record_jooble_request() for where this count is incremented.
    jooble_setting = JobSourceSetting.query.filter_by(source_name="jooble").first()
    jooble_used = jooble_setting.request_count if jooble_setting else 0
    stats["jooble_requests_used"] = f"{jooble_used} / {JOOBLE_LIFETIME_BUDGET}"
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
        flash(_("You can't deactivate your own account."), "error")
        return redirect(url_for("admin.users"))
    user.is_active = not user.is_active
    db.session.commit()
    log_event(
        "admin",
        f"Admin {'activated' if user.is_active else 'deactivated'} a user account.",
        user_id=current_user.id,
    )
    flash(_("User activated.") if user.is_active else _("User deactivated."), "success")
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
        flash(_("Code created: %(code)s", code=code_value), "success")
        return redirect(url_for("admin.codes"))

    all_codes = InvitationCode.query.order_by(InvitationCode.created_at.desc()).all()
    return render_template("admin/codes.html", form=form, codes=all_codes)


@bp.route("/codes/<int:code_id>/revoke", methods=["POST"])
def revoke_code(code_id):
    code = db.get_or_404(InvitationCode, code_id)
    code.is_active = False
    db.session.commit()
    log_event("admin", "Invitation code revoked.", user_id=current_user.id)
    flash(_("Code revoked."), "info")
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
    flash(
        _("%(source)s enabled.", source=setting.display_name)
        if setting.is_enabled
        else _("%(source)s disabled.", source=setting.display_name),
        "success",
    )
    return redirect(url_for("admin.job_sources"))


@bp.route("/ai-usage")
def ai_usage():
    entries = AIUsage.query.order_by(AIUsage.created_at.desc()).limit(100).all()
    totals = {
        "calls": AIUsage.query.count(),
        "input_tokens": db.session.query(db.func.coalesce(db.func.sum(AIUsage.input_tokens), 0)).scalar(),
        "output_tokens": db.session.query(db.func.coalesce(db.func.sum(AIUsage.output_tokens), 0)).scalar(),
    }
    return render_template("admin/ai_usage.html", entries=entries, totals=totals)


@bp.route("/components")
def components():
    """Component layer pass, 2026-08-25: living reference for every macro in
    app/templates/_components.html - not a real product screen, no data
    reads/writes. Admin-only (this blueprint's before_request guard) so it
    can't ship to real users by accident, same as every other page here -
    deliberately not a separate DEBUG-only route, since that would exempt
    it from the auth check entirely rather than just from the nav."""
    # i18n pass 1, 2026-08-28: real render-time value for the
    # format_local_date() demo - the currency figure has no live data to
    # draw on (see the template's own note), so it stays a literal.
    return render_template("admin/components.html", now=datetime.now())
