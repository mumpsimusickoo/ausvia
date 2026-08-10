"""
Structured admin-diagnostics logging. Deliberately takes no 'extra' free-form
payload - callers pass a short message string only, so it's not possible to
accidentally dump a password, access code, API key, or document contents into
the log by passing an object through. Keep messages short and factual.
"""
from app.extensions import db
from app.models.system_log import SystemLog


def log_event(category, message, level="info", user_id=None):
    entry = SystemLog(category=category, message=message[:1000], level=level, user_id=user_id)
    db.session.add(entry)
    db.session.commit()
    return entry
