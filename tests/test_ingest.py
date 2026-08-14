"""Tests for app/jobs/ingest.py: provider isolation (one source failing
must not block the others - explicit requirement of the job-source
integration pass) and the per-query cache added to protect metered APIs
(Adzuna/Jooble) from being re-hit on every repeated search.
"""
import app.jobs.ingest as ingest_module
from app.jobs.adapters.base import NormalizedJob
from app.jobs.ingest import ingest_search
from app.models.job import Job, ProviderQueryCache


class FakeAdapter:
    def __init__(self, source_name, jobs=None, error=None):
        self.source_name = source_name
        self.display_name = source_name
        self._jobs = jobs or []
        self._error = error
        self.call_count = 0

    def search(self, keywords, location=None, **kwargs):
        self.call_count += 1
        if self._error:
            raise self._error
        return self._jobs

    def normalize(self, raw):
        return raw  # raw IS already a NormalizedJob in these tests

    def get_job(self, external_id):
        return None


def make_job(source, external_id, title="Elektroniker", company="Firma X"):
    return NormalizedJob(source=source, external_id=external_id, title=title, company_name=company)


def test_one_provider_failing_does_not_block_others(app, db, monkeypatch):
    ba = FakeAdapter("arbeitsagentur", error=ConnectionError("blocked"))
    adzuna = FakeAdapter("adzuna", jobs=[make_job("adzuna", "AZ-1", title="Elektroniker", company="Firma X")])
    jooble = FakeAdapter("jooble", jobs=[make_job("jooble", "JB-1", title="Mechatroniker", company="Firma Y")])

    monkeypatch.setattr(ingest_module, "get_enabled_adapters", lambda: [ba, adzuna, jooble])

    result = ingest_search("Elektroniker")

    assert len(result.errors) == 1
    assert result.errors[0][0] == "arbeitsagentur"
    assert result.jobs_new == 2
    assert Job.query.count() == 2


def test_all_providers_succeeding_ingests_from_all(app, db, monkeypatch):
    adzuna = FakeAdapter("adzuna", jobs=[make_job("adzuna", "AZ-1")])
    jooble = FakeAdapter("jooble", jobs=[make_job("jooble", "JB-1", title="Mechatroniker", company="Firma Y")])

    monkeypatch.setattr(ingest_module, "get_enabled_adapters", lambda: [adzuna, jooble])

    result = ingest_search("Elektroniker")
    assert result.errors == []
    assert result.jobs_new == 2


def test_all_providers_failing_returns_empty_but_no_exception(app, db, monkeypatch):
    ba = FakeAdapter("arbeitsagentur", error=Exception("403"))
    adzuna = FakeAdapter("adzuna", error=Exception("trial expired"))

    monkeypatch.setattr(ingest_module, "get_enabled_adapters", lambda: [ba, adzuna])

    result = ingest_search("Elektroniker")
    assert len(result.errors) == 2
    assert result.jobs_new == 0
    assert Job.query.count() == 0


def test_repeated_identical_search_within_ttl_skips_second_call(app, db, monkeypatch):
    adzuna = FakeAdapter("adzuna", jobs=[make_job("adzuna", "AZ-1")])
    monkeypatch.setattr(ingest_module, "get_enabled_adapters", lambda: [adzuna])

    ingest_search("Elektroniker", location="Berlin")
    ingest_search("Elektroniker", location="Berlin")

    assert adzuna.call_count == 1


def test_search_is_cached_per_normalized_keywords_and_location_combo(app, db, monkeypatch):
    adzuna = FakeAdapter("adzuna", jobs=[make_job("adzuna", "AZ-1")])
    monkeypatch.setattr(ingest_module, "get_enabled_adapters", lambda: [adzuna])

    ingest_search("Elektroniker", location="Berlin")
    ingest_search("  ELEKTRONIKER  ", location="berlin")  # same query, different case/whitespace

    assert adzuna.call_count == 1


def test_different_queries_are_not_cached_against_each_other(app, db, monkeypatch):
    adzuna = FakeAdapter("adzuna", jobs=[make_job("adzuna", "AZ-1")])
    monkeypatch.setattr(ingest_module, "get_enabled_adapters", lambda: [adzuna])

    ingest_search("Elektroniker", location="Berlin")
    ingest_search("Mechatroniker", location="Berlin")

    assert adzuna.call_count == 2


def test_cache_expires_after_ttl(app, db, monkeypatch):
    from datetime import timedelta

    from app.models.user import utcnow

    adzuna = FakeAdapter("adzuna", jobs=[make_job("adzuna", "AZ-1")])
    monkeypatch.setattr(ingest_module, "get_enabled_adapters", lambda: [adzuna])

    ingest_search("Elektroniker", location="Berlin")
    assert adzuna.call_count == 1

    # Simulate the cache entry being older than the TTL window.
    row = ProviderQueryCache.query.filter_by(source="adzuna").first()
    row.last_queried_at = utcnow() - timedelta(minutes=ingest_module.QUERY_CACHE_TTL_MINUTES + 1)
    db.session.commit()

    ingest_search("Elektroniker", location="Berlin")
    assert adzuna.call_count == 2


def test_failed_search_is_also_cached_to_avoid_retry_storms(app, db, monkeypatch):
    ba = FakeAdapter("arbeitsagentur", error=Exception("403"))
    monkeypatch.setattr(ingest_module, "get_enabled_adapters", lambda: [ba])

    ingest_search("Elektroniker")
    ingest_search("Elektroniker")

    assert ba.call_count == 1


def test_cache_is_independent_per_source(app, db, monkeypatch):
    adzuna = FakeAdapter("adzuna", jobs=[make_job("adzuna", "AZ-1")])
    jooble = FakeAdapter("jooble", jobs=[make_job("jooble", "JB-1")])
    monkeypatch.setattr(ingest_module, "get_enabled_adapters", lambda: [adzuna])

    ingest_search("Elektroniker", location="Berlin")

    # jooble wasn't queried at all yet - its own cache entry for this exact
    # query must not exist, so it should still be queried on its own first hit.
    monkeypatch.setattr(ingest_module, "get_enabled_adapters", lambda: [jooble])
    ingest_search("Elektroniker", location="Berlin")
    assert jooble.call_count == 1
