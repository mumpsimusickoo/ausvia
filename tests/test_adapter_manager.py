"""Tests for app/jobs/adapters/manager.py's config-based adapter
registration (job-source integration pass) - Adzuna/Jooble should be
silently absent when unconfigured (not an error), and present once
credentials exist. Arbeitsagentur must remain unconditionally present,
matching pre-existing behavior tests/test_jobs.py already relies on
(monkeypatching adapter_manager.ADAPTERS["arbeitsagentur"] directly).
"""
from flask_babel import force_locale

from app.jobs.adapters import manager as adapter_manager
from app.jobs.adapters.adzuna import AdzunaAdapter
from app.jobs.adapters.arbeitsagentur import ArbeitsagenturAdapter
from app.jobs.adapters.jooble import JoobleAdapter
from app.models.job import JobSourceSetting


def test_arbeitsagentur_always_present(app):
    with app.app_context():
        adapters = adapter_manager.all_adapters()
    assert isinstance(adapters["arbeitsagentur"], ArbeitsagenturAdapter)


def test_adzuna_absent_when_unconfigured(app):
    # TestingConfig forces these to None regardless of a real local .env -
    # see config.py.
    with app.app_context():
        adapters = adapter_manager.all_adapters()
    assert "adzuna" not in adapters


def test_jooble_absent_when_unconfigured(app):
    with app.app_context():
        adapters = adapter_manager.all_adapters()
    assert "jooble" not in adapters


def test_adzuna_present_once_configured(app, monkeypatch):
    app.config["ADZUNA_APP_ID"] = "test-id"
    app.config["ADZUNA_APP_KEY"] = "test-key"
    with app.app_context():
        adapters = adapter_manager.all_adapters()
    assert isinstance(adapters["adzuna"], AdzunaAdapter)
    assert adapters["adzuna"].app_id == "test-id"
    assert adapters["adzuna"].country == "de"


def test_adzuna_absent_with_only_app_id_set(app):
    # Both app_id AND app_key are required - one alone must not register it.
    app.config["ADZUNA_APP_ID"] = "test-id"
    with app.app_context():
        adapters = adapter_manager.all_adapters()
    assert "adzuna" not in adapters


def test_jooble_present_once_configured(app):
    app.config["JOOBLE_API_KEY"] = "test-jooble-key"
    with app.app_context():
        adapters = adapter_manager.all_adapters()
    assert isinstance(adapters["jooble"], JoobleAdapter)
    assert adapters["jooble"].api_key == "test-jooble-key"


def test_configured_adzuna_appears_in_enabled_adapters(app, db):
    app.config["ADZUNA_APP_ID"] = "test-id"
    app.config["ADZUNA_APP_KEY"] = "test-key"
    with app.app_context():
        names = adapter_manager.get_enabled_adapter_names()
    assert "adzuna" in names
    assert "arbeitsagentur" in names


def test_known_sources_includes_new_providers():
    assert "adzuna" in adapter_manager.KNOWN_SOURCES
    assert "jooble" in adapter_manager.KNOWN_SOURCES


def test_ensure_source_settings_seeded_creates_rows_for_new_providers(app, db):
    adapter_manager.ensure_source_settings_seeded()
    from app.models.job import JobSourceSetting

    names = {s.source_name for s in JobSourceSetting.query.all()}
    assert {"arbeitsagentur", "adzuna", "jooble", "manual"} <= names


# --- i18n sweep (2026-08-30): KNOWN_SOURCES["manual"] is a real, locale-
# aware label (_l()-wrapped) - unlike "Bundesagentur für Arbeit
# (Jobsuche)"/"Adzuna"/"Jooble", which are proper names and correctly
# never vary by locale. ---

def test_manual_source_label_is_locale_aware(app):
    with app.test_request_context("/"):
        with force_locale("en"):
            en = str(adapter_manager.KNOWN_SOURCES["manual"])
        with force_locale("de"):
            de = str(adapter_manager.KNOWN_SOURCES["manual"])
    assert en == "Manual import"
    assert de == "Manueller Import"


def test_ensure_source_settings_seeded_does_not_crash_on_lazystring(app, db):
    # The exact LazyString-can't-bind-to-SQLite pattern this app has hit
    # repeatedly - display_name must be str()'d before assignment, or
    # this raises sqlite3.ProgrammingError instead of committing cleanly.
    adapter_manager.ensure_source_settings_seeded()
    setting = JobSourceSetting.query.filter_by(source_name="manual").first()
    assert setting is not None
    assert isinstance(setting.display_name, str)
    assert setting.display_name == "Manual import"


def test_record_run_does_not_crash_on_lazystring_for_new_source(app, db):
    adapter_manager.record_run("manual", "ok", "test message")
    setting = JobSourceSetting.query.filter_by(source_name="manual").first()
    assert setting is not None
    assert isinstance(setting.display_name, str)
    assert setting.display_name == "Manual import"


def test_job_sources_page_prefers_live_translation_over_stored_snapshot(client, db, make_user):
    from tests.conftest import login

    # Seed the row in English (the default locale), matching what already
    # happens in production today - the stored display_name is frozen at
    # whatever locale was active at seed time.
    adapter_manager.ensure_source_settings_seeded()
    setting = JobSourceSetting.query.filter_by(source_name="manual").first()
    assert setting.display_name == "Manual import"  # sanity: seeded in English

    make_user(email="admin-jobsources@example.com", password="Password123!", role="admin")
    login(client, "admin-jobsources@example.com", "Password123!")
    client.post("/set-locale", data={"lang": "de", "next": "/admin/job-sources"})

    resp = client.get("/admin/job-sources")
    body = resp.data.decode("utf-8")
    # Must show the CURRENT (German) translation, not the stored
    # (English, seed-time) snapshot - proves the page reads live from
    # KNOWN_SOURCES, not s.display_name.
    assert "Manueller Import" in body
    assert "Manual import" not in body
