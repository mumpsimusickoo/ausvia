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
