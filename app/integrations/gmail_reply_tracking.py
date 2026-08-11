"""
Reply detection (spec section 31). Ausvia never sends the original
application email itself (spec: user always sends manually), so there is no
Gmail thread to track from creation - the thread doesn't exist in Gmail
until the user sends the draft. Detection therefore works by searching the
connected inbox for messages from the application's contact email, which is
the best available approach without controlling the send step. This is a
manual, user-triggered check for now (no background polling - see
ARCHITECTURE.md's background-jobs gap).
"""
import base64
from datetime import datetime, timezone

from app.extensions import db
from app.models.integration import GmailMessage
from app.utils.logging import log_event

MAX_BODY_CHARS = 8000  # cap what we store/pass to AI - a reply doesn't need more than this


def _header(headers, name):
    return next((h["value"] for h in headers if h["name"].lower() == name.lower()), None)


def _extract_plain_text(payload):
    """Recursively finds the first text/plain part in a Gmail message payload
    and decodes it. Falls back to None if the message has no plain-text part
    (e.g. HTML-only) - callers fall back to the snippet in that case."""
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        data = payload["body"]["data"]
        return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")

    for part in payload.get("parts", []) or []:
        text = _extract_plain_text(part)
        if text:
            return text
    return None


def check_for_replies(user, application, service):
    """Returns the list of newly-detected GmailMessage rows (empty if none)."""
    if not application.contact_email:
        return []

    query = f"from:{application.contact_email}"
    if application.sent_at:
        query += f" after:{int(application.sent_at.replace(tzinfo=timezone.utc).timestamp())}"

    results = service.users().messages().list(userId="me", q=query, maxResults=25).execute()
    message_refs = results.get("messages", [])
    if not message_refs:
        return []

    known_ids = {
        row.gmail_message_id
        for row in GmailMessage.query.filter_by(application_id=application.id).all()
    }

    new_messages = []
    for ref in message_refs:
        if ref["id"] in known_ids:
            continue

        full = service.users().messages().get(userId="me", id=ref["id"], format="full").execute()
        headers = full.get("payload", {}).get("headers", [])
        received_at = None
        if full.get("internalDate"):
            received_at = datetime.fromtimestamp(int(full["internalDate"]) / 1000, tz=timezone.utc).replace(tzinfo=None)

        body_text = _extract_plain_text(full.get("payload", {}))
        if body_text:
            body_text = body_text[:MAX_BODY_CHARS]

        record = GmailMessage(
            application_id=application.id,
            gmail_message_id=full["id"],
            gmail_thread_id=full.get("threadId"),
            rfc_message_id=_header(headers, "Message-ID"),
            from_address=_header(headers, "From"),
            subject=_header(headers, "Subject"),
            snippet=full.get("snippet"),
            body_text=body_text,
            received_at=received_at,
        )
        db.session.add(record)
        new_messages.append(record)

    if new_messages:
        application.log_event(
            "reply_detected",
            f"{len(new_messages)} new message(s) detected from {application.contact_email}.",
        )
        log_event("gmail", f"{len(new_messages)} reply message(s) detected.", user_id=user.id)
        db.session.commit()

    return new_messages
