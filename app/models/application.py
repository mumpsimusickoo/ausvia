from flask_babel import lazy_gettext as _l

from app.extensions import db
from app.models.user import utcnow

APPLICATION_STATUSES = (
    "preparing",
    "ready",
    "sent",
    "follow_up",
    "interview",
    "offer",
    "accepted",
    "rejected",
    "withdrawn",
    "expired",
)

# i18n pass 2, 2026-08-28: single source of truth for the translated
# display label of each status code - status_pill() (_components.html)
# and StatusForm's dropdown (app/applications/forms.py) both read this
# instead of each mechanically deriving one from the code
# (status.replace('_', ' ')|title has no German equivalent - there's no
# rule that turns "follow_up" into a correct German word that way).
# lazy_gettext works at both call sites: StatusForm builds its choices at
# class-body/import time (needs deferred evaluation), status_pill() reads
# it per-request (a LazyString coerces to the right translated str either
# way). The status CODE itself is never translated - every status
# comparison in the app (`application.status == "ready"`, etc.) matches
# on this raw string, unaffected by locale.
APPLICATION_STATUS_LABELS = {
    "preparing": _l("In preparation"),
    "ready": _l("Ready"),
    "sent": _l("Sent"),
    "follow_up": _l("Follow-up"),
    "interview": _l("Interview"),
    "offer": _l("Offer"),
    "accepted": _l("Accepted"),
    "rejected": _l("Rejected"),
    "withdrawn": _l("Withdrawn"),
    "expired": _l("Expired"),
}

class Application(db.Model):
    __tablename__ = "applications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    job_id = db.Column(db.Integer, db.ForeignKey("jobs.id"), nullable=False, index=True)

    status = db.Column(db.String(20), nullable=False, default="preparing")

    contact_person = db.Column(db.String(255), nullable=True)
    contact_email = db.Column(db.String(255), nullable=True)
    application_url = db.Column(db.String(1000), nullable=True)
    notes = db.Column(db.Text, nullable=True)

    package_storage_path = db.Column(db.String(500), nullable=True)
    package_filename = db.Column(db.String(255), nullable=True)

    sent_at = db.Column(db.DateTime, nullable=True)
    interview_date = db.Column(db.DateTime, nullable=True)
    follow_up_date = db.Column(db.Date, nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    user = db.relationship("User")
    job = db.relationship("Job")
    events = db.relationship(
        "ApplicationEvent", back_populates="application", cascade="all, delete-orphan",
        order_by="ApplicationEvent.created_at",
    )
    cover_letter = db.relationship(
        "GeneratedDocument", back_populates="application", uselist=False, cascade="all, delete-orphan"
    )
    email = db.relationship(
        "GeneratedEmail", back_populates="application", uselist=False, cascade="all, delete-orphan"
    )
    follow_up_email = db.relationship(
        "FollowUpEmail", back_populates="application", uselist=False, cascade="all, delete-orphan"
    )
    selected_documents = db.relationship(
        "ApplicationDocument", back_populates="application", cascade="all, delete-orphan",
        order_by="ApplicationDocument.order_index",
    )
    # Application deletion pass: both of these have a NOT NULL FK to
    # applications.id but, unlike every relationship above, had no cascade
    # declared here before now - with SQLite FK enforcement on
    # (app/__init__.py), deleting an application with reply-tracking or
    # interview-prep data would have raised an IntegrityError rather than
    # silently orphaning anything, but it would still have made delete
    # crash for exactly the applications a user is most likely to want to
    # clean up (ones with real history). Same cascade as the rest.
    gmail_messages = db.relationship(
        "GmailMessage", back_populates="application", cascade="all, delete-orphan"
    )
    interview_prep = db.relationship(
        "InterviewPrep", back_populates="application", uselist=False, cascade="all, delete-orphan"
    )
    cv_profile_statement = db.relationship(
        "CvProfileStatement", back_populates="application", uselist=False, cascade="all, delete-orphan"
    )

    __table_args__ = (db.UniqueConstraint("user_id", "job_id", name="uq_application_user_job"),)

    def log_event(self, event_type, description):
        event = ApplicationEvent(application_id=self.id, event_type=event_type, description=description)
        db.session.add(event)
        return event


class ApplicationEvent(db.Model):
    __tablename__ = "application_events"

    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey("applications.id"), nullable=False, index=True)
    event_type = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    application = db.relationship("Application", back_populates="events")


