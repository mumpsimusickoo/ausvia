import json
import re
from datetime import date
from urllib.parse import quote

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_babel import gettext as _
from flask_babel import ngettext
from flask_login import login_required, current_user

from app.extensions import db
from app.models.job import Job, JobListing, SavedJob
from app.models.manual_import import ManualImportBatch
from app.jobs.forms import SearchForm, ManualImportUrlForm, ManualImportReviewForm
from app.jobs.ingest import ingest_search, enrich_job_detail
from app.jobs.radar import run_job_radar
from app.jobs.adapters.manager import ADMIN_ONLY_SOURCES, KNOWN_SOURCES, get_enabled_adapter_names
from app.ai.job_requirements_extraction import extract_job_requirements, should_retry_requirements_extraction
from app.tasks.runner import submit_task
from app.jobs.manual_import import fetch_and_extract_text, FetchFailed
from app.jobs.adapters.base import NormalizedJob
from app.jobs.dedupe import find_or_create_canonical_job
from app.jobs.matching import (
    get_or_compute_match, get_or_compute_matches, generate_narrative,
    generate_improvement_tips, match_label, summarize_match_line,
)
from app.ai.job_explainer import get_job_explainer, generate_job_explainer
from app.ai.provider import AIProviderError
from app.extensions import limiter
from app.utils.logging import log_event

bp = Blueprint("jobs", __name__, url_prefix="/jobs")

MAX_BATCH_URLS = 10
MAX_BOOKMARKLET_TEXT_CHARS = 8000

# Screens pass 4 (Find Ausbildung), 2026-08-28: how many keyword/location
# matches to fetch, score, and display - one page, no pagination UI this
# pass (out of scope; every filter is a query param, so real pagination
# can be added later without changing how filters work). Sorting by match
# score means every candidate needs a score first (see
# get_or_compute_matches()'s docstring for the measured cost - even 100
# scored cold is ~440ms, comfortable), so this is sized for a sane single
# results page, not for scoring cost - a narrow trade keyword in this
# app's own dev data returns 13-89 matches; 40 keeps a strong keyword
# (78 "Elektroniker" matches, plus whatever a live search adds) from
# rendering as a hundred-card page.
SEARCH_CANDIDATE_LIMIT = 40


def _job_start_year(job):
    """Extracts a 4-digit year from Job.start_date - the same free-form
    field ("01.09.2027", "sofort", "2027", ...) and the same \\d{4}
    extraction app/ai/matching.py's _score_start_date() already uses for
    scoring, reused here for the year-range filter rather than a second
    parsing approach. None if start_date is empty or has no parseable
    year."""
    if not job.start_date:
        return None
    match = re.search(r"\d{4}", job.start_date)
    return int(match.group()) if match else None


def _profile_has_scorable_data(profile):
    """Whether compute_match() has anything real to evaluate against, at
    all - deliberately NOT the same check as a JobMatch's own
    recommendation == "insufficient_data" (found during Playwright
    verification, 2026-08-28: a genuinely blank profile, no Preference row
    at all, still scored some jobs 100/100 "Strong match", because
    _score_location() treats "no location preference set" as "open to
    anywhere" - a real 1.0 on its own, honest for a candidate who has
    actually stated other preferences but left location open, but wrong
    read as "nothing about this candidate is known" when NOTHING has been
    entered. compute_match()'s own possible==0 check doesn't catch this,
    since that one category still contributes weight - so a job with no
    skills/language/education requirements (most of them, see DECISIONS.md's
    German-level fill-rate numbers) plus a wholly empty profile can still
    produce a positive score from a default, not from anything the
    candidate provided. This checks for real candidate-entered data
    directly, not matching.py's scoring outcome - a search-page display
    decision (which score results to trust and show), not a change to how
    compute_match() itself scores anything."""
    if profile is None:
        return False
    if profile.skills or profile.languages or profile.education_entries:
        return True
    preference = profile.preference
    return bool(preference and (preference.locations or preference.desired_start_date))


def _query_without(*keys):
    """The current request's query params with the given key(s) removed -
    used to build each removable filter chip's href. Reads multi-value
    params (sources) as lists so removing one filter never silently drops
    another that happens to be multi-valued - query params, not session
    state, so filters stay shareable/bookmarkable and survive a reload."""
    kept = {}
    for key in request.args:
        if key in keys:
            continue
        values = request.args.getlist(key)
        kept[key] = values if len(values) > 1 else values[0]
    return kept


