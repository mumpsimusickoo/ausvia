"""Tests for the Jooble admin-only scoping pass (2026-08-29): Jooble's
free tier is a 500-request LIFETIME cap (no reset, only a new key), so
its budget is reserved for the maintainer's own account and never spent
on general invited-user search traffic. These are route-level proof -
not just unit-level - that the real adapter is never invoked for a
non-admin user; tests/test_ingest.py covers the underlying
ingest_search(admin=...) filter directly against a fake adapter.

Arbeitsagentur's own adapter is mocked in every test here (returns []) to
avoid a real outbound network call - unrelated to what's being tested,
but ADAPTERS["arbeitsagentur"] is unconditionally present and would
otherwise be queried on every /jobs/ search alongside Jooble.
"""
from app.jobs.adapters import manager as adapter_manager
from app.jobs.adapters.jooble import JOOBLE_LIFETIME_BUDGET, JOOBLE_WARNING_THRESHOLD, JoobleAdapter, record_jooble_request
from app.models.job import JobSourceSetting
from app.models.profile import Preference
from app.models.system_log import SystemLog
from tests.conftest import login

JOOBLE_RAW_JOB = {
    "id": 555111222,
    "title": "Ausbildung Elektroniker",
    "location": "Leipzig",
    "snippet": "Wir suchen dich...",
    "company": "Jooble Test GmbH",
    "type": "Vollzeit",
    "link": "https://de.jooble.org/jdp/555111222",
}


def _configure_jooble(app):
    app.config["JOOBLE_API_KEY"] = "test-jooble-key"


def _mock_arbeitsagentur_empty(monkeypatch):
    monkeypatch.setattr(adapter_manager.ADAPTERS["arbeitsagentur"], "search", lambda keywords, location=None, **kw: [])


def test_non_admin_search_never_invokes_jooble_adapter(client, db, app, make_user, monkeypatch):
    _configure_jooble(app)
    _mock_arbeitsagentur_empty(monkeypatch)
    make_user(email="regular@example.com", password="Password123!", role="user")
    login(client, "regular@example.com", "Password123!")

    calls = []
    monkeypatch.setattr(JoobleAdapter, "search", lambda self, *a, **kw: calls.append(1) or [JOOBLE_RAW_JOB])

    resp = client.get("/jobs/?keywords=Elektroniker")
    assert resp.status_code == 200
    # Proves the call itself never happened - not just that results are
    # filtered out afterward.
    assert calls == []
    assert b"Jooble Test GmbH" not in resp.data


def test_non_admin_source_choices_exclude_jooble(client, db, app, make_user, monkeypatch):
    _configure_jooble(app)
    _mock_arbeitsagentur_empty(monkeypatch)
    make_user(email="regular2@example.com", password="Password123!", role="user")
    login(client, "regular2@example.com", "Password123!")

    resp = client.get("/jobs/")
    assert resp.status_code == 200
    assert b"jooble" not in resp.data.lower()


def test_admin_search_invokes_jooble_adapter_and_shows_source_badge(client, db, app, make_user, monkeypatch):
    _configure_jooble(app)
    _mock_arbeitsagentur_empty(monkeypatch)
    make_user(email="theadmin@example.com", password="Password123!", role="admin")
    login(client, "theadmin@example.com", "Password123!")

    calls = []
    monkeypatch.setattr(JoobleAdapter, "search", lambda self, *a, **kw: calls.append(1) or [JOOBLE_RAW_JOB])

    resp = client.get("/jobs/?keywords=Elektroniker")
    assert resp.status_code == 200
    assert len(calls) == 1
    body = resp.data.decode("utf-8")
    assert "Jooble Test GmbH" in body
    assert "JOOBLE" in body.upper()  # existing per-job chip_source() badge, unmodified


