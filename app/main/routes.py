from datetime import date, datetime

from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, current_user

from app.ai.dashboard_insight import MIN_APPLICATIONS_FOR_INSIGHT, generate_dashboard_insight, get_dashboard_insight
from app.ai.provider import AIProviderError
from app.applications.status_route import latest_transition_at
from app.models.job import SavedJob, JobRadarStatus
from app.models.application import Application
from app.priority_digest import ACTIVE_STATUSES, TERMINAL_STATUSES, compute_priority_digest
from app.jobs.matching import get_or_compute_match
from app.utils.logging import log_event

bp = Blueprint("main", __name__)

# Dashboard applications table: a quick-glance list, not the full history -
# "View all" goes to the real applications list page (out of this pass's
# scope). Capped rather than paginated, matching every other dashboard
# rail card's "show a handful, link to the rest" shape.
DASHBOARD_APPLICATIONS_LIMIT = 8


def _time_of_day_greeting():
    # Server local time - a reasonable default for now; per-user timezone
    # would need a stored profile preference, tracked as future polish.
    hour = datetime.now().hour
    if hour < 12:
        return "Good morning"
    if hour < 18:
        return "Good afternoon"
    return "Good evening"


def _relative_date(dt):
    """Screens pass 3 (Dashboard, 2026-08-27): humanized date for the
    applications table and the hero card's staleness marker. Absolute
    beyond 13 days - a relative date stops being useful ("47 days ago"
    reads worse than the actual date) and the bundle's own dashboard mock
    mixes relative and absolute for exactly this reason (recent items get
    "seit 3 Tagen"/"gestern", an older one just shows "27.08.2026")."""
    if dt is None:
        return "—"
    days = (datetime.now() - dt).days
    if days <= 0:
        return "today"
    if days == 1:
        return "yesterday"
    if days < 14:
        return f"{days} days ago"
    return dt.strftime("%d.%m.%Y")


def _situation_summary(digest_items):
    """One real sentence, not the bundle's literal text - computed from
    actual digest data (Screens pass 3, 2026-08-27). "Nothing urgent" is
    the honest default for a healthy account, not an edge case to
    apologize for."""
    if not digest_items:
        return "Nothing urgent right now — good time to keep applying."
    n = len(digest_items)
    summary = f"{n} item{'s' if n != 1 else ''} need{'s' if n == 1 else ''} your attention this week."
    if any("deadline" in reason.lower() for item in digest_items for reason in item.reasons):
        summary += " One has a deadline coming up."
    return summary


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
    saved_job_count = SavedJob.query.filter_by(user_id=current_user.id).count()

    applications = Application.query.filter_by(user_id=current_user.id).all()
    applications_sent = sum(1 for a in applications if a.status not in ("preparing", "ready"))
    interviews = sum(1 for a in applications if a.status == "interview")
    # Was hardcoded to 0 - compute_priority_digest()'s own per-application
    # check already identifies exactly this ("Follow-up date has arrived");
    # counting it directly here is the same real signal, not a second
    # definition of "due" to keep in sync.
    today = date.today()
    follow_ups_due = sum(1 for a in applications if a.follow_up_date and a.follow_up_date <= today)
    active_count = sum(1 for a in applications if a.status in ACTIVE_STATUSES)
    terminal_count = sum(1 for a in applications if a.status in TERMINAL_STATUSES)

    digest_items = compute_priority_digest(current_user)
    hero_item = digest_items[0] if digest_items else None
    hero_staleness = None
    hero_application = None
    if hero_item and hero_item.kind == "application":
        hero_application = next((a for a in applications if a.id == hero_item.url_kwargs.get("application_id")), None)
        if hero_application:
            days = (datetime.now() - latest_transition_at(hero_application)).days
            if days >= 1:
                hero_staleness = f"unchanged for {days} day{'s' if days != 1 else ''}"

    dashboard_applications = sorted(applications, key=latest_transition_at, reverse=True)[:DASHBOARD_APPLICATIONS_LIMIT]
    applications_table = [
        {"application": a, "date_label": _relative_date(latest_transition_at(a))}
        for a in dashboard_applications
    ]

    radar_status = JobRadarStatus.query.filter_by(user_id=current_user.id).first()
    radar_new_count = radar_status.new_job_count if radar_status else 0

    insight = get_dashboard_insight(current_user) if len(applications) >= MIN_APPLICATIONS_FOR_INSIGHT else None

    return render_template(
        "main/dashboard.html",
        greeting=_time_of_day_greeting(),
        # A brand-new invite-only account: distinguishes "nothing urgent"
        # (healthy) from "nothing here yet" (needs a first action) so the
        # empty-state copy can tell them apart honestly.
        is_brand_new=(len(applications) == 0 and saved_job_count == 0),
        profile=profile,
        today_label=datetime.now().strftime("%A, %d %B %Y").upper(),
        situation_summary=_situation_summary(digest_items),
        saved_job_count=saved_job_count,
        applications_count=len(applications),
        applications_sent=applications_sent,
        interviews=interviews,
        follow_ups_due=follow_ups_due,
        active_count=active_count,
        terminal_count=terminal_count,
        completeness=profile.completeness_percent() if profile else 0,
        completeness_missing=[label for label, ok in profile.completeness_checklist() if not ok] if profile else [],
        digest_items=digest_items,
        hero_item=hero_item,
        hero_staleness=hero_staleness,
        applications_table=applications_table,
        applications_shown_all=len(applications) <= DASHBOARD_APPLICATIONS_LIMIT,
        hero_application=hero_application,
        radar_status=radar_status,
        radar_new_count=radar_new_count,
        dashboard_insight=insight,
        min_applications_for_insight=MIN_APPLICATIONS_FOR_INSIGHT,
    )


@bp.route("/dashboard/insight", methods=["POST"])
@login_required
def generate_insight():
    applications = Application.query.filter_by(user_id=current_user.id).all()
    if len(applications) < MIN_APPLICATIONS_FOR_INSIGHT:
        flash("Add at least two applications before generating a cross-application insight.", "error")
        return redirect(url_for("main.dashboard"))

    match_by_job_id = {a.job_id: get_or_compute_match(current_user, a.job) for a in applications}
    try:
        generate_dashboard_insight(current_user, applications, match_by_job_id)
        flash("Insight generated.", "success")
    except AIProviderError as e:
        flash(str(e), "error")
        log_event("ai", f"Dashboard insight generation failed: {e}", level="warning", user_id=current_user.id)
    return redirect(url_for("main.dashboard"))


@bp.route("/digest")
@login_required
def priority_digest():
    return render_template("main/digest.html", items=compute_priority_digest(current_user))
