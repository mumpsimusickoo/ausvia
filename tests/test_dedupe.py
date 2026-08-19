from app.jobs.adapters.base import NormalizedJob
from app.jobs.dedupe import (
    normalize_company_name,
    normalize_title,
    compute_dedup_key,
    find_or_create_canonical_job,
    merge_missing_fields,
)
from app.jobs.matching import get_or_compute_match
from app.models.ai import JobMatch
from app.models.job import Job, JobListing, Company


def test_normalize_company_name_strips_legal_suffixes():
    assert normalize_company_name("Siemens GmbH") == "siemens"
    assert normalize_company_name("Muster & Söhne AG") == "muster & söhne"
    assert normalize_company_name("Beispiel GmbH & Co KG") == "beispiel"


def test_normalize_title_strips_mwd_suffix():
    assert normalize_title("Elektroniker (m/w/d)") == "elektroniker"
    assert normalize_title("Elektroniker  für   Automatisierungstechnik") == "elektroniker für automatisierungstechnik"


def test_dedup_key_stable_for_same_inputs():
    key1 = compute_dedup_key("Siemens GmbH", "Elektroniker (m/w/d)", "München", "2027-09-01")
    key2 = compute_dedup_key("Siemens", "Elektroniker", "München", "2027-09-01")
    assert key1 == key2


def make_normalized(source, external_id, **overrides):
    defaults = dict(
        source=source,
        external_id=external_id,
        title="Elektroniker für Automatisierungstechnik",
        company_name="Siemens GmbH",
        location="München",
        start_date="2027-09-01",
        raw={"external_id": external_id},
    )
    defaults.update(overrides)
    return NormalizedJob(**defaults)


def test_two_sources_for_same_job_group_under_one_canonical_job(app, db):
    job1, created1 = find_or_create_canonical_job(make_normalized("arbeitsagentur", "AA-1"))
    job2, created2 = find_or_create_canonical_job(
        make_normalized(
            "manual", None, company_name="Siemens AG", title="Elektroniker für Automatisierungstechnik (m/w/d)"
        )
    )

    assert created1 is True
    assert created2 is False
    assert job1.id == job2.id
    assert Job.query.count() == 1
    assert JobListing.query.count() == 2
    assert set(job1.sources) == {"arbeitsagentur", "manual"}


def test_different_jobs_create_separate_canonical_jobs(app, db):
    job1, _ = find_or_create_canonical_job(make_normalized("arbeitsagentur", "AA-1"))
    job2, _ = find_or_create_canonical_job(make_normalized("arbeitsagentur", "AA-2", location="Berlin"))
    assert job1.id != job2.id
    assert Job.query.count() == 2


def test_company_deduplicated_across_jobs(app, db):
    find_or_create_canonical_job(make_normalized("arbeitsagentur", "AA-1", title="Elektroniker"))
    find_or_create_canonical_job(make_normalized("arbeitsagentur", "AA-2", title="Mechatroniker"))
    assert Company.query.count() == 1


def test_reingesting_same_external_id_does_not_duplicate_listing(app, db):
    find_or_create_canonical_job(make_normalized("arbeitsagentur", "AA-1"))
    find_or_create_canonical_job(make_normalized("arbeitsagentur", "AA-1"))
    assert JobListing.query.count() == 1


def test_same_url_across_adzuna_and_jooble_merges_despite_different_text(app, db):
    """Job-source integration pass: the same real vacancy aggregated onto
    two different job boards often has slightly different title/company
    text (translation, punctuation) that fails the company+title+location
    heuristic - but if both listings point at the identical original URL,
    that's an unambiguous signal they're the same posting."""
    same_url = "https://example.com/careers/elektroniker-123"
    job1, created1 = find_or_create_canonical_job(
        make_normalized(
            "adzuna", "AZ-1", title="Elektroniker (m/w/d)", company_name="Beispiel GmbH",
            application_url=same_url, source_url=same_url,
        )
    )
    job2, created2 = find_or_create_canonical_job(
        make_normalized(
            "jooble", "JB-1", title="Ausbildung zum Elektroniker", company_name="Beispiel AG - Werk Nord",
            application_url=same_url, source_url=same_url,
        )
    )

    assert created1 is True
    assert created2 is False
    assert job1.id == job2.id
    assert Job.query.count() == 1
    assert set(job1.sources) == {"adzuna", "jooble"}


