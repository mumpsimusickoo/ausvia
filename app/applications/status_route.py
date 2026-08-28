"""Builds the Wayfinding application-status route (visual direction 1c) shown
on the application detail page. This is a *display* transformation only -
every station's marker state and one-line description is derived from data
that already exists (Job.discovered_at, JobMatch.computed_at,
Application.status, ApplicationEvent log, GmailMessage.received_at,
contact_email, interview_date, follow_up_date, notes), never a new data
source.

Screens pass 2 (Application Detail, 2026-08-27) extended this from six
stations to the bundle's eight: Discovered and Matched are new leading
stations (both effectively always reached the moment an application
exists - see build_status_route's docstring for the one edge case where
Matched genuinely can be pending); Reply replaces the old implicit
"follow_up as a station" - follow_up is still a real Application.status
value (a reminder state, not a route position), so status="follow_up" now
maps onto the Reply station's index rather than getting its own station.
The vertical Wayfinding *presentation* itself (marker sizes/rings, dashed-
vs-solid skip/future distinction, the connector rail) is unchanged from
the accessibility-hardened Phase 7 remediation - this pass changed the
station data, not the component. See DECISIONS.md for why the bundle's
own horizontal treatment for this same screen wasn't adopted instead.

accepted/rejected/withdrawn/expired are terminal exits from the route, not
stations on it, so they're surfaced as a separate terminal note rather
than a ninth/tenth station (see build_status_route's docstring).
"""
from flask_babel import gettext as _
from flask_babel import lazy_gettext as _l
from flask_babel import ngettext

from app.i18n import format_local_date, format_local_datetime
from app.models.application import APPLICATION_STATUS_LABELS

STATION_ORDER = ["discovered", "matched", "prepared", "approved", "sent", "reply", "interview", "offer"]
# i18n pass 2: "Sent"/"Interview"/"Offer" reuse APPLICATION_STATUS_LABELS'
# translations (same English word, same catalog entry) rather than
# re-translating separately - "Discovered"/"Matched"/"Prepared"/"Reply"
# have no status-code equivalent, so those are new lazy strings here.
STATION_LABELS = {
    "discovered": _l("Discovered"),
    "matched": _l("Matched"),
    "prepared": _l("Prepared"),
    "approved": _l("Approved"),
    "sent": APPLICATION_STATUS_LABELS["sent"],
    "reply": _l("Reply"),
    "interview": APPLICATION_STATUS_LABELS["interview"],
    "offer": APPLICATION_STATUS_LABELS["offer"],
}
# Application.status values that correspond to a station further down the
# route than "prepared" - not a station name itself (discovered/matched/
# reply have no corresponding status value; "follow_up" is a real status
# but lands on the Reply station's index, not a station of its own).
STATUS_TO_STATION_INDEX = {
    "preparing": STATION_ORDER.index("prepared"),
    "ready": STATION_ORDER.index("approved"),
    "sent": STATION_ORDER.index("sent"),
    "follow_up": STATION_ORDER.index("reply"),
    "interview": STATION_ORDER.index("interview"),
    "offer": STATION_ORDER.index("offer"),
}
TERMINAL_EXCEPTION_STATUSES = ("rejected", "withdrawn", "expired")


def _fmt(dt):
    return format_local_date(dt, format="d MMM") if dt else None


def _latest(events, event_type):
    matches = [e for e in events if e.event_type == event_type]
    return matches[-1] if matches else None


def _status_changed_to(events, value):
    """A status_changed event's description is always
    "Status changed: {old} -> {new}." (see applications/routes.py
    update_status()) - matching the exact "-> {value}." suffix tells us the
    application's status was genuinely set to `value` at some point, as
    opposed to the route having simply moved past that station's index.
    `value` is always a raw status code (never translated - see
    APPLICATION_STATUS_LABELS), and the log line it's matched against is
    built from that same raw code (application.log_event, never a
    translated label), so this comparison is unaffected by UI locale."""
    matches = [e for e in events if e.event_type == "status_changed" and e.description.endswith(f"-> {value}.")]
    return matches[-1] if matches else None


# Event types that represent a real status transition, not just work-in-
# progress on the content (cover_letter_generated, documents_selected,
# etc. don't move the application to a new stage). Every real transition
# this app makes goes through one of these four - see
# app/applications/routes.py: start() logs "created", approve() logs
# "approved", mark_sent() logs "sent", update_status() logs
# "status_changed" whenever old != new.
_TRANSITION_EVENT_TYPES = {"created", "approved", "sent", "status_changed"}


