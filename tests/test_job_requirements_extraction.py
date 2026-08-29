"""Tests for app/ai/job_requirements_extraction.py (job-description
extraction pass) - the AI-assisted skills/language extraction chained off
app/jobs/ingest.py's enrich_job_detail(). Uses the same FakeProvider(
AIProvider) pattern as tests/test_reply_ai.py rather than mocking
.complete() directly - a real, minimal AIProvider implementation.
"""
from datetime import timedelta

import app.ai.job_requirements_extraction as extraction_module
from app.ai.job_requirements_extraction import (
    MAX_EXTRACTION_ATTEMPTS,
    RETRY_BACKOFF,
    extract_job_requirements,
    should_retry_requirements_extraction,
)
from app.ai.provider import AIProvider, AIProviderError, AIResponse
from app.models.ai import JobMatch
from app.models.job import Job
from app.models.user import utcnow

PFIZER_DESCRIPTION = """Möchtest du in einem internationalen Unternehmen arbeiten?

Das erwartet Dich:

 - Umgang mit der Steuer- und Regelungstechnik wie Pneumatik und SPS-Programmierung sowie Robotertechnik

Das bringst Du mit:

 - Ein guter Schulabschluss – eine mittlere Reife, Fachhochschulreife oder Abitur
 - Technisches Verständnis und analytisches Denkvermögen
 - Sehr gute Deutschkenntnisse in Wort und Schrift

Das bieten wir Dir:

 - Sammle wertvolle Praxiserfahrungen
"""

VERGOELST_DESCRIPTION = """Du hast Spaß am direkten Kundenkontakt?

Was solltest du mitbringen?

• Lust auf direkten Kundenkontakt
• Spaß an Wirtschaftsfächern und Deutsch

Bewerbungsart: Ausschließlich online über Continental.
"""

# Contact info deliberately lives outside the requirements section (like
# real postings) - proves contact extraction is grounded against its own
# separately isolated contact/application section, not incorrectly
# excluded the way curriculum content is kept out of skills.
PFIZER_WITH_CONTACT = PFIZER_DESCRIPTION + """
Interessiert?

Dann bewirb dich direkt per E-Mail an bewerbung@pfizer-beispiel.de. Deine Ansprechpartnerin ist Frau Meier.
"""

PFIZER_WITH_NON_EMAIL_CONTACT_TEXT = PFIZER_DESCRIPTION + """
Interessiert?

Wende dich an unser Team unter office-berlin (interner Kürzel, keine Email).
"""


class FakeProvider(AIProvider):
    provider_name = "fake"

    def __init__(self, text=None, raise_error=None):
        self._text = text
        self._raise_error = raise_error
        self.last_prompt = None

    def complete(self, system_prompt, user_prompt, max_tokens=1024):
        self.last_prompt = user_prompt
        if self._raise_error:
            raise self._raise_error
        return AIResponse(text=self._text, model="fake-model", provider=self.provider_name, input_tokens=5, output_tokens=5)


def make_job(db, description, source="arbeitsagentur", skills=None):
    job = Job(
        title="Ausbildung Mechatroniker (m/w/d)",
        dedup_key=f"extract-test-{description[:20]}",
        description=description,
        skills=skills,
    )
    db.session.add(job)
    db.session.commit()
    return job


def test_valid_extraction_populates_skills(app, db, make_user, monkeypatch):
    user = make_user(email="ex1@example.com")
    job = make_job(db, PFIZER_DESCRIPTION)

    fake = FakeProvider(text='{"skills": ["Deutschkenntnisse"], "languages": ["Deutsch"]}')
    monkeypatch.setattr(extraction_module, "get_provider", lambda: fake)

    result = extract_job_requirements(job.id, user.id)

    db.session.refresh(job)
    assert job.skills == ["Deutschkenntnisse"]
    assert "1 skill" in result


