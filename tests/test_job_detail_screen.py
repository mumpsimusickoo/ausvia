"""Screens pass 1, 2026-08-27: Job Detail. Covers the new template/route
behavior specifically - honest-absence states (no deadline, no salary, an
unevaluated criterion, no dedup), the requirement-tag gap flag, and the
dedup/source disclosure. Rendering correctness (macros, layout, mobile
reordering) was verified with Playwright and is not re-asserted here -
these tests are the regression guard for the data-shaping logic in
app/jobs/routes.py::detail().
"""
from datetime import date, timedelta

from app.extensions import db
from app.models import Company, Job, JobListing, Skill
from tests.conftest import login


def make_job(**overrides):
    kwargs = dict(dedup_key="detail-screen-test", employment_type="Ausbildung", title="Elektroniker")
    kwargs.update(overrides)
    job = Job(**kwargs)
    db.session.add(job)
    db.session.commit()
    return job


def test_duration_tile_is_never_rendered(client, db, make_user):
    """No model anywhere backs a job "duration" - see DECISIONS.md. This is
    a regression guard: if a Duration fact tile is ever added back without
    a real field to source it from, this test catches the fabricated
    "Not specified" tile before it ships."""
    make_user(email="d1@example.com", password="Password123!")
    login(client, "d1@example.com", "Password123!")
    job = make_job(title="Elektroniker A")

    resp = client.get(f"/jobs/{job.id}")
    assert b"DURATION" not in resp.data
    assert b"DAUER" not in resp.data


def test_fact_tiles_show_not_specified_for_missing_start_and_salary(client, db, make_user):
    make_user(email="d2@example.com", password="Password123!")
    login(client, "d2@example.com", "Password123!")
    job = make_job(title="Elektroniker B", start_date=None, salary=None)
    db.session.add(JobListing(job_id=job.id, source="manual", external_id="fact-tile-source"))
    db.session.commit()

    resp = client.get(f"/jobs/{job.id}")
    # Only start date and salary are missing here - source has a real listing.
    assert resp.data.count(b"Not specified") == 2


def test_contact_card_renders_when_populated(client, db, make_user):
    """Contact display pass (2026-09-02): job.contact_person/contact_email
    (made significantly more reliable this session - see DECISIONS.md's
    contact-extraction entries) had nowhere visible on the job detail page
    matching the rest of the rail's design language before this - the
    CONTACT card must actually render, same mono-label treatment as
    APPLY/COMPANY/SOURCE, whenever the data already exists on the row."""
    make_user(email="d-contact1@example.com", password="Password123!")
    login(client, "d-contact1@example.com", "Password123!")
    job = make_job(title="Elektroniker D", contact_person="Frau Julia Weber", contact_email="julia.weber@example.de")

    resp = client.get(f"/jobs/{job.id}")
    body = resp.data.decode("utf-8")
    assert "CONTACT" in body
    assert "Frau Julia Weber" in body
    assert "julia.weber@example.de" in body
    assert 'href="mailto:julia.weber@example.de"' in body


def test_contact_card_absent_when_no_contact_on_file(client, db, make_user):
    make_user(email="d-contact2@example.com", password="Password123!")
    login(client, "d-contact2@example.com", "Password123!")
    job = make_job(title="Elektroniker E", contact_person=None, contact_email=None)

    resp = client.get(f"/jobs/{job.id}")
    assert b"CONTACT" not in resp.data


def test_contact_card_renders_with_only_email_no_person(client, db, make_user):
    make_user(email="d-contact3@example.com", password="Password123!")
    login(client, "d-contact3@example.com", "Password123!")
    job = make_job(title="Elektroniker F", contact_person=None, contact_email="bewerbung@example.de")

    resp = client.get(f"/jobs/{job.id}")
    body = resp.data.decode("utf-8")
    assert "CONTACT" in body
    assert "bewerbung@example.de" in body


def test_requirement_tags_render_and_flag_gaps(client, db, make_user):
    user = make_user(email="d3@example.com", password="Password123!")
    login(client, "d3@example.com", "Password123!")
    db.session.add(Skill(profile_id=user.profile.id, name="PLC"))
    db.session.commit()
    job = make_job(title="Elektroniker C", skills=["PLC", "STEP7"])

    resp = client.get(f"/jobs/{job.id}")
    assert b"REQUIREMENTS FROM THE POSTING" in resp.data
    assert b"PLC" in resp.data
    assert b"STEP7" in resp.data
    # STEP7 isn't in the candidate's skills - flagged err-toned (chip_attribute(gap=True)).
    assert b"bg-err-tint" in resp.data


