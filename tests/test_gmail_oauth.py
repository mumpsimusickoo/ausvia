import json
from datetime import datetime, timedelta, timezone

import pytest

from app.integrations import gmail_oauth
from app.models.integration import GmailConnection
from tests.conftest import login


class FakeCredentials:
    def __init__(self, token="access-token-123", refresh_token="refresh-token-456"):
        self.token = token
        self.refresh_token = refresh_token
        self.expiry = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)
        self.scopes = gmail_oauth.SCOPES


class FakeProfileService:
    def users(self):
        return self

    def getProfile(self, userId):
        return self

    def execute(self):
        return {"emailAddress": "candidate@gmail.com"}


def test_not_configured_by_default(app):
    # no credentials.json is committed to the repo - confirms the app
    # correctly detects "not set up yet" rather than assuming it's there
    assert gmail_oauth.is_configured() is False


def test_status_page_shows_not_configured(client, db, make_user):
    make_user(email="g1@example.com", password="Password123!")
    login(client, "g1@example.com", "Password123!")
    resp = client.get("/integrations/gmail")
    assert resp.status_code == 200
    assert b"isn" in resp.data  # "isn't configured yet"


def test_connect_redirects_with_error_when_not_configured(client, db, make_user):
    make_user(email="g2@example.com", password="Password123!")
    login(client, "g2@example.com", "Password123!")
    resp = client.get("/integrations/gmail/connect", follow_redirects=True)
    assert resp.status_code == 200
    assert b"configured" in resp.data


def test_get_gmail_service_raises_when_not_connected(app, db, make_user):
    user = make_user(email="g3@example.com")
    with pytest.raises(gmail_oauth.GmailNotConnectedError):
        gmail_oauth.get_gmail_service(user)


@pytest.fixture
def fake_credentials_file(app, tmp_path, monkeypatch):
    cred_file = tmp_path / "credentials.json"
    cred_file.write_text(json.dumps({
        "installed": {
            "client_id": "fake-client-id",
            "client_secret": "fake-client-secret",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }))
    monkeypatch.setattr(gmail_oauth, "CREDENTIALS_FILE", str(cred_file))
    return cred_file


def test_is_configured_true_with_fake_credentials_file(app, fake_credentials_file):
    assert gmail_oauth.is_configured() is True


def test_connect_failure_does_not_leak_exception_text_to_user(
    client, db, make_user, fake_credentials_file, monkeypatch
):
    """Phase 8 security audit (2.6): get_authorization_url() calls into
    google-auth-oauthlib, whose exceptions this app doesn't control the
    content of - the route used to flash str(e) straight to the user."""
    make_user(email="g4@example.com", password="Password123!")
    login(client, "g4@example.com", "Password123!")

    def _boom():
        raise RuntimeError("token_uri unreachable, client_secret=super-secret-value-123")

    monkeypatch.setattr(gmail_oauth, "get_authorization_url", _boom)

    resp = client.get("/integrations/gmail/connect", follow_redirects=True)
    assert resp.status_code == 200
    assert b"super-secret-value-123" not in resp.data
    assert b"Could not start the Gmail connection" in resp.data


def test_callback_failure_does_not_leak_exception_text_to_user(
    client, db, make_user, fake_credentials_file, monkeypatch
):
    """Same as above, for exchange_code() - the real network call to
    Google's token endpoint carrying this app's own client_secret."""
    user = make_user(email="g5@example.com", password="Password123!")
    login(client, "g5@example.com", "Password123!")

    with client.session_transaction() as sess:
        sess["gmail_oauth_state"] = "expected-state-value"

    def _boom(state, full_callback_url):
        raise RuntimeError("token exchange failed, client_secret=super-secret-value-123")

    monkeypatch.setattr(gmail_oauth, "exchange_code", _boom)

    resp = client.get(
        "/integrations/gmail/callback?state=expected-state-value&code=abc",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"super-secret-value-123" not in resp.data
    assert b"Could not complete the Gmail connection" in resp.data


def test_save_and_retrieve_connection(app, db, make_user, fake_credentials_file, monkeypatch):
    user = make_user(email="g4@example.com")
    monkeypatch.setattr(gmail_oauth, "build", lambda *a, **kw: FakeProfileService())

    conn = gmail_oauth.save_connection(user, FakeCredentials())
    assert conn.id is not None
    assert conn.google_email == "candidate@gmail.com"
    # tokens are encrypted at rest, not stored as plaintext
    assert conn.access_token_encrypted != "access-token-123"

    fetched = gmail_oauth.get_connection(user)
    assert fetched.id == conn.id

    creds = gmail_oauth.get_credentials_for_user(user)
    assert creds.token == "access-token-123"
    assert creds.refresh_token == "refresh-token-456"


def test_disconnect_removes_connection(app, db, make_user, fake_credentials_file, monkeypatch):
    user = make_user(email="g5@example.com")
    monkeypatch.setattr(gmail_oauth, "build", lambda *a, **kw: FakeProfileService())
    gmail_oauth.save_connection(user, FakeCredentials())

    assert GmailConnection.query.filter_by(user_id=user.id).count() == 1
    gmail_oauth.disconnect(user)
    assert GmailConnection.query.filter_by(user_id=user.id).count() == 0


def test_connection_is_per_user_not_shared(app, db, make_user, fake_credentials_file, monkeypatch):
    user_a = make_user(email="g6a@example.com")
    user_b = make_user(email="g6b@example.com")
    monkeypatch.setattr(gmail_oauth, "build", lambda *a, **kw: FakeProfileService())

    gmail_oauth.save_connection(user_a, FakeCredentials(token="token-a"))
    assert gmail_oauth.get_connection(user_b) is None
    assert gmail_oauth.get_connection(user_a).id is not None
