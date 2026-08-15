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
    category_scores = db.Column(
        db.JSON, nullable=False, default=dict, server_default="{}"
    )  # {"skills": 92, "language": 88, ...}

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


class CompanyInsight(db.Model):
    """Cached "why this company might fit you" AI synthesis (Phase 6, spec
    sections 18/19 - Company Intelligence). Per-(user, company), like
    JobMatch - the synthesis is grounded in one candidate's real profile, so
    it is never shared across users the way Company's own fields are.
    Recomputed when the candidate profile changes after computed_at, same
    staleness rule as JobMatch."""

    __tablename__ = "company_insights"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False, index=True)

    summary_text = db.Column(db.Text, nullable=True)
    provider = db.Column(db.String(30), nullable=True)
    profile_updated_at_snapshot = db.Column(db.DateTime, nullable=True)
    generated_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User")
    company = db.relationship("Company")

    __table_args__ = (db.UniqueConstraint("user_id", "company_id", name="uq_company_insight_user_company"),)


class ProfileCoaching(db.Model):
    """Cached AI review of the whole candidate profile (Phase 9), independent
    of any one job posting - distinct from JobMatch's job-specific
    improvement tips. Same staleness pattern as JobMatch/CompanyInsight:
    recomputed only when the profile has changed since the last generation.
    No deterministic core - reviewing a career narrative is inherently a
    language task, so mock mode declines honestly (see
    app/ai/profile_coaching.py), same pattern as CompanyInsight."""

    __tablename__ = "profile_coachings"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False, index=True)

    summary_text = db.Column(db.Text, nullable=True)
    provider = db.Column(db.String(30), nullable=True)
    profile_updated_at_snapshot = db.Column(db.DateTime, nullable=True)
    generated_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User")


class InterviewPrep(db.Model):
    """Cached AI-generated likely interview questions + talking points for
    one application (Phase 9), grounded in the candidate's real profile and
    the job/company's real stored facts. Per-application (not per-job) since
    that's the natural lookup key on the page it's shown on, and an
    Application is already unique per (user, job). Same staleness pattern as
    JobMatch/CompanyInsight; no deterministic core (see
    app/ai/interview_prep.py)."""

    __tablename__ = "interview_preps"

    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey("applications.id"), unique=True, nullable=False, index=True)

    prep_text = db.Column(db.Text, nullable=True)
    provider = db.Column(db.String(30), nullable=True)
    profile_updated_at_snapshot = db.Column(db.DateTime, nullable=True)
    generated_at = db.Column(db.DateTime, nullable=True)

    application = db.relationship("Application", back_populates="interview_prep")


class JobExplainer(db.Model):
    """Cached AI plain-language summary of one job posting's original text
    (Phase 9), calibrated to the candidate's own stated German level when
    known - see app/ai/job_explainer.py for the reasoning. Personalized per
    candidate (not shared across users the way Job's own fields are) because
    of that calibration, so it's per-(user, job) like JobMatch/CompanyInsight,
    with the same staleness rule and no deterministic core (plain-language
    simplification is inherently a language task)."""

    __tablename__ = "job_explainers"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    job_id = db.Column(db.Integer, db.ForeignKey("jobs.id"), nullable=False, index=True)

    explainer_text = db.Column(db.Text, nullable=True)
    provider = db.Column(db.String(30), nullable=True)
    profile_updated_at_snapshot = db.Column(db.DateTime, nullable=True)
    generated_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User")
    job = db.relationship("Job")

    __table_args__ = (db.UniqueConstraint("user_id", "job_id", name="uq_job_explainer_user_job"),)


PROCESS_QA_QUESTIONS = {
    "ausbildungsverguetung": "What does Ausbildungsvergütung mean?",
    "unrelated_experience": "Should I mention unrelated work experience?",
    "response_time": "What's the normal response time for an application?",
    "document_translation": "Do I need to translate my documents into German?",
    "ausbildung_vs_duales_studium": "What's the difference between an Ausbildung and a Duales Studium?",
}


class ProcessQAAnswer(db.Model):
    """Cached AI answer to one of a fixed set of common process/terminology
    questions (Phase 9, PROCESS_QA_QUESTIONS above) - deliberately a typed
    question picker, not open free-text chat (this app has no chat-style UI
    anywhere else). Per-(user, question) since one question
    ("Should I mention unrelated work experience?") is grounded in the
    candidate's own profile, not just general domain knowledge, so answers
    aren't safely shareable across users. Same staleness pattern as
    JobMatch/CompanyInsight."""

    __tablename__ = "process_qa_answers"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    question_key = db.Column(db.String(50), nullable=False)

    answer_text = db.Column(db.Text, nullable=True)
    provider = db.Column(db.String(30), nullable=True)
    profile_updated_at_snapshot = db.Column(db.DateTime, nullable=True)
    generated_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User")

    __table_args__ = (db.UniqueConstraint("user_id", "question_key", name="uq_process_qa_user_question"),)
