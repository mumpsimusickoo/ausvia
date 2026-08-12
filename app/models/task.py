from app.extensions import db
from app.models.user import utcnow

TASK_STATUSES = ("pending", "running", "done", "error")


class BackgroundTask(db.Model):
    """A unit of work run off the request/response cycle (Phase 6 - see
    app/tasks/runner.py). Deliberately minimal: no broker, no separate
    worker process - a DB row plus an in-process thread pool, matching this
    project's established "no new infra beyond SQLite" pattern (no
    Docker/Redis available in this dev environment - see DECISIONS.md).
    Real deployments needing durability across restarts or multi-process
    scaling would swap this for Celery/RQ + Redis; the row shape here
    (task_type, status, result/error text) is deliberately compatible with
    that upgrade path."""

    __tablename__ = "background_tasks"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    task_type = db.Column(db.String(50), nullable=False)  # e.g. "gmail_check_replies"
    status = db.Column(db.String(20), nullable=False, default="pending")
    # free-form, task-specific: e.g. {"application_id": 5}
    context = db.Column(db.JSON, nullable=True)

    result_message = db.Column(db.String(500), nullable=True)
    error_message = db.Column(db.String(500), nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    started_at = db.Column(db.DateTime, nullable=True)
    finished_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User")

    @property
    def is_active(self):
        return self.status in ("pending", "running")
