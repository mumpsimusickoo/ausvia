from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from app.extensions import db


def utcnow():
    """Naive UTC timestamp - matches what SQLite round-trips, avoiding aware/naive mismatches."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)

    role = db.Column(db.String(20), nullable=False, default="user")  # user | admin
    plan = db.Column(db.String(20), nullable=False, default="trial")  # trial | standard | premium | admin
    locale = db.Column(db.String(5), nullable=False, default="en")

    is_active = db.Column(db.Boolean, nullable=False, default=True)
    email_verified = db.Column(db.Boolean, nullable=False, default=False)

    # Impressum/privacy/registration-consent pass (2026-08-31): the actual
    # opt-in record for marketing emails (app/mail.py's marketing-send path,
    # once one exists, must check this before sending) - set once at
    # registration from RegisterForm.marketing_consent, a genuinely separate,
    # unticked-by-default checkbox (GDPR requires marketing consent to be
    # freely given, never bundled with a required checkbox like the age
    # confirmation on the same form). The age confirmation itself is
    # deliberately NOT a column here - it's a one-time submission gate
    # (server-side DataRequired on that BooleanField blocks registration
    # entirely if unchecked), not a fact worth retaining about the account
    # after the fact.
    marketing_consent = db.Column(db.Boolean, nullable=False, default=False, server_default="0")

    # Plans page + access expiry pass (2026-08-30): None = no expiry -
    # unaffected by default (trial/admin accounts, every pre-existing user,
    # and any code redeemed without a duration set - see
    # InvitationCode.access_duration_months). When set, both the login
    # check (app/auth/routes.py's login()) and the mid-session check
    # (app/access_expiry.py's enforce_access_expiry(), registered as an
    # app-wide before_request) refuse/end access once this passes. Not
    # itself the AI-generation-count limit (User.plan + PLAN_AI_LIMITS,
    # app/models/access_code.py) - that limit stays unenforced, a known,
    # separate, deliberate gap - see DECISIONS.md.
    access_expires_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    profile = db.relationship(
        "CandidateProfile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    documents = db.relationship("Document", back_populates="user", cascade="all, delete-orphan")

    def set_password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        return check_password_hash(self.password_hash, raw_password)

    @property
    def is_admin(self):
        return self.role == "admin"

    def __repr__(self):
        return f"<User {self.email}>"
