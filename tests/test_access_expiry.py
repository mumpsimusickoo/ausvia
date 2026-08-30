"""Tests for real automatic access expiry (plans page + access expiry
pass, 2026-08-30): compute_access_expiry()'s relativedelta arithmetic,
InvitationCode.access_duration_months flowing into User.access_expires_at
at redemption, and both enforcement checkpoints - login-time refusal
(app/auth/routes.py's login()) and the mid-session before_request cutoff
(app/access_expiry.py's enforce_access_expiry(), registered app-wide in
app/__init__.py).
"""
from datetime import datetime, timedelta

from app.access_expiry import compute_access_expiry, is_access_expired
from app.extensions import db
from app.models import InvitationCode, User
from app.models.access_code import generate_code
from app.models.user import utcnow
from tests.conftest import login


# --- compute_access_expiry() / is_access_expired() unit tests ---

def test_relativedelta_jan_31_plus_one_month_lands_on_feb_28():
    # The exact edge case named in the spec: no error, no rollover to
    # March, clamped to February's real last day in a non-leap year.
    result = compute_access_expiry(datetime(2027, 1, 31), 1)
    assert result == datetime(2027, 2, 28)


def test_relativedelta_jan_31_plus_one_month_lands_on_feb_29_leap_year():
    result = compute_access_expiry(datetime(2028, 1, 31), 1)
    assert result == datetime(2028, 2, 29)


def test_relativedelta_mid_month_purchase_not_shorted():
    # A flat "30 days" approximation would land on the 14th, not the 15th -
    # this confirms real calendar-month arithmetic, not a day count.
    result = compute_access_expiry(datetime(2026, 8, 15), 1)
    assert result == datetime(2026, 9, 15)


def test_is_access_expired_none_means_never_expired():
    user = User(email="none-expiry@example.com", role="user", plan="trial")
    user.access_expires_at = None
    assert is_access_expired(user) is False


def test_is_access_expired_future_timestamp_not_expired():
    user = User(email="future-expiry@example.com", role="user", plan="trial")
    user.access_expires_at = utcnow() + timedelta(days=5)
    assert is_access_expired(user) is False


def test_is_access_expired_past_timestamp_is_expired():
    user = User(email="past-expiry@example.com", role="user", plan="trial")
    user.access_expires_at = utcnow() - timedelta(days=1)
    assert is_access_expired(user) is True


# --- Redemption: InvitationCode.access_duration_months -> User.access_expires_at ---

def _make_code(db, access_duration_months=None, code_type="premium", max_uses=1):
    code = InvitationCode(
        code=generate_code(), code_type=code_type, max_uses=max_uses,
        access_duration_months=access_duration_months,
    )
    db.session.add(code)
    db.session.commit()
    return code


def test_redeeming_code_with_duration_sets_access_expires_at(client, db):
    code = _make_code(db, access_duration_months=1)
    before = utcnow()

    resp = client.post(
        "/auth/register",
        data={
            "email": "duration1@example.com", "password": "Password123!",
            "confirm_password": "Password123!", "access_code": code.code,
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200

    user = User.query.filter_by(email="duration1@example.com").first()
    assert user is not None
    assert user.access_expires_at is not None
    # Roughly one calendar month out, not some arbitrary/default value.
    assert user.access_expires_at > before + timedelta(days=25)
    assert user.access_expires_at < before + timedelta(days=32)


def test_redeeming_code_without_duration_leaves_access_expires_at_none(client, db):
    # Backward-compatible default - every code type this app already
    # issues (trial/standard/admin, or a premium code made the old way)
    # must behave exactly as before this pass.
    code = _make_code(db, access_duration_months=None)

    client.post(
        "/auth/register",
        data={
            "email": "noduration@example.com", "password": "Password123!",
            "confirm_password": "Password123!", "access_code": code.code,
        },
        follow_redirects=True,
    )

    user = User.query.filter_by(email="noduration@example.com").first()
    assert user is not None
    assert user.access_expires_at is None


def test_yearly_duration_twelve_months_computed_correctly(client, db):
    code = _make_code(db, access_duration_months=12)
    before = utcnow()

    client.post(
        "/auth/register",
        data={
            "email": "duration12@example.com", "password": "Password123!",
            "confirm_password": "Password123!", "access_code": code.code,
        },
        follow_redirects=True,
    )

    user = User.query.filter_by(email="duration12@example.com").first()
    assert user.access_expires_at > before + timedelta(days=360)
    assert user.access_expires_at < before + timedelta(days=370)


# --- Checkpoint 1: login-time refusal ---

def test_login_refused_when_access_expired(client, db, make_user):
    user = make_user(email="expired-login@example.com", password="Password123!")
    user.access_expires_at = utcnow() - timedelta(days=1)
    db.session.commit()

    resp = client.post(
        "/auth/login",
        data={"email": "expired-login@example.com", "password": "Password123!"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"access period has ended" in resp.data
    assert b"WhatsApp" in resp.data
    # Never actually logged in - dashboard must still require login.
    dashboard_resp = client.get("/dashboard", follow_redirects=False)
    assert dashboard_resp.status_code in (302, 401, 403)
    assert dashboard_resp.status_code != 200


def test_login_succeeds_when_access_not_yet_expired(client, db, make_user):
    user = make_user(email="future-login@example.com", password="Password123!")
    user.access_expires_at = utcnow() + timedelta(days=5)
    db.session.commit()

    resp = client.post(
        "/auth/login",
        data={"email": "future-login@example.com", "password": "Password123!"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"access period has ended" not in resp.data


def test_login_succeeds_when_no_expiry_set(client, db, make_user):
    make_user(email="never-expires@example.com", password="Password123!")
    resp = client.post(
        "/auth/login",
        data={"email": "never-expires@example.com", "password": "Password123!"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"access period has ended" not in resp.data


# --- Checkpoint 2: mid-session cutoff ---

def test_already_logged_in_session_cut_off_once_expiry_passes(client, db, make_user):
    user = make_user(email="midsession@example.com", password="Password123!")
    login(client, "midsession@example.com", "Password123!")

    # Confirm the session is genuinely active before expiring it.
    resp = client.get("/dashboard")
    assert resp.status_code == 200

    # Simulate the expiry passing mid-session - not logged out yet, no new
    # login attempt made, just time (simulated) moving past the deadline.
    user.access_expires_at = utcnow() - timedelta(seconds=1)
    db.session.commit()

    resp = client.get("/dashboard", follow_redirects=True)
    assert resp.status_code == 200
    assert b"access period has ended" in resp.data

    # The session must be genuinely ended, not just this one response
    # redirected - a fresh request should be treated as logged out too.
    resp2 = client.get("/dashboard", follow_redirects=False)
    assert resp2.status_code == 302
    assert "/auth/login" in resp2.headers["Location"]


def test_mid_session_check_does_not_affect_users_with_no_expiry(client, db, make_user):
    make_user(email="midsession-safe@example.com", password="Password123!")
    login(client, "midsession-safe@example.com", "Password123!")

    for _ in range(3):
        resp = client.get("/dashboard")
        assert resp.status_code == 200


def test_mid_session_check_does_not_affect_users_with_future_expiry(client, db, make_user):
    user = make_user(email="midsession-future@example.com", password="Password123!")
    login(client, "midsession-future@example.com", "Password123!")
    user.access_expires_at = utcnow() + timedelta(days=30)
    db.session.commit()

    resp = client.get("/dashboard")
    assert resp.status_code == 200
