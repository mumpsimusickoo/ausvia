"""
Duplicate detection (spec section 14). The same Ausbildung posting often
appears on multiple sources with slightly different text. Rather than delete
"duplicates", every new listing is grouped under one canonical Job when its
normalized company + title + location + start date match an existing one.
This is a deliberately simple v1 heuristic (exact match on normalized fields)
- swap compute_dedup_key for fuzzy/embedding-based matching later without
touching callers.
"""
import re

from app.extensions import db
from app.models.job import Company, Job, JobListing
from app.models.user import utcnow

LEGAL_SUFFIXES = (
    "gmbh & co kg", "gmbh and co kg", "gmbh", "ag & co kg", "ag", "kg",
    "e.k.", "e.v.", "ug", "co kg", "se",
)


def normalize_company_name(name):
    if not name:
        return ""
    value = name.lower().strip()
    value = re.sub(r"[.,]", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    for suffix in sorted(LEGAL_SUFFIXES, key=len, reverse=True):
        if value.endswith(" " + suffix):
            value = value[: -(len(suffix) + 1)].strip()
            break
    return value


def normalize_title(title):
    if not title:
        return ""
    value = title.lower()
    value = re.sub(r"\(.*?\)", "", value)  # drop "(m/w/d)" style suffixes
    value = re.sub(r"[^\w\s]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def normalize_location(location):
    return (location or "").strip().lower()


def compute_dedup_key(company_name, title, location, start_date):
    return "|".join(
        [
            normalize_company_name(company_name),
            normalize_title(title),
            normalize_location(location),
            (start_date or "").strip().lower(),
        ]
    )


def resolve_or_create_company(company_name):
    if not company_name:
        return None
    normalized = normalize_company_name(company_name)
    if not normalized:
        return None

    company = Company.query.filter_by(normalized_name=normalized).first()
    if company:
        return company

    company = Company(name=company_name.strip(), normalized_name=normalized)
    db.session.add(company)
    db.session.flush()
    return company


def find_or_create_canonical_job(normalized_job):
    """Returns (Job, created: bool). Attaches a JobListing for this source
    either way - to a freshly created Job or to an existing matching one."""
    company = resolve_or_create_company(normalized_job.company_name)
    dedup_key = compute_dedup_key(
        normalized_job.company_name, normalized_job.title, normalized_job.location, normalized_job.start_date
    )

    # Job-source integration pass: a second, independent dedup signal,
    # checked first and purely additive - it only ever *widens* matching,
    # never narrows it, so it can't regress the existing company+title+
    # location behavior below. The same real vacancy can appear on multiple
    # providers with slightly different company/title text (translation,
    # punctuation, "(m/w/d)" placement) that still fails the exact-match
    # heuristic, but an identical canonical/original URL across two
    # listings is an unambiguous signal they're the same posting - a
    # coincidental URL collision between two genuinely different real jobs
    # is not a realistic concern.
    existing = None
    url = normalized_job.application_url or normalized_job.source_url
    if url:
        existing = (
            Job.query.join(Job.listings).filter(JobListing.source_url == url).first()
            or Job.query.filter(Job.application_url == url).first()
        )

    if existing is None:
        existing = Job.query.filter_by(dedup_key=dedup_key).first()

    if existing:
        job = existing
        created = False
        job.last_checked_at = utcnow()
        merge_missing_fields(job, normalized_job)
    else:
        job = Job(
            company_id=company.id if company else None,
            title=normalized_job.title,
            location=normalized_job.location,
            federal_state=normalized_job.federal_state,
            postal_code=normalized_job.postal_code,
            start_date=normalized_job.start_date,
            application_deadline=normalized_job.application_deadline,
            salary=normalized_job.salary,
            employment_type=normalized_job.employment_type,
            description=normalized_job.description,
            requirements=normalized_job.requirements,
            language_requirements=normalized_job.language_requirements,
            skills=normalized_job.skills,
            education_requirements=normalized_job.education_requirements,
            contact_person=normalized_job.contact_person,
            contact_email=normalized_job.contact_email,
            application_url=normalized_job.application_url,
            dedup_key=dedup_key,
        )
        db.session.add(job)
        db.session.flush()
        created = True

    listing = None
    if normalized_job.external_id is not None:
        listing = JobListing.query.filter_by(
            source=normalized_job.source, external_id=normalized_job.external_id
        ).first()

    if listing is None:
        listing = JobListing(
            job_id=job.id,
            source=normalized_job.source,
            external_id=normalized_job.external_id,
            source_url=normalized_job.source_url,
            raw_snapshot=normalized_job.raw,
            is_preferred=(normalized_job.source == "manual"),
        )
        db.session.add(listing)
    else:
        listing.source_url = normalized_job.source_url or listing.source_url
        listing.raw_snapshot = normalized_job.raw or listing.raw_snapshot
        listing.last_checked_at = utcnow()

    db.session.commit()
    return job, created


def merge_missing_fields(job, normalized_job):
    """Fills in canonical fields that are still empty using data from a newly
    seen duplicate listing, without overwriting anything already known.
    Public (not underscore-prefixed): also reused by
    app/jobs/ingest.py's enrich_job_detail() for the lazy detail-fetch-on-
    open path, not just find_or_create_canonical_job() above - the "fill
    only what's empty" behavior is exactly what a detail fetch enriching an
    already-created Job needs too."""
    fillable = [
        "federal_state", "postal_code", "start_date", "application_deadline", "salary",
        "description", "requirements", "language_requirements", "skills",
        "education_requirements", "contact_person", "contact_email", "application_url",
    ]
    for attr in fillable:
        if not getattr(job, attr, None):
            value = getattr(normalized_job, attr, None)
            if value:
                setattr(job, attr, value)
