"""
Real per-user Gmail OAuth web flow (spec section 30/77; supersedes the
single-machine desktop-app flow in gmail_client.py - see DECISIONS.md).

Each user connects their own Gmail account via a standard OAuth
authorization-code web flow (redirect to Google -> user consents -> Google
redirects back to our own callback route). Tokens are stored per-user,
encrypted at rest (app/utils/crypto.py) - never a single shared token file.

Reuses the same credentials.json a "Desktop app"-type Google Cloud OAuth
client produces: Google's loopback exception for that client type accepts
http://127.0.0.1:<port>/... redirect URIs without pre-registration, which
matches how this app runs locally (python app.py binds 127.0.0.1). A "Web
application"-type client with the callback URL registered in Google Cloud
Console also works and is what a real (non-localhost) deployment needs -
see README.md.

Never exercised against a live Google OAuth consent screen in this
environment (no credentials.json configured) - the code follows the
documented google-auth-oauthlib API precisely, but its live behavior is
unverified. See PROJECT_AUDIT.md.
"""
import json
import os

from flask import current_app, url_for
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from app.extensions import db
from app.models.integration import GmailConnection
from app.models.user import utcnow
from app.utils.crypto import decrypt_text, encrypt_text

# gmail.readonly: search/read messages to detect replies.
# gmail.compose: create drafts (including reply drafts) - never send/modify/delete.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
]

CREDENTIALS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "credentials.json")


class GmailNotConfiguredError(Exception):
    """No credentials.json - the app owner hasn't set up a Google Cloud OAuth client yet."""


class GmailNotConnectedError(Exception):
    """This user hasn't connected their Gmail account."""


def is_configured():
    return os.path.exists(CREDENTIALS_FILE)


def _client_config():
    with open(CREDENTIALS_FILE) as f:
        data = json.load(f)
    key = "web" if "web" in data else "installed"
    return data[key]


def _callback_url():
    return url_for("integrations.gmail_callback", _external=True)


def _build_flow(state=None):
    if not is_configured():
        raise GmailNotConfiguredError(
            "Gmail isn't configured yet. An admin needs to add credentials.json - see README.md."
        )
    return Flow.from_client_secrets_file(
        CREDENTIALS_FILE, scopes=SCOPES, state=state, redirect_uri=_callback_url()
    )


def get_authorization_url():
    """Returns (authorization_url, state). Caller must stash state in the
    session and pass it back to exchange_code() on the callback."""
    flow = _build_flow()
    auth_url, state = flow.authorization_url(
        access_type="offline", include_granted_scopes="true", prompt="consent"
    )
    return auth_url, state


def exchange_code(state, full_callback_url):
    """Completes the OAuth exchange. Returns google.oauth2.credentials.Credentials."""
    flow = _build_flow(state=state)
    flow.fetch_token(authorization_response=full_callback_url)
    return flow.credentials


def save_connection(user, credentials):
    conn = GmailConnection.query.filter_by(user_id=user.id).first()
    if not conn:
        conn = GmailConnection(user_id=user.id)
        db.session.add(conn)

    conn.access_token_encrypted = encrypt_text(credentials.token)
    if credentials.refresh_token:
        conn.refresh_token_encrypted = encrypt_text(credentials.refresh_token)
    conn.token_expiry = credentials.expiry
    conn.scopes = " ".join(credentials.scopes or SCOPES)
    conn.updated_at = utcnow()

    try:
        service = build("gmail", "v1", credentials=credentials)
        profile = service.users().getProfile(userId="me").execute()
        conn.google_email = profile.get("emailAddress")
    except Exception:
        pass  # non-fatal - the connection still works without a cached display email

    db.session.commit()
    return conn


def get_connection(user):
    return GmailConnection.query.filter_by(user_id=user.id).first()


def disconnect(user):
    GmailConnection.query.filter_by(user_id=user.id).delete()
    db.session.commit()


def get_credentials_for_user(user):
    conn = get_connection(user)
    if not conn or not conn.access_token_encrypted:
        return None

    cfg = _client_config()
    creds = Credentials(
        token=decrypt_text(conn.access_token_encrypted),
        refresh_token=decrypt_text(conn.refresh_token_encrypted),
        token_uri=cfg.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=cfg["client_id"],
        client_secret=cfg["client_secret"],
        scopes=conn.scopes.split() if conn.scopes else SCOPES,
    )

    if creds.expired and creds.refresh_token:
        creds.refresh(GoogleAuthRequest())
        conn.access_token_encrypted = encrypt_text(creds.token)
        conn.token_expiry = creds.expiry
        db.session.commit()

    return creds


def get_gmail_service(user):
    creds = get_credentials_for_user(user)
    if not creds:
        raise GmailNotConnectedError("Connect your Gmail account first.")
    return build("gmail", "v1", credentials=creds)
