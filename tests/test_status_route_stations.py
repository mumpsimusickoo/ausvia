"""Screens pass 2 (Application Detail, 2026-08-27): the eight-station
journey. Discovered/Matched are new leading stations; Reply replaces the
implicit "follow_up as a station" - see DECISIONS.md for the full dating
logic. test_status_route_accessibility.py already covers the marker
ring/shape construction (unchanged by this pass); these tests cover the
new station data and dating logic specifically.
"""
from datetime import timedelta

from app.applications.status_route import build_status_route, latest_transition_at
from app.jobs.matching import get_or_compute_match
from app.models.integration import GmailMessage
from app.models.user import utcnow
from tests.conftest import login
from tests.test_applications import make_job, start_application


def test_discovered_and_matched_are_always_dated_when_match_exists(client, db, make_user):
    make_user(email="st1@example.com", password="Password123!")
    login(client, "st1@example.com", "Password123!")
    job = make_job(db)
    _, application = start_application(client, db, job)
    match = get_or_compute_match(application.user, job)

    route = build_status_route(application, job_match=match)
    stations = {s["key"]: s for s in route["stations"]}

    assert stations["discovered"]["reached"] is True
    assert stations["discovered"]["date_label"] != "—"
    assert stations["matched"]["reached"] is True
    assert stations["matched"]["date_label"] != "—"


def test_matched_is_pending_when_no_job_match_exists(client, db, make_user):
    """A JobMatch row isn't guaranteed to exist just because an application
    does - starting an application never computes one (see
    app/applications/routes.py's start()). build_status_route must not
    assume it's there."""
    make_user(email="st2@example.com", password="Password123!")
    login(client, "st2@example.com", "Password123!")
    job = make_job(db)
    _, application = start_application(client, db, job)

    route = build_status_route(application, job_match=None)
    stations = {s["key"]: s for s in route["stations"]}

    assert stations["matched"]["reached"] is False
    assert stations["matched"]["description"] == "Not yet computed."


def test_reply_station_dates_from_earliest_gmail_message(client, db, make_user):
    make_user(email="st3@example.com", password="Password123!")
    login(client, "st3@example.com", "Password123!")
    job = make_job(db, dedup_key="st-reply-1")
    _, application = start_application(client, db, job)
    application.contact_email = "hr@example.de"
    db.session.commit()

    earlier = utcnow() - timedelta(days=5)
    later = utcnow() - timedelta(days=1)
    db.session.add(GmailMessage(application_id=application.id, gmail_message_id="m1", received_at=later))
    db.session.add(GmailMessage(application_id=application.id, gmail_message_id="m2", received_at=earlier))
    db.session.commit()

    route = build_status_route(application)
    reply = next(s for s in route["stations"] if s["key"] == "reply")
    assert reply["reached"] is True
    assert reply["skipped"] is False
    assert reply["date_label"] == earlier.strftime("%d %b")


def test_reply_station_skipped_when_route_passed_it_with_no_reply(client, db, make_user):
    """Mirrors test_status_route_accessibility.py's own scenario (status
    jumps straight to "interview", skipping past the reply position) -
    that test asserts on the marker's CSS classes; this one asserts on
    the underlying station data those classes are driven by."""
    make_user(email="st4@example.com", password="Password123!")
    login(client, "st4@example.com", "Password123!")
    job = make_job(db, dedup_key="st-reply-2")
    _, application = start_application(client, db, job)
    application.status = "interview"
    db.session.commit()

    route = build_status_route(application)
    reply = next(s for s in route["stations"] if s["key"] == "reply")
    assert reply["reached"] is True
    assert reply["skipped"] is True
    assert reply["description"] == "Skipped."
    assert reply["date_label"] == "—"


def test_reply_station_not_reached_before_sent(client, db, make_user):
    make_user(email="st5@example.com", password="Password123!")
    login(client, "st5@example.com", "Password123!")
    job = make_job(db, dedup_key="st-reply-3")
    _, application = start_application(client, db, job)  # status stays "preparing"

    route = build_status_route(application)
    reply = next(s for s in route["stations"] if s["key"] == "reply")
    assert reply["reached"] is False
    assert reply["skipped"] is False
    assert reply["description"] == "Not reached yet."


