"""Tests for the browser-bookmarklet import path (app/jobs/routes.py:
_bookmarklet_href, import_bookmarklet). The bookmarklet itself runs
client-side JS on a third-party page and hands data to AUSVIA only via a
URL fragment - none of that is executable by pytest's test client (no JS
engine), so this covers what actually runs server-side: the bookmarklet
link is generated correctly, the landing page requires login and renders
the right field IDs/nonce for the client-side script to find, and -
critically - that nothing is ever saved without the normal review-and-
submit step. The client-side capture-and-prefill behavior itself was
verified live via Chrome DevTools Protocol against a real third-party page
(iana.org) - see PR notes/report, not reproducible here.
"""
import re

from app.models import Job
from tests.conftest import login


def login_user(client, db, make_user, email="bookmarkuser@example.com"):
    make_user(email=email, password="Password123!")
    login(client, email, "Password123!")


def test_import_page_requires_login(client):
    resp = client.get("/jobs/import", follow_redirects=True)
    assert b"Log in" in resp.data or b"log in" in resp.data.lower()


def test_bookmarklet_route_requires_login(client):
    resp = client.get("/jobs/import/bookmarklet", follow_redirects=True)
    assert b"Log in" in resp.data or b"log in" in resp.data.lower()


def test_import_page_contains_a_javascript_bookmarklet_link(client, db, make_user):
    login_user(client, db, make_user)
    resp = client.get("/jobs/import")
    match = re.search(rb'id="bookmarklet-link" href="(javascript:[^"]*)"', resp.data)
    assert match is not None
    href = match.group(1).decode()
    assert href.startswith("javascript:")
    # the encoded JS source must reference the real bookmarklet landing route
    from urllib.parse import unquote
    decoded = unquote(href)
    assert "/jobs/import/bookmarklet" in decoded
    # reads the DOM directly - never makes a request of its own
    assert "document.title" in decoded
    assert "location.href" in decoded
    assert "innerText" in decoded
    assert "fetch(" not in decoded
    assert "XMLHttpRequest" not in decoded


def test_bookmarklet_href_uses_the_actual_request_origin(client, db, make_user):
    login_user(client, db, make_user)
    resp = client.get("/jobs/import", base_url="http://testserver.example")
    match = re.search(rb'id="bookmarklet-link" href="(javascript:[^"]*)"', resp.data)
    from urllib.parse import unquote
    decoded = unquote(match.group(1).decode())
    assert "testserver.example" in decoded


def test_bookmarklet_landing_page_renders_review_form_with_expected_field_ids(client, db, make_user):
    login_user(client, db, make_user)
    resp = client.get("/jobs/import/bookmarklet")
    assert resp.status_code == 200
    # these exact IDs are what the page's own client-side script targets -
    # a rename here would silently break the prefill with no visible error
    for field_id in (b'id="title"', b'id="application_url"', b'id="description"', b'id="company_name"'):
        assert field_id in resp.data


def test_bookmarklet_landing_page_script_carries_a_csp_nonce(client, db, make_user):
    login_user(client, db, make_user)
    resp = client.get("/jobs/import/bookmarklet")
    match = re.search(rb'<script nonce="([^"]+)">', resp.data)
    assert match is not None
    assert len(match.group(1)) > 10  # a real generated nonce, not empty/placeholder

    csp = resp.headers.get("Content-Security-Policy", "")
    nonce = match.group(1).decode()
    assert f"'nonce-{nonce}'" in csp  # the same nonce the header actually allows


def test_bookmarklet_landing_page_saves_nothing_by_itself(client, db, make_user):
    login_user(client, db, make_user)
    before = Job.query.count()
    client.get("/jobs/import/bookmarklet")
    assert Job.query.count() == before


def test_save_from_bookmarklet_still_requires_company_name(client, db, make_user):
    """The bookmarklet can't reliably capture a structured company name from
    arbitrary page text, so it's deliberately left blank - this must still
    block the save via the same validation every other import path uses,
    forcing a human to actually fill it in rather than saving a job with no
    company."""
    login_user(client, db, make_user)
    resp = client.post(
        "/jobs/import/save",
        data={
            "title": "Some Job From The Web",
            "company_name": "",
            "application_url": "https://example.test/job/1",
            "description": "Some captured page text.",
        },
        follow_redirects=True,
    )
    assert b"Please fill in" in resp.data
    assert Job.query.filter_by(title="Some Job From The Web").first() is None


def test_save_from_bookmarklet_with_company_filled_in_succeeds(client, db, make_user):
    login_user(client, db, make_user)
    resp = client.post(
        "/jobs/import/save",
        data={
            "title": "Some Job From The Web",
            "company_name": "Some Company",
            "application_url": "https://example.test/job/1",
            "description": "Some captured page text.",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    job = Job.query.filter_by(title="Some Job From The Web").first()
    assert job is not None
    assert job.company_name == "Some Company"
