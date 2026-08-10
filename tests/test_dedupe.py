from app.jobs.adapters.base import NormalizedJob
from app.jobs.dedupe import (
    normalize_company_name,
    normalize_title,
    compute_dedup_key,
    find_or_create_canonical_job,
)
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
