from app.ai.cover_letter import render_template_cover_letter, generate_cover_letter, validate_cover_letter
from app.ai.salutation import build_salutation
from app.models import Skill, Education, Job


def make_job(db, **overrides):
    kwargs = dict(dedup_key="cl-test", employment_type="Ausbildung", title="Elektroniker")
    kwargs.update(overrides)
    job = Job(**kwargs)
    db.session.add(job)
    db.session.commit()
    return job


def test_salutation_uses_stored_title_when_present():
    assert build_salutation("Frau Müller") == "Sehr geehrte Frau Müller"
    assert build_salutation("Herr Schmidt") == "Sehr geehrter Herr Schmidt"


def test_salutation_uses_genuine_neutral_opener_when_no_title():
    # Contact-info follow-up pass (2026-08-30): a title-less name is a
    # real, correctly-extracted result (the extraction prompts explicitly
    # forbid adding a title the source doesn't state), not a rarity - it
    # must not collapse to the fully generic fallback, and must never
    # guess a "Frau"/"Herr" title from the name either.
    assert build_salutation("Alex Müller") == "Guten Tag Alex Müller"
    assert build_salutation("Julia Weber") == "Guten Tag Julia Weber"


def test_salutation_falls_back_only_when_no_name_at_all():
    assert build_salutation(None) == "Sehr geehrte Damen und Herren"
    assert build_salutation("") == "Sehr geehrte Damen und Herren"
    assert build_salutation("   ") == "Sehr geehrte Damen und Herren"


def test_template_cover_letter_includes_only_real_profile_facts(app, db, make_user):
    user = make_user(email="letter1@example.com")
    user.profile.first_name = "Ilias"
    user.profile.last_name = "Jabbour"
    db.session.add(Skill(profile_id=user.profile.id, name="PLC"))
    db.session.add(Education(profile_id=user.profile.id, institution="TU Berlin", degree="Elektrotechnik", field="Automatisierung"))
    db.session.commit()

    job = make_job(db, title="Elektroniker für Automatisierungstechnik")
    # company_name is a property derived from Company; set via a real Company instead
    from app.models import Company

    company = Company(name="Beispiel GmbH", normalized_name="beispiel")
    db.session.add(company)
    db.session.commit()
    job.company_id = company.id
    db.session.commit()

    text = render_template_cover_letter(user.profile, job)

    assert "Ilias Jabbour" in text
    assert "Elektroniker für Automatisierungstechnik" in text
    assert "Beispiel GmbH" in text
    assert "PLC" in text
    assert "Automatisierung" in text
    assert "Sehr geehrte Damen und Herren" in text  # no contact person on the job


def test_generate_cover_letter_uses_template_in_mock_mode(app, db, make_user):
    user = make_user(email="letter2@example.com")
    job = make_job(db, title="Mechatroniker")

    text, source, provider = generate_cover_letter(user, job)
    assert source == "template"
    assert provider is None
    assert "Mechatroniker" in text


def test_deterministic_validation_flags_missing_facts(app, db, make_user):
    user = make_user(email="letter3@example.com")
    user.profile.first_name = "Test"
    user.profile.last_name = "Candidate"
    db.session.commit()
    job = make_job(db, title="Fachinformatiker")

    ok, notes, corrected = validate_cover_letter(user, job, "A letter that mentions nothing relevant.", "template")
    assert ok is False
    assert "job title" in notes
    assert corrected is None


def test_deterministic_validation_passes_when_facts_present(app, db, make_user):
    user = make_user(email="letter4@example.com")
    user.profile.first_name = "Test"
    user.profile.last_name = "Candidate"
    db.session.commit()
    job = make_job(db, title="Fachinformatiker")
    from app.models import Company

    company = Company(name="Firma AG", normalized_name="firma")
    db.session.add(company)
    db.session.commit()
    job.company_id = company.id
    db.session.commit()

    letter = "Bewerbung als Fachinformatiker bei Firma AG.\n\nMfG\nTest Candidate"
    ok, notes, corrected = validate_cover_letter(user, job, letter, "template")
    assert ok is True
