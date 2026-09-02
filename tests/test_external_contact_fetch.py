"""Tests for the external-posting contact fallback (contact-display pass,
2026-09-02): app/jobs/ingest.py's should_attempt_external_contact_fetch()/
fill_contact_from_external_posting(). Investigation this session found a
real, common shape for Arbeitsagentur postings - the source's own listing
genuinely states no contact info at all anywhere (202 of 250 sampled jobs
with no contact_person/email had no contact text anywhere in their own
description either), with the real contact only reachable via the
employer's own linked external posting page. Real motivating case: a
Vetter Pharma-Fertigung Elektroniker/in posting whose Arbeitsagentur
description states no contact at all, but whose real external
ausbildung.de page names a real contact (Moritz Gehring) - see
DECISIONS.md.
"""
from app.ai.provider import AIProvider, AIResponse
from app.jobs.ingest import fill_contact_from_external_posting, should_attempt_external_contact_fetch
from app.jobs.manual_import import FetchFailed
from app.models.job import Job, JobListing
from app.models.user import User


class FakeProvider(AIProvider):
    provider_name = "fake"

    def __init__(self, text=None):
        self._text = text

    def complete(self, system_prompt, user_prompt, max_tokens=1024):
        return AIResponse(text=self._text, model="fake-model", provider=self.provider_name, input_tokens=5, output_tokens=5)


def make_aa_job(db, **overrides):
    kwargs = dict(
        dedup_key="external-contact-test",
        employment_type="Ausbildung",
        title="Elektroniker",
        description="Wir bieten dir eine tolle Ausbildung mit persönlicher Betreuung.",
        skills=[],  # extraction already ran and found nothing - eligible for the fallback
        application_url="https://www.ausbildung.de/unternehmen/vetter/stellen/elektroniker/",
    )
    kwargs.update(overrides)
    job = Job(**kwargs)
    db.session.add(job)
    db.session.commit()
    db.session.add(JobListing(job_id=job.id, source="arbeitsagentur", external_id="AA-EXT-1"))
    db.session.commit()
    return job


# --- should_attempt_external_contact_fetch() eligibility gate ---


def test_eligible_when_no_contact_extraction_ran_and_has_url(db, make_user):
    make_user(email="ext1@example.com")
    job = make_aa_job(db)
    assert should_attempt_external_contact_fetch(job) is True


def test_ineligible_when_contact_already_populated(db, make_user):
    make_user(email="ext2@example.com")
    job = make_aa_job(db, contact_person="Frau Weber")
    assert should_attempt_external_contact_fetch(job) is False


def test_ineligible_when_already_attempted(db, make_user):
    make_user(email="ext3@example.com")
    job = make_aa_job(db, contact_external_fetch_attempted=True)
    assert should_attempt_external_contact_fetch(job) is False


def test_ineligible_when_description_extraction_never_ran(db, make_user):
    # skills is None - extraction hasn't had its own shot yet; the
    # cheaper, more-trusted source should run first, not a simultaneous
    # second attempt.
    make_user(email="ext4@example.com")
    job = make_aa_job(db, skills=None)
    assert should_attempt_external_contact_fetch(job) is False


def test_ineligible_without_a_real_application_url(db, make_user):
    make_user(email="ext5@example.com")
    job = make_aa_job(db, application_url=None)
    assert should_attempt_external_contact_fetch(job) is False


def test_ineligible_for_non_arbeitsagentur_sources(db, make_user):
    make_user(email="ext6@example.com")
    job = Job(
        dedup_key="external-contact-manual-test", employment_type="Ausbildung", title="Elektroniker",
        skills=[], application_url="https://example.com/job",
    )
    db.session.add(job)
    db.session.commit()
    db.session.add(JobListing(job_id=job.id, source="manual", external_id=None))
    db.session.commit()
    assert should_attempt_external_contact_fetch(job) is False


# --- fill_contact_from_external_posting() ---


def test_fills_contact_from_real_grounded_extraction(app, db, make_user, monkeypatch):
    make_user(email="ext7@example.com")
    job = make_aa_job(db)
    user = User.query.first()

    fake_page_text = "Deine Kontaktperson\nMoritz Gehring\nElektrotechnischer Ausbilder\nE-Mail\nmoritz.gehring@vetter-pharma.com"
    monkeypatch.setattr(
        "app.jobs.manual_import.fetch_and_extract_text",
        lambda url: {"page_title": "Ausbildung Elektroniker | Vetter Pharma", "text": fake_page_text},
    )
    fake_json = (
        '{"title": null, "company_name": null, "location": null, "start_date": null, "salary": null, '
        '"contact_person": "Moritz Gehring", "contact_email": "moritz.gehring@vetter-pharma.com", '
        '"exclude_line_numbers": []}'
    )
    monkeypatch.setattr("app.ai.manual_import_extraction.get_provider", lambda: FakeProvider(text=fake_json))

    changed = fill_contact_from_external_posting(job.id, user.id)

    assert changed is True
    db.session.refresh(job)
    assert job.contact_person == "Moritz Gehring"
    assert job.contact_email == "moritz.gehring@vetter-pharma.com"
    assert job.contact_external_fetch_attempted is True


