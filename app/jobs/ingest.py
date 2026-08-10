"""
Ingestion pipeline (spec section 66): SOURCE -> FETCH -> VALIDATION ->
NORMALIZATION -> DEDUPLICATION -> INDEXING. One source failing (network error,
API change, disabled) never blocks the others - each is isolated and logged.
"""
from dataclasses import dataclass, field

from app.jobs.adapters.manager import get_enabled_adapters, record_run
from app.jobs.dedupe import find_or_create_canonical_job
from app.utils.logging import log_event


@dataclass
class IngestResult:
    jobs_found: int = 0
    jobs_new: int = 0
    jobs_updated: int = 0
    errors: list = field(default_factory=list)  # [(source_name, message)]


def ingest_search(keywords, location=None):
    result = IngestResult()

    for adapter in get_enabled_adapters():
        try:
            raw_results = adapter.search(keywords, location=location)
        except Exception as e:
            message = f"{e.__class__.__name__}: {e}"
            result.errors.append((adapter.source_name, message))
            record_run(adapter.source_name, "error", message)
            log_event("job_source", f"{adapter.display_name} search failed: {message}", level="error")
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

    return result
