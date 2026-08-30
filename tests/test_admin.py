from app.models import InvitationCode
from tests.conftest import login


def test_admin_can_create_code_with_access_duration(client, make_user):
    make_user(email="admin-plan@example.com", password="Password123!", role="admin")
    login(client, "admin-plan@example.com", "Password123!")

    resp = client.post(
        "/admin/codes",
        data={"code_type": "premium", "max_uses": "2", "access_duration_months": "12", "notes": ""},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    code = InvitationCode.query.filter_by(code_type="premium", max_uses=2).first()
    assert code is not None
    assert code.access_duration_months == 12


def test_admin_code_without_duration_stays_none(client, make_user):
    # Backward-compatible default - the field is unfilled by default, same
    # as every other Optional field on this form.
    make_user(email="admin-plan2@example.com", password="Password123!", role="admin")
    login(client, "admin-plan2@example.com", "Password123!")

    resp = client.post(
        "/admin/codes",
        data={"code_type": "trial", "max_uses": "1", "notes": ""},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    code = InvitationCode.query.filter_by(code_type="trial").first()
    assert code is not None
    assert code.access_duration_months is None


def test_non_admin_cannot_access_admin_area(client, make_user):
    make_user(email="regular@example.com", password="Password123!", role="user")
    login(client, "regular@example.com", "Password123!")

    for path in ["/admin/", "/admin/users", "/admin/codes"]:
        resp = client.get(path)
        assert resp.status_code == 403


def test_anonymous_redirected_to_login(client):
    resp = client.get("/admin/", follow_redirects=True)
    assert b"Log in" in resp.data


def test_admin_can_create_and_revoke_code(client, make_user):
    make_user(email="admin2@example.com", password="Password123!", role="admin")
    login(client, "admin2@example.com", "Password123!")

    resp = client.post(
        "/admin/codes",
        data={"code_type": "standard", "max_uses": "3", "notes": "test"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    code = InvitationCode.query.filter_by(code_type="standard").first()
    assert code is not None
    assert code.max_uses == 3
    assert code.is_active is True

    resp = client.post(f"/admin/codes/{code.id}/revoke", follow_redirects=True)
    assert resp.status_code == 200

    from app.extensions import db

    db.session.refresh(code)
    assert code.is_active is False


def test_admin_can_toggle_user_active_but_not_self(client, make_user):
    admin = make_user(email="admin3@example.com", password="Password123!", role="admin")
    other = make_user(email="regular2@example.com", password="Password123!", role="user")
    login(client, "admin3@example.com", "Password123!")

    resp = client.post(f"/admin/users/{other.id}/toggle-active", follow_redirects=True)
    assert resp.status_code == 200

    from app.extensions import db

    db.session.refresh(other)
    assert other.is_active is False

    resp = client.post(f"/admin/users/{admin.id}/toggle-active", follow_redirects=True)
    assert b"deactivate your own account" in resp.data
