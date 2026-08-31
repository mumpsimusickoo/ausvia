"""Tests for the real Impressum/privacy policy pages (2026-08-31) - see
DECISIONS.md's 2026-08-28 entry for why these were deliberately deferred
until the operator's real legal identity was available, and this pass's
own entry for the pages themselves. Both routes are pre-auth-reachable by
design (a legal notice/privacy policy has to stay reachable regardless of
login state, unlike main.plans()'s redirect-authenticated-users-away
convention)."""
from tests.conftest import login


def test_impressum_accessible_without_login(client):
    resp = client.get("/impressum")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert "Ilias Jabbour" in body
    assert "contact@ausvia.org" in body


def test_privacy_accessible_without_login(client):
    resp = client.get("/privacy")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert "contact@ausvia.org" in body


def test_impressum_accessible_when_logged_in(client, db, make_user):
    make_user(email="impressum-loggedin@example.com", password="Password123!")
    login(client, "impressum-loggedin@example.com", "Password123!")
    resp = client.get("/impressum")
    assert resp.status_code == 200
    assert "Ilias Jabbour" in resp.data.decode("utf-8")


def test_privacy_accessible_when_logged_in(client, db, make_user):
    make_user(email="privacy-loggedin@example.com", password="Password123!")
    login(client, "privacy-loggedin@example.com", "Password123!")
    resp = client.get("/privacy")
    assert resp.status_code == 200
    assert "contact@ausvia.org" in resp.data.decode("utf-8")


def test_privacy_covers_the_required_topics(client):
    """Real content, not a stub - confirms the page actually discusses the
    specific topics DECISIONS.md's 2026-08-28 entry flagged as required
    before any public opening (Gmail OAuth scope, uploaded documents, AI
    providers, job source APIs), not generic boilerplate."""
    resp = client.get("/privacy")
    body = resp.data.decode("utf-8")
    assert "Gmail" in body
    assert "Gemini" in body
    assert "Arbeitsagentur" in body or "Federal Employment Agency" in body
