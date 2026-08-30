import secrets
import string

from flask_babel import gettext as _

from app.extensions import db
from app.models.user import utcnow

CODE_TYPES = ("trial", "standard", "premium", "admin")

# Generation limits by plan, applied at redemption time (Phase 3+ AI usage tracking
# enforces these; stored here so the limit travels with the code/plan).
PLAN_AI_LIMITS = {
    "trial": 10,
    "standard": 100,
    "premium": 1000,
    "admin": None,  # unlimited
}


def generate_code():
    """Generates a code like A7K9-XP42-QM8L. Excludes ambiguous chars (0/O, 1/I).

    Phase 8 security audit (D1): was stdlib `random` (not cryptographically
    secure) despite SECURITY.md documenting `secrets`-backed generation -
    a docs/code mismatch, now fixed to match what was already documented.
    """
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    groups = ["".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(3)]
    return "-".join(groups)


class InvitationCode(db.Model):
    __tablename__ = "invitation_codes"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(32), unique=True, nullable=False, index=True)

    code_type = db.Column(db.String(20), nullable=False, default="trial")
    max_uses = db.Column(db.Integer, nullable=False, default=1)
    use_count = db.Column(db.Integer, nullable=False, default=0)

    is_active = db.Column(db.Boolean, nullable=False, default=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    notes = db.Column(db.Text, nullable=True)

    # Plans page + access expiry pass (2026-08-30): None = no auto-expiry -
    # the same backward-compatible default as every other field here, so
    # every code type this app already issues (trial/standard/admin, and
    # any premium code created the old way) behaves exactly as before.
    # When set, redeeming this code computes the new user's
    # User.access_expires_at as redeemed_at + this many CALENDAR months
    # (dateutil.relativedelta, not a flat day count - see
    # app/auth/routes.py's register()). Deliberately NOT the same field as
    # `expires_at` above: that one governs the CODE's own redemption
    # window (unchanged by this pass, still just "can this code still be
    # used"); this one governs how long the RESULTING ACCOUNT stays
    # active once redeemed - two different clocks that happen to both
    # live on this row.
    access_duration_months = db.Column(db.Integer, nullable=True)

    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    redemptions = db.relationship(
        "CodeRedemption", back_populates="code", cascade="all, delete-orphan"
    )

    def is_valid(self):
        if not self.is_active:
            return False, _("This access code has been deactivated.")
        if self.expires_at and self.expires_at < utcnow():
            return False, _("This access code has expired.")
        if self.use_count >= self.max_uses:
            return False, _("This access code has already been used the maximum number of times.")
        return True, None

    def __repr__(self):
        return f"<InvitationCode {self.code}>"


class CodeRedemption(db.Model):
    __tablename__ = "code_redemptions"

    id = db.Column(db.Integer, primary_key=True)
    code_id = db.Column(db.Integer, db.ForeignKey("invitation_codes.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    redeemed_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    code = db.relationship("InvitationCode", back_populates="redemptions")
    user = db.relationship("User")
