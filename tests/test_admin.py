import re

import pytest
from flask_babel import force_locale

from app.models import InvitationCode
from app.models.access_code import CODE_TYPE_LABELS, CODE_TYPES
from tests.conftest import login

# The six real option values app/templates/admin/codes.html's Plan
# selector renders - (users, duration_months) pairs the spec names
# explicitly: 1/2/5 users x 1 month/1 year.
PLAN_SELECTOR_COMBINATIONS = [(1, 1), (2, 1), (5, 1), (1, 12), (2, 12), (5, 12)]


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


def test_plan_selector_renders_exactly_the_six_expected_option_values(client, make_user):
    # Guards against admin/codes.html's Plan selector silently drifting
    # from the six combinations the spec names (1/2/5 users x 1/12
    # months) - if a future edit changes an option's value string, this
    # fails here rather than only being caught by eyeballing the page.
    make_user(email="admin-plan-render@example.com", password="Password123!", role="admin")
    login(client, "admin-plan-render@example.com", "Password123!")

    resp = client.get("/admin/codes")
    body = resp.data.decode("utf-8")
    rendered_values = set(re.findall(r'<option value="(premium\|[^"]+)"', body))
    expected_values = {f"premium|{users}|{months}" for users, months in PLAN_SELECTOR_COMBINATIONS}
    assert rendered_values == expected_values


@pytest.mark.parametrize("users,months", PLAN_SELECTOR_COMBINATIONS)
def test_plan_selector_option_produces_correct_code(client, db, make_user, users, months):
    # Simulates exactly what plan-selector.js's change handler submits for
    # this option (codeType.value/maxUses.value/duration.value split from
    # "premium|{users}|{months}") - proves the backend persists each of
    # the six real combinations correctly, not just plausibly. This is
    # the field every real paid code gets issued through going forward.
    make_user(email=f"admin-plan-{users}-{months}@example.com", password="Password123!", role="admin")
    login(client, f"admin-plan-{users}-{months}@example.com", "Password123!")

    resp = client.post(
        "/admin/codes",
        data={
            "code_type": "premium", "max_uses": str(users),
            "access_duration_months": str(months), "notes": "",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200

    code = InvitationCode.query.filter_by(code_type="premium", max_uses=users, access_duration_months=months).first()
    assert code is not None, f"No code created for users={users}, months={months}"
    assert code.code_type == "premium"
    assert code.max_uses == users
    assert code.access_duration_months == months


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


# --- i18n sweep (2026-08-30): CreateCodeForm's "Type" dropdown used to
# build choice labels with a bare t.capitalize() on the raw CODE_TYPES
# enum - always English, and structurally invisible to pybabel extract
# (no _()/_l() call site existed at all). CODE_TYPE_LABELS replaces it. ---

def test_code_type_labels_covers_every_code_type():
    assert set(CODE_TYPE_LABELS) == set(CODE_TYPES)


def test_code_type_labels_are_locale_aware(app):
    with app.test_request_context("/"):
        with force_locale("en"):
            en = {k: str(v) for k, v in CODE_TYPE_LABELS.items()}
        with force_locale("de"):
            de = {k: str(v) for k, v in CODE_TYPE_LABELS.items()}
    assert en == {"trial": "Trial", "standard": "Standard", "premium": "Premium", "admin": "Admin"}
    assert de == {"trial": "Testversion", "standard": "Standard", "premium": "Premium", "admin": "Admin"}


def test_admin_codes_page_type_dropdown_is_translated_in_german(client, make_user):
    make_user(email="admin-typelabel@example.com", password="Password123!", role="admin")
    login(client, "admin-typelabel@example.com", "Password123!")
    client.post("/set-locale", data={"lang": "de", "next": "/admin/codes"})

    resp = client.get("/admin/codes")
    body = resp.data.decode("utf-8")
    assert "Testversion" in body
    # The old bare .capitalize() output must not leak through anywhere.
    assert ">Trial<" not in body
