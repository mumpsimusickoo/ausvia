from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, current_user

from app.extensions import db, limiter
from app.models.application import Application
from app.models.job import Company, Job
from app.companies.insights import get_company_insight, generate_company_insight
from app.jobs.matching import get_or_compute_matches, match_label
from app.jobs.routes import _profile_has_scorable_data
from app.ai.provider import AIProviderError
from app.utils.logging import log_event

bp = Blueprint("companies", __name__, url_prefix="/companies")


def _company_initials(name):
    # Screens pass 6 (Company Detail, 2026-08-28): same first-two-words
    # rule jobs/detail.html already uses for its own company-initials
    # avatar (see that template's company_initials, computed inline) -
    # reused as the same logic here rather than a second convention.
    words = name.split() if name else []
    first = words[0][0] if words else ""
    second = words[1][0] if len(words) > 1 else ""
    return (first + second).upper() or "?"


@bp.route("/<int:company_id>")
@login_required
def detail(company_id):
    company = db.get_or_404(Company, company_id)
    jobs = (
        Job.query.filter_by(company_id=company.id)
        .order_by(Job.discovered_at.desc())
        .all()
    )
    insight = get_company_insight(current_user, company)

    # Screens pass 4 (Find Ausbildung)'s batched matcher, per the task's
    # own instruction - a company with several openings would otherwise
    # repeat the N+1 get_or_compute_match() pattern that pass fixed.
    match_by_job_id = get_or_compute_matches(current_user, jobs)
    # Same fix that pass needed for its own results list: a wholly blank
    # profile can still make compute_match() return a positive score (see
    # _score_location()'s "no preference = open to anywhere" default) -
    # profile_insufficient forces every position's score display to "Not
    # scored" rather than repeating that fabricated-100 bug here too.
    profile_insufficient = bool(jobs) and not _profile_has_scorable_data(current_user.profile)

    # "Listings on file" (facts panel) is deliberately the raw JobListing
    # count, not len(jobs) - a genuinely different, real number whenever
    # this company's postings have been merged from more than one source/
    # duplicate (see app/jobs/dedupe.py), same duplicates-are-honest-signal
    # reasoning as Find Ausbildung's "N duplicates merged" line. Equal to
    # the position count only when nothing was ever merged.
    listings_on_file = sum(len(job.listings) for job in jobs)
    first_seen = min((job.discovered_at for job in jobs), default=None)
    last_checked = max((job.last_checked_at for job in jobs), default=None)

    applications = (
        Application.query.filter_by(user_id=current_user.id)
        .join(Job, Application.job_id == Job.id)
        .filter(Job.company_id == company.id)
        .order_by(Application.updated_at.desc())
        .all()
    )

    return render_template(
        "companies/detail.html",
        company=company,
        jobs=jobs,
        insight=insight,
        match_by_job_id=match_by_job_id,
        match_label=match_label,
        profile_insufficient=profile_insufficient,
        listings_on_file=listings_on_file,
        first_seen=first_seen,
        last_checked=last_checked,
        applications=applications,
        company_initials=_company_initials(company.name),
    )


@bp.route("/<int:company_id>/generate-insight", methods=["POST"])
@login_required
@limiter.limit("30 per hour")
def generate_insight(company_id):
    company = db.get_or_404(Company, company_id)
    jobs = Job.query.filter_by(company_id=company.id).order_by(Job.discovered_at.desc()).all()
    try:
        generate_company_insight(current_user, company, jobs)
    except AIProviderError as e:
        flash(str(e), "error")
        log_event("ai", f"Company insight generation failed: {e}", level="warning", user_id=current_user.id)
    return redirect(url_for("companies.detail", company_id=company.id))