def test_never_overwrites_other_fields(app, db, make_user, monkeypatch):
    """Only contact_person/contact_email are ever taken from the external
    extraction - title/company/description are already correctly
    populated by Arbeitsagentur's own API and must never be silently
    overwritten by a second, less-trusted source."""
    make_user(email="ext8@example.com")
    job = make_aa_job(db, title="Original AA Title", description="Original AA description text.")
    user = User.query.first()

    monkeypatch.setattr(
        "app.jobs.manual_import.fetch_and_extract_text",
        lambda url: {"page_title": "A Totally Different Title", "text": "Ansprechpartner: Max Mustermann\nmax@example.de"},
    )
    fake_json = (
        '{"title": "A Totally Different Title", "company_name": "Some Other Company", "location": null, '
        '"start_date": null, "salary": null, "contact_person": "Max Mustermann", '
        '"contact_email": "max@example.de", "exclude_line_numbers": []}'
    )
    monkeypatch.setattr("app.ai.manual_import_extraction.get_provider", lambda: FakeProvider(text=fake_json))

    fill_contact_from_external_posting(job.id, user.id)

    db.session.refresh(job)
    assert job.title == "Original AA Title"
    assert job.description == "Original AA description text."
    assert job.contact_person == "Max Mustermann"


def test_never_overwrites_existing_manual_contact_fields(app, db, make_user, monkeypatch):
    """A concurrent write - e.g. extract_job_requirements()'s own
    background task landing between this function's eligibility check and
    its own commit - must never be clobbered. (Note: a job with only one
    of the two fields already set is never eligible for this fetch at all
    per should_attempt_external_contact_fetch()'s own gate, so the only
    real way this merge-safety code path is reachable is a genuine race,
    not a pre-existing partial value - simulated here via the fetch
    mock's side effect.)"""
    make_user(email="ext9@example.com")
    job = make_aa_job(db)
    user = User.query.first()

    def _fetch(url):
        job.contact_email = "already-set@example.de"
        db.session.commit()
        return {"page_title": "Title", "text": "Ansprechpartner: Max Mustermann\nnew@example.de"}

    monkeypatch.setattr("app.jobs.manual_import.fetch_and_extract_text", _fetch)
    fake_json = (
        '{"title": null, "company_name": null, "location": null, "start_date": null, "salary": null, '
        '"contact_person": "Max Mustermann", "contact_email": "new@example.de", "exclude_line_numbers": []}'
    )
    monkeypatch.setattr("app.ai.manual_import_extraction.get_provider", lambda: FakeProvider(text=fake_json))

    fill_contact_from_external_posting(job.id, user.id)

    db.session.refresh(job)
    assert job.contact_person == "Max Mustermann"  # was blank, correctly filled
    assert job.contact_email == "already-set@example.de"  # concurrently set, never overwritten


def test_fetch_failure_is_a_genuine_dead_end_not_retried(app, db, make_user, monkeypatch):
    """Bot protection or any fetch failure marks attempted and stops -
    never bypassed, never retried automatically."""
    make_user(email="ext10@example.com")
    job = make_aa_job(db)
    user = User.query.first()

    def _raise(url):
        raise FetchFailed("That site declined the request.")

    monkeypatch.setattr("app.jobs.manual_import.fetch_and_extract_text", _raise)

    changed = fill_contact_from_external_posting(job.id, user.id)

    assert changed is False
    db.session.refresh(job)
    assert job.contact_person is None
    assert job.contact_email is None
    assert job.contact_external_fetch_attempted is True

    # Re-checking eligibility now correctly refuses a second attempt.
    assert should_attempt_external_contact_fetch(job) is False


def test_ungrounded_contact_from_external_page_is_dropped(app, db, make_user, monkeypatch):
    """The external extraction is subject to the exact same grounding
    discipline as manual import - a name the fetched page never actually
    states must never be trusted, even from this second-source fallback."""
    make_user(email="ext11@example.com")
    job = make_aa_job(db)
    user = User.query.first()

    monkeypatch.setattr(
        "app.jobs.manual_import.fetch_and_extract_text",
        lambda url: {"page_title": "Title", "text": "This page genuinely never names a contact person."},
    )
    fabricated_json = (
        '{"title": null, "company_name": null, "location": null, "start_date": null, "salary": null, '
        '"contact_person": "Someone Invented", "contact_email": "fake@nowhere.example", "exclude_line_numbers": []}'
    )
    monkeypatch.setattr("app.ai.manual_import_extraction.get_provider", lambda: FakeProvider(text=fabricated_json))

    changed = fill_contact_from_external_posting(job.id, user.id)

    assert changed is False
    db.session.refresh(job)
    assert job.contact_person is None
    assert job.contact_email is None
    assert job.contact_external_fetch_attempted is True
