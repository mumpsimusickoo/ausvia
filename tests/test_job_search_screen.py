"""Screens pass 4 (Find Ausbildung), 2026-08-28. Covers: the batched
scoring path (get_or_compute_matches), sort-by-score, the year-range/
minimum-score/source filters, removable filter chips, the duplicates-merged
count, partial source-failure notice, and profile_insufficient - the real
bug found via Playwright verification where a wholly blank profile still
scored some jobs 100/100 via _score_location()'s "no preference = open to
anywhere" default. See DECISIONS.md for the full rationale.
"""
import pytest

from app.jobs.adapters import manager as adapter_manager
from app.jobs.matching import get_or_compute_matches
from app.models import Job, JobListing, Company, Skill, Language, Preference
from tests.conftest import login


@pytest.fixture(autouse=True)
def no_live_adapter_search(monkeypatch):
    # Every test in this file hits /jobs/ with real keywords, and the route
    # always calls ingest_search() first, which calls the real
    # (credential-free) Arbeitsagentur adapter - without this, a live API
    # call injects real, freshly-discovered_at jobs into the test DB ahead
    # of each test's own hand-built ones, pushing them past
    # SEARCH_CANDIDATE_LIMIT and making every assertion about *which* jobs
    # appear meaningless. Matches tests/test_jobs.py's own established
    # pattern for the same route.
    monkeypatch.setattr(adapter_manager.ADAPTERS["arbeitsagentur"], "search", lambda keywords, location=None, **kw: [])


def make_company(db, name="Testfirma GmbH"):
    company = Company(name=name, normalized_name=name.lower())
    db.session.add(company)
    db.session.commit()
    return company


def make_job(db, **overrides):
    kwargs = dict(dedup_key=f"search-test-{overrides.get('title', 'job')}", employment_type="Ausbildung", title="Elektroniker")
    kwargs.update(overrides)
    job = Job(**kwargs)
    db.session.add(job)
    db.session.commit()
    db.session.add(JobListing(job_id=job.id, source="arbeitsagentur", external_id=f"ext-{job.id}"))
    db.session.commit()
    return job


def give_profile_real_data(db, profile):
    """A profile with enough real data that compute_match() has something
    genuine to evaluate - the counterpart to the wholly-blank profile used
    in test_profile_insufficient_* below."""
    db.session.add(Skill(profile_id=profile.id, name="SPS", proficiency="advanced"))
    db.session.add(Language(profile_id=profile.id, name="German", level="B2"))
    db.session.add(Preference(profile_id=profile.id, locations=["Leipzig"], open_to_relocation=True))
    db.session.commit()


def test_get_or_compute_matches_scores_every_job_in_one_batch(client, db, make_user):
    user = make_user(email="batch1@example.com", password="Password123!")
    give_profile_real_data(db, user.profile)
    job1 = make_job(db, title="Elektroniker A", skills=["SPS"])
    job2 = make_job(db, title="Elektroniker B", skills=["CAD"])

    result = get_or_compute_matches(user, [job1, job2])
    assert set(result.keys()) == {job1.id, job2.id}
    assert result[job1.id].score is not None
    assert result[job2.id].score is not None
    # job1's candidate skill (SPS) is met, job2's (CAD) is not - real
    # difference, not both defaulting to the same number.
    assert result[job1.id].score > result[job2.id].score


def test_get_or_compute_matches_reuses_cache_until_profile_changes(client, db, make_user):
    user = make_user(email="batch2@example.com", password="Password123!")
    give_profile_real_data(db, user.profile)
    job = make_job(db, skills=["SPS"])

    first = get_or_compute_matches(user, [job])[job.id]
    first_computed_at = first.computed_at

    second = get_or_compute_matches(user, [job])[job.id]
    assert second.computed_at == first_computed_at  # cache hit, not recomputed

    user.profile.city = "Berlin"
    db.session.commit()
    third = get_or_compute_matches(user, [job])[job.id]
    assert third.computed_at != first_computed_at  # profile changed - recomputed


