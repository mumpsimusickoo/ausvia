"""
Central registry of job source adapters (spec section 10). Sources can be
enabled/disabled independently by an admin via JobSourceSetting without
touching code - see app/admin/routes.py.
"""
from flask import current_app

from app.extensions import db
from app.models.job import JobSourceSetting
from app.jobs.adapters.arbeitsagentur import ArbeitsagenturAdapter
from app.jobs.adapters.adzuna import AdzunaAdapter
from app.jobs.adapters.jooble import JoobleAdapter

# Adapters that need no configuration - built once at import time, exactly
# like before. Adzuna/Jooble need credentials that only exist once a Flask
# app/request context is active (current_app.config isn't readable at
# plain module-import time), so they're built lazily by
# _configured_adapters() below instead of living in this dict.
ADAPTERS = {
    "arbeitsagentur": ArbeitsagenturAdapter(),
}

# "manual" isn't a searchable adapter (it's user-driven, one URL at a time -
# see app/jobs/manual_import.py) but still gets a settings row so admins can
# see/toggle it alongside real adapters for consistency. Adzuna/Jooble get a
# row too even before their credentials are configured, same reasoning.
KNOWN_SOURCES = {
    "arbeitsagentur": "Bundesagentur für Arbeit (Jobsuche)",
    "adzuna": "Adzuna",
    "jooble": "Jooble",
    "manual": "Manual import",
}

# Jooble admin-only scoping pass (2026-08-29): Jooble's free tier is a
# 500-request LIFETIME cap (no reset, only a new key), and this budget is
# reserved for the maintainer's own account rather than spent on general
# invited-user traffic. A source in this set stays fully configurable via
# JobSourceSetting like any other (an admin can still enable/disable it
# in /admin/job-sources), but is deliberately excluded from every
# non-admin-facing enabled-source list regardless of that toggle - see
# app/jobs/ingest.py's ingest_search(admin=...), app/jobs/routes.py's
# search(), and app/main/routes.py's landing() for the three places this
# is actually enforced (this module intentionally does NOT filter it out
# of get_enabled_adapter_names()/get_enabled_adapters() itself, so admin
# call sites can still see and use it). See DECISIONS.md for the full
# reasoning.
ADMIN_ONLY_SOURCES = {"jooble"}


def _configured_adapters():
    """Adzuna/Jooble, built fresh per call from current_app.config - a
    provider with no credentials configured is simply absent from the
    returned dict (not an error, not a placeholder), so it's silently
    skipped everywhere downstream (search, admin diagnostics) until real
    credentials are set."""
    adapters = {}

    app_id = current_app.config.get("ADZUNA_APP_ID")
    app_key = current_app.config.get("ADZUNA_APP_KEY")
    if app_id and app_key:
        adapters["adzuna"] = AdzunaAdapter(
            app_id=app_id, app_key=app_key, country=current_app.config.get("ADZUNA_COUNTRY") or "de",
        )

    jooble_key = current_app.config.get("JOOBLE_API_KEY")
    if jooble_key:
        adapters["jooble"] = JoobleAdapter(api_key=jooble_key)

    return adapters


def all_adapters():
    """The full adapter set for this request: the always-present ones plus
    whichever configured ones are actually available right now."""
    return {**ADAPTERS, **_configured_adapters()}


def ensure_source_settings_seeded():
    existing = {s.source_name for s in JobSourceSetting.query.all()}
    for name, display_name in KNOWN_SOURCES.items():
        if name not in existing:
            db.session.add(JobSourceSetting(source_name=name, display_name=display_name, is_enabled=True))
    db.session.commit()


def get_enabled_adapter_names():
    settings = {s.source_name: s for s in JobSourceSetting.query.all()}
    return [
        name
        for name in all_adapters()
        if name not in settings or settings[name].is_enabled
    ]


def get_enabled_adapters():
    enabled_names = set(get_enabled_adapter_names())
    return [adapter for name, adapter in all_adapters().items() if name in enabled_names]


def is_source_enabled(source_name):
    setting = JobSourceSetting.query.filter_by(source_name=source_name).first()
    return setting.is_enabled if setting else True


def record_run(source_name, status, message=None):
    from app.models.user import utcnow

    setting = JobSourceSetting.query.filter_by(source_name=source_name).first()
    if setting is None:
        setting = JobSourceSetting(
            source_name=source_name, display_name=KNOWN_SOURCES.get(source_name, source_name)
        )
        db.session.add(setting)
    setting.last_run_at = utcnow()
    setting.last_run_status = status
    setting.last_run_message = (message or "")[:500]
    db.session.commit()
