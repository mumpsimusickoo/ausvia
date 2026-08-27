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
STATION_ORDER = ["discovered", "matched", "prepared", "approved", "sent", "reply", "interview", "offer"]
STATION_LABELS = {
    "discovered": "Discovered",
    "matched": "Matched",
    "prepared": "Prepared",
    "approved": "Approved",
    "sent": "Sent",
    "reply": "Reply",
    "interview": "Interview",
    "offer": "Offer",
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
    return dt.strftime("%d %b") if dt else None


def _latest(events, event_type):
    matches = [e for e in events if e.event_type == event_type]
    return matches[-1] if matches else None


def _status_changed_to(events, value):
    """A status_changed event's description is always
    "Status changed: {old} -> {new}." (see applications/routes.py
    update_status()) - matching the exact "-> {value}." suffix tells us the
    application's status was genuinely set to `value` at some point, as
    opposed to the route having simply moved past that station's index."""
    matches = [e for e in events if e.event_type == "status_changed" and e.description.endswith(f"-> {value}.")]
    return matches[-1] if matches else None


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
        when = application.interview_date.strftime("%d.%m, %H:%M")
        if days <= 0:
            return f"Interview {when} — today"
        return f"Interview {when} — in {days} day{'s' if days != 1 else ''}"

    remaining = [s for s in stations if not s["reached"]]
    if remaining:
        return f"{len(remaining)} station{'s' if len(remaining) != 1 else ''} remaining"
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
            description = "AUSVIA found this posting."
            date_label = _fmt(application.job.discovered_at)

        elif key == "matched":
            if job_match:
                reached = True
                description = "Your match score was computed for this posting."
                date_label = _fmt(job_match.computed_at)
            else:
                # Genuinely reachable in production: an application can be
                # started without a JobMatch row existing yet (starting
                # doesn't compute one - see app/applications/routes.py's
                # start()). Rare in practice (search/detail both compute
                # eagerly) but not impossible, so it's handled, not assumed
                # away.
                reached = False
                description = "Not yet computed."

        elif key == "prepared":
            cl = _latest(events, "cover_letter_generated")
            em = _latest(events, "email_generated")
            if cl and em:
                description = "Cover letter and application email generated."
            elif cl:
                description = "Cover letter generated."
            elif em:
                description = "Application email generated."
            else:
                description = "Application started."
            ev = em or cl or _latest(events, "created")
            date_label = _fmt(ev.created_at) if ev else None

        elif key == "approved":
            if reached:
                ev = _latest(events, "approved")
                description = "You approved the application. PDF package built."
                date_label = _fmt(ev.created_at) if ev else None
            else:
                description = "Not reached yet."

        elif key == "sent":
            if reached:
                ev = _latest(events, "sent")
                description = (
                    f"Marked as sent to {application.contact_email}."
                    if application.contact_email else "Marked as sent."
                )
                date_label = _fmt(ev.created_at) if ev else None
            else:
                description = "Not reached yet."

        elif key == "reply":
            if has_reply:
                description = (
                    f"Reply received from {application.contact_email}."
                    if application.contact_email else "A reply was detected."
                )
                date_label = _fmt(first_reply_at) if first_reply_at else _fmt(reply_event.created_at if reply_event else None)
            elif reached:
                # the route moved past this point with no tracked reply -
                # e.g. an interview arranged by phone, or a manual status
                # correction. Worth naming as a real skip, not silence.
                is_skipped = True
                description = "Skipped."
                date_label = "—"
            else:
                description = "Not reached yet."

        elif key == "interview":
            if reached:
                parts = []
                if application.interview_date:
                    parts.append(application.interview_date.strftime("%d %B, %H:%M"))
                if application.notes:
                    parts.append(application.notes.rstrip("."))
                description = ". ".join(parts) + "." if parts else "Interview stage reached."
                ev = _status_changed_to(events, "interview")
                date_label = _fmt(ev.created_at) if ev else (_fmt(application.interview_date) if application.interview_date else None)
            else:
                description = "Not reached yet."

        elif key == "offer":
            if reached:
                description = "Offer received."
                ev = _status_changed_to(events, "offer")
                date_label = _fmt(ev.created_at) if ev else None
            else:
                description = "Not reached yet."

        stations.append({
            "key": key,
            "label": STATION_LABELS[key],
            "reached": reached,
            "current": is_current,
            "skipped": is_skipped,
            "description": description,
            "date_label": date_label or "—",
        })

    terminal_label = None
    if status == "accepted":
        terminal_label = "Accepted"
    elif status in TERMINAL_EXCEPTION_STATUSES:
        terminal_label = status.replace("_", " ").title()

    return {
        "stations": stations,
        "terminal_label": terminal_label,
        "next_event": _next_event(application, stations) if not is_terminal else None,
    }
