from app.models import User, InvitationCode
from tests.conftest import login


def test_register_with_valid_code_creates_user_and_profile(client, db, trial_code):
    resp = client.post(
        "/auth/register",
        data={
            "access_code": trial_code.code,
            "email": "new@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    user = User.query.filter_by(email="new@example.com").first()
    assert user is not None
    assert user.check_password("Password123!")
    assert user.profile is not None

    code = db.session.get(InvitationCode, trial_code.id)
    assert code.use_count == 1


def test_register_rejects_invalid_code(client, db):
    resp = client.post(
        "/auth/register",
        data={
            "access_code": "ZZZZ-ZZZZ-ZZZZ",
            "email": "nobody@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
        },
        follow_redirects=True,
    )
    assert b"Invalid access code" in resp.data
    assert User.query.filter_by(email="nobody@example.com").first() is None


def test_register_rejects_code_past_max_uses(client, db, trial_code):
    trial_code.max_uses = 1
    trial_code.use_count = 1
    db.session.commit()

    resp = client.post(
        "/auth/register",
        data={
            "access_code": trial_code.code,
            "email": "late@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
        },
        follow_redirects=True,
    )
    assert b"maximum number of times" in resp.data
    assert User.query.filter_by(email="late@example.com").first() is None


def test_register_rejects_duplicate_email(client, db, trial_code, make_user):
    make_user(email="taken@example.com")
    resp = client.post(
        "/auth/register",
        data={
            "access_code": trial_code.code,
            "email": "taken@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
        },
        follow_redirects=True,
    )
    assert b"already exists" in resp.data


def test_admin_code_grants_admin_role(client, db, admin_code):
    client.post(
        "/auth/register",
        data={
            "access_code": admin_code.code,
            "email": "boss@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
        },
        follow_redirects=True,
    )
    user = User.query.filter_by(email="boss@example.com").first()
    assert user.role == "admin"
    assert user.is_admin


def test_login_and_logout(client, make_user):
    make_user(email="loginuser@example.com", password="Password123!")
    resp = login(client, "loginuser@example.com", "Password123!")
    assert b"Dashboard" in resp.data

    resp = client.get("/auth/logout", follow_redirects=True)
    assert resp.status_code == 200


def test_login_rejects_wrong_password(client, make_user):
    make_user(email="wrongpass@example.com", password="Password123!")
    resp = login(client, "wrongpass@example.com", "WrongPassword!")
    assert b"Invalid email or password" in resp.data


def test_login_rejects_inactive_user(client, db, make_user):
    user = make_user(email="inactive@example.com", password="Password123!")
    user.is_active = False
    db.session.commit()
    resp = login(client, "inactive@example.com", "Password123!")
    assert b"Invalid email or password" in resp.data


def test_dashboard_requires_login(client):
    resp = client.get("/dashboard", follow_redirects=True)
    assert b"Log in" in resp.data


# --- Security fix, 2026-08-30 (see DECISIONS.md): request_reset() used
# to render the real reset link/token directly on the page whenever
# current_app.config.get("MAIL_PROVIDER_CONFIGURED") was falsy - a key
# that was never actually defined anywhere in config.py, so that
# condition was always true and the link was always shown, to anyone who
# submitted any registered email. Full account takeover, no inbox access
# needed. The test this block replaces (test_password_reset_flow_dev_
# fallback_shows_link) exercised exactly that hole: it extracted the
# token straight out of the HTTP response body and used it to prove the
# reset flow "worked" - it was testing the vulnerability as if it were
# correct behavior. ---

def test_password_reset_link_never_appears_in_response(client, make_user):
    make_user(email="reset@example.com", password="OldPassword123!")
    resp = client.post("/auth/reset-password", data={"email": "reset@example.com"}, follow_redirects=True)
    assert resp.status_code == 200

    import re

    # The exact extraction technique the old (vulnerable) test used to
    # pull a working token out of the page - must now find nothing, for
    # a real, registered email, under any circumstance.
    assert re.search(rb"/auth/reset-password/[\w\.\-]+", resp.data) is None
    assert b"password reset link has been sent" in resp.data


def test_password_reset_identical_message_for_unregistered_email(client):
    resp = client.post(
        "/auth/reset-password", data={"email": "definitely-not-registered@example.com"}, follow_redirects=True
    )
    assert resp.status_code == 200
    assert b"password reset link has been sent" in resp.data
    import re

    assert re.search(rb"/auth/reset-password/[\w\.\-]+", resp.data) is None


def test_password_reset_response_does_not_reveal_whether_account_exists(client, make_user):
    make_user(email="does-exist@example.com", password="OldPassword123!")
    real_resp = client.post(
        "/auth/reset-password", data={"email": "does-exist@example.com"}, follow_redirects=True
    )
    fake_resp = client.post(
        "/auth/reset-password", data={"email": "does-not-exist@example.com"}, follow_redirects=True
    )
    # Same flash message either way - no signal in the response content
    # that would let a caller distinguish a real account from a fake one.
    assert b"password reset link has been sent" in real_resp.data
    assert b"password reset link has been sent" in fake_resp.data


def test_password_reset_endpoint_still_works_with_a_real_token(app, client, make_user):
    # Confirms the underlying reset mechanism itself is unbroken by the
    # exposure fix - a real token (built the same way request_reset()
    # builds one internally, never extracted from an HTTP response, the
    # way a real emailed link would reach a user) still lets someone set
    # a new password.
    from app.auth.routes import RESET_SALT, _serializer

    make_user(email="reset2@example.com", password="OldPassword123!")
    with app.test_request_context():
        token = _serializer().dumps("reset2@example.com", salt=RESET_SALT)

    resp = client.post(
        f"/auth/reset-password/{token}",
        data={"password": "NewPassword123!", "confirm_password": "NewPassword123!"},
        follow_redirects=True,
    )
    assert resp.status_code == 200

    user = User.query.filter_by(email="reset2@example.com").first()
    assert user.check_password("NewPassword123!")
    assert not user.check_password("OldPassword123!")
