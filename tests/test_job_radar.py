"""Tests for the on-demand "Check now" job radar (design-audit decision,
2026-08-24): request-triggered only, no scheduler involved anywhere in this
feature - see app/jobs/radar.py's module docstring."""
from app.jobs.adapters import manager as adapter_manager
from app.models.job import Job, JobRadarStatus, JobSourceSetting
from app.models.profile import Preference
from tests.conftest import login
from tests.test_jobs import SAMPLE_RAW_JOB


def _set_preference(db, user, fields, locations=None):
    profile = user.profile
    pref = Preference(profile_id=profile.id, fields=fields, locations=locations or [])
    db.session.add(pref)
    db.session.commit()


def test_check_now_requires_preferences_first(client, db, make_user):
    make_user(email="radar1@example.com", password="Password123!")
    login(client, "radar1@example.com", "Password123!")

    resp = client.post("/jobs/check-now", follow_redirects=True)
    assert resp.status_code == 200
    assert b"Set at least one desired field" in resp.data
    assert JobRadarStatus.query.count() == 0


def test_check_now_ingests_and_records_new_jobs(client, db, make_user, monkeypatch):
    user = make_user(email="radar2@example.com", password="Password123!")
    login(client, "radar2@example.com", "Password123!")
    _set_preference(db, user, fields=["Elektroniker"])

    monkeypatch.setattr(
        adapter_manager.ADAPTERS["arbeitsagentur"], "search",
        lambda keywords, location=None, **kw: [SAMPLE_RAW_JOB],
    )

    resp = client.post("/jobs/check-now", follow_redirects=True)
    assert resp.status_code == 200
    assert b"1 new listing" in resp.data
    assert Job.query.count() == 1

    status = JobRadarStatus.query.filter_by(user_id=user.id).first()
    job = Job.query.first()
    assert status is not None
    assert status.new_job_count == 1
    assert status.new_job_ids == [job.id]


def test_check_now_second_run_of_same_job_finds_nothing_new(client, db, make_user, monkeypatch):
    user = make_user(email="radar3@example.com", password="Password123!")
    login(client, "radar3@example.com", "Password123!")
    _set_preference(db, user, fields=["Elektroniker"])

    monkeypatch.setattr(
        adapter_manager.ADAPTERS["arbeitsagentur"], "search",
        lambda keywords, location=None, **kw: [SAMPLE_RAW_JOB],
    )
    client.post("/jobs/check-now")

    resp = client.post("/jobs/check-now", follow_redirects=True)
    assert b"No new listings found" in resp.data
    assert Job.query.count() == 1  # deduped, not a second row


def test_check_now_respects_disabled_sources(client, db, make_user, monkeypatch):
    user = make_user(email="radar4@example.com", password="Password123!")
    login(client, "radar4@example.com", "Password123!")
    _set_preference(db, user, fields=["Elektroniker"])

    adapter_manager.ensure_source_settings_seeded()
    setting = JobSourceSetting.query.filter_by(source_name="arbeitsagentur").first()
    setting.is_enabled = False
    db.session.commit()

    calls = []
    monkeypatch.setattr(
        adapter_manager.ADAPTERS["arbeitsagentur"], "search",
        lambda keywords, location=None, **kw: calls.append(1) or [SAMPLE_RAW_JOB],
    )

    client.post("/jobs/check-now")
    assert calls == []
    assert Job.query.count() == 0


def test_check_now_caps_number_of_fields_searched(client, db, make_user, monkeypatch):
    user = make_user(email="radar5@example.com", password="Password123!")
    login(client, "radar5@example.com", "Password123!")
    _set_preference(db, user, fields=["A", "B", "C", "D", "E"])

    calls = []

    def fake_search(keywords, location=None, **kw):
        calls.append(keywords)
        return []

    monkeypatch.setattr(adapter_manager.ADAPTERS["arbeitsagentur"], "search", fake_search)

    client.post("/jobs/check-now")
    assert calls == ["A", "B", "C"]  # MAX_FIELDS_PER_CHECK, not all 5


def test_dashboard_shows_check_now_button_and_latest_results(client, db, make_user, monkeypatch):
    # Screens pass 3 (Dashboard, 2026-08-27): the rail card shows a count of
    # new listings, not an inline per-job list (matches the bundle's compact
    # rail treatment - see DECISIONS.md) - the job itself is still reachable
    # via Find Ausbildung, not asserted here.
    user = make_user(email="radar6@example.com", password="Password123!")
    login(client, "radar6@example.com", "Password123!")
    _set_preference(db, user, fields=["Elektroniker"])

    monkeypatch.setattr(
        adapter_manager.ADAPTERS["arbeitsagentur"], "search",
        lambda keywords, location=None, **kw: [SAMPLE_RAW_JOB],
    )
    client.post("/jobs/check-now")

    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert b"Check now" in resp.data
    assert b"1 new listing for your profile" in resp.data


def test_dashboard_check_now_button_present_without_any_prior_check(client, db, make_user):
    make_user(email="radar7@example.com", password="Password123!")
    login(client, "radar7@example.com", "Password123!")

    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert b"Check now" in resp.data
    assert b"haven&#39;t run a check yet" in resp.data or b"haven't run a check yet" in resp.data
