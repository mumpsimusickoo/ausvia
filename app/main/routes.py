from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user

from app.models.document import Document
from app.models.job import SavedJob

bp = Blueprint("main", __name__)


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

    return render_template(
        "main/dashboard.html",
        profile=profile,
        doc_count=doc_count,
        has_cv=has_cv,
        saved_job_count=saved_job_count,
        completeness=profile.completeness_percent() if profile else 0,
    )