def _build_filter_chips(form, enabled_source_names):
    chips = []

    lo, hi = form.start_year_min.data, form.start_year_max.data
    if lo or hi:
        if lo and hi:
            label = _("Start %(lo)s–%(hi)s", lo=lo, hi=hi)
        elif lo:
            label = _("Start from %(lo)s", lo=lo)
        else:
            label = _("Start by %(hi)s", hi=hi)
        chips.append((label, url_for("jobs.search", **_query_without("start_year_min", "start_year_max"))))

    if form.min_score.data:
        chips.append((_("Score ≥ %(score)s", score=form.min_score.data), url_for("jobs.search", **_query_without("min_score"))))

    selected_sources = form.sources.data
    if selected_sources and set(selected_sources) != set(enabled_source_names):
        names = [KNOWN_SOURCES.get(s, s) for s in selected_sources]
        chips.append((", ".join(names), url_for("jobs.search", **_query_without("sources"))))

    return chips


@bp.route("/", methods=["GET"])
@login_required
def search():
    form = SearchForm(request.args, meta={"csrf": False})
    enabled_source_names = get_enabled_adapter_names()
    if not current_user.is_admin:
        # Jooble's lifetime request budget is reserved for the admin's own
        # use (see app/jobs/adapters/manager.py's ADMIN_ONLY_SOURCES) - a
        # regular user never sees it as a selectable source, and since
        # WTForms' SelectMultipleField rejects submitted values outside
        # its own .choices, this also blocks a hand-crafted ?sources=jooble
        # from reaching form.sources.data at all, not just from being
        # offered in the UI.
        enabled_source_names = [name for name in enabled_source_names if name not in ADMIN_ONLY_SOURCES]
    form.sources.choices = [(name, KNOWN_SOURCES.get(name, name)) for name in enabled_source_names]
    if not form.sources.data:
        # No explicit selection yet (fresh search, or every box left
        # checked) - every enabled source is active by default, matching
        # the bundle's own "alle 3 Quellen aktiv" starting state.
        form.sources.process_data(enabled_source_names)

    results = []
    unscored_results = []
    ingest_errors = []
    filter_chips = []
    result_meta = None
    match_by_job_id = {}
    profile_insufficient = False
    excluded_by_score = 0

    if form.keywords.data:
        if form.validate():
            outcome = ingest_search(
                form.keywords.data, location=form.location.data or None, admin=current_user.is_admin,
            )
            ingest_errors = outcome.errors

            query = Job.query.filter(Job.title.ilike(f"%{form.keywords.data}%"))
            if form.location.data:
                query = query.filter(Job.location.ilike(f"%{form.location.data}%"))
            # Always restricted to the selected sources - defaulting to
            # every *enabled* one, not "no filter at all" - a job whose
            # only listing is on a source that's disabled (or was never
            # configured) shouldn't surface just because the selection
            # happens to equal the full enabled set; the intro line
            # ("Searches X, Y, Z") would be lying otherwise. "manual" is
            # always included regardless of the toggle - it isn't a
            # searchable adapter to begin with (see KNOWN_SOURCES/
            # get_enabled_adapter_names()'s own docstrings), just the
            # user's own directly-imported jobs, which keyword search
            # found before this pass added a source filter at all and
            # shouldn't now disappear from it.
            selected_sources = form.sources.data or enabled_source_names
            query = query.filter(Job.listings.any(JobListing.source.in_([*selected_sources, "manual"])))
            candidate_jobs = query.order_by(Job.discovered_at.desc()).limit(SEARCH_CANDIDATE_LIMIT).all()

            if form.start_year_min.data:
                min_year = int(form.start_year_min.data)
                candidate_jobs = [j for j in candidate_jobs if (_job_start_year(j) or 0) >= min_year]
            if form.start_year_max.data:
                max_year = int(form.start_year_max.data)
                candidate_jobs = [j for j in candidate_jobs if (_job_start_year(j) or 9999) <= max_year]

            # Every candidate scored before sorting/filtering by score - see
            # get_or_compute_matches()'s docstring for why this is a single
            # batched call, not a per-card lazy one.
            match_by_job_id = get_or_compute_matches(current_user, candidate_jobs)
            profile_insufficient = bool(candidate_jobs) and not _profile_has_scorable_data(current_user.profile)

            min_score = int(form.min_score.data) if form.min_score.data else None
            scored_jobs = []
            for j in candidate_jobs:
                score = None if profile_insufficient else match_by_job_id[j.id].score
                if score is None:
                    # An unscoreable job is not a zero-scoring job (spec) -
                    # never dropped by a minimum-score filter, always shown,
                    # just kept in its own honestly-labeled section instead
                    # of blended into a numeric ranking it was never placed
                    # on. profile_insufficient forces every candidate down
                    # this path too, regardless of any individual score
                    # compute_match() happened to produce - see
                    # _profile_has_scorable_data()'s docstring for why that
                    # score can't be trusted when nothing real was entered.
                    unscored_results.append(j)
                elif min_score is not None and score < min_score:
                    excluded_by_score += 1
                else:
                    scored_jobs.append(j)

            if form.sort.data == "newest":
                scored_jobs.sort(key=lambda j: j.discovered_at, reverse=True)
            else:
                scored_jobs.sort(key=lambda j: (-match_by_job_id[j.id].score, -j.discovered_at.timestamp()))
            unscored_results.sort(key=lambda j: j.discovered_at, reverse=True)
            results = scored_jobs

            all_jobs = results + unscored_results
            all_sources = set()
            duplicates_merged = 0
            for j in all_jobs:
                all_sources.update(j.sources)
                if len(j.listings) > 1:
                    duplicates_merged += len(j.listings) - 1
            result_meta = {
                "count": len(all_jobs),
                "source_count": len(all_sources),
                "duplicates_merged": duplicates_merged,
            }
            filter_chips = _build_filter_chips(form, enabled_source_names)
        else:
            flash(_("Please enter valid search terms."), "error")

    saved_job_ids = {sj.job_id for sj in SavedJob.query.filter_by(user_id=current_user.id).all()}

    return render_template(
        "jobs/search.html",
        form=form,
        results=results,
        unscored_results=unscored_results,
        ingest_errors=ingest_errors,
        saved_job_ids=saved_job_ids,
        match_by_job_id=match_by_job_id,
        searched=bool(form.keywords.data),
        filter_chips=filter_chips,
        result_meta=result_meta,
        profile_insufficient=profile_insufficient,
        excluded_by_score=excluded_by_score,
        match_label=match_label,
        summarize_match_line=summarize_match_line,
        source_display_names=[KNOWN_SOURCES.get(n, n) for n in enabled_source_names],
        today=date.today(),
    )


