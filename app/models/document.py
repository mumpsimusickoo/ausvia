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

    uploaded_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    user = db.relationship("User", back_populates="documents")

    def human_size(self):
        size = self.file_size
        for unit in ("B", "KB", "MB"):
            if size < 1024:
                return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} GB"
