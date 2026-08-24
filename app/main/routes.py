from datetime import datetime

from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user

from app.models.document import Document
from app.models.job import SavedJob, Job, JobRadarStatus
from app.models.application import Application
from app.priority_digest import compute_priority_digest
from app.jobs.matching import get_or_compute_match

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


@bp.route("/health")
def health():
    # Used by the hosting platform to know the process is up - deliberately
    # no auth, no DB/dependency check, no version info: just "the WSGI
    # process is alive and answering requests."
    return "ok", 200


@bp.route("/diagnostics/arbeitsagentur-cors-test")
def arbeitsagentur_cors_test():
    # Temporary diagnostic, not a feature - answers whether a browser
    # request to the Arbeitsagentur Jobsuche API works from *our* deployed
    # origin specifically (server-side calls are confirmed blocked; this
    # checks the client-side path). No auth, deliberately unlinked from
    # navigation. Remove this route + its template + the matching
    # connect-src CSP carve-out (app/security_headers.py,
    # DIAGNOSTIC_CORS_TEST_PATH) once the finding is confirmed either way.
    return render_template("diagnostics/arbeitsagentur_cors_test.html")


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

    radar_status = JobRadarStatus.query.filter_by(user_id=current_user.id).first()
    radar_jobs = []
    if radar_status and radar_status.new_job_ids:
        jobs_by_id = {j.id: j for j in Job.query.filter(Job.id.in_(radar_status.new_job_ids)).all()}
        radar_jobs = [jobs_by_id[jid] for jid in radar_status.new_job_ids if jid in jobs_by_id]
    # deterministic, no AI call - same cheap per-result computation search() already does
    radar_matches = {job.id: get_or_compute_match(current_user, job) for job in radar_jobs}

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
        radar_status=radar_status,
        radar_jobs=radar_jobs,
        radar_matches=radar_matches,
    )


@bp.route("/digest")
@login_required
def priority_digest():
    return render_template("main/digest.html", items=compute_priority_digest(current_user))