def test_different_urls_with_matching_text_still_dedupe_via_existing_heuristic(app, db):
    # The new URL-based signal is purely additive - two listings with no
    # URL at all must still fall back to the existing company+title+
    # location+start_date match exactly as before.
    job1, created1 = find_or_create_canonical_job(make_normalized("arbeitsagentur", "AA-1"))
    job2, created2 = find_or_create_canonical_job(make_normalized("manual", None))
    assert created2 is False
    assert job1.id == job2.id


def test_same_url_does_not_merge_genuinely_different_jobs_missing_url(app, db):
    # A job with no URL at all must never accidentally match one that has a
    # URL, just because both hit the same "no url" code path.
    job1, _ = find_or_create_canonical_job(
        make_normalized("adzuna", "AZ-2", title="Bäcker", company_name="Bäckerei Nord", application_url=None)
    )
    job2, _ = find_or_create_canonical_job(
        make_normalized("jooble", "JB-2", title="Bäcker", company_name="Bäckerei Süd", application_url=None)
    )
    assert job1.id != job2.id


# --- Conditional JobMatch invalidation on dedupe re-match ------------------
# merge_missing_fields() only fills currently-empty fields, so a re-match can
# genuinely be a no-op; unconditionally invalidating on every re-match would
# wipe a perfectly valid cached JobMatch (and any AI narrative/improvement-
# tips text on it) for no reason. See app/ai/matching.py's
# SCORE_RELEVANT_JOB_FIELDS and app/jobs/dedupe.py's find_or_create_canonical_job().


def make_job(db, **overrides):
    kwargs = dict(title="Elektroniker", dedup_key="merge-test")
    kwargs.update(overrides)
    job = Job(**kwargs)
    db.session.add(job)
    db.session.commit()
    return job


def test_merge_missing_fields_returns_only_the_fields_actually_changed(app, db):
    # start_date set to match make_normalized()'s own default below, so it's
    # correctly excluded from "changed" too - only skills/description are
    # actually empty going in.
    job = make_job(db, skills=None, description=None, postal_code="10115", start_date="2027-09-01")
    normalized = make_normalized(
        "arbeitsagentur", "MERGE-1",
        skills=["Löten"], description="Volle Beschreibung.", postal_code="99999",
    )

    changed = merge_missing_fields(job, normalized)

    assert changed == {"skills", "description"}
    assert job.skills == ["Löten"]
    assert job.description == "Volle Beschreibung."
    assert job.postal_code == "10115"  # already set - untouched, correctly not reported as changed


def test_merge_missing_fields_returns_empty_set_on_genuine_noop(app, db):
    job = make_job(
        db, skills=["Löten"], description="Schon bekannt.", postal_code="10115",
        federal_state="Berlin", start_date="2027-09-01", salary="1000",
        application_deadline=None, requirements=None, language_requirements=None,
        education_requirements=None, contact_person=None, contact_email=None, application_url=None,
    )
    normalized = make_normalized(
        "arbeitsagentur", "MERGE-2",
        skills=["Andere Skill"], description="Andere Beschreibung.", postal_code="00000",
    )

    changed = merge_missing_fields(job, normalized)

    assert changed == set()
    # Untouched, not just "not reported" - confirms the no-op is real, not a bug in the return value alone.
    assert job.skills == ["Löten"]
    assert job.description == "Schon bekannt."


def test_merge_missing_fields_returns_every_field_filled_on_a_full_fill(app, db):
    job = make_job(db)  # every fillable field starts empty
    normalized = make_normalized(
        "arbeitsagentur", "MERGE-3",
        federal_state="Bayern", postal_code="80331", start_date="2027-09-01",
        salary="1000", description="Text.", requirements="Text.",
        language_requirements=[{"language": "German", "level": "B1"}], skills=["Löten"],
        education_requirements="MITTLERER_BILDUNGSABSCHLUSS", contact_person="A B",
        contact_email="a@b.de", application_url="https://example.com/x",
    )

    changed = merge_missing_fields(job, normalized)

    assert changed == {
        "federal_state", "postal_code", "start_date", "salary", "description", "requirements",
        "language_requirements", "skills", "education_requirements", "contact_person",
        "contact_email", "application_url",
    }


