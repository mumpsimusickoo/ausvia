from flask_babel import lazy_gettext as _l

from app.extensions import db
from app.models.user import utcnow

DOCUMENT_TYPES = (
    "cv",
    "diploma",
    "language_certificate",
    "training_certificate",
    "transcript",
    "recommendation_letter",
    "other",
)

# i18n pass 2, 2026-08-28: single source of truth for the translated
# display label of each document type - applications/detail.html and
# documents/list.html both read this instead of each mechanically
# deriving one from the code (doc_type.replace('_', ' ')|capitalize has
# no German equivalent, same class of fix as APPLICATION_STATUS_LABELS).
# Deliberately separate from app/applications/routes.py's DOC_TYPE_LABEL_DE,
# which feeds the application-email AI prompt and stays German always
# regardless of UI language (see DECISIONS.md's i18n pass 3 scope) - this
# dict follows the UI locale instead.
DOCUMENT_TYPE_LABELS = {
    "cv": _l("CV"),
    "diploma": _l("Diploma"),
    "language_certificate": _l("Language certificate"),
    "training_certificate": _l("Training certificate"),
    "transcript": _l("Transcript"),
    "recommendation_letter": _l("Recommendation letter"),
    "other": _l("Other"),
}


class Document(db.Model):
    __tablename__ = "documents"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)

    doc_type = db.Column(db.String(30), nullable=False, default="other")
    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(255), nullable=False, unique=True)
    storage_path = db.Column(db.String(500), nullable=False)
    mime_type = db.Column(db.String(100), nullable=True)
    file_size = db.Column(db.Integer, nullable=False, default=0)
    description = db.Column(db.String(500), nullable=True)

    is_primary_cv = db.Column(db.Boolean, nullable=False, default=False)
    is_primary_diploma = db.Column(db.Boolean, nullable=False, default=False)
    is_primary_german_cert = db.Column(db.Boolean, nullable=False, default=False)

    # Document AI extraction (Phase 6): a heuristic best-guess doc_type from
    # the file's own extracted text, shown to the user as a suggestion they
    # must explicitly apply - never auto-applied. None if extraction wasn't
    # possible (non-PDF, unreadable) or agreed with what the user picked.
    # See app/documents/extraction.py.
    ai_suggested_doc_type = db.Column(db.String(30), nullable=True)

    uploaded_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    user = db.relationship("User", back_populates="documents")
    # Phase 7 remediation (QA finding B1): an ApplicationDocument selection
    # referencing this document must not outlive it - without this, deleting
    # a document that's still selected on an application left a dangling FK
    # that crashed "Generate email"/"Approve" with a raw 500 the next time
    # either read sd.document.
    application_documents = db.relationship(
        "ApplicationDocument", back_populates="document", cascade="all, delete-orphan"
    )

    def human_size(self):
        size = self.file_size
        for unit in ("B", "KB", "MB"):
            if size < 1024:
                return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} GB"
