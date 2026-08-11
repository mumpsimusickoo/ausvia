"""Builds the Wayfinding application-status route (visual direction 1c) shown
on the application detail page. This is a *display* transformation only -
every station's marker state and one-line description is derived from data
that already exists (Application.status, ApplicationEvent log, contact_email,
interview_date, follow_up_date, notes), never a new data source.

The six stations are a fixed subset of Application.APPLICATION_STATUSES -
accepted/rejected/withdrawn/expired are terminal exits from the route, not
stations on it, so they're surfaced as a separate terminal note rather than
a seventh/eighth station (see build_status_route's docstring).
"""

STATION_ORDER = ["preparing", "ready", "sent", "follow_up", "interview", "offer"]
STATION_LABELS = {
    "preparing": "Preparing",
    "ready": "Ready",
    "sent": "Sent",
    "follow_up": "Follow-up",
    "interview": "Interview",
    "offer": "Offer",
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


def build_status_route(application):
    events = application.events  # already ordered by created_at (Application.events relationship)
    status = application.status

    if status in STATION_ORDER:
        current_idx = STATION_ORDER.index(status)
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
            current_idx = max(current_idx, 0)
        if _latest(events, "approved"):
            current_idx = max(current_idx, 1)
        if _latest(events, "sent"):
            current_idx = max(current_idx, 2)
        if _status_changed_to(events, "follow_up"):
            current_idx = max(current_idx, 3)
        if _status_changed_to(events, "interview") or application.interview_date:
            current_idx = max(current_idx, 4)
        if _status_changed_to(events, "offer"):
            current_idx = max(current_idx, 5)
        is_terminal = True

    stations = []
    for i, key in enumerate(STATION_ORDER):
        reached = i <= current_idx
        is_current = reached and i == current_idx and not is_terminal
        is_skipped = False
        description = None
        date_label = None

        if key == "preparing":
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

        elif key == "ready":
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

        elif key == "follow_up":
            explicit = _status_changed_to(events, "follow_up")
            if explicit:
                description = (
                    f"Follow-up due {application.follow_up_date.strftime('%d %b')}."
                    if application.follow_up_date else "Follow-up reminder set."
                )
                date_label = _fmt(explicit.created_at)
            elif reached:
                # the route moved past this point without ever actually
                # pausing at "follow_up" - a reply arriving first is the
                # one case worth naming; otherwise just say it was skipped.
                is_skipped = True
                reply = _latest(events, "reply_detected")
                description = "Skipped — the employer replied first." if reply else "Skipped."
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

    return {"stations": stations, "terminal_label": terminal_label}
