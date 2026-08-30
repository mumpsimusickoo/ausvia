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


# --- Adzuna off-by-default pass (2026-08-30): real credentials must never
# be sufficient on their own to go live in real search - see
# app/jobs/adapters/manager.py's SEED_DISABLED_SOURCES docstring. Found
# live: real credentials existing in .env would have made Adzuna appear
# in real user search results immediately, with no deliberate admin
# action, because (a) ensure_source_settings_seeded()'s old blanket
# default seeded every source is_enabled=True, and (b) even without a
# seeded row at all, get_enabled_adapter_names()'s old fallback treated
# an absent row as enabled. Both are fixed below; this replaces the old
# test_configured_adzuna_appears_in_enabled_adapters, which was asserting
# the buggy fail-open behavior as if it were correct - same shape as an
# earlier session's password-reset test rewrite. ---

def test_configured_adzuna_is_not_enabled_with_no_settings_row_at_all(app, db):
    # ensure_source_settings_seeded() is only ever called from the admin
    # job-sources page - a fresh deployment can run real search traffic
    # before any admin has ever visited it, so no JobSourceSetting row
    # exists for any source yet. Real credentials alone must still not be
    # enough for Adzuna in that state.
    app.config["ADZUNA_APP_ID"] = "test-id"
    app.config["ADZUNA_APP_KEY"] = "test-key"
    with app.app_context():
        assert JobSourceSetting.query.count() == 0
        names = adapter_manager.get_enabled_adapter_names()
    assert "adzuna" not in names
    # Arbeitsagentur's fail-open default is unaffected - it needs no
    # credentials and should keep working with zero admin setup.
    assert "arbeitsagentur" in names


def test_configured_adzuna_defaults_disabled_when_freshly_seeded(app, db):
    app.config["ADZUNA_APP_ID"] = "test-id"
    app.config["ADZUNA_APP_KEY"] = "test-key"
    with app.app_context():
        adapter_manager.ensure_source_settings_seeded()
        setting = JobSourceSetting.query.filter_by(source_name="adzuna").first()
        assert setting.is_enabled is False
        names = adapter_manager.get_enabled_adapter_names()
    assert "adzuna" not in names


def test_configured_adzuna_appears_once_explicitly_enabled(app, db):
    app.config["ADZUNA_APP_ID"] = "test-id"
    app.config["ADZUNA_APP_KEY"] = "test-key"
    with app.app_context():
        db.session.add(JobSourceSetting(source_name="adzuna", display_name="Adzuna", is_enabled=True))
        db.session.commit()
        names = adapter_manager.get_enabled_adapter_names()
    assert "adzuna" in names


def test_configured_adzuna_disappears_once_explicitly_disabled_again(app, db):
    app.config["ADZUNA_APP_ID"] = "test-id"
    app.config["ADZUNA_APP_KEY"] = "test-key"
    with app.app_context():
        setting = JobSourceSetting(source_name="adzuna", display_name="Adzuna", is_enabled=True)
        db.session.add(setting)
        db.session.commit()
        assert "adzuna" in adapter_manager.get_enabled_adapter_names()

        setting.is_enabled = False
        db.session.commit()
        assert "adzuna" not in adapter_manager.get_enabled_adapter_names()


def test_other_sources_still_default_enabled_with_no_settings_row(app, db):
    # Only Adzuna's default changed - Jooble (once configured) and
    # Arbeitsagentur must keep their existing fail-open-enabled behavior
    # with zero admin setup.
    app.config["JOOBLE_API_KEY"] = "test-jooble-key"
    with app.app_context():
        assert JobSourceSetting.query.count() == 0
        names = adapter_manager.get_enabled_adapter_names()
    assert "jooble" in names
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


# --- Route-level verification, Adzuna off-by-default pass (2026-08-30):
# a non-admin user's actual search page must not offer Adzuna as a source
# while disabled, even with real credentials configured, and must offer
# it immediately after an admin toggles it on via the real admin route -
# no code change, no restart, matching how every other source's toggle
# already works. ---

def test_search_page_does_not_offer_adzuna_while_disabled(client, app, db, make_user):
    from tests.conftest import login

    app.config["ADZUNA_APP_ID"] = "test-id"
    app.config["ADZUNA_APP_KEY"] = "test-key"

    make_user(email="searcher@example.com", password="Password123!")
    login(client, "searcher@example.com", "Password123!")

    resp = client.get("/jobs/")
    body = resp.data.decode("utf-8")
    assert "Adzuna" not in body


def test_search_page_offers_adzuna_immediately_after_admin_enables_it(client, app, db, make_user):
    from tests.conftest import login

    app.config["ADZUNA_APP_ID"] = "test-id"
    app.config["ADZUNA_APP_KEY"] = "test-key"

    make_user(email="searcher2@example.com", password="Password123!")
    admin = make_user(email="admin-adzuna@example.com", password="Password123!", role="admin")

    login(client, "admin-adzuna@example.com", "Password123!")
    # ensure_source_settings_seeded() runs as a side effect of visiting
    # the admin page - matches how a real admin would actually enable it.
    client.get("/admin/job-sources")
    setting = JobSourceSetting.query.filter_by(source_name="adzuna").first()
    assert setting.is_enabled is False  # confirms the off-by-default fix seeded it correctly
    client.post(f"/admin/job-sources/{setting.id}/toggle")
    db.session.refresh(setting)
    assert setting.is_enabled is True

    client.get("/auth/logout")
    login(client, "searcher2@example.com", "Password123!")
    resp = client.get("/jobs/")
    body = resp.data.decode("utf-8")
    assert "Adzuna" in body
