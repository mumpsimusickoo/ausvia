"""Tests for app/jobs/adapters/manager.py's config-based adapter
registration (job-source integration pass) - Adzuna/Jooble should be
silently absent when unconfigured (not an error), and present once
credentials exist. Arbeitsagentur must remain unconditionally present,
matching pre-existing behavior tests/test_jobs.py already relies on
(monkeypatching adapter_manager.ADAPTERS["arbeitsagentur"] directly).
"""
from app.jobs.adapters import manager as adapter_manager
from app.jobs.adapters.adzuna import AdzunaAdapter
from app.jobs.adapters.arbeitsagentur import ArbeitsagenturAdapter
from app.jobs.adapters.jooble import JoobleAdapter


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
