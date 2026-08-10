from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user

from app.extensions import db
from app.models.job import Job, SavedJob
from app.jobs.forms import SearchForm, ManualImportUrlForm, ManualImportReviewForm
from app.jobs.ingest import ingest_search
from app.jobs.manual_import import fetch_and_extract_text, FetchFailed
from app.jobs.adapters.base import NormalizedJob
from app.jobs.dedupe import find_or_create_canonical_job
from app.utils.logging import log_event

bp = Blueprint("jobs", __name__, url_prefix="/jobs")


@bp.route("/", methods=["GET"])
@login_required
def search():
    form = SearchForm(request.args, meta={"csrf": False})
    results = []
    ingest_errors = []

    if form.keywords.data:
        if form.validate():
            outcome = ingest_search(form.keywords.data, location=form.location.data or None)
            ingest_errors = outcome.errors

            query = Job.query.filter(Job.title.ilike(f"%{form.keywords.data}%"))
            if form.location.data:
                query = query.filter(Job.location.ilike(f"%{form.location.data}%"))
            results = query.order_by(Job.discovered_at.desc()).limit(50).all()
        else:
            flash("Please enter valid search terms.", "error")

    saved_job_ids = {sj.job_id for sj in SavedJob.query.filter_by(user_id=current_user.id).all()}

    return render_template(
        "jobs/search.html",
        form=form,
        results=results,
        ingest_errors=ingest_errors,
        saved_job_ids=saved_job_ids,
        searched=bool(form.keywords.data),
    )


@bp.route("/saved")
@login_required
def saved():
    saved_jobs = (
        SavedJob.query.filter_by(user_id=current_user.id).order_by(SavedJob.saved_at.desc()).all()
    )
    return render_template("jobs/saved.html", saved_jobs=saved_jobs)


@bp.route("/<int:job_id>")
@login_required
def detail(job_id):
    job = db.get_or_404(Job, job_id)
    is_saved = SavedJob.query.filter_by(user_id=current_user.id, job_id=job.id).first() is not None
    return render_template("jobs/detail.html", job=job, is_saved=is_saved)


@bp.route("/<int:job_id>/save", methods=["POST"])
@login_required
def save(job_id):
    job = db.get_or_404(Job, job_id)
    if not SavedJob.query.filter_by(user_id=current_user.id, job_id=job.id).first():
        db.session.add(SavedJob(user_id=current_user.id, job_id=job.id))
        db.session.commit()
        flash("Saved.", "success")
    return redirect(request.referrer or url_for("jobs.detail", job_id=job.id))


@bp.route("/<int:job_id>/unsave", methods=["POST"])
@login_required
def unsave(job_id):
    entry = SavedJob.query.filter_by(user_id=current_user.id, job_id=job_id).first()
    if entry:
        db.session.delete(entry)
        db.session.commit()
        flash("Removed from saved jobs.", "info")
    return redirect(request.referrer or url_for("jobs.saved"))


@bp.route("/import", methods=["GET"])
@login_required
def import_start():
    return render_template(
        "jobs/import.html",
        url_form=ManualImportUrlForm(),
        review_form=ManualImportReviewForm(),
        show_review=False,
    )


@bp.route("/import/fetch", methods=["POST"])
@login_required
def import_fetch():
    url_form = ManualImportUrlForm()
    review_form = ManualImportReviewForm()

    if not url_form.validate_on_submit():
        flash("Please enter a valid URL.", "error")
        return render_template("jobs/import.html", url_form=url_form, review_form=review_form, show_review=False)

    try:
        extracted = fetch_and_extract_text(url_form.url.data)
    except FetchFailed as e:
        flash(str(e), "error")
        log_event("job_source", "Manual import fetch failed.", level="warning", user_id=current_user.id)
        review_form.application_url.data = url_form.url.data
        return render_template("jobs/import.html", url_form=url_form, review_form=review_form, show_review=True)

    review_form.title.data = extracted["page_title"][:500]
    review_form.description.data = extracted["text"]
    review_form.application_url.data = url_form.url.data
    flash(
        "Page fetched. Please review and fill in the title/company/location - "
        "automatic extraction only pulls raw text, it doesn't guess structured fields.",
        "info",
    )
    return render_template("jobs/import.html", url_form=url_form, review_form=review_form, show_review=True)


@bp.route("/import/save", methods=["POST"])
@login_required
def import_save():
    review_form = ManualImportReviewForm()
    if not review_form.validate_on_submit():
        flash("Please fill in at least the job title and company.", "error")
        return render_template(
            "jobs/import.html", url_form=ManualImportUrlForm(), review_form=review_form, show_review=True
        )

    normalized = NormalizedJob(
        source="manual",
        title=review_form.title.data,
        company_name=review_form.company_name.data,
        location=review_form.location.data or None,
        start_date=review_form.start_date.data or None,
        application_url=review_form.application_url.data or None,
        source_url=review_form.application_url.data or None,
        description=review_form.description.data or None,
        raw={"imported_by_user_id": current_user.id},
    )
    job, created = find_or_create_canonical_job(normalized)
    log_event(
        "job_source",
        f"Manual job import ({'new' if created else 'matched existing'}).",
        user_id=current_user.id,
    )
    flash("Job imported." if created else "This matched an already-known opportunity - merged.", "success")
    return redirect(url_for("jobs.detail", job_id=job.id))