def test_jooble_request_counter_increments_on_real_call_not_on_cache_hit(client, db, app, make_user, monkeypatch):
    _configure_jooble(app)
    _mock_arbeitsagentur_empty(monkeypatch)
    make_user(email="theadmin2@example.com", password="Password123!", role="admin")
    login(client, "theadmin2@example.com", "Password123!")

    monkeypatch.setattr(JoobleAdapter, "search", lambda self, *a, **kw: [JOOBLE_RAW_JOB])

    client.get("/jobs/?keywords=Elektroniker")
    setting = JobSourceSetting.query.filter_by(source_name="jooble").first()
    assert setting.request_count == 1

    # Same query again immediately - ProviderQueryCache's 15-minute TTL
    # (app/jobs/ingest.py) makes this a cache hit, never reaching the
    # adapter - the counter must not move for a call that never happened.
    client.get("/jobs/?keywords=Elektroniker")
    db.session.refresh(setting)
    assert setting.request_count == 1


def test_non_admin_radar_check_also_gates_jooble(client, db, app, make_user, monkeypatch):
    # app/jobs/radar.py:54 is the second call site named in the scoping
    # spec - "Jetzt prüfen" must respect the same admin-only rule as the
    # typed search box.
    _configure_jooble(app)
    _mock_arbeitsagentur_empty(monkeypatch)

    user = make_user(email="regular3@example.com", password="Password123!", role="user")
    pref = Preference(profile_id=user.profile.id, fields=["Elektroniker"], locations=["Berlin"])
    db.session.add(pref)
    db.session.commit()
    login(client, "regular3@example.com", "Password123!")

    calls = []
    monkeypatch.setattr(JoobleAdapter, "search", lambda self, *a, **kw: calls.append(1) or [JOOBLE_RAW_JOB])

    resp = client.post("/jobs/check-now", follow_redirects=True)
    assert resp.status_code == 200
    assert calls == []


def test_admin_radar_check_invokes_jooble(client, db, app, make_user, monkeypatch):
    _configure_jooble(app)
    _mock_arbeitsagentur_empty(monkeypatch)

    user = make_user(email="theadmin3@example.com", password="Password123!", role="admin")
    pref = Preference(profile_id=user.profile.id, fields=["Elektroniker"], locations=["Berlin"])
    db.session.add(pref)
    db.session.commit()
    login(client, "theadmin3@example.com", "Password123!")

    calls = []
    monkeypatch.setattr(JoobleAdapter, "search", lambda self, *a, **kw: calls.append(1) or [JOOBLE_RAW_JOB])

    resp = client.post("/jobs/check-now", follow_redirects=True)
    assert resp.status_code == 200
    assert len(calls) == 1


# --- record_jooble_request() unit tests ---

def test_record_jooble_request_creates_row_and_increments(app, db):
    assert JobSourceSetting.query.filter_by(source_name="jooble").first() is None

    count = record_jooble_request()
    assert count == 1
    setting = JobSourceSetting.query.filter_by(source_name="jooble").first()
    assert setting is not None
    assert setting.request_count == 1

    record_jooble_request()
    db.session.refresh(setting)
    assert setting.request_count == 2


def test_record_jooble_request_logs_warning_below_threshold(app, db):
    setting = JobSourceSetting(
        source_name="jooble", display_name="Jooble",
        request_count=JOOBLE_LIFETIME_BUDGET - JOOBLE_WARNING_THRESHOLD,  # one call from the threshold
    )
    db.session.add(setting)
    db.session.commit()

    record_jooble_request()

    warning = SystemLog.query.filter_by(category="job_source", level="warning").order_by(
        SystemLog.created_at.desc()
    ).first()
    assert warning is not None
    assert "budget low" in warning.message.lower()


def test_record_jooble_request_no_warning_well_above_threshold(app, db):
    record_jooble_request()  # 1 of 500 used, nowhere near JOOBLE_WARNING_THRESHOLD

    warning = SystemLog.query.filter_by(category="job_source", level="warning").first()
    assert warning is None