def test_no_requirement_tags_section_when_job_has_no_skills(client, db, make_user):
    make_user(email="d4@example.com", password="Password123!")
    login(client, "d4@example.com", "Password123!")
    job = make_job(title="Elektroniker D", skills=[])

    resp = client.get(f"/jobs/{job.id}")
    assert b"REQUIREMENTS FROM THE POSTING" not in resp.data


def test_skipped_category_renders_as_not_evaluated_not_missing(client, db, make_user):
    """The third state - distinct from a real gap. skills/language/
    education are all empty on this job, so all three get skipped by
    compute_match() and must render as "not evaluated", never silently
    dropped or folded into "Missing"."""
    make_user(email="d5@example.com", password="Password123!")
    login(client, "d5@example.com", "Password123!")
    job = make_job(title="Elektroniker E", skills=[], language_requirements=[], education_requirements=None)

    resp = client.get(f"/jobs/{job.id}")
    assert b"not evaluated (missing data)" in resp.data
    assert b"Skills" in resp.data and b"Language" in resp.data and b"Education" in resp.data


def test_deadline_shows_days_remaining(client, db, make_user):
    make_user(email="d6@example.com", password="Password123!")
    login(client, "d6@example.com", "Password123!")
    job = make_job(title="Elektroniker F", application_deadline=date.today() + timedelta(days=10))

    resp = client.get(f"/jobs/{job.id}")
    assert b"in 10 days" in resp.data


def test_deadline_shows_passed_when_in_the_past(client, db, make_user):
    make_user(email="d7@example.com", password="Password123!")
    login(client, "d7@example.com", "Password123!")
    job = make_job(title="Elektroniker G", application_deadline=date.today() - timedelta(days=5))

    resp = client.get(f"/jobs/{job.id}")
    assert b"passed 5 days ago" in resp.data


def test_no_deadline_listed_when_absent(client, db, make_user):
    make_user(email="d8@example.com", password="Password123!")
    login(client, "d8@example.com", "Password123!")
    job = make_job(title="Elektroniker H", application_deadline=None)

    resp = client.get(f"/jobs/{job.id}")
    assert b"No deadline listed" in resp.data


def test_source_disclosure_mentions_merge_when_multiple_listings(client, db, make_user):
    make_user(email="d9@example.com", password="Password123!")
    login(client, "d9@example.com", "Password123!")
    job = make_job(title="Elektroniker I", dedup_key="detail-screen-merge")
    db.session.add(JobListing(job_id=job.id, source="arbeitsagentur", external_id="m1"))
    db.session.add(JobListing(job_id=job.id, source="adzuna", external_id="m2"))
    db.session.commit()

    resp = client.get(f"/jobs/{job.id}")
    assert b"automatically merged" in resp.data


def test_source_disclosure_omits_merge_for_single_listing(client, db, make_user):
    make_user(email="d10@example.com", password="Password123!")
    login(client, "d10@example.com", "Password123!")
    job = make_job(title="Elektroniker J", dedup_key="detail-screen-nomerge")
    db.session.add(JobListing(job_id=job.id, source="arbeitsagentur", external_id="s1"))
    db.session.commit()

    resp = client.get(f"/jobs/{job.id}")
    assert b"automatically merged" not in resp.data


def test_company_rail_shows_open_position_count(client, db, make_user):
    make_user(email="d11@example.com", password="Password123!")
    login(client, "d11@example.com", "Password123!")
    company = Company(name="Raildorf GmbH", normalized_name="raildorf")
    db.session.add(company)
    db.session.flush()
    job = make_job(title="Elektroniker K", company_id=company.id, dedup_key="detail-screen-company-1", status="active")
    make_job(title="Elektroniker L", company_id=company.id, dedup_key="detail-screen-company-2", status="active")
    make_job(title="Elektroniker M (closed)", company_id=company.id, dedup_key="detail-screen-company-3", status="closed")

    resp = client.get(f"/jobs/{job.id}")
    assert b"OPEN POSITIONS" in resp.data
    # 2 active jobs at this company (the closed one doesn't count).
    assert b">2<" in resp.data


def test_match_band_hidden_when_score_is_none(client, db, make_user):
    """compute_match() returns score=None only when profile is None
    entirely (location alone always evaluates, so any real profile
    - even a bare one - always produces a score) - deleting the
    CandidateProfile row is the only way to reach that branch through the
    real route, mirroring the one case where it's reachable in production
    (a user record without a profile). The honest "not enough data"
    message must render instead of an empty match_band."""
    user = make_user(email="d12@example.com", password="Password123!")
    login(client, "d12@example.com", "Password123!")
    db.session.delete(user.profile)
    db.session.commit()
    job = make_job(title="Elektroniker N")

    resp = client.get(f"/jobs/{job.id}")
    assert b"Not enough data to compute a match" in resp.data