def latest_transition_at(application):
    """The timestamp of the most recent real status transition - used for
    the Dashboard's staleness marker ("unchanged for 3 days") and its
    applications table's date column (Screens pass 3, 2026-08-27).
    Deliberately not Application.updated_at, which bumps on any field edit
    (notes, contact_email, ...) - this is scoped to transitions the way
    build_status_route's own event-based inference already is, not a new
    concept. No schema change: ApplicationEvent already logs every one of
    these. Falls back to created_at if the event log is somehow empty
    (shouldn't happen - start() always logs "created" - but an absent
    timestamp is worse than a slightly-conservative one)."""
    transition_times = [e.created_at for e in application.events if e.event_type in _TRANSITION_EVENT_TYPES]
    return max(transition_times) if transition_times else application.created_at


def _next_event(application, stations):
    """The header line naming the next dated, not-yet-reached station with a
    countdown - new in this pass (the bundle's own "VERLAUF DER BEWERBUNG"
    header line). Only interview_date currently gives a real future
    timestamp to count down to (follow_up_date has no time-of-day, and
    nothing else on the route is a genuine future appointment) - anything
    else just says how many stations remain, not a fabricated date."""
    from app.models.user import utcnow

    if application.interview_date and application.interview_date > utcnow():
        delta = application.interview_date - utcnow()
        days = delta.days
        when = format_local_datetime(application.interview_date, format="short")
        if days <= 0:
            return _("Interview %(when)s — today", when=when)
        return ngettext(
            "Interview %(when)s — in %(num)d day", "Interview %(when)s — in %(num)d days", days, when=when,
        )

    remaining = [s for s in stations if not s["reached"]]
    if remaining:
        return ngettext("%(num)d station remaining", "%(num)d stations remaining", len(remaining))
    return None