def test_search_sorts_by_score_when_requested(client, db, make_user):
    user = make_user(email="sort1@example.com", password="Password123!")
    login(client, "sort1@example.com", "Password123!")
    give_profile_real_data(db, user.profile)
    make_job(db, title="ZZZ Weak Match Elektroniker", skills=["COBOL", "Fortran"])
    make_job(db, title="AAA Strong Match Elektroniker", skills=["SPS"])

    resp = client.get("/jobs/?keywords=Elektroniker&sort=match")
    html = resp.get_data(as_text=True)
    assert html.index("AAA Strong Match Elektroniker") < html.index("ZZZ Weak Match Elektroniker")


def test_search_sort_newest_ignores_score(client, db, make_user):
    user = make_user(email="sort2@example.com", password="Password123!")
    login(client, "sort2@example.com", "Password123!")
    give_profile_real_data(db, user.profile)
    make_job(db, title="First Elektroniker Posted", skills=["COBOL"])  # weak match, but older
    make_job(db, title="Second Elektroniker Posted", skills=["SPS"])  # strong match, but newer

    resp = client.get("/jobs/?keywords=Elektroniker&sort=newest")
    html = resp.get_data(as_text=True)
    assert html.index("Second Elektroniker Posted") < html.index("First Elektroniker Posted")


def test_min_score_filter_excludes_low_scores_and_shows_notice(client, db, make_user):
    user = make_user(email="minscore1@example.com", password="Password123!")
    login(client, "minscore1@example.com", "Password123!")
    give_profile_real_data(db, user.profile)
    make_job(db, title="Elektroniker Strong", skills=["SPS"])
    make_job(db, title="Elektroniker Weak", skills=["COBOL", "Fortran", "Assembler"])

    resp = client.get("/jobs/?keywords=Elektroniker&min_score=60")
    html = resp.get_data(as_text=True)
    assert "Elektroniker Strong" in html
    assert "Elektroniker Weak" not in html
    assert "scored below your minimum" in html


def test_profile_insufficient_never_shows_a_fabricated_score(client, db, make_user):
    """The real bug found via Playwright verification: a wholly blank
    profile (no skills/languages/education/preference at all) still let
    compute_match() return score=100 for a job with none of its own
    skills/language/education requirements set, because
    _score_location() treats "no preference row" as "open to anywhere" -
    a real 1.0 from nothing the candidate actually entered. The search
    route must not display that number."""
    make_user(email="blank1@example.com", password="Password123!")
    login(client, "blank1@example.com", "Password123!")
    # No skills/languages/education/preference added - profile stays blank.
    make_job(db, title="Elektroniker Blank Profile Job")  # no skills/language/education set either

    resp = client.get("/jobs/?keywords=Elektroniker")
    html = resp.get_data(as_text=True)
    assert "doesn&#39;t have enough data yet to score" in html or "doesn't have enough data yet to score" in html
    assert "Not scored" in html
    assert "100" not in html.split("Elektroniker Blank Profile Job")[1][:400]


def test_profile_insufficient_min_score_never_excludes_unscored_jobs(client, db, make_user):
    make_user(email="blank2@example.com", password="Password123!")
    login(client, "blank2@example.com", "Password123!")
    make_job(db, title="Elektroniker Unscored Job")

    resp = client.get("/jobs/?keywords=Elektroniker&min_score=80")
    html = resp.get_data(as_text=True)
    assert "Elektroniker Unscored Job" in html
    assert "scored below your minimum" not in html  # nothing was excluded by score - it can't be evaluated


def test_source_toggle_filters_results(client, db, make_user):
    user = make_user(email="source1@example.com", password="Password123!")
    login(client, "source1@example.com", "Password123!")
    give_profile_real_data(db, user.profile)
    job_aa = make_job(db, title="Elektroniker From AA", dedup_key="src-aa")
    job_adzuna = Job(title="Elektroniker From Adzuna", employment_type="Ausbildung", dedup_key="src-adzuna")
    db.session.add(job_adzuna)
    db.session.commit()
    db.session.add(JobListing(job_id=job_adzuna.id, source="adzuna", external_id="adz-1"))
    db.session.commit()

    resp = client.get("/jobs/?keywords=Elektroniker&sources=arbeitsagentur")
    html = resp.get_data(as_text=True)
    assert "Elektroniker From AA" in html
    assert "Elektroniker From Adzuna" not in html


