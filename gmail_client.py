"""
Handles Gmail OAuth login and creates DRAFT emails (never sends automatically).
Requires a credentials.json downloaded from Google Cloud Console (see README).
"""
import base64
import mimetypes
import os
from email.message import EmailMessage

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# gmail.compose is enough to create/edit drafts - it deliberately does NOT
# include permission to send mail directly.
SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]

TOKEN_FILE = "token.json"
CREDENTIALS_FILE = "credentials.json"


def get_gmail_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(
                    "credentials.json not found. Download it from Google Cloud "
                    "Console (OAuth client, 'Desktop app' type) and place it in "
                    "this folder. See README.md for steps."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def create_draft(to_email, subject, body_text, attachment_path):
    """Creates a Gmail draft with one PDF attachment. Does NOT send it."""
    service = get_gmail_service()

    message = EmailMessage()
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body_text)

    ctype, encoding = mimetypes.guess_type(attachment_path)
    if ctype is None:
        ctype = "application/pdf"
    maintype, subtype = ctype.split("/", 1)

    with open(attachment_path, "rb") as f:
        file_data = f.read()
        file_name = os.path.basename(attachment_path)

    message.add_attachment(file_data, maintype=maintype, subtype=subtype, filename=file_name)

    encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
    draft_body = {"message": {"raw": encoded_message}}

    draft = service.users().drafts().create(userId="me", body=draft_body).execute()
    return draft