def build_status_route(application, job_match=None):
    """job_match: the already-computed JobMatch for (application.user,
    application.job), if the caller has one (applications/routes.py's
    detail() route always does - matching Job Detail's "compute the match
    once, thread it through" pattern rather than a second query here).
    None is handled honestly (Matched renders pending), not assumed."""
    events = application.events  # already ordered by created_at (Application.events relationship)
    status = application.status

    reply_messages = [m for m in application.gmail_messages if m.received_at]
    first_reply_at = min((m.received_at for m in reply_messages), default=None)
    reply_event = _latest(events, "reply_detected")
    has_reply = bool(first_reply_at or reply_event)

    if status in STATUS_TO_STATION_INDEX:
        current_idx = STATUS_TO_STATION_INDEX[status]
        # A detected reply is real evidence the route has passed this
        # point even if the user never manually advanced status past
        # "sent" - Gmail reply detection (app/integrations/
        # gmail_reply_tracking.py) doesn't touch Application.status at
        # all, so without this, a genuinely-arrived reply would sit
        # invisible on the journey until a manual status edit. Found
        # while testing the Reply station, not assumed - the terminal
        # branch below already did this same evidence-over-status-string
        # bump for the old six-station route; this was the missing
        # non-terminal counterpart.
        if has_reply:
            current_idx = max(current_idx, STATION_ORDER.index("reply"))
        is_terminal = False
    elif status == "accepted":
        current_idx = len(STATION_ORDER) - 1  # accepted implies the full route was completed
        is_terminal = True
    else:
        # rejected / withdrawn / expired: infer how far the route actually got
        # from real evidence (events / fields), since the status string itself
        # doesn't say where the process stopped.
        current_idx = -1
        if _latest(events, "created"):
            current_idx = max(current_idx, STATION_ORDER.index("prepared"))
        if _latest(events, "approved"):
            current_idx = max(current_idx, STATION_ORDER.index("approved"))
        if _latest(events, "sent"):
            current_idx = max(current_idx, STATION_ORDER.index("sent"))
        if _status_changed_to(events, "follow_up") or has_reply:
            current_idx = max(current_idx, STATION_ORDER.index("reply"))
        if _status_changed_to(events, "interview") or application.interview_date:
            current_idx = max(current_idx, STATION_ORDER.index("interview"))
        if _status_changed_to(events, "offer"):
            current_idx = max(current_idx, STATION_ORDER.index("offer"))
        is_terminal = True

    stations = []
    for i, key in enumerate(STATION_ORDER):
        reached = i <= current_idx
        is_current = reached and i == current_idx and not is_terminal
        is_skipped = False
        description = None
        date_label = None

        if key == "discovered":
            # Always reached and always dated: an application can't exist
            # without its job existing first, and Job.discovered_at is
            # non-nullable with a default - no pending case is honest here.
            reached = True
            description = _("AUSVIA found this posting.")
            date_label = _fmt(application.job.discovered_at)

        elif key == "matched":
            if job_match:
                reached = True
                description = _("Your match score was computed for this posting.")
                date_label = _fmt(job_match.computed_at)
            else:
                # Genuinely reachable in production: an application can be
                # started without a JobMatch row existing yet (starting
                # doesn't compute one - see app/applications/routes.py's
                # start()). Rare in practice (search/detail both compute
                # eagerly) but not impossible, so it's handled, not assumed
                # away.
                reached = False
                description = _("Not yet computed.")

        elif key == "prepared":
            cl = _latest(events, "cover_letter_generated")
            em = _latest(events, "email_generated")
            if cl and em:
                description = _("Cover letter and application email generated.")
            elif cl:
                description = _("Cover letter generated.")
            elif em:
                description = _("Application email generated.")
            else:
                description = _("Application started.")
            ev = em or cl or _latest(events, "created")
            date_label = _fmt(ev.created_at) if ev else None

        elif key == "approved":
            if reached:
                ev = _latest(events, "approved")
                description = _("You approved the application. PDF package built.")
                date_label = _fmt(ev.created_at) if ev else None
            else:
                description = _("Not reached yet.")

        elif key == "sent":
            if reached:
                ev = _latest(events, "sent")
                description = (
                    _("Marked as sent to %(contact)s.", contact=application.contact_email)
                    if application.contact_email else _("Marked as sent.")
                )
                date_label = _fmt(ev.created_at) if ev else None
            else:
                description = _("Not reached yet.")

        elif key == "reply":
            if has_reply:
                description = (
                    _("Reply received from %(contact)s.", contact=application.contact_email)
                    if application.contact_email else _("A reply was detected.")
                )
                date_label = _fmt(first_reply_at) if first_reply_at else _fmt(reply_event.created_at if reply_event else None)
            elif reached:
                # the route moved past this point with no tracked reply -
                # e.g. an interview arranged by phone, or a manual status
                # correction. Worth naming as a real skip, not silence.
                is_skipped = True
                description = _("Skipped.")
                date_label = "—"
            else:
                description = _("Not reached yet.")

        elif key == "interview":
            if reached:
                parts = []
                if application.interview_date:
                    parts.append(format_local_datetime(application.interview_date, format="d MMMM, HH:mm"))
                if application.notes:
                    parts.append(application.notes.rstrip("."))
                description = ". ".join(parts) + "." if parts else _("Interview stage reached.")
                ev = _status_changed_to(events, "interview")
                date_label = _fmt(ev.created_at) if ev else (_fmt(application.interview_date) if application.interview_date else None)
            else:
                description = _("Not reached yet.")

        elif key == "offer":
            if reached:
                description = _("Offer received.")
                ev = _status_changed_to(events, "offer")
                date_label = _fmt(ev.created_at) if ev else None
            else:
                description = _("Not reached yet.")

        stations.append({
            "key": key,
            "label": STATION_LABELS[key],
            "reached": reached,
            "current": is_current,
            "skipped": is_skipped,
            "description": description,
            "date_label": date_label or "—",
        })

    # i18n pass 2: "Accepted"/rejected/withdrawn/expired all reuse
    # APPLICATION_STATUS_LABELS - the same lookup status_pill() and
    # StatusForm use - instead of status.replace("_", " ").title(), which
    # has no German equivalent (same class of fix as status_pill() itself,
    # see DECISIONS.md).
    terminal_label = None
    if status == "accepted":
        terminal_label = APPLICATION_STATUS_LABELS["accepted"]
    elif status in TERMINAL_EXCEPTION_STATUSES:
        terminal_label = APPLICATION_STATUS_LABELS[status]

    return {
        "stations": stations,
        "terminal_label": terminal_label,
        "next_event": _next_event(application, stations) if not is_terminal else None,
    }
