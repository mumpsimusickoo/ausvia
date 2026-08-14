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


FAKE_CLIENT_CONFIG = {
    "web": {
        "client_id": "env-fake-client-id",
        "client_secret": "env-fake-client-secret",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    }
}


def test_is_configured_true_with_only_env_var_set(app, monkeypatch):
    # No credentials.json on disk (test_not_configured_by_default already
    # confirms that) - GOOGLE_CREDENTIALS_JSON alone must be enough.
    monkeypatch.setenv(gmail_oauth.GOOGLE_CREDENTIALS_JSON_ENV, json.dumps(FAKE_CLIENT_CONFIG))
    assert gmail_oauth.is_configured() is True


def test_client_config_from_env_var_matches_shape_of_file_based_config(
    app, fake_credentials_file, monkeypatch
):
    # File-based config for comparison (same _client_config() call the app
    # already relies on for token refresh - app/integrations/gmail_oauth.py's
    # get_credentials_for_user()).
    from_file = gmail_oauth._client_config()

    monkeypatch.setenv(gmail_oauth.GOOGLE_CREDENTIALS_JSON_ENV, json.dumps(FAKE_CLIENT_CONFIG))
    from_env = gmail_oauth._client_config()

    # Same shape: both are the unwrapped inner dict (no "web"/"installed"
    # wrapper), with the same core fields get_credentials_for_user() reads.
    for key in ("client_id", "client_secret", "token_uri"):
        assert key in from_file
        assert key in from_env
    assert from_env["client_id"] == "env-fake-client-id"
    assert from_env["client_secret"] == "env-fake-client-secret"


def test_env_var_takes_precedence_when_both_are_present(app, fake_credentials_file, monkeypatch):
    monkeypatch.setenv(gmail_oauth.GOOGLE_CREDENTIALS_JSON_ENV, json.dumps(FAKE_CLIENT_CONFIG))
    cfg = gmail_oauth._client_config()
    assert cfg["client_id"] == "env-fake-client-id"  # not the fake_credentials_file value


def test_build_flow_uses_from_client_config_when_env_var_set(app, monkeypatch):
    # CREDENTIALS_FILE deliberately left pointing at a real-but-nonexistent
    # path - if _build_flow() fell back to file-based loading it would
    # raise FileNotFoundError instead of succeeding, proving this exercised
    # the env-var branch specifically.
    monkeypatch.setattr(gmail_oauth, "CREDENTIALS_FILE", "/nonexistent/credentials.json")
    monkeypatch.setenv(gmail_oauth.GOOGLE_CREDENTIALS_JSON_ENV, json.dumps(FAKE_CLIENT_CONFIG))

    # url_for(..., _external=True) inside _build_flow() needs a request
    # context, unlike the other tests above that only touch _client_config().
    with app.test_request_context():
        flow = gmail_oauth._build_flow()
    assert flow.client_config["client_id"] == "env-fake-client-id"


def test_connection_is_per_user_not_shared(app, db, make_user, fake_credentials_file, monkeypatch):
    user_a = make_user(email="g6a@example.com")
    user_b = make_user(email="g6b@example.com")
    monkeypatch.setattr(gmail_oauth, "build", lambda *a, **kw: FakeProfileService())

    gmail_oauth.save_connection(user_a, FakeCredentials(token="token-a"))
    assert gmail_oauth.get_connection(user_b) is None
    assert gmail_oauth.get_connection(user_a).id is not None
