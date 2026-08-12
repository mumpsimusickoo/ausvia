from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, current_user

from app.extensions import db, limiter
from app.models.job import Company, Job
from app.companies.insights import get_company_insight, generate_company_insight
from app.ai.provider import AIProviderError
from app.utils.logging import log_event

bp = Blueprint("companies", __name__, url_prefix="/companies")


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
    return render_template("companies/detail.html", company=company, jobs=jobs, insight=insight)


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
