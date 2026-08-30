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
       "page_title": str (only when status == "fetched") - the raw
         <title> tag, unchanged, kept as the fallback source of truth,
       "text": str (only when status == "fetched") - the raw fetched
         text dump, unchanged, kept as the fallback source of truth,
       "error": str (only when status == "failed"),
       "extracted": bool, once the lazy AI extraction pass
         (app/ai/manual_import_extraction.py) has actually run for this
         item, whether or not it found anything; never re-run once True,
         so revisiting an already-reviewed item never burns a second AI
         call. Two trigger points, same caching contract either way (see
         app/jobs/routes.py's _store_extraction_result()): a "fetched"
         item runs it via _ensure_item_extracted() before the review form
         is ever shown (source: page_title/text below); a "failed" item
         instead runs it via _ensure_pasted_text_extracted() the first
         time the user pastes text into the description field and clicks
         Save (source: whatever they just typed on that submission -
         there's nothing to extract from until then),
       "extracted_title"/"extracted_company_name"/"extracted_location"/
         "extracted_start_date"/"extracted_salary"/"extracted_contact_person"/
         "extracted_contact_email"/"extracted_description":
         str or None (only once "extracted" is True) - grounded
         AI-suggested values, or the same safe fallback (raw page_title/
         text for a fetched item, the user's own pasted text unchanged
         for a failed one; blank company/location/start_date/salary/
         contact_person/contact_email either way) if extraction declined,
         failed, or found nothing usable. These, not
         page_title/text directly, are what the review form actually
         displays - see _render_batch_review() in app/jobs/routes.py.}
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
