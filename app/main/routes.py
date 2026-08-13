from datetime import datetime

from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user

from app.models.document import Document
from app.models.job import SavedJob
from app.models.application import Application
from app.priority_digest import compute_priority_digest

bp = Blueprint("main", __name__)


def _time_of_day_greeting():
    # Server local time - a reasonable default for now; per-user timezone
    # would need a stored profile preference, tracked as future polish.
    hour = datetime.now().hour
    if hour < 12:
        return "Good morning"
    if hour < 18:
        return "Good afternoon"
    return "Good evening"


@bp.route("/")
def landing():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    return render_template("landing.html")


@bp.route("/dashboard")
@login_required
def dashboard():
    profile = current_user.profile
    doc_count = Document.query.filter_by(user_id=current_user.id).count()
    has_cv = Document.query.filter_by(user_id=current_user.id, is_primary_cv=True).first() is not None
    saved_job_count = SavedJob.query.filter_by(user_id=current_user.id).count()

    applications = Application.query.filter_by(user_id=current_user.id).all()
    applications_sent = sum(1 for a in applications if a.status not in ("preparing", "ready"))
    interviews = sum(1 for a in applications if a.status == "interview")

    return render_template(
        "main/dashboard.html",
        greeting=_time_of_day_greeting(),
        profile=profile,
        doc_count=doc_count,
        has_cv=has_cv,
        saved_job_count=saved_job_count,
        applications_count=len(applications),
        applications_sent=applications_sent,
        interviews=interviews,
        completeness=profile.completeness_percent() if profile else 0,
    )


@bp.route("/digest")
@login_required
def priority_digest():
    return render_template("main/digest.html", items=compute_priority_digest(current_user))
