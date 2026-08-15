"""Tests for the lazy Arbeitsagentur detail-fetch-on-open path
(app/jobs/ingest.py's enrich_job_detail(), wired into jobs.detail() in
app/jobs/routes.py). Recommended as option C over eager/background
fetching (see conversation): fetches full detail - description,
education_requirements - at most once per canonical Job, triggered by a
real user opening it, not during search/ingestion where it would mean an
extra API call per result for listings nobody ever opens.

Also covers the flagged wrinkle: get_or_compute_match() only checks
*profile* staleness, not job staleness, so a JobMatch cached before
enrichment (e.g. from the eager per-result computation on the search
results page) must be invalidated, or the improved education-category
result would stay hidden behind a stale cached score indefinitely.
"""
from app.jobs.adapters import manager as adapter_manager
from app.jobs.adapters.base import NormalizedJob
from app.jobs.dedupe import find_or_create_canonical_job
from app.jobs.ingest import enrich_job_detail
from app.jobs.matching import get_or_compute_match
from app.models.ai import JobMatch
from app.models.profile import Education
from tests.conftest import login

RAW_SEARCH_RESULT = {
    "referenznummer": "AA-ENRICH-1",
    "stellenangebotsTitel": "Elektroniker (m/w/d)",
    "firma": "TestFirma GmbH",
    "stellenlokationen": [{"adresse": {"ort": "Stuttgart"}}],
    "externeURL": "https://example.com/job/1",
}
DETAIL_RESPONSE = {
    "stellenangebotsBeschreibung": "Volle Stellenbeschreibung hier.",
    "geforderterBildungsabschluss": "MITTLERER_BILDUNGSABSCHLUSS",
}


def make_arbeitsagentur_job(db):
    adapter = adapter_manager.ADAPTERS["arbeitsagentur"]
    normalized = adapter.normalize(RAW_SEARCH_RESULT)
    job, _ = find_or_create_canonical_job(normalized)
    return job


def test_enrich_job_detail_fetches_and_fills_missing_fields(app, db, monkeypatch):
    job = make_arbeitsagentur_job(db)
    assert job.description is None

    monkeypatch.setattr(
        adapter_manager.ADAPTERS["arbeitsagentur"], "get_job", lambda external_id: DETAIL_RESPONSE
    )
    enriched = enrich_job_detail(job)

    assert enriched is True
    assert job.description == "Volle Stellenbeschreibung hier."
    assert job.education_requirements == "MITTLERER_BILDUNGSABSCHLUSS"


def test_enrich_job_detail_only_fetches_once_across_repeated_opens(app, db, monkeypatch):
    job = make_arbeitsagentur_job(db)
    calls = []
    monkeypatch.setattr(
        adapter_manager.ADAPTERS["arbeitsagentur"], "get_job",
        lambda external_id: calls.append(1) or DETAIL_RESPONSE,
    )
    enrich_job_detail(job)
    enrich_job_detail(job)
    enrich_job_detail(job)
    assert len(calls) == 1


def test_enrich_job_detail_noop_when_description_already_present(app, db, monkeypatch):
    job = make_arbeitsagentur_job(db)
    job.description = "Already known."
    db.session.commit()

    calls = []
    monkeypatch.setattr(
        adapter_manager.ADAPTERS["arbeitsagentur"], "get_job",
        lambda external_id: calls.append(1) or DETAIL_RESPONSE,
    )
    enriched = enrich_job_detail(job)
    assert enriched is False
    assert calls == []


def test_enrich_job_detail_returns_false_when_get_job_returns_none(app, db, monkeypatch):
    job = make_arbeitsagentur_job(db)
    monkeypatch.setattr(adapter_manager.ADAPTERS["arbeitsagentur"], "get_job", lambda external_id: None)
    assert enrich_job_detail(job) is False
    assert job.description is None


def test_enrich_job_detail_isolates_a_raised_exception(app, db, monkeypatch):
    job = make_arbeitsagentur_job(db)

    def _boom(external_id):
        raise ConnectionError("blocked")

    monkeypatch.setattr(adapter_manager.ADAPTERS["arbeitsagentur"], "get_job", _boom)
    enriched = enrich_job_detail(job)  # must not raise
    assert enriched is False
    assert job.description is None


def test_enrich_job_detail_noop_for_a_manual_only_job(app, db):
    # Manual imports have no adapter with a real get_job() - matches the
    # base class default (returns None) and the general "unknown adapter"
    # skip path, without special-casing "manual" by name.
    normalized = NormalizedJob(source="manual", title="Bäcker", company_name="Beispiel GmbH")
    job, _ = find_or_create_canonical_job(normalized)
    assert enrich_job_detail(job) is False


