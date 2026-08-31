"""Regression test for QA Phase 7 finding W5: flash messages used to be
differentiated only by color, with no icon and no ARIA live-region
behavior."""
from tests.conftest import login


def test_error_flash_has_role_alert_and_icon(client, db):
    resp = client.post(
        "/auth/login",
        data={"email": "nobody@example.com", "password": "wrong"},
        follow_redirects=True,
    )
    html = resp.get_data(as_text=True)
    assert "Invalid email or password." in html
    assert 'role="alert"' in html
    # a non-color cue (icon svg) must accompany the message, not just the
    # colored border/background
    assert "<svg" in html
    assert 'class="sr-only">Error:' in html


def test_success_flash_has_role_status_and_icon(client, db, trial_code):
    resp = client.post(
        "/auth/register",
        data={
            "access_code": trial_code.code,
            "email": "flashsuccess@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
            "age_confirmed": "y",
        },
        follow_redirects=True,
    )
    html = resp.get_data(as_text=True)
    assert 'role="status"' in html
    assert 'aria-live="polite"' in html
