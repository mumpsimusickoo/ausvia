"""
Builds and creates Gmail drafts via an already-authenticated per-user
service object (see gmail_oauth.get_gmail_service). Only ever creates
DRAFTS - never sends. Mirrors gmail_client.py's MIME-building approach but
takes a service instead of constructing one itself, and supports proper
in-thread reply drafts (threadId + In-Reply-To/References headers) for the
reply-tracking feature.
"""
import base64
import mimetypes
from email.message import EmailMessage


def _build_mime(to_email, subject, body_text, attachment_path=None, in_reply_to=None, references=None):
    message = EmailMessage()
    message["To"] = to_email
    message["Subject"] = subject
    if in_reply_to:
        message["In-Reply-To"] = in_reply_to
        message["References"] = references or in_reply_to
    message.set_content(body_text)

    if attachment_path:
        ctype, _ = mimetypes.guess_type(attachment_path)
        ctype = ctype or "application/pdf"
        maintype, subtype = ctype.split("/", 1)
        with open(attachment_path, "rb") as f:
            file_data = f.read()
        import os

        message.add_attachment(file_data, maintype=maintype, subtype=subtype, filename=os.path.basename(attachment_path))

    return message


def create_draft(service, to_email, subject, body_text, attachment_path=None):
    """Creates a plain (non-reply) draft. Never sends."""
    message = _build_mime(to_email, subject, body_text, attachment_path=attachment_path)
    encoded = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return service.users().drafts().create(userId="me", body={"message": {"raw": encoded}}).execute()


def create_reply_draft(service, to_email, subject, body_text, thread_id, in_reply_to_rfc_id):
    """Creates a draft that Gmail will thread as a reply. Never sends."""
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"
    message = _build_mime(to_email, subject, body_text, in_reply_to=in_reply_to_rfc_id, references=in_reply_to_rfc_id)
    encoded = base64.urlsafe_b64encode(message.as_bytes()).decode()
    body = {"message": {"raw": encoded, "threadId": thread_id}}
    return service.users().drafts().create(userId="me", body=body).execute()