@bp.route("/check-now", methods=["POST"])
@login_required
@limiter.limit("10 per hour")
def check_now():
    """On-demand job radar (design-audit decision, 2026-08-24) - triggered
    only by this request, never by a scheduler. See app/jobs/radar.py."""
    try:
        new_jobs, errors = run_job_radar(current_user)
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("main.dashboard"))

    if new_jobs:
        flash(ngettext("%(num)d new listing found.", "%(num)d new listings found.", len(new_jobs)), "success")
    else:
        flash(_("No new listings found for your preferences right now."), "info")
    for source, message in errors:
        # `message` is an adapter-level diagnostic string (timeout, rate
        # limit, etc. - app/jobs/adapters/*), deliberately not translated
        # this pass - see DECISIONS.md's i18n pass 2 entry for the same
        # call made on JobMatch gap notes, for the same reason (a large,
        # separate surface, not this pass's own UI copy).
        flash(f"{source}: {message}", "error")
    return redirect(url_for("main.dashboard"))


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
    # Lazy detail-fetch-on-open (job-source integration follow-up): before
    # computing the match below, so a first-time enrichment's improved
    # education_requirements - and the cache invalidation it triggers -
    # are reflected in *this* view too, not just future ones.
    enriched = enrich_job_detail(job)
    # Chained off a real enrichment OR a previously-failed extraction
    # that's eligible for a backoff-gated retry (extraction retry pass,
    # 2026-08-29 - see should_retry_requirements_extraction()'s own
    # docstring for the state machine and app/jobs/routes.py isn't the
    # only caller: extract_job_requirements() itself double-checks the
    # attempt cap too) - not every view regardless of state, and off the
    # request entirely either way: a real AI call has meaningfully more
    # latency than the fast inline detail fetch above, and unlike that
    # fetch, there's no reason the current viewer needs to wait for it -
    # the page is fully usable without extracted skills, same as before
    # this feature existed.
    if enriched or should_retry_requirements_extraction(job):
        submit_task(current_user, "job_requirements_extraction", extract_job_requirements, job.id, current_user.id)
    is_saved = SavedJob.query.filter_by(user_id=current_user.id, job_id=job.id).first() is not None
    match = get_or_compute_match(current_user, job)

    from app.models import Application

    application = Application.query.filter_by(user_id=current_user.id, job_id=job.id).first()

    # Screens pass 1 (Job Detail), 2026-08-27: cross-references a gap's
    # label against job.skills to flag the matching requirement tag err-
    # toned in the template (chip_attribute(gap=True)) - a gap's label for
    # the "skills" category is always the literal skill string (see
    # app/ai/matching.py::_score_skills), so an exact-string match is
    # correct here, not a heuristic.
    gap_skill_labels = {g["label"] for g in (match.gaps or [])} & set(job.skills or [])

    deadline_days_left = None
    if job.application_deadline:
        deadline_days_left = (job.application_deadline - date.today()).days

    company_open_positions = None
    if job.company_id:
        company_open_positions = Job.query.filter_by(company_id=job.company_id, status="active").count()

    return render_template(
        "jobs/detail.html", job=job, is_saved=is_saved, match=match, application=application,
        explainer=get_job_explainer(current_user, job),
        gap_skill_labels=gap_skill_labels,
        deadline_days_left=deadline_days_left,
        company_open_positions=company_open_positions,
    )


