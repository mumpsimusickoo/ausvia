"""
Ingestion pipeline (spec section 66): SOURCE -> FETCH -> VALIDATION ->
NORMALIZATION -> DEDUPLICATION -> INDEXING. One source failing (network error,
API change, disabled) never blocks the others - each is isolated and logged.
"""
from dataclasses import dataclass, field
from datetime import timedelta

from app.extensions import db
from app.jobs.adapters.jooble import record_jooble_request
from app.jobs.adapters.manager import ADMIN_ONLY_SOURCES, all_adapters, get_enabled_adapters, record_run
from app.jobs.dedupe import find_or_create_canonical_job, merge_missing_fields
from app.models.ai import JobMatch
from app.models.job import ProviderQueryCache
from app.models.user import utcnow
from app.utils.logging import log_event

# Job-source integration pass: how long a (source, keyword, location)
# combination is skipped after being queried once - see
# ProviderQueryCache's docstring (app/models/job.py) for why this exists.
# 15 minutes is conservative relative to Adzuna's 25/minute limit while
# still keeping search results reasonably fresh for a small user base.
QUERY_CACHE_TTL_MINUTES = 15


@dataclass
class IngestResult:
    jobs_found: int = 0
    jobs_new: int = 0
    jobs_updated: int = 0
    errors: list = field(default_factory=list)  # [(source_name, message)]


def _query_key(keywords, location):
    return f"{(keywords or '').strip().lower()}|{(location or '').strip().lower()}"[:300]


def _recently_queried(source, query_key):
    cutoff = utcnow() - timedelta(minutes=QUERY_CACHE_TTL_MINUTES)
    row = ProviderQueryCache.query.filter_by(source=source, query_key=query_key).first()
    return row is not None and row.last_queried_at > cutoff


def _record_query(source, query_key):
    row = ProviderQueryCache.query.filter_by(source=source, query_key=query_key).first()
    if row is None:
        row = ProviderQueryCache(source=source, query_key=query_key)
        db.session.add(row)
    row.last_queried_at = utcnow()
    db.session.commit()


def ingest_search(keywords, location=None, admin=False):
    """admin=True is required for a source in ADMIN_ONLY_SOURCES (Jooble)
    to be queried at all - see that constant's own docstring
    (app/jobs/adapters/manager.py) for why. Callers pass the requesting
    user's own current_user.is_admin, never a hardcoded value - see
    app/jobs/routes.py's search() and app/jobs/radar.py's
    run_job_radar()."""
    result = IngestResult()
    query_key = _query_key(keywords, location)

    adapters = get_enabled_adapters()
    if not admin:
        adapters = [a for a in adapters if a.source_name not in ADMIN_ONLY_SOURCES]

    for adapter in adapters:
        if _recently_queried(adapter.source_name, query_key):
            continue

        if adapter.source_name == "jooble":
            # Only a real, uncached call spends lifetime budget - counted
            # before the call (not after) so a failure still counts, since
            # a request that reached Jooble's servers already cost its
            # lifetime price regardless of what it returned.
            # record_jooble_request() returns False once the hard-stop
            # ceiling is reached (app/jobs/adapters/jooble.py) - the call
            # must be refused entirely at that point, not attempted and
            # merely warned about. Deliberately not added to
            # result.errors: this is an intentional budget decision, not
            # a provider failure, so it shouldn't surface to the user as
            # one - it just means no Jooble results for this search,
            # exactly as if the source were disabled.
            if not record_jooble_request():
                continue

        try:
            raw_results = adapter.search(keywords, location=location)
        except Exception as e:
            message = f"{e.__class__.__name__}: {e}"
            result.errors.append((adapter.source_name, message))
            record_run(adapter.source_name, "error", message)
            log_event("job_source", f"{adapter.display_name} search failed: {message}", level="error")
            _record_query(adapter.source_name, query_key)
            continue

        new_count = 0
        for raw in raw_results:
            try:
                normalized = adapter.normalize(raw)
                _, created = find_or_create_canonical_job(normalized)
                result.jobs_found += 1
                if created:
                    result.jobs_new += 1
                    new_count += 1
                else:
                    result.jobs_updated += 1
            except Exception as e:
                message = f"Failed to process one listing: {e.__class__.__name__}: {e}"
                result.errors.append((adapter.source_name, message))
                log_event("job_source", message, level="warning")

        record_run(adapter.source_name, "ok", f"{len(raw_results)} results, {new_count} new")
        _record_query(adapter.source_name, query_key)

    return result