def test_curriculum_skill_not_grounded_in_isolated_section_is_dropped(app, db, make_user, monkeypatch):
    # The AI (faked here) misbehaves and reports "SPS-Programmierung" -
    # real text, but only present in the *curriculum* section, which the
    # deterministic isolator excludes before the AI ever sees it. Since
    # grounding is checked against the text the AI was actually shown
    # (the isolated section), not the full description, this must be
    # rejected even though the phrase is genuinely real text somewhere in
    # the job.
    user = make_user(email="ex2@example.com")
    job = make_job(db, PFIZER_DESCRIPTION)

    fake = FakeProvider(text='{"skills": ["SPS-Programmierung", "Deutschkenntnisse"], "languages": []}')
    monkeypatch.setattr(extraction_module, "get_provider", lambda: fake)

    extract_job_requirements(job.id, user.id)

    db.session.refresh(job)
    assert "SPS-Programmierung" not in job.skills
    assert "Deutschkenntnisse" in job.skills
    # Confirms the AI was actually only shown the isolated section, not
    # the full description with the curriculum text in it.
    assert "SPS-Programmierung" not in fake.last_prompt


def test_school_subject_deutsch_not_extracted_as_language(app, db, make_user, monkeypatch):
    user = make_user(email="ex3@example.com")
    job = make_job(db, VERGOELST_DESCRIPTION)

    # A well-behaved AI following the prompt's rules would not report
    # "Deutsch" here at all (school-subject mention, not a language
    # requirement) - this test locks in that even if it did, the fixture
    # itself proves nothing is fabricated beyond what's grounded; the real
    # protection against this specific trap is prompt discipline, which
    # can't be unit-tested directly, so this test instead confirms the
    # pipeline doesn't ADD any invented signal on top of a benign response.
    fake = FakeProvider(text='{"skills": [], "languages": []}')
    monkeypatch.setattr(extraction_module, "get_provider", lambda: fake)

    extract_job_requirements(job.id, user.id)

    db.session.refresh(job)
    assert job.skills == []


def test_invented_skill_absent_from_source_text_is_rejected(app, db, make_user, monkeypatch):
    user = make_user(email="ex4@example.com")
    job = make_job(db, PFIZER_DESCRIPTION)

    fake = FakeProvider(text='{"skills": ["Deutschkenntnisse", "Python", "AWS"], "languages": []}')
    monkeypatch.setattr(extraction_module, "get_provider", lambda: fake)

    extract_job_requirements(job.id, user.id)

    db.session.refresh(job)
    assert job.skills == ["Deutschkenntnisse"]
    assert "Python" not in job.skills
    assert "AWS" not in job.skills


def test_malformed_json_leaves_fields_untouched(app, db, make_user, monkeypatch):
    user = make_user(email="ex5@example.com")
    job = make_job(db, PFIZER_DESCRIPTION)

    fake = FakeProvider(text="not json at all, just prose")
    monkeypatch.setattr(extraction_module, "get_provider", lambda: fake)

    result = extract_job_requirements(job.id, user.id)

    db.session.refresh(job)
    assert job.skills is None
    assert "malformed" in result


def test_wrong_shape_json_leaves_fields_untouched(app, db, make_user, monkeypatch):
    user = make_user(email="ex6@example.com")
    job = make_job(db, PFIZER_DESCRIPTION)

    fake = FakeProvider(text='{"skills": "not a list", "languages": []}')
    monkeypatch.setattr(extraction_module, "get_provider", lambda: fake)

    extract_job_requirements(job.id, user.id)

    db.session.refresh(job)
    assert job.skills is None


def test_missing_expected_keys_leaves_fields_untouched(app, db, make_user, monkeypatch):
    user = make_user(email="ex7@example.com")
    job = make_job(db, PFIZER_DESCRIPTION)

    fake = FakeProvider(text='{"result": "some other shape entirely"}')
    monkeypatch.setattr(extraction_module, "get_provider", lambda: fake)

    extract_job_requirements(job.id, user.id)

    db.session.refresh(job)
    assert job.skills is None


