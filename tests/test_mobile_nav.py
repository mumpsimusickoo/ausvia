"""Regression test for QA Phase 7 finding B2: the authenticated sidebar was
`hidden` below the md breakpoint with no replacement, leaving mobile users
unable to navigate anywhere but the page they landed on. This test checks
the static markup (drawer, toggle, ARIA wiring, and that every desktop nav
destination is mirrored into the drawer); the dynamic open/close/focus/
Escape behavior was verified live via Chrome DevTools Protocol during the
remediation pass (real keyboard events, not just reading the JS source) -
this project has no in-repo browser-automation harness to assert that part
of the behavior from pytest."""
from tests.conftest import login


def test_mobile_nav_drawer_present_with_all_desktop_destinations(client, db, make_user):
    make_user(email="navtest1@example.com", password="Password123!")
    login(client, "navtest1@example.com", "Password123!")

    resp = client.get("/dashboard")
    html = resp.get_data(as_text=True)

    assert 'id="mobile-nav-toggle"' in html
    assert 'aria-expanded="false"' in html
    assert 'aria-controls="mobile-nav-drawer"' in html
    assert 'id="mobile-nav-drawer"' in html
    assert 'role="dialog"' in html
    assert 'aria-modal="true"' in html
    assert 'id="mobile-nav-close"' in html
    assert 'id="mobile-nav-backdrop"' in html

    for label in ("Dashboard", "Find Ausbildung", "Saved Jobs", "Applications", "Candidate Profile", "Documents", "Gmail"):
        assert html.count(label) >= 2, f"{label!r} should appear in both the desktop sidebar and the mobile drawer"


def test_mobile_nav_drawer_includes_admin_links_for_admin_users(client, db, make_user):
    make_user(email="navtest2@example.com", password="Password123!", role="admin")
    login(client, "navtest2@example.com", "Password123!")

    resp = client.get("/dashboard")
    html = resp.get_data(as_text=True)

    assert html.count("Admin Dashboard") >= 2
    assert html.count("Invitation Codes") >= 2


def test_mobile_nav_absent_for_unauthenticated_pages(client, db):
    resp = client.get("/")
    html = resp.get_data(as_text=True)
    assert 'id="mobile-nav-drawer"' not in html