@bp.route("/<int:job_id>/explain", methods=["POST"])
@login_required
@limiter.limit("30 per hour")
def explain(job_id):
    job = db.get_or_404(Job, job_id)
    try:
        generate_job_explainer(current_user, job)
        flash(_("Plain-language summary generated."), "success")
    except AIProviderError as e:
        flash(str(e), "error")
        log_event("ai", f"Job explainer generation failed: {e}", level="warning", user_id=current_user.id)
    return redirect(url_for("jobs.detail", job_id=job.id))


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
        flash(_("Saved."), "success")
    return redirect(request.referrer or url_for("jobs.detail", job_id=job.id))


@bp.route("/<int:job_id>/unsave", methods=["POST"])
@login_required
def unsave(job_id):
    entry = SavedJob.query.filter_by(user_id=current_user.id, job_id=job_id).first()
    if entry:
        db.session.delete(entry)
        db.session.commit()
        flash(_("Removed from saved jobs."), "info")
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
            _(
                "Couldn't fetch %(url)s: %(error)s Paste the text yourself below, or skip it.",
                url=item["url"], error=item["error"],
            ),
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
        flash(_("Please paste at least one URL."), "error")
        return _render_import_page(url_form=url_form)

    urls, truncated = _parse_batch_urls(url_form.urls.data)
    if not urls:
        flash(_("Please paste at least one URL."), "error")
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
        flash(_("Only the first %(max)d URLs were used - that's the limit per batch.", max=MAX_BATCH_URLS), "info")
    summary = ngettext(
        "Fetched %(succeeded)d of %(total)d page successfully.",
        "Fetched %(succeeded)d of %(total)d pages successfully.",
        len(items),
        succeeded=succeeded, total=len(items),
    )
    if failed:
        summary += " " + ngettext(
            "%(num)d failed - you'll get a chance to paste those in manually.",
            "%(num)d failed - you'll get a chance to paste those in manually.",
            failed,
        )
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
        flash(_("Please fill in at least the job title and company."), "error")
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
        flash(_("Job imported.") if created else _("This matched an already-known opportunity - merged."), "success")
        return redirect(url_for("jobs.detail", job_id=job.id))

    items = list(batch.items)
    items[batch.current_index] = {**items[batch.current_index], "status": "saved"}
    batch.items = items
    batch.current_index += 1
    db.session.commit()

    if not batch.is_complete:
        flash(_("Job imported.") if created else _("Matched an already-known opportunity - merged."), "success")
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
        flash(_("Import batch cancelled."), "info")
    return redirect(url_for("jobs.import_start"))


def _finish_batch(batch, last_job_id):
    saved_count = sum(1 for i in batch.items if i["status"] == "saved")
    not_imported = len(batch.items) - saved_count
    db.session.delete(batch)
    db.session.commit()

    if not_imported:
        summary = _(
            "Batch complete: %(saved)d imported, %(not_imported)d not imported.",
            saved=saved_count, not_imported=not_imported,
        )
    else:
        summary = _("Batch complete: %(saved)d imported.", saved=saved_count)
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