def test_no_requirements_section_found_falls_back_to_full_description(app, db, make_user, monkeypatch):
    user = make_user(email="ex8@example.com")
    job = make_job(db, "Kurze Stellenbeschreibung ohne erkennbaren Anforderungsabschnitt.")

    fake = FakeProvider(text='{"skills": [], "languages": []}')
    monkeypatch.setattr(extraction_module, "get_provider", lambda: fake)

    extract_job_requirements(job.id, user.id)

    assert "Kurze Stellenbeschreibung" in fake.last_prompt


def test_stub_or_empty_description_produces_no_extraction_and_completes_successfully(app, db, make_user):
    user = make_user(email="ex9@example.com")
    job = Job(title="Elektroniker", dedup_key="extract-empty", description=None)
    db.session.add(job)
    db.session.commit()

    result = extract_job_requirements(job.id, user.id)

    assert job.skills is None
    assert "No description" in result


def test_mock_provider_leaves_fields_untouched(app, db, make_user):
    user = make_user(email="ex10@example.com")
    job = make_job(db, PFIZER_WITH_CONTACT)

    # TestingConfig forces AI_PROVIDER=mock regardless of any real .env -
    # get_provider() is deliberately NOT monkeypatched here, exercising
    # the real mock-mode branch.
    result = extract_job_requirements(job.id, user.id)

    db.session.refresh(job)
    assert job.skills is None
    assert job.contact_person is None
    assert job.contact_email is None
    assert "Mock mode" in result


def test_ai_provider_error_leaves_fields_untouched(app, db, make_user, monkeypatch):
    user = make_user(email="ex11@example.com")
    job = make_job(db, PFIZER_DESCRIPTION)

    fake = FakeProvider(raise_error=AIProviderError("provider unavailable"))
    monkeypatch.setattr(extraction_module, "get_provider", lambda: fake)

    result = extract_job_requirements(job.id, user.id)

    db.session.refresh(job)
    assert job.skills is None
    assert "failed" in result.lower()


def test_extraction_is_idempotent_does_not_recall_provider(app, db, make_user, monkeypatch):
    user = make_user(email="ex12@example.com")
    job = make_job(db, PFIZER_DESCRIPTION)

    call_count = {"n": 0}

    def fake_get_provider():
        call_count["n"] += 1
        return FakeProvider(text='{"skills": ["Deutschkenntnisse"], "languages": []}')

    monkeypatch.setattr(extraction_module, "get_provider", fake_get_provider)

    extract_job_requirements(job.id, user.id)
    extract_job_requirements(job.id, user.id)
    extract_job_requirements(job.id, user.id)

    assert call_count["n"] == 1


def test_successful_extraction_invalidates_cached_job_match(app, db, make_user, monkeypatch):
    from app.jobs.matching import get_or_compute_match

    user = make_user(email="ex13@example.com")
    job = make_job(db, PFIZER_DESCRIPTION)

    stale_match_id = get_or_compute_match(user, job).id
    assert "skills" in (JobMatch.query.filter_by(id=stale_match_id).first().skipped_categories or [])

    fake = FakeProvider(text='{"skills": ["Deutschkenntnisse"], "languages": []}')
    monkeypatch.setattr(extraction_module, "get_provider", lambda: fake)
    extract_job_requirements(job.id, user.id)

    assert JobMatch.query.filter_by(id=stale_match_id).first() is None


def test_failed_extraction_does_not_touch_existing_job_match(app, db, make_user, monkeypatch):
    from app.jobs.matching import get_or_compute_match

    user = make_user(email="ex14@example.com")
    job = make_job(db, PFIZER_DESCRIPTION)

    match_id = get_or_compute_match(user, job).id

    fake = FakeProvider(text="not valid json")
    monkeypatch.setattr(extraction_module, "get_provider", lambda: fake)
    extract_job_requirements(job.id, user.id)

    # A malformed/failed extraction must not corrupt or invalidate an
    # existing, still-accurate cached match.
    assert JobMatch.query.filter_by(id=match_id).first() is not None


