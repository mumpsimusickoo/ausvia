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
from app.jobs.adapters.jooble import (
    JOOBLE_HARD_STOP_AT,
    JOOBLE_LIFETIME_BUDGET,
    JOOBLE_WARNING_THRESHOLD,
    JoobleAdapter,
    record_jooble_request,
)
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

    proceed = record_jooble_request()
    assert proceed is True
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


# --- Hard stop (2026-08-29 follow-up): the counter/warning alone never
# refused a call - request_count could climb straight past the true
# lifetime cap while only ever logging about it. record_jooble_request()
# now refuses the call outright once JOOBLE_HARD_STOP_AT is reached. ---

def test_record_jooble_request_refuses_at_hard_stop_ceiling(app, db):
    setting = JobSourceSetting(source_name="jooble", display_name="Jooble", request_count=JOOBLE_HARD_STOP_AT)
    db.session.add(setting)
    db.session.commit()

    proceed = record_jooble_request()

    assert proceed is False
    db.session.refresh(setting)
    assert setting.request_count == JOOBLE_HARD_STOP_AT  # unchanged - no call means nothing to count

    error_log = SystemLog.query.filter_by(category="job_source", level="error").order_by(
        SystemLog.created_at.desc()
    ).first()
    assert error_log is not None
    assert "hard stop" in error_log.message.lower()
    # Distinct from the "getting close" warning - this call produced the
    # error, not another warning.
    assert SystemLog.query.filter_by(category="job_source", level="warning").first() is None


def test_record_jooble_request_refuses_past_hard_stop_ceiling(app, db):
    # Not just exactly-at-ceiling - anything at or above must refuse too.
    setting = JobSourceSetting(source_name="jooble", display_name="Jooble", request_count=JOOBLE_LIFETIME_BUDGET)
    db.session.add(setting)
    db.session.commit()

    assert record_jooble_request() is False
    db.session.refresh(setting)
    assert setting.request_count == JOOBLE_LIFETIME_BUDGET


def test_record_jooble_request_still_proceeds_just_below_hard_stop(app, db):
    setting = JobSourceSetting(source_name="jooble", display_name="Jooble", request_count=JOOBLE_HARD_STOP_AT - 1)
    db.session.add(setting)
    db.session.commit()

    assert record_jooble_request() is True
    db.session.refresh(setting)
    assert setting.request_count == JOOBLE_HARD_STOP_AT


def test_admin_search_gets_no_jooble_results_once_hard_stopped(client, db, app, make_user, monkeypatch):
    # The whole point: refuse the call, not just log about it - and the
    # request itself must still succeed gracefully (no Jooble results,
    # not an error page), same as if the source were simply disabled.
    _configure_jooble(app)
    _mock_arbeitsagentur_empty(monkeypatch)
    make_user(email="theadmin4@example.com", password="Password123!", role="admin")
    login(client, "theadmin4@example.com", "Password123!")

    setting = JobSourceSetting(source_name="jooble", display_name="Jooble", request_count=JOOBLE_HARD_STOP_AT)
    db.session.add(setting)
    db.session.commit()

    calls = []
    monkeypatch.setattr(JoobleAdapter, "search", lambda self, *a, **kw: calls.append(1) or [JOOBLE_RAW_JOB])

    resp = client.get("/jobs/?keywords=Elektroniker")

    assert resp.status_code == 200
    assert calls == []  # the call was refused, not attempted
    assert b"Jooble Test GmbH" not in resp.data
    db.session.refresh(setting)
    assert setting.request_count == JOOBLE_HARD_STOP_AT  # unchanged

    error_log = SystemLog.query.filter_by(category="job_source", level="error").first()
    assert error_log is not None
    assert "hard stop" in error_log.message.lower()


def test_radar_check_with_three_fields_increments_counter_by_three(client, db, app, make_user, monkeypatch):
    # Each of MAX_FIELDS_PER_CHECK preferred fields is a distinct keyword,
    # so none of the three ingest_search() calls collide in
    # ProviderQueryCache - each is a real, separately-counted call.
    _configure_jooble(app)
    _mock_arbeitsagentur_empty(monkeypatch)
    user = make_user(email="theadmin5@example.com", password="Password123!", role="admin")
    pref = Preference(
        profile_id=user.profile.id,
        fields=["Elektroniker", "Mechatroniker", "Fachinformatiker"],
        locations=["Berlin"],
    )
    db.session.add(pref)
    db.session.commit()
    login(client, "theadmin5@example.com", "Password123!")

    monkeypatch.setattr(JoobleAdapter, "search", lambda self, *a, **kw: [JOOBLE_RAW_JOB])

    resp = client.post("/jobs/check-now", follow_redirects=True)
    assert resp.status_code == 200

    setting = JobSourceSetting.query.filter_by(source_name="jooble").first()
    assert setting.request_count == 3
