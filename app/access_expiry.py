"""Real automatic access expiry once a paid period ends (plans page +
access expiry pass, 2026-08-30). Two checkpoints, no scheduler -
consistent with this app's existing check-at-request-time architecture
(app/jobs/radar.py's on-demand job radar, app/priority_digest.py) rather
than a background job:

1. Login time (app/auth/routes.py's login()) - refuses login outright if
   access_expires_at has passed.
2. Mid-session (enforce_access_expiry() below, registered as an app-wide
   before_request in app/__init__.py) - logs an already-authenticated
   user out the moment their expiry passes, on their very next request,
   not just their next login attempt.

is_access_expired() is the single shared check both use, so the two
checkpoints can never drift on what "expired" means.
"""
from dateutil.relativedelta import relativedelta
from flask import flash, redirect, url_for
from flask_babel import gettext as _
from flask_login import current_user, logout_user

from app.models.user import utcnow
from app.plans import whatsapp_display


def compute_access_expiry(redeemed_at, duration_months):
    """redeemed_at + duration_months CALENDAR months (dateutil.relativedelta,
    not a flat day count) - a mid-month purchase isn't shorted a few days,
    and a leap-year February doesn't cause drift or an error (Jan 31 + 1
    month correctly lands on Feb 28/29, clamped to that month's real last
    day, never rolled over into March). Called once, at redemption time
    (app/auth/routes.py's register()) - never recomputed later."""
    return redeemed_at + relativedelta(months=duration_months)


def is_access_expired(user):
    """None means no expiry (unaffected: trial/admin accounts, pre-existing
    users, any code redeemed without a duration) - only a real, passed
    timestamp counts as expired."""
    return user.access_expires_at is not None and user.access_expires_at < utcnow()


def enforce_access_expiry():
    """App-wide before_request (registered in app/__init__.py) - the
    mid-session checkpoint. Cheap for the overwhelming majority of
    requests (anonymous, or an authenticated user with no expiry set):
    current_user is already loaded by Flask-Login's own session handling
    for every authenticated request regardless of this hook, so checking
    its already-loaded access_expires_at attribute adds no new query."""
    if not current_user.is_authenticated:
        return None
    if not is_access_expired(current_user):
        return None
    logout_user()
    flash(
        _(
            "Your access period has ended. Contact us on WhatsApp (%(whatsapp)s) to renew.",
            whatsapp=whatsapp_display(),
        ),
        "error",
    )
    return redirect(url_for("auth.login"))