# --- Contact-info extraction (contact-extraction pass) ----------------------


def test_response_without_contact_keys_is_not_malformed(app, db, make_user, monkeypatch):
    """contact_person/contact_email are optional keys - their absence must
    not make an otherwise-valid response malformed. This is what keeps
    every pre-existing fixture in this file (none of which include these
    keys) still passing unchanged."""
    user = make_user(email="ex15@example.com")
    job = make_job(db, PFIZER_DESCRIPTION)

    fake = FakeProvider(text='{"skills": ["Deutschkenntnisse"], "languages": []}')
    monkeypatch.setattr(extraction_module, "get_provider", lambda: fake)

    result = extract_job_requirements(job.id, user.id)

    db.session.refresh(job)
    assert job.skills == ["Deutschkenntnisse"]
    assert job.contact_person is None
    assert job.contact_email is None
    assert "malformed" not in result


def test_contact_person_and_email_extracted_and_grounded(app, db, make_user, monkeypatch):
    user = make_user(email="ex16@example.com")
    job = make_job(db, PFIZER_WITH_CONTACT)

    fake = FakeProvider(
        text='{"skills": ["Deutschkenntnisse"], "languages": [], '
        '"contact_person": "Frau Meier", "contact_email": "bewerbung@pfizer-beispiel.de"}'
    )
    monkeypatch.setattr(extraction_module, "get_provider", lambda: fake)

    result = extract_job_requirements(job.id, user.id)

    db.session.refresh(job)
    assert job.contact_person == "Frau Meier"
    assert job.contact_email == "bewerbung@pfizer-beispiel.de"
    assert "contact person" in result and "contact email" in result


def test_contact_info_outside_requirements_section_still_extracted(app, db, make_user, monkeypatch):
    """Contact details structurally live outside the isolated requirements
    section here (confirmed directly: extract_requirements_section() on
    this fixture does not include the email) - grounding contact fields
    against a separately isolated contact/application section, rather
    than the requirements one, is what makes this still work instead of
    being incorrectly excluded the way curriculum content is for skills."""
    from app.jobs.requirements_section import extract_requirements_section

    user = make_user(email="ex17@example.com")
    job = make_job(db, PFIZER_WITH_CONTACT)

    requirements_only, _ = extract_requirements_section(PFIZER_WITH_CONTACT)
    assert "bewerbung@pfizer-beispiel.de" not in requirements_only

    fake = FakeProvider(
        text='{"skills": [], "languages": [], '
        '"contact_person": null, "contact_email": "bewerbung@pfizer-beispiel.de"}'
    )
    monkeypatch.setattr(extraction_module, "get_provider", lambda: fake)

    extract_job_requirements(job.id, user.id)

    db.session.refresh(job)
    assert job.contact_email == "bewerbung@pfizer-beispiel.de"


def test_invented_contact_person_and_email_rejected(app, db, make_user, monkeypatch):
    user = make_user(email="ex18@example.com")
    job = make_job(db, PFIZER_WITH_CONTACT)

    fake = FakeProvider(
        text='{"skills": [], "languages": [], '
        '"contact_person": "Herr Schmidt", "contact_email": "fake@invented.example"}'
    )
    monkeypatch.setattr(extraction_module, "get_provider", lambda: fake)

    extract_job_requirements(job.id, user.id)

    db.session.refresh(job)
    assert job.contact_person is None
    assert job.contact_email is None


def test_malformed_email_shape_rejected_even_when_grounded(app, db, make_user, monkeypatch):
    # "office-berlin" genuinely appears in the source text (grounds), but
    # it isn't shaped like an email - the format check must reject it
    # independently of grounding succeeding.
    user = make_user(email="ex19@example.com")
    job = make_job(db, PFIZER_WITH_NON_EMAIL_CONTACT_TEXT)

    fake = FakeProvider(text='{"skills": [], "languages": [], "contact_person": null, "contact_email": "office-berlin"}')
    monkeypatch.setattr(extraction_module, "get_provider", lambda: fake)

    extract_job_requirements(job.id, user.id)

    db.session.refresh(job)
    assert job.contact_email is None