def test_enrich_job_detail_invalidates_stale_cached_job_match(app, db, make_user, monkeypatch):
    job = make_arbeitsagentur_job(db)
    user = make_user(email="enrich1@example.com")

    # Simulates the eager per-result match computed on the search results
    # page, before any detail exists - education has nothing to evaluate
    # yet (job.education_requirements is None), so it's skipped.
    stale_match = get_or_compute_match(user, job)
    assert "education" in (stale_match.skipped_categories or [])
    stale_match_id = stale_match.id

    db.session.add(Education(profile_id=user.profile.id, institution="Realschule Musterstadt", degree="Mittlerer Bildungsabschluss"))
    db.session.commit()

    monkeypatch.setattr(
        adapter_manager.ADAPTERS["arbeitsagentur"], "get_job", lambda external_id: DETAIL_RESPONSE
    )
    enrich_job_detail(job)

    # The old cached row is gone - not just stale, actually deleted.
    # .filter_by().first() rather than .get(): match_id refers to an
    # object still held in this session's identity map from earlier in
    # this test - .get() tries to refresh it and raises ObjectDeletedError
    # once the row is actually gone, instead of returning None cleanly.
    assert JobMatch.query.filter_by(id=stale_match_id).first() is None

    # Not just "a row exists again" (SQLite can reuse a freed integer id) -
    # the real proof is that education is now evaluable, reflecting the
    # just-enriched job.education_requirements.
    fresh_match = get_or_compute_match(user, job)
    assert "education" not in (fresh_match.skipped_categories or [])


def test_enrich_job_detail_does_not_touch_other_jobs_cached_matches(app, db, make_user, monkeypatch):
    job_a = make_arbeitsagentur_job(db)
    # Distinct externeURL too - a shared URL across two raw postings is
    # exactly the (correct, intentional) cross-provider dedup signal
    # added earlier, and would merge these into one job otherwise.
    other_raw = dict(
        RAW_SEARCH_RESULT,
        referenznummer="AA-ENRICH-2",
        stellenangebotsTitel="Mechatroniker",
        externeURL="https://example.com/job/2",
    )
    adapter = adapter_manager.ADAPTERS["arbeitsagentur"]
    job_b, _ = find_or_create_canonical_job(adapter.normalize(other_raw))
    assert job_b.id != job_a.id

    user = make_user(email="enrich2@example.com")
    # Captured into plain ints before enrichment runs - enrich_job_detail()
    # commits after its delete, which expires every object still loaded in
    # this session (SQLAlchemy's default expire_on_commit); reading
    # match_a.id afterward would itself try to refresh the now-deleted row
    # and raise ObjectDeletedError, same as querying it would.
    match_a_id = get_or_compute_match(user, job_a).id
    match_b_id = get_or_compute_match(user, job_b).id

    monkeypatch.setattr(adapter_manager.ADAPTERS["arbeitsagentur"], "get_job", lambda external_id: DETAIL_RESPONSE)
    enrich_job_detail(job_a)

    assert JobMatch.query.filter_by(id=match_a_id).first() is None  # job_a's match invalidated
    assert JobMatch.query.filter_by(id=match_b_id).first() is not None  # job_b's is untouched


def test_detail_page_triggers_enrichment_and_shows_description(client, db, make_user, monkeypatch):
    make_user(email="enrich3@example.com", password="Password123!")
    login(client, "enrich3@example.com", "Password123!")
    job = make_arbeitsagentur_job(db)

    monkeypatch.setattr(
        adapter_manager.ADAPTERS["arbeitsagentur"], "get_job", lambda external_id: DETAIL_RESPONSE
    )
    resp = client.get(f"/jobs/{job.id}")
    assert resp.status_code == 200
    assert b"Volle Stellenbeschreibung hier." in resp.data


def test_detail_page_second_view_does_not_refetch(client, db, make_user, monkeypatch):
    make_user(email="enrich4@example.com", password="Password123!")
    login(client, "enrich4@example.com", "Password123!")
    job = make_arbeitsagentur_job(db)

    calls = []
    monkeypatch.setattr(
        adapter_manager.ADAPTERS["arbeitsagentur"], "get_job",
        lambda external_id: calls.append(1) or DETAIL_RESPONSE,
    )
    client.get(f"/jobs/{job.id}")
    client.get(f"/jobs/{job.id}")
    assert len(calls) == 1