def test_dedupe_remerge_invalidates_cached_match_when_score_relevant_field_filled(app, db, make_user):
    job, _ = find_or_create_canonical_job(make_normalized("arbeitsagentur", "AA-SCORE-1"))
    assert job.education_requirements is None
    user = make_user(email="dedupe-score1@example.com")
    stale_match = get_or_compute_match(user, job)
    assert "education" in (stale_match.skipped_categories or [])
    stale_match_id = stale_match.id

    # A second listing for the same job (matched via dedup_key, same
    # company/title/location/start_date) that happens to carry
    # education_requirements this time.
    find_or_create_canonical_job(
        make_normalized("manual", None, education_requirements="MITTLERER_BILDUNGSABSCHLUSS")
    )

    # .filter_by().first() not .get(): stale_match_id refers to an object
    # still in this session's identity map - .get() would try to refresh it
    # and raise ObjectDeletedError once the row is actually gone.
    assert JobMatch.query.filter_by(id=stale_match_id).first() is None

    # Not just "a row exists again" (SQLite can reuse a freed integer id) -
    # the real proof is that education is now evaluable, reflecting the
    # just-merged job.education_requirements.
    fresh_match = get_or_compute_match(user, job)
    assert "education" not in (fresh_match.skipped_categories or [])


def test_dedupe_remerge_does_not_invalidate_when_only_non_score_fields_change(app, db, make_user):
    job, _ = find_or_create_canonical_job(
        make_normalized("arbeitsagentur", "AA-SCORE-2", description=None, salary=None)
    )
    user = make_user(email="dedupe-score2@example.com")
    cached_match_id = get_or_compute_match(user, job).id

    # A second listing filling only non-score fields (description, salary,
    # postal_code) - a real merge happens, just not one that could have
    # changed the score.
    find_or_create_canonical_job(
        make_normalized(
            "manual", None, description="Volle Beschreibung.", salary="1200", postal_code="12345",
        )
    )

    assert JobMatch.query.filter_by(id=cached_match_id).first() is not None


def test_dedupe_remerge_does_not_invalidate_on_genuine_noop(app, db, make_user):
    job, _ = find_or_create_canonical_job(
        make_normalized("arbeitsagentur", "AA-SCORE-3", skills=["Löten"], education_requirements="ABITUR")
    )
    user = make_user(email="dedupe-score3@example.com")
    cached_match_id = get_or_compute_match(user, job).id

    # Same job re-matched again (e.g. the same search re-run) - every
    # score-relevant field is already populated, so nothing can change.
    find_or_create_canonical_job(
        make_normalized("manual", None, skills=["Andere Skill"], education_requirements="ANDERE")
    )

    assert JobMatch.query.filter_by(id=cached_match_id).first() is not None


def test_enrich_and_extraction_call_sites_unaffected_by_return_value_addition(app, db, monkeypatch):
    # Regression check: both existing callers discard merge_missing_fields()'s
    # return value entirely - confirms the signature addition changed
    # nothing observable for either of them.
    from app.jobs.adapters import manager as adapter_manager
    from app.jobs.ingest import enrich_job_detail

    job, _ = find_or_create_canonical_job(make_normalized("arbeitsagentur", "AA-REGRESSION-1"))
    assert job.description is None

    monkeypatch.setattr(
        adapter_manager.ADAPTERS["arbeitsagentur"], "get_job",
        lambda external_id: {
            "stellenangebotsBeschreibung": "Volle Stellenbeschreibung hier.",
            "geforderterBildungsabschluss": "MITTLERER_BILDUNGSABSCHLUSS",
        },
    )
    enriched = enrich_job_detail(job)

    assert enriched is True
    assert job.description == "Volle Stellenbeschreibung hier."
    assert job.education_requirements == "MITTLERER_BILDUNGSABSCHLUSS"
