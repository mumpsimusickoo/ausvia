from app.extensions import db
from app.models.user import utcnow


class JobMatch(db.Model):
    """Cached result of app/ai/matching.py for one (user, job) pair (spec
    section 37: don't recompute stable analyses unnecessarily). Recomputed
    when the candidate profile changes after computed_at - see
    app/jobs/matching_routes.py::_get_or_compute_match."""

    __tablename__ = "job_matches"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    job_id = db.Column(db.Integer, db.ForeignKey("jobs.id"), nullable=False, index=True)

    score = db.Column(db.Integer, nullable=True)
    strengths = db.Column(db.JSON, nullable=False, default=list)
    gaps = db.Column(db.JSON, nullable=False, default=list)  # [{"label", "status", "note"}]
    recommendation = db.Column(db.String(30), nullable=False, default="insufficient_data")
    skipped_categories = db.Column(db.JSON, nullable=False, default=list)

    profile_updated_at_snapshot = db.Column(db.DateTime, nullable=True)
    computed_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    narrative_text = db.Column(db.Text, nullable=True)
    narrative_provider = db.Column(db.String(30), nullable=True)
    narrative_generated_at = db.Column(db.DateTime, nullable=True)

    improvement_tips_text = db.Column(db.Text, nullable=True)
    improvement_tips_provider = db.Column(db.String(30), nullable=True)
    improvement_tips_generated_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User")
    job = db.relationship("Job")

    __table_args__ = (db.UniqueConstraint("user_id", "job_id", name="uq_job_match_user_job"),)


class AIUsage(db.Model):
    """Per-call usage/cost log (spec section 37 - AI cost control). Never
    stores prompt/response content, only metadata - see app/ai/usage.py."""

    __tablename__ = "ai_usage"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    feature = db.Column(db.String(50), nullable=False)  # "match_narrative" | "improvement_tips"
    provider = db.Column(db.String(30), nullable=False)
    model = db.Column(db.String(100), nullable=True)
    input_tokens = db.Column(db.Integer, nullable=False, default=0)
    output_tokens = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    user = db.relationship("User")