def enrich_job_detail(job):
    """Lazily fetches full provider detail for a Job the first time it's
    opened (app/jobs/routes.py's detail() route) - deliberately NOT done
    during search/ingestion, where it would mean an extra API call per
    result even for listings nobody ever opens. Gated on job.description
    being empty, so this fetches at most once per canonical Job ever,
    regardless of how many users open it or how many source listings it
    has - subsequent opens (by the same or a different user) see the
    already-enriched row with no further API call.

    Only Arbeitsagentur has a genuinely separate detail step today (see
    ArbeitsagenturAdapter.get_job()) - Adzuna/Jooble's get_job() always
    returns None since their search results already carry everything they
    expose, so this is naturally a no-op for those sources without
    special-casing by name. Uses all_adapters() (not the enabled-only
    subset) since opening a specific job the user already knows about
    shouldn't depend on whether the source is still enabled for new
    searches - matches check_availability()'s existing precedent of
    calling get_job() directly.

    A single fast (~0.5s, confirmed live) inline call on a page load
    someone's already waiting on - no background-task executor needed for
    this, unlike ingest_search()'s multi-provider search step.

    Returns True if a detail fetch actually happened and enrichment was
    applied (the caller uses this to know whether cached JobMatch rows for
    this job need invalidating), False otherwise (already enriched, no
    matching listing/adapter, or the fetch found nothing new).
    """
    if job.description:
        return False

    adapters = all_adapters()
    enriched = False
    for listing in job.listings:
        adapter = adapters.get(listing.source)
        if adapter is None or listing.external_id is None:
            continue
        try:
            detail_raw = adapter.get_job(listing.external_id)
        except Exception as e:
            log_event(
                "job_source",
                f"Detail fetch failed for job {job.id} ({listing.source}): {e.__class__.__name__}: {e}",
                level="warning",
            )
            continue
        if not detail_raw:
            continue

        merged_raw = {**(listing.raw_snapshot or {}), "_detail": detail_raw}
        normalized = adapter.normalize(merged_raw)
        merge_missing_fields(job, normalized)
        listing.last_checked_at = utcnow()
        enriched = True
        if job.description:
            break  # got what we came for - no need to also fetch other listings' detail

    if enriched:
        # The wrinkle: get_or_compute_match() only checks *profile*
        # staleness, not job staleness - a JobMatch already cached (e.g.
        # from the eager per-result computation on the search results
        # page, before detail existed) would otherwise keep showing the
        # pre-enrichment score/education-category-skipped result
        # indefinitely. Deleting every cached JobMatch for this job (not
        # just the current viewer's) forces a fresh recompute for anyone
        # who views it next, current viewer included.
        JobMatch.query.filter_by(job_id=job.id).delete()
        db.session.commit()

    return enriched


def should_attempt_external_contact_fetch(job):
    """Contact-display pass (2026-09-02): True if this Arbeitsagentur job
    is eligible for the external-posting contact fallback -
    fill_contact_from_external_posting() below. Gated on the job's own
    data genuinely having no contact info yet, a real external posting
    URL existing to try, and this never having been attempted before -
    never retried once tried, regardless of outcome (see that function's
    own docstring for why a bot-protection block or a genuinely
    contact-less external page are both accepted as permanent, not
    transient, states).

    Arbeitsagentur-only, not every source: confirmed via investigation
    (DECISIONS.md) that this specific gap - real contact info sitting on
    an employer's own linked posting page, absent from the source API's
    own data - is real and common for Arbeitsagentur specifically (its
    detail API has no structured contact field at all, see
    ArbeitsagenturAdapter's own docstring); Adzuna/Jooble weren't part of
    this investigation and aren't assumed to have the same shape.

    Deliberately sequenced BEHIND extract_job_requirements(): this is a
    genuine fallback, only worth trying once the cheaper, more-trusted
    description-based extraction has already had its own shot at finding
    a contact and genuinely found none - not a second simultaneous
    attempt that would just double the AI cost for jobs the description
    extraction would have solved on its own. job.skills is not None is
    the same "extraction already ran and concluded" signal
    extract_job_requirements() itself already establishes (an empty list
    means "ran, found nothing", distinct from None, "never attempted or
    still pending") - reused here rather than a second tracking field."""
    if job.contact_person or job.contact_email:
        return False
    if job.contact_external_fetch_attempted:
        return False
    if job.skills is None:
        return False
    if "arbeitsagentur" not in job.sources:
        return False
    return bool(job.preferred_application_url)