def test_year_range_filter(client, db, make_user):
    user = make_user(email="year1@example.com", password="Password123!")
    login(client, "year1@example.com", "Password123!")
    give_profile_real_data(db, user.profile)
    make_job(db, title="Elektroniker Starts 2026", start_date="01.09.2026")
    make_job(db, title="Elektroniker Starts 2030", start_date="01.09.2030")

    resp = client.get("/jobs/?keywords=Elektroniker&start_year_min=2026&start_year_max=2027")
    html = resp.get_data(as_text=True)
    assert "Elektroniker Starts 2026" in html
    assert "Elektroniker Starts 2030" not in html


def test_duplicates_merged_count_in_result_line(client, db, make_user):
    user = make_user(email="dupe1@example.com", password="Password123!")
    login(client, "dupe1@example.com", "Password123!")
    give_profile_real_data(db, user.profile)
    job = make_job(db, title="Elektroniker Merged Listing")
    db.session.add(JobListing(job_id=job.id, source="adzuna", external_id="adz-dupe-1"))
    db.session.commit()

    resp = client.get("/jobs/?keywords=Elektroniker")
    html = resp.get_data(as_text=True)
    assert "1 duplicate merged" in html


def test_filter_chip_removal_link_preserves_other_filters(client, db, make_user):
    user = make_user(email="chip1@example.com", password="Password123!")
    login(client, "chip1@example.com", "Password123!")
    give_profile_real_data(db, user.profile)
    make_job(db, title="Elektroniker Chip Test")

    resp = client.get("/jobs/?keywords=Elektroniker&min_score=60&start_year_min=2026")
    html = resp.get_data(as_text=True)
    assert "Score ≥ 60" in html
    # the chip's own href must clear only min_score, keeping start_year_min
    chip_start = html.index("Score ≥ 60")
    chip_markup = html[max(0, chip_start - 200):chip_start]
    assert "start_year_min=2026" in chip_markup
    assert "min_score=60" not in chip_markup


def test_partial_source_failure_shows_named_notice(client, db, make_user, monkeypatch):
    make_user(email="fail1@example.com", password="Password123!")
    login(client, "fail1@example.com", "Password123!")

    def boom(keywords, location=None, **kw):
        raise TimeoutError("Request timed out.")

    monkeypatch.setattr(adapter_manager.ADAPTERS["arbeitsagentur"], "search", boom)

    resp = client.get("/jobs/?keywords=Elektroniker")
    html = resp.get_data(as_text=True)
    assert "Bundesagentur" in html or "arbeitsagentur" in html
    assert "TimeoutError" in html or "Request timed out" in html


def test_no_search_yet_and_no_results_are_distinct_empty_states(client, db, make_user):
    make_user(email="empty1@example.com", password="Password123!")
    login(client, "empty1@example.com", "Password123!")

    resp = client.get("/jobs/")
    assert b"Search for an Ausbildung posting" in resp.data

    resp = client.get("/jobs/?keywords=Zzznonexistenttitle999")
    assert b"No results found" in resp.data
    assert b"Search for an Ausbildung posting" not in resp.data


def test_source_choices_generated_from_enabled_adapters(client, db, make_user):
    from app.models.job import JobSourceSetting

    make_user(email="sourcegen1@example.com", password="Password123!")
    login(client, "sourcegen1@example.com", "Password123!")
    adapter_manager.ensure_source_settings_seeded()
    setting = JobSourceSetting.query.filter_by(source_name="arbeitsagentur").first()
    setting.is_enabled = False
    db.session.commit()

    resp = client.get("/jobs/")
    html = resp.get_data(as_text=True)
    assert "Bundesagentur für Arbeit" not in html
