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


def test_password_reset_flow_dev_fallback_shows_link(client, make_user):
    make_user(email="reset@example.com", password="OldPassword123!")
    resp = client.post("/auth/reset-password", data={"email": "reset@example.com"}, follow_redirects=True)
    assert b"/auth/reset-password/" in resp.data

    import re

    token = re.search(rb"/auth/reset-password/([\w\.\-]+)", resp.data).group(1).decode()

    resp = client.post(
        f"/auth/reset-password/{token}",
        data={"password": "NewPassword123!", "confirm_password": "NewPassword123!"},
        follow_redirects=True,
    )
    assert b"Please log in" in resp.data or resp.status_code == 200

    resp = login(client, "reset@example.com", "NewPassword123!")
    assert b"Dashboard" in resp.data
