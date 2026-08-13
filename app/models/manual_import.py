from app.extensions import db
from app.models.user import utcnow

MANUAL_IMPORT_ITEM_STATUSES = ("fetched", "failed", "saved", "skipped")


class ManualImportBatch(db.Model):
    """Holds the in-progress queue for the bulk manual-import flow (several
    URLs pasted at once, reviewed and saved one at a time - see
    app/jobs/manual_import.py). At most one row per user; starting a new
    fetch replaces any existing incomplete batch for that user.

    Deliberately a small DB row rather than the Flask session: fetched
    job-posting text (up to 20,000 chars each, up to 10 URLs per batch) is
    far too large for a client-side signed session cookie, and this project
    has no server-side session backend - same "no new infra beyond SQLite"
    reasoning as BackgroundTask (app/models/task.py, Phase 6).

    `items` is a JSON list of dicts, each shaped:
      {"url": str, "status": one of MANUAL_IMPORT_ITEM_STATUSES,
       "page_title": str (only when status == "fetched"),
       "text": str (only when status == "fetched"),
       "error": str (only when status == "failed")}
    `items` is always *reassigned* wholesale when an item changes (never
    mutated in place) so SQLAlchemy's change tracking on the JSON column
    reliably notices the update without needing sqlalchemy.ext.mutable.
    """

    __tablename__ = "manual_import_batches"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False, index=True)
    items = db.Column(db.JSON, nullable=False)
    current_index = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    user = db.relationship("User")

    @property
    def current_item(self):
        if self.current_index < len(self.items):
            return self.items[self.current_index]
        return None

    @property
    def is_complete(self):
        return self.current_index >= len(self.items)
