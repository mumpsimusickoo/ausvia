from app.extensions import db
from app.models.user import utcnow

REPLY_INTENTS = (
    "interview_invitation",
    "rejection",
    "document_request",
    "offer",
    "acknowledgement",
    "unclear",
)


class GmailConnection(db.Model):
    """Per-user Gmail OAuth connection (spec: real per-user web OAuth flow,
    not the single shared-token desktop-app flow the prototype used - see
    DECISIONS.md). Tokens are encrypted at rest (app/utils/crypto.py)."""

    __tablename__ = "gmail_connections"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)

    google_email = db.Column(db.String(255), nullable=True)
    access_token_encrypted = db.Column(db.Text, nullable=True)
    refresh_token_encrypted = db.Column(db.Text, nullable=True)
    token_expiry = db.Column(db.DateTime, nullable=True)
    scopes = db.Column(db.String(500), nullable=True)

    connected_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    user = db.relationship("User")


class GmailMessage(db.Model):
    """A detected inbound message related to an application (spec: reply
    tracking). We can only ever *detect* replies by searching, never track a
    thread from creation, because AUSVIA never sends the original email
    itself - the Gmail thread doesn't exist until the user sends the draft
    manually. See app/integrations/gmail_reply_tracking.py."""

    __tablename__ = "gmail_messages"

    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey("applications.id"), nullable=False, index=True)

    gmail_message_id = db.Column(db.String(100), unique=True, nullable=False)
    gmail_thread_id = db.Column(db.String(100), nullable=True)
    rfc_message_id = db.Column(db.String(255), nullable=True)  # the Message-ID header, needed to thread a reply draft
    from_address = db.Column(db.String(255), nullable=True)
    subject = db.Column(db.String(500), nullable=True)
    snippet = db.Column(db.Text, nullable=True)
    body_text = db.Column(db.Text, nullable=True)  # full plain-text body, when extractable
    received_at = db.Column(db.DateTime, nullable=True)

    classified_intent = db.Column(db.String(30), nullable=True)  # one of REPLY_INTENTS, or None if unclassified
    classification_confidence = db.Column(db.String(20), nullable=True)  # "high" | "medium" | "low" - never a fake numeric score
    classification_notes = db.Column(db.Text, nullable=True)
    classification_provider = db.Column(db.String(30), nullable=True)

    ai_suggested_reply = db.Column(db.Text, nullable=True)
    ai_suggested_reply_provider = db.Column(db.String(30), nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    application = db.relationship("Application", back_populates="gmail_messages")
