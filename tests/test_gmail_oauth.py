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