class GeneratedDocument(db.Model):
    """The generated Anschreiben (cover letter) for one application. One per
    application - regenerating overwrites it, with the change logged as an
    ApplicationEvent rather than kept as full history (spec section 46)."""

    __tablename__ = "generated_documents"

    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey("applications.id"), unique=True, nullable=False)

    content = db.Column(db.Text, nullable=False)
    source = db.Column(db.String(20), nullable=False)  # "ai" | "template"
    provider = db.Column(db.String(30), nullable=True)

    validated = db.Column(db.Boolean, nullable=False, default=False)
    validation_notes = db.Column(db.Text, nullable=True)
    # "high"|"medium"|"low", same range as GmailMessage.classification_confidence.
    # Deliberately NOT derived from `validated` above, even though it's
    # tempting to have one column feed the other - `validated` is a
    # pass/fail fact-check (did the AI invent something not in the
    # candidate's real data), a different question from "how confident is
    # the model in this text", and conflating the two would misrepresent
    # what either one means. Null by design, unwired by any generator -
    # see DECISIONS.md's 2026-08-26 "Reliability field" entry.
    reliability = db.Column(db.String(20), nullable=True)

    generated_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    edited_at = db.Column(db.DateTime, nullable=True)

    application = db.relationship("Application", back_populates="cover_letter")


class GeneratedEmail(db.Model):
    __tablename__ = "generated_emails"

    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey("applications.id"), unique=True, nullable=False)

    subject = db.Column(db.String(500), nullable=False)
    body = db.Column(db.Text, nullable=False)
    source = db.Column(db.String(20), nullable=False)  # "ai" | "template"
    provider = db.Column(db.String(30), nullable=True)
    reliability = db.Column(db.String(20), nullable=True)  # see GeneratedDocument.reliability

    generated_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    edited_at = db.Column(db.DateTime, nullable=True)

    application = db.relationship("Application", back_populates="email")


class FollowUpEmail(db.Model):
    """A drafted follow-up email for an application sitting in Sent/Follow-up
    status (Phase 9) - user-triggered, same shape as GeneratedEmail
    (regenerating overwrites it, editable/saveable, "ai" or "template"
    source). Deliberately its own table rather than reusing GeneratedEmail:
    a follow-up is a distinct piece of content from the original application
    email, and an application may reasonably want both preserved at once."""

    __tablename__ = "follow_up_emails"

    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey("applications.id"), unique=True, nullable=False)

    subject = db.Column(db.String(500), nullable=False)
    body = db.Column(db.Text, nullable=False)
    source = db.Column(db.String(20), nullable=False)  # "ai" | "template"
    provider = db.Column(db.String(30), nullable=True)

    generated_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    edited_at = db.Column(db.DateTime, nullable=True)

    application = db.relationship("Application", back_populates="follow_up_email")


class ApplicationDocument(db.Model):
    """A document from the user's library selected for inclusion in this
    application's PDF package, with its position in the package."""

    __tablename__ = "application_documents"

    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey("applications.id"), nullable=False, index=True)
    document_id = db.Column(db.Integer, db.ForeignKey("documents.id"), nullable=False)
    order_index = db.Column(db.Integer, nullable=False, default=0)

    application = db.relationship("Application", back_populates="selected_documents")
    document = db.relationship("Document", back_populates="application_documents")

    __table_args__ = (
        db.UniqueConstraint("application_id", "document_id", name="uq_app_document_once"),
    )
