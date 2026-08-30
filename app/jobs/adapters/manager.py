"""
Central registry of job source adapters (spec section 10). Sources can be
enabled/disabled independently by an admin via JobSourceSetting without
touching code - see app/admin/routes.py.
"""
from flask import current_app
from flask_babel import lazy_gettext as _l

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
#
# i18n sweep (2026-08-30): "manual" is the only value here that's a real
# functional label, not a proper name - "Bundesagentur für Arbeit
# (Jobsuche)" is the agency's actual name, "Adzuna"/"Jooble" are company
# names, none of the three vary by locale on purpose. "manual" now does,
# via _l() - callers that persist this to JobSourceSetting.display_name
# (ensure_source_settings_seeded()/record_run() below) must str() it at
# the point of assignment, the same LazyString-can't-bind-to-SQLite
# pattern this app has hit repeatedly elsewhere. Also note: a value
# resolved and stored that way is frozen at whichever locale was active
# the moment that row was first created, not re-evaluated per later
# admin page view - see app/admin/routes.py's job_sources() route, which
# renders straight from this dict instead of the stored column for
# exactly that reason.
KNOWN_SOURCES = {
    "arbeitsagentur": "Bundesagentur für Arbeit (Jobsuche)",
    "adzuna": "Adzuna",
    "jooble": "Jooble",
    "manual": _l("Manual import"),
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


# Adzuna off-by-default pass (2026-08-30): unlike every other source here,
# Adzuna must never go live just because ADZUNA_APP_ID/ADZUNA_APP_KEY exist
# in config - real credentials are necessary but not sufficient, an admin
# also has to deliberately flip JobSourceSetting.is_enabled on via
# /admin/job-sources first. Found live: this row was seeded is_enabled=True
# (same blanket default every other source gets) back when no Adzuna
# credentials existed yet, so the moment real credentials were added to
# .env this session, Adzuna would have started appearing in real user
# search results with no deliberate admin action at all - the exact
# opposite of Jooble's already-careful ADMIN_ONLY_SOURCES gating above.
# This doesn't need Jooble's admin-only *scoping* (Adzuna's limits reset
# daily/weekly/monthly, not a lifetime cap) - just an off-by-default
# toggle, reusing the same is_enabled infrastructure every source already
# has. See migrations/versions/ for the one-time fix to any row seeded
# True before this pass, in this DB or an already-deployed one.
SEED_DISABLED_SOURCES = {"adzuna"}


def ensure_source_settings_seeded():
    existing = {s.source_name for s in JobSourceSetting.query.all()}
    for name, display_name in KNOWN_SOURCES.items():
        if name not in existing:
            # str(): display_name may be a LazyString (KNOWN_SOURCES["manual"]) -
            # SQLite/SQLAlchemy can't bind that type directly to a column.
            db.session.add(JobSourceSetting(
                source_name=name, display_name=str(display_name),
                is_enabled=name not in SEED_DISABLED_SOURCES,
            ))
    db.session.commit()


def get_enabled_adapter_names():
    # ensure_source_settings_seeded() is only ever called from the admin
    # job-sources page itself (app/admin/routes.py) - a fresh deployment
    # can genuinely run real search traffic before any admin has ever
    # visited it, meaning no JobSourceSetting row exists for ANY source
    # yet. The old fallback (no row -> treat as enabled) is intentional
    # and correct for Arbeitsagentur (needs no credentials, should just
    # work) but was ALSO silently applying to Adzuna - the exact
    # "credentials alone are enough" gap this pass closes. A source in
    # SEED_DISABLED_SOURCES defaults to NOT enabled when no row exists
    # yet, same as its seed default above, so the two can never disagree.
    settings = {s.source_name: s for s in JobSourceSetting.query.all()}
    return [
        name
        for name in all_adapters()
        if (settings[name].is_enabled if name in settings else name not in SEED_DISABLED_SOURCES)
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
        # str(): same LazyString-can't-bind-to-SQLite reasoning as
        # ensure_source_settings_seeded() above.
        setting = JobSourceSetting(
            source_name=source_name, display_name=str(KNOWN_SOURCES.get(source_name, source_name))
        )
        db.session.add(setting)
    setting.last_run_at = utcnow()
    setting.last_run_status = status
    setting.last_run_message = (message or "")[:500]
    db.session.commit()