def test_existing_manual_contact_fields_never_overwritten(app, db, make_user, monkeypatch):
    user = make_user(email="ex20@example.com")
    job = make_job(db, PFIZER_WITH_CONTACT)
    job.contact_person = "Manually Entered Person"
    job.contact_email = "manual@example.com"
    db.session.commit()

    fake = FakeProvider(
        text='{"skills": [], "languages": [], '
        '"contact_person": "Frau Meier", "contact_email": "bewerbung@pfizer-beispiel.de"}'
    )
    monkeypatch.setattr(extraction_module, "get_provider", lambda: fake)

    extract_job_requirements(job.id, user.id)

    db.session.refresh(job)
    assert job.contact_person == "Manually Entered Person"
    assert job.contact_email == "manual@example.com"


def test_only_contact_person_prefilled_leaves_email_fillable(app, db, make_user, monkeypatch):
    # "fill only if empty" applies per-field, not all-or-nothing.
    user = make_user(email="ex21@example.com")
    job = make_job(db, PFIZER_WITH_CONTACT)
    job.contact_person = "Manually Entered Person"
    db.session.commit()

    fake = FakeProvider(
        text='{"skills": [], "languages": [], '
        '"contact_person": "Frau Meier", "contact_email": "bewerbung@pfizer-beispiel.de"}'
    )
    monkeypatch.setattr(extraction_module, "get_provider", lambda: fake)

    extract_job_requirements(job.id, user.id)

    db.session.refresh(job)
    assert job.contact_person == "Manually Entered Person"  # untouched
    assert job.contact_email == "bewerbung@pfizer-beispiel.de"  # filled


def test_no_contact_section_found_contact_fields_stay_none(app, db, make_user, monkeypatch):
    # PFIZER_DESCRIPTION has no application/contact section at all -
    # extract_contact_section() returns found=False, and the placeholder
    # text used in its place can't ground anything.
    user = make_user(email="ex22@example.com")
    job = make_job(db, PFIZER_DESCRIPTION)

    fake = FakeProvider(
        text='{"skills": ["Deutschkenntnisse"], "languages": [], '
        '"contact_person": "Frau Meier", "contact_email": "bewerbung@pfizer-beispiel.de"}'
    )
    monkeypatch.setattr(extraction_module, "get_provider", lambda: fake)

    extract_job_requirements(job.id, user.id)

    db.session.refresh(job)
    assert job.contact_person is None
    assert job.contact_email is None


# --- Extraction retry pass (2026-08-29): attempt-count / last-attempted-at tracking ---

def test_provider_error_records_attempt_and_timestamp(app, db, make_user, monkeypatch):
    user = make_user(email="ex23@example.com")
    job = make_job(db, PFIZER_DESCRIPTION)
    assert job.requirements_extraction_attempts == 0
    assert job.requirements_extraction_last_attempted_at is None

    fake = FakeProvider(raise_error=AIProviderError("provider unavailable"))
    monkeypatch.setattr(extraction_module, "get_provider", lambda: fake)

    before = utcnow()
    extract_job_requirements(job.id, user.id)

    db.session.refresh(job)
    assert job.skills is None
    assert job.requirements_extraction_attempts == 1
    assert job.requirements_extraction_last_attempted_at is not None
    assert job.requirements_extraction_last_attempted_at >= before


def test_malformed_response_records_attempt_and_timestamp(app, db, make_user, monkeypatch):
    user = make_user(email="ex24@example.com")
    job = make_job(db, PFIZER_DESCRIPTION)

    fake = FakeProvider(text="not json at all, just prose")
    monkeypatch.setattr(extraction_module, "get_provider", lambda: fake)

    extract_job_requirements(job.id, user.id)

    db.session.refresh(job)
    assert job.skills is None
    assert job.requirements_extraction_attempts == 1
    assert job.requirements_extraction_last_attempted_at is not None