def test_follow_up_status_maps_onto_reply_station_index(client, db, make_user):
    """follow_up is a real Application.status value (a reminder state) but
    not a station of its own in the new eight - it lands on Reply's index,
    matching the "current" station in the route."""
    make_user(email="st6@example.com", password="Password123!")
    login(client, "st6@example.com", "Password123!")
    job = make_job(db, dedup_key="st-followup")
    _, application = start_application(client, db, job)
    application.status = "follow_up"
    db.session.commit()

    route = build_status_route(application)
    stations = {s["key"]: s for s in route["stations"]}
    assert stations["reply"]["current"] is True
    assert stations["interview"]["reached"] is False


def test_next_event_counts_down_to_a_future_interview(client, db, make_user):
    make_user(email="st7@example.com", password="Password123!")
    login(client, "st7@example.com", "Password123!")
    job = make_job(db, dedup_key="st-next-1")
    _, application = start_application(client, db, job)
    application.status = "interview"
    # +1 hour buffer: .days floors, and a `3 days` delta computed here could
    # read back as `2 days` after the test's own execution time elapses.
    application.interview_date = utcnow() + timedelta(days=3, hours=1)
    db.session.commit()

    route = build_status_route(application)
    assert route["next_event"] is not None
    assert "Interview" in route["next_event"]
    assert "3 day" in route["next_event"]


def test_latest_transition_at_advances_on_real_transitions_only(client, db, make_user):
    """Dashboard pass (2026-08-27): latest_transition_at() dates the
    dashboard's staleness marker and applications-table date column - it
    must track real status transitions (created/approved/sent/
    status_changed events), not Application.updated_at, which bumps on any
    field edit."""
    make_user(email="st8@example.com", password="Password123!")
    login(client, "st8@example.com", "Password123!")
    job = make_job(db, dedup_key="st-transition-1")
    _, application = start_application(client, db, job)

    created_transition = latest_transition_at(application)
    assert created_transition is not None

    # A field edit that logs no ApplicationEvent must not move the marker,
    # even though it bumps updated_at (onupdate=utcnow).
    application.notes = "Called HR to confirm receipt."
    db.session.commit()
    assert latest_transition_at(application) == created_transition
    assert application.updated_at >= created_transition

    application.log_event("approved", "Application approved by user - package generated.")
    application.status = "ready"
    db.session.commit()
    approved_transition = latest_transition_at(application)
    assert approved_transition >= created_transition


def test_next_event_falls_back_to_remaining_station_count(client, db, make_user):
    make_user(email="st8@example.com", password="Password123!")
    login(client, "st8@example.com", "Password123!")
    job = make_job(db, dedup_key="st-next-2")
    _, application = start_application(client, db, job)  # preparing, no interview_date

    route = build_status_route(application)
    assert route["next_event"] is not None
    assert "remaining" in route["next_event"]


def test_next_event_is_none_for_terminal_status(client, db, make_user):
    make_user(email="st9@example.com", password="Password123!")
    login(client, "st9@example.com", "Password123!")
    job = make_job(db, dedup_key="st-next-3")
    _, application = start_application(client, db, job)
    application.status = "rejected"
    db.session.commit()

    route = build_status_route(application)
    assert route["next_event"] is None


def test_offer_status_is_current_not_terminal(client, db, make_user):
    make_user(email="st10@example.com", password="Password123!")
    login(client, "st10@example.com", "Password123!")
    job = make_job(db, dedup_key="st-offer")
    _, application = start_application(client, db, job)
    application.status = "offer"
    db.session.commit()

    route = build_status_route(application)
    offer = next(s for s in route["stations"] if s["key"] == "offer")
    assert offer["reached"] is True
    assert offer["current"] is True
    assert route["terminal_label"] is None


def test_accepted_status_marks_offer_reached_and_terminal(client, db, make_user):
    make_user(email="st11@example.com", password="Password123!")
    login(client, "st11@example.com", "Password123!")
    job = make_job(db, dedup_key="st-accepted")
    _, application = start_application(client, db, job)
    application.status = "accepted"
    db.session.commit()

    route = build_status_route(application)
    offer = next(s for s in route["stations"] if s["key"] == "offer")
    assert offer["reached"] is True
    assert offer["current"] is False  # terminal, not "current"
    assert route["terminal_label"] == "Accepted"
