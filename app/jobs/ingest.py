"""
Ingestion pipeline (spec section 66): SOURCE -> FETCH -> VALIDATION ->
NORMALIZATION -> DEDUPLICATION -> INDEXING. One source failing (network error,
API change, disabled) never blocks the others - each is isolated and logged.
"""
from dataclasses import dataclass, field
from datetime import timedelta

from app.extensions import db
from app.jobs.adapters.manager import get_enabled_adapters, record_run
from app.jobs.dedupe import find_or_create_canonical_job
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


def ingest_search(keywords, location=None):
    result = IngestResult()
    query_key = _query_key(keywords, location)

    for adapter in get_enabled_adapters():
        if _recently_queried(adapter.source_name, query_key):
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