def test_successful_extraction_does_not_touch_attempt_tracking(app, db, make_user, monkeypatch):
    # A prior failed attempt's count should be left alone once a later
    # retry actually succeeds - attempts is a "how many tries so far"
    # counter, not something success needs to reset or increment further.
    user = make_user(email="ex25@example.com")
    job = make_job(db, PFIZER_DESCRIPTION)
    job.requirements_extraction_attempts = 1
    job.requirements_extraction_last_attempted_at = utcnow() - RETRY_BACKOFF
    db.session.commit()

    fake = FakeProvider(text='{"skills": ["Deutschkenntnisse"], "languages": []}')
    monkeypatch.setattr(extraction_module, "get_provider", lambda: fake)

    extract_job_requirements(job.id, user.id)

    db.session.refresh(job)
    assert job.skills == ["Deutschkenntnisse"]
    assert job.requirements_extraction_attempts == 1


def test_extraction_refuses_once_attempt_cap_reached(app, db, make_user, monkeypatch):
    user = make_user(email="ex26@example.com")
    job = make_job(db, PFIZER_DESCRIPTION)
    job.requirements_extraction_attempts = MAX_EXTRACTION_ATTEMPTS
    job.requirements_extraction_last_attempted_at = utcnow() - RETRY_BACKOFF
    db.session.commit()

    calls = []
    fake = FakeProvider(text='{"skills": ["Deutschkenntnisse"], "languages": []}')
    monkeypatch.setattr(extraction_module, "get_provider", lambda: calls.append(1) or fake)

    result = extract_job_requirements(job.id, user.id)

    assert calls == []  # provider never even called - cap enforced before the call
    assert "exhausted" in result.lower()
    db.session.refresh(job)
    assert job.skills is None
    assert job.requirements_extraction_attempts == MAX_EXTRACTION_ATTEMPTS


def test_should_retry_false_for_never_attempted_job(db):
    # Triggering a *first* attempt outside the enrichment moment is
    # enrich_job_detail()'s concern, not this function's - see its
    # docstring in app/ai/job_requirements_extraction.py.
    job = make_job(db, PFIZER_DESCRIPTION)
    assert job.requirements_extraction_attempts == 0
    assert should_retry_requirements_extraction(job) is False


def test_should_retry_false_before_backoff_elapses(db):
    job = make_job(db, PFIZER_DESCRIPTION)
    job.requirements_extraction_attempts = 1
    job.requirements_extraction_last_attempted_at = utcnow()
    db.session.commit()
    assert should_retry_requirements_extraction(job) is False


def test_should_retry_true_after_backoff_elapses(db):
    job = make_job(db, PFIZER_DESCRIPTION)
    job.requirements_extraction_attempts = 1
    job.requirements_extraction_last_attempted_at = utcnow() - RETRY_BACKOFF - timedelta(minutes=1)
    db.session.commit()
    assert should_retry_requirements_extraction(job) is True


def test_should_retry_false_once_attempt_cap_reached(db):
    job = make_job(db, PFIZER_DESCRIPTION)
    job.requirements_extraction_attempts = MAX_EXTRACTION_ATTEMPTS
    job.requirements_extraction_last_attempted_at = utcnow() - RETRY_BACKOFF - timedelta(days=1)
    db.session.commit()
    assert should_retry_requirements_extraction(job) is False
    # "gave up permanently" must stay visibly distinct from "never tried".
    assert job.requirements_extraction_attempts != 0


def test_should_retry_false_once_succeeded(db):
    job = make_job(db, PFIZER_DESCRIPTION, skills=["Deutschkenntnisse"])
    job.requirements_extraction_attempts = 1
    job.requirements_extraction_last_attempted_at = utcnow() - RETRY_BACKOFF - timedelta(minutes=1)
    db.session.commit()
    assert should_retry_requirements_extraction(job) is False
