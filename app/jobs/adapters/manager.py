"""
Central registry of job source adapters (spec section 10). Sources can be
enabled/disabled independently by an admin via JobSourceSetting without
touching code - see app/admin/routes.py.
"""
from app.extensions import db
from app.models.job import JobSourceSetting
from app.jobs.adapters.arbeitsagentur import ArbeitsagenturAdapter

ADAPTERS = {
    "arbeitsagentur": ArbeitsagenturAdapter(),
}

# "manual" isn't a searchable adapter (it's user-driven, one URL at a time -
# see app/jobs/manual_import.py) but still gets a settings row so admins can
# see/toggle it alongside real adapters for consistency.
KNOWN_SOURCES = {
    "arbeitsagentur": "Bundesagentur für Arbeit (Jobsuche)",
    "manual": "Manual import",
}


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
        for name in ADAPTERS
        if name not in settings or settings[name].is_enabled
    ]


def get_enabled_adapters():
    enabled_names = set(get_enabled_adapter_names())
    return [adapter for name, adapter in ADAPTERS.items() if name in enabled_names]


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
