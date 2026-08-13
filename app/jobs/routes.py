import json
from urllib.parse import quote

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user

from app.extensions import db
from app.models.job import Job, SavedJob
from app.models.manual_import import ManualImportBatch
from app.jobs.forms import SearchForm, ManualImportUrlForm, ManualImportReviewForm
from app.jobs.ingest import ingest_search
from app.jobs.manual_import import fetch_and_extract_text, FetchFailed
from app.jobs.adapters.base import NormalizedJob
from app.jobs.dedupe import find_or_create_canonical_job
from app.jobs.matching import get_or_compute_match, generate_narrative, generate_improvement_tips
from app.ai.provider import AIProviderError
from app.extensions import limiter
from app.utils.logging import log_event

bp = Blueprint("jobs", __name__, url_prefix="/jobs")

MAX_BATCH_URLS = 10
MAX_BOOKMARKLET_TEXT_CHARS = 8000


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
    # deterministic, no AI call - cheap enough to compute per result
    match_by_job_id = {job.id: get_or_compute_match(current_user, job) for job in results}

    return render_template(
        "jobs/search.html",
        form=form,
        results=results,
        ingest_errors=ingest_errors,
        saved_job_ids=saved_job_ids,
        match_by_job_id=match_by_job_id,
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
    match = get_or_compute_match(current_user, job)

    from app.models import Application

    application = Application.query.filter_by(user_id=current_user.id, job_id=job.id).first()

    return render_template(
        "jobs/detail.html", job=job, is_saved=is_saved, match=match, application=application
    )


@bp.route("/<int:job_id>/narrative", methods=["POST"])
@login_required
@limiter.limit("30 per hour")
def narrative(job_id):
    job = db.get_or_404(Job, job_id)
    match = get_or_compute_match(current_user, job)
    try:
        generate_narrative(current_user, job, match)
    except AIProviderError as e:
        flash(str(e), "error")
        log_event("ai", f"Narrative generation failed: {e}", level="warning", user_id=current_user.id)
    return redirect(url_for("jobs.detail", job_id=job.id))


@bp.route("/<int:job_id>/improve-tips", methods=["POST"])
@login_required
@limiter.limit("30 per hour")
def improve_tips(job_id):
    job = db.get_or_404(Job, job_id)
    match = get_or_compute_match(current_user, job)
    try:
        generate_improvement_tips(current_user, job, match)
    except AIProviderError as e:
        flash(str(e), "error")
        log_event("ai", f"Improvement tips generation failed: {e}", level="warning", user_id=current_user.id)
    return redirect(url_for("jobs.detail", job_id=job.id))


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


def _get_batch():
    return ManualImportBatch.query.filter_by(user_id=current_user.id).first()


def _parse_batch_urls(raw_text):
    """One URL per line, blanks ignored, de-duplicated preserving order,
    capped at MAX_BATCH_URLS. Returns (urls, was_truncated) - format/
    reachability validation happens per-URL in fetch_and_extract_text(),
    same as the original single-URL path, so a bad line doesn't reject the
    whole paste."""
    seen = set()
    urls = []
    truncated = False
    for line in (raw_text or "").splitlines():
        line = line.strip()
        if not line or line in seen:
            continue
        seen.add(line)
        if len(urls) >= MAX_BATCH_URLS:
            truncated = True
            continue
        urls.append(line)
    return urls, truncated


def _bookmarklet_href():
    """A javascript: bookmarklet that reads the CURRENTLY LOADED page's own
    title/URL/visible text straight out of the DOM - it never makes a
    request of its own, so there's nothing here for a site to block, and
    nothing that needs AUSVIA's permission to run (the user's own browser,
    reading what's already on their own screen).

    Handoff to AUSVIA: the captured data travels only as a URL *fragment*
    (the part after '#') on a window.open() to import_bookmarklet below.
    Fragments are never sent to any server by the browser - only AUSVIA's
    own same-origin JS on that page reads it (see import_bookmarklet.html) -
    so this never touches a third-party site's network requests, never
    needs CORS, and never needs a CSRF token to hand the data over (nothing
    is persisted at this step at all; the existing CSRF-protected
    import_save form is still what actually saves anything, unchanged).
    """
    origin = request.url_root.rstrip("/")
    target = f"{origin}{url_for('jobs.import_bookmarklet')}"
    js = (
        "(function(){"
        "var t=document.title||'';"
        "var u=location.href;"
        "var b=document.body;"
        "var x=b?(b.innerText||b.textContent||''):'';"
        f"x=x.trim().slice(0,{MAX_BOOKMARKLET_TEXT_CHARS});"
        "var p=encodeURIComponent(JSON.stringify({t:t,u:u,x:x}));"
        f"window.open({json.dumps(target)}+'#'+p,'_blank');"
        "})();"
    )
    return "javascript:" + quote(js)


def _render_import_page(url_form=None, review_form=None, show_review=False, batch=None):
    return render_template(
        "jobs/import.html",
        url_form=url_form or ManualImportUrlForm(),
        # formdata=None: a bare ManualImportReviewForm() constructed while
        # handling a POST request auto-binds to request.form by default
        # (standard Flask-WTF behavior) - fine when re-rendering after a
        # failed *review-form* submission (we want the user's typed values
        # back), wrong here, where this is a fresh form being rendered
        # after some *other* POST (e.g. the fetch form). Without this, a
        # field name collision would leak the previous request's values in.
        review_form=review_form or ManualImportReviewForm(formdata=None),
        show_review=show_review,
        batch=batch,
        max_batch_urls=MAX_BATCH_URLS,
        bookmarklet_href=_bookmarklet_href(),
    )


def _render_batch_review(batch):
    item = batch.current_item
    # formdata=None for the same reason as _render_import_page above: this
    # renders a fresh item's data, not a resubmission of the form being
    # built here - found via a real test failure where a failed item's
    # empty title field was silently pre-filled with the *previous* item's
    # just-submitted title, because plain ManualImportReviewForm() had
    # auto-bound to request.form from the save/skip POST that got us here.
    review_form = ManualImportReviewForm(formdata=None)
    review_form.batch_index.data = str(batch.current_index)

    if item["status"] == "fetched":
        review_form.title.data = item["page_title"]
        review_form.description.data = item["text"]
        review_form.application_url.data = item["url"]
    else:
        review_form.application_url.data = item["url"]
        flash(
            f"Couldn't fetch {item['url']}: {item['error']} "
            "Paste the text yourself below, or skip it.",
            "error",
        )

    return _render_import_page(review_form=review_form, show_review=True, batch=batch)


@bp.route("/import", methods=["GET"])
@login_required
def import_start():
    batch = _get_batch()
    if batch and not batch.is_complete:
        return _render_batch_review(batch)
    return _render_import_page()


@bp.route("/import/fetch", methods=["POST"])
@login_required
def import_fetch():
    url_form = ManualImportUrlForm()

    if not url_form.validate_on_submit():
        flash("Please paste at least one URL.", "error")
        return _render_import_page(url_form=url_form)

    urls, truncated = _parse_batch_urls(url_form.urls.data)
    if not urls:
        flash("Please paste at least one URL.", "error")
        return _render_import_page(url_form=url_form)

    # A new fetch replaces any existing incomplete batch for this user -
    # simpler than offering a "resume old batch or start new one" choice,
    # and matches this being a lightweight convenience tool, not a queue
    # someone is expected to juggle multiple of at once.
    existing = _get_batch()
    if existing:
        db.session.delete(existing)
        db.session.flush()

    items = []
    for url in urls:
        try:
            extracted = fetch_and_extract_text(url)
            items.append({
                "url": url,
                "status": "fetched",
                "page_title": extracted["page_title"][:500],
                "text": extracted["text"],
            })
        except FetchFailed as e:
            items.append({"url": url, "status": "failed", "error": str(e)})
            log_event("job_source", "Manual import fetch failed.", level="warning", user_id=current_user.id)

    batch = ManualImportBatch(user_id=current_user.id, items=items, current_index=0)
    db.session.add(batch)
    db.session.commit()

    succeeded = sum(1 for i in items if i["status"] == "fetched")
    failed = len(items) - succeeded
    if truncated:
        flash(f"Only the first {MAX_BATCH_URLS} URLs were used - that's the limit per batch.", "info")
    summary = f"Fetched {succeeded} of {len(items)} page{'s' if len(items) != 1 else ''} successfully."
    if failed:
        summary += f" {failed} failed - you'll get a chance to paste those in manually."
    flash(summary, "info" if succeeded else "error")

    return _render_batch_review(batch)


@bp.route("/import/save", methods=["POST"])
@login_required
def import_save():
    review_form = ManualImportReviewForm()
    batch = _get_batch()
    # Only treat this save as "advancing my in-progress batch" if the form
    # actually says it belongs to that batch's current item - otherwise an
    # unrelated save (bookmarklet, or a stray direct POST) while some batch
    # happens to be sitting in progress would silently consume a step of it.
    in_batch = (
        batch is not None
        and not batch.is_complete
        and review_form.batch_index.data == str(batch.current_index)
    )

    if not review_form.validate_on_submit():
        flash("Please fill in at least the job title and company.", "error")
        return _render_import_page(review_form=review_form, show_review=True, batch=batch if in_batch else None)

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

    if not in_batch:
        flash("Job imported." if created else "This matched an already-known opportunity - merged.", "success")
        return redirect(url_for("jobs.detail", job_id=job.id))

    items = list(batch.items)
    items[batch.current_index] = {**items[batch.current_index], "status": "saved"}
    batch.items = items
    batch.current_index += 1
    db.session.commit()

    if not batch.is_complete:
        flash("Job imported." if created else "Matched an already-known opportunity - merged.", "success")
        return _render_batch_review(batch)

    return _finish_batch(batch, last_job_id=job.id)


@bp.route("/import/skip", methods=["POST"])
@login_required
def import_skip():
    batch = _get_batch()
    if not batch or batch.is_complete:
        return redirect(url_for("jobs.import_start"))

    items = list(batch.items)
    items[batch.current_index] = {**items[batch.current_index], "status": "skipped"}
    batch.items = items
    batch.current_index += 1
    db.session.commit()

    if not batch.is_complete:
        return _render_batch_review(batch)
    return _finish_batch(batch, last_job_id=None)


@bp.route("/import/cancel", methods=["POST"])
@login_required
def import_cancel():
    batch = _get_batch()
    if batch:
        db.session.delete(batch)
        db.session.commit()
        flash("Import batch cancelled.", "info")
    return redirect(url_for("jobs.import_start"))


def _finish_batch(batch, last_job_id):
    saved_count = sum(1 for i in batch.items if i["status"] == "saved")
    not_imported = len(batch.items) - saved_count
    db.session.delete(batch)
    db.session.commit()

    summary = f"Batch complete: {saved_count} imported"
    summary += f", {not_imported} not imported." if not_imported else "."
    flash(summary, "success" if saved_count else "info")

    if last_job_id:
        return redirect(url_for("jobs.detail", job_id=last_job_id))
    return redirect(url_for("jobs.search"))


@bp.route("/import/bookmarklet", methods=["GET"])
@login_required
def import_bookmarklet():
    """Landing page for the bookmarklet (see _bookmarklet_href above). Just
    renders the same review form as every other import path - the actual
    prefill happens client-side, reading the URL fragment the bookmarklet
    attached, via a nonce'd inline script in the template. Nothing is
    persisted here; "Save opportunity" still posts to the normal
    CSRF-protected import_save route above like any other save."""
    return render_template("jobs/import_bookmarklet.html", review_form=ManualImportReviewForm())