def fill_contact_from_external_posting(job_id, user_id):
    """Lazy, one-shot fallback for an Arbeitsagentur job whose own listing
    genuinely never states a contact - confirmed via investigation this
    session (see DECISIONS.md) that this is a real, common shape (202 of
    250 sampled jobs with no contact_person/email had no contact text
    anywhere in their own description either - a data-availability gap
    on Arbeitsagentur's side for most of these, not a remaining bug in
    extract_job_requirements()'s isolator/grounding). Live-verified
    against the real motivating case: a Vetter Pharma-Fertigung
    Elektroniker/in posting whose Arbeitsagentur description states no
    contact at all, but whose real external ausbildung.de posting names
    a real contact (Moritz Gehring) this fills in correctly.

    Reuses the exact grounded extraction pipeline already built and
    proven for manual import (app/ai/manual_import_extraction.py)
    against the job's real preferred_application_url - same structural
    fencing, same never-guess grounding, same bot-protection respect
    (fetch_and_extract_text() never attempts to evade a block) as a user
    pasting that same URL into manual import themselves would get. Only
    the two contact fields are ever kept from the result - title/
    company/location/salary/description are already correctly populated
    by Arbeitsagentur's own API and must never be silently overwritten
    by a second, less-trusted source.

    Calls _run_extraction() (the core provider-call/parse/ground logic),
    not extract_manual_import_fields() itself - that wrapper's rate-limit
    check requires an active HTTP request context (it's a real
    Flask-Limiter check keyed off the request's client IP), which doesn't
    exist here: this runs via submit_task() on a worker thread with only
    an app context. Matches job_requirements_extraction.py's own
    precedent of no rate limiter at all for its background-task AI call -
    this is naturally throttled to one attempt per job, ever, by
    contact_external_fetch_attempted itself.

    Takes job_id/user_id (not a Job object) to match
    extract_job_requirements()'s own precedent - this runs via
    submit_task() on a worker thread with its own app context, where a
    model instance from the request's session would be detached.

    Called from app/jobs/routes.py's detail() route, off the request via
    submit_task() (same as extract_job_requirements()) - a real external
    HTTP fetch plus a real AI call have meaningfully more latency than a
    page load someone's already waiting on, and the page is fully usable
    without this either way. Marks contact_external_fetch_attempted
    unconditionally before returning, regardless of outcome - this is a
    real accepted dead end for this one job when it fails, never retried."""
    from app.ai.manual_import_extraction import _run_extraction
    from app.jobs.manual_import import FetchFailed, fetch_and_extract_text
    from app.models.job import Job

    job = db.session.get(Job, job_id)
    if job is None or not should_attempt_external_contact_fetch(job):
        return False

    try:
        fetched = fetch_and_extract_text(job.preferred_application_url)
    except FetchFailed as e:
        log_event(
            "job_source",
            f"External contact fetch skipped for job {job.id}: {e}",
            level="info",
        )
        job.contact_external_fetch_attempted = True
        db.session.commit()
        return False

    result = _run_extraction(fetched["page_title"], fetched["text"], user_id)
    job.contact_external_fetch_attempted = True
    changed = False
    if result["contact_person"] and not job.contact_person:
        job.contact_person = result["contact_person"]
        changed = True
    if result["contact_email"] and not job.contact_email:
        job.contact_email = result["contact_email"]
        changed = True
    db.session.commit()
    return changed
