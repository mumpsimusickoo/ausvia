from app.extensions import db
from app.models.user import utcnow

JOB_STATUSES = ("active", "expired", "closed", "unknown")


class Company(db.Model):
    __tablename__ = "companies"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False, index=True)
    normalized_name = db.Column(db.String(255), nullable=False, index=True)
    industry = db.Column(db.String(120), nullable=True)
    website = db.Column(db.String(500), nullable=True)
    location = db.Column(db.String(255), nullable=True)
    description = db.Column(db.Text, nullable=True)  # only ever filled from verified sources, see app/jobs/company.py

    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    jobs = db.relationship("Job", back_populates="company")


class Job(db.Model):
    """A canonical Ausbildung opportunity. May be backed by one or more JobListing
    rows (one per source) - see app/jobs/dedupe.py for how listings get grouped here."""

    __tablename__ = "jobs"

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=True, index=True)

    title = db.Column(db.String(500), nullable=False)
    location = db.Column(db.String(255), nullable=True)
    federal_state = db.Column(db.String(100), nullable=True)
    postal_code = db.Column(db.String(20), nullable=True)

    start_date = db.Column(db.String(50), nullable=True)  # free-form: postings say "01.09.2027", "sofort", "2027", etc.
    application_deadline = db.Column(db.Date, nullable=True)
    salary = db.Column(db.String(255), nullable=True)
    employment_type = db.Column(db.String(100), nullable=True, default="Ausbildung")

    description = db.Column(db.Text, nullable=True)
    requirements = db.Column(db.Text, nullable=True)
    language_requirements = db.Column(db.JSON, nullable=True)  # [{"language": "German", "level": "B1"}]
    skills = db.Column(db.JSON, nullable=True)  # ["PLC", "STEP7", ...]
    education_requirements = db.Column(db.Text, nullable=True)

    contact_person = db.Column(db.String(255), nullable=True)
    contact_email = db.Column(db.String(255), nullable=True)
    application_url = db.Column(db.String(1000), nullable=True)

    dedup_key = db.Column(db.String(500), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default="active")

    discovered_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    last_checked_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    company = db.relationship("Company", back_populates="jobs")
    listings = db.relationship("JobListing", back_populates="job", cascade="all, delete-orphan")
    saved_by = db.relationship("SavedJob", back_populates="job", cascade="all, delete-orphan")

    @property
    def company_name(self):
        return self.company.name if self.company else None

    @property
    def sources(self):
        return sorted({listing.source for listing in self.listings})

    @property
    def preferred_application_url(self):
        """Prefer an explicit application_url, else the official company-site
        listing (if any), else whichever source listing was discovered first."""
        if self.application_url:
            return self.application_url
        preferred = next((l for l in self.listings if l.is_preferred and l.source_url), None)
        if preferred:
            return preferred.source_url
        with_url = [l for l in self.listings if l.source_url]
        return with_url[0].source_url if with_url else None


class JobListing(db.Model):
    """One occurrence of a job on one source. Multiple listings can point at the
    same canonical Job (see Job.listings) once duplicate detection groups them."""

    __tablename__ = "job_listings"

    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey("jobs.id"), nullable=False, index=True)

    source = db.Column(db.String(50), nullable=False)  # "arbeitsagentur" | "manual"
    external_id = db.Column(db.String(255), nullable=True)
    source_url = db.Column(db.String(1000), nullable=True)
    raw_snapshot = db.Column(db.JSON, nullable=True)  # full raw payload, kept for reprocessing/debugging
    is_preferred = db.Column(db.Boolean, nullable=False, default=False)

    discovered_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    last_checked_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    job = db.relationship("Job", back_populates="listings")

    __table_args__ = (
        db.UniqueConstraint("source", "external_id", name="uq_listing_source_external_id"),
    )


class SavedJob(db.Model):
    __tablename__ = "saved_jobs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    job_id = db.Column(db.Integer, db.ForeignKey("jobs.id"), nullable=False, index=True)
    notes = db.Column(db.Text, nullable=True)
    saved_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    user = db.relationship("User")
    job = db.relationship("Job", back_populates="saved_by")

    __table_args__ = (db.UniqueConstraint("user_id", "job_id", name="uq_saved_job_user_job"),)


class JobSourceSetting(db.Model):
    """Admin-controlled enable/disable + last-run diagnostics per job source
    (spec: admin can manage job sources independently). One row per adapter,
    plus one for "manual" so it shows up in admin diagnostics too."""

    __tablename__ = "job_source_settings"

    id = db.Column(db.Integer, primary_key=True)
    source_name = db.Column(db.String(50), unique=True, nullable=False)
    display_name = db.Column(db.String(100), nullable=False)
    is_enabled = db.Column(db.Boolean, nullable=False, default=True)

    last_run_at = db.Column(db.DateTime, nullable=True)
    last_run_status = db.Column(db.String(20), nullable=True)  # "ok" | "error"
    last_run_message = db.Column(db.String(500), nullable=True)
