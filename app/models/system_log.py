from app.extensions import db
from app.models.user import utcnow

LOG_LEVELS = ("info", "warning", "error")


class SystemLog(db.Model):
    """Admin-visible diagnostics. Never store secrets, raw access codes, or document
    contents here - see app/utils/logging.py for the write path that enforces this."""

    __tablename__ = "system_logs"

    id = db.Column(db.Integer, primary_key=True)
    level = db.Column(db.String(10), nullable=False, default="info")
    category = db.Column(db.String(50), nullable=False)  # e.g. "auth", "upload", "ai", "job_source"
    message = db.Column(db.String(1000), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
