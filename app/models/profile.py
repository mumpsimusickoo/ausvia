from flask_babel import lazy_gettext as _l

from app.extensions import db
from app.models.user import utcnow

CEFR_LEVELS = ("A1", "A2", "B1", "B2", "C1", "C2", "Native")
PROFICIENCY_LEVELS = ("beginner", "intermediate", "advanced", "expert")


class CandidateProfile(db.Model):
    __tablename__ = "candidate_profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)

    first_name = db.Column(db.String(100), nullable=True)
    last_name = db.Column(db.String(100), nullable=True)
    date_of_birth = db.Column(db.Date, nullable=True)
    nationality = db.Column(db.String(100), nullable=True)

    address = db.Column(db.String(255), nullable=True)
    city = db.Column(db.String(120), nullable=True)
    postal_code = db.Column(db.String(20), nullable=True)
    country = db.Column(db.String(100), nullable=True)
    phone = db.Column(db.String(50), nullable=True)
    contact_email = db.Column(db.String(255), nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    user = db.relationship("User", back_populates="profile")
    education_entries = db.relationship(
        "Education", back_populates="profile", cascade="all, delete-orphan",
        order_by="desc(Education.end_date)",
    )
    experience_entries = db.relationship(
        "Experience", back_populates="profile", cascade="all, delete-orphan",
        order_by="desc(Experience.end_date)",
    )
    skills = db.relationship("Skill", back_populates="profile", cascade="all, delete-orphan")
    languages = db.relationship("Language", back_populates="profile", cascade="all, delete-orphan")
    preference = db.relationship(
        "Preference", back_populates="profile", uselist=False, cascade="all, delete-orphan"
    )

    @property
    def full_name(self):
        return " ".join(p for p in [self.first_name, self.last_name] if p) or None

    def completeness_checklist(self):
        """(label, satisfied) pairs backing completeness_percent() below -
        split out in the Dashboard pass (2026-08-27) so the dashboard can
        name what's actually missing ("Missing: Skills, Job preferences")
        instead of showing a bare percentage. Same eight checks, same
        order, same weighting as before this pass - only exposing the
        labels is new, the percentage itself is unchanged.

        i18n pass 2: these eight labels are deliberately plain, untranslated
        strings - they're stable internal keys other code matches against
        (app/profile/routes.py's _COMPLETENESS_PHRASING dict), the same
        "raw code, translated only at the display boundary" pattern as
        Application.status/Document.doc_type. See CHECKLIST_LABEL_TRANSLATIONS
        below for the translated version, used wherever one of these eight
        labels is shown directly rather than routed through
        _COMPLETENESS_PHRASING's done/missing sentence."""
        return [
            ("Name", bool(self.first_name and self.last_name)),
            ("Location", bool(self.city and self.country)),
            ("Phone number", bool(self.phone)),
            ("Contact email", bool(self.contact_email)),
            ("Education", bool(self.education_entries)),
            ("Skills", bool(self.skills)),
            ("Languages", bool(self.languages)),
            ("Job preferences", bool(self.preference)),
        ]

    def completeness_percent(self):
        """Rough profile-completeness signal shown on the dashboard."""
        checks = self.completeness_checklist()
        return round(100 * sum(ok for _, ok in checks) / len(checks))


# i18n pass 2, 2026-08-28: translated display label for each of
# completeness_checklist()'s eight raw label strings - used directly by
# main/routes.py's dashboard() for the "Missing: X, Y" line (no
# done/missing phrasing there, just the bare names). See
# completeness_checklist()'s own docstring for why the checklist labels
# themselves stay untranslated.
CHECKLIST_LABEL_TRANSLATIONS = {
    "Name": _l("Name"),
    "Location": _l("Location"),
    "Phone number": _l("Phone number"),
    "Contact email": _l("Contact email"),
    "Education": _l("Education"),
    "Skills": _l("Skills"),
    "Languages": _l("Languages"),
    "Job preferences": _l("Job preferences"),
}


class Education(db.Model):
    __tablename__ = "education_entries"

    id = db.Column(db.Integer, primary_key=True)
    profile_id = db.Column(db.Integer, db.ForeignKey("candidate_profiles.id"), nullable=False)

    institution = db.Column(db.String(255), nullable=False)
    degree = db.Column(db.String(255), nullable=True)
    field = db.Column(db.String(255), nullable=True)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    description = db.Column(db.Text, nullable=True)
    country = db.Column(db.String(100), nullable=True)

    profile = db.relationship("CandidateProfile", back_populates="education_entries")


class Experience(db.Model):
    __tablename__ = "experience_entries"

    id = db.Column(db.Integer, primary_key=True)
    profile_id = db.Column(db.Integer, db.ForeignKey("candidate_profiles.id"), nullable=False)

    company = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(255), nullable=True)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    responsibilities = db.Column(db.Text, nullable=True)
    achievements = db.Column(db.Text, nullable=True)

    profile = db.relationship("CandidateProfile", back_populates="experience_entries")


class Skill(db.Model):
    __tablename__ = "skills"

    id = db.Column(db.Integer, primary_key=True)
    profile_id = db.Column(db.Integer, db.ForeignKey("candidate_profiles.id"), nullable=False)

    name = db.Column(db.String(120), nullable=False)
    proficiency = db.Column(db.String(20), nullable=True)  # one of PROFICIENCY_LEVELS

    profile = db.relationship("CandidateProfile", back_populates="skills")


class Language(db.Model):
    __tablename__ = "languages"

    id = db.Column(db.Integer, primary_key=True)
    profile_id = db.Column(db.Integer, db.ForeignKey("candidate_profiles.id"), nullable=False)

    name = db.Column(db.String(100), nullable=False)
    level = db.Column(db.String(10), nullable=True)  # one of CEFR_LEVELS

    profile = db.relationship("CandidateProfile", back_populates="languages")


class Preference(db.Model):
    __tablename__ = "preferences"

    id = db.Column(db.Integer, primary_key=True)
    profile_id = db.Column(db.Integer, db.ForeignKey("candidate_profiles.id"), unique=True, nullable=False)

    fields = db.Column(db.JSON, nullable=True, default=list)  # e.g. ["automation", "electronics"]
    locations = db.Column(db.JSON, nullable=True, default=list)  # states/cities, [] = Germany-wide
    desired_start_date = db.Column(db.String(20), nullable=True)  # e.g. "2027" or "2027-09"
    min_german_level = db.Column(db.String(10), nullable=True)  # one of CEFR_LEVELS
    max_distance_km = db.Column(db.Integer, nullable=True)
    open_to_relocation = db.Column(db.Boolean, nullable=False, default=True)
    other_notes = db.Column(db.Text, nullable=True)

    profile = db.relationship("CandidateProfile", back_populates="preference")
