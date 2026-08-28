"""Tests for the CV profile statement feature (app/ai/cv_profile_statement.py,
CvProfileStatement model, applications.generate_cv_profile_statement_route)
and the read-only JobMatch.strengths surfacing alongside it - option A from
the CV-tailoring investigation.
"""
import time

from app.ai import cv_profile_statement as cv_profile_statement_module
from app.ai.facts import format_candidate_facts, format_job_facts
from app.ai.prompts.cv_profile_statement import build_generation_prompt
from app.ai.provider import AIProvider, AIResponse
from app.jobs import matching as matching_module
from app.models import Application, Job, Skill
from app.models.ai import CvProfileStatement
from app.applications import pdf_package as pdf_package_module
from tests.conftest import login


class FakeProvider(AIProvider):
    provider_name = "fake"

    def __init__(self, text):
        self._text = text
        self.calls = 0

    def complete(self, system_prompt, user_prompt, max_tokens=1024):
        self.calls += 1
        return AIResponse(text=self._text, model="fake-model", provider=self.provider_name, input_tokens=8, output_tokens=8)


class SequencedFakeProvider(AIProvider):
    """Returns each response in order on successive .complete() calls -
    needed to test the real generate-then-validate two-pass flow, where
    the generation call and the validation call must be able to return
    different text."""

    provider_name = "fake"

    def __init__(self, texts):
        self._texts = list(texts)
        self.calls = 0

    def complete(self, system_prompt, user_prompt, max_tokens=1024):
        text = self._texts[self.calls]
        self.calls += 1
        return AIResponse(text=text, model="fake-model", provider=self.provider_name, input_tokens=8, output_tokens=8)


def make_job(db, **overrides):
    kwargs = dict(dedup_key="cvps-test", employment_type="Ausbildung", title="Elektroniker")
    kwargs.update(overrides)
    job = Job(**kwargs)
    db.session.add(job)
    db.session.commit()
    return job


def start_application(client, db, job):
    resp = client.post(f"/applications/start/{job.id}", follow_redirects=True)
    application = Application.query.filter_by(job_id=job.id).first()
    return resp, application


def make_application(db, user, job):
    application = Application(user_id=user.id, job_id=job.id)
    db.session.add(application)
    db.session.commit()
    return application


# --- Grounding -----------------------------------------------------------


def test_generation_prompt_includes_real_candidate_and_job_facts(app, db, make_user):
    user = make_user(email="cvps1@example.com")
    user.profile.first_name = "Ilias"
    user.profile.last_name = "Jabbour"
    db.session.add(Skill(profile_id=user.profile.id, name="PLC-Programmierung"))
    db.session.commit()
    job = make_job(db, title="Elektroniker für Automatisierungstechnik")

    _, prompt = build_generation_prompt(format_candidate_facts(user.profile), format_job_facts(job), "de")

    assert "Ilias Jabbour" in prompt
    assert "PLC-Programmierung" in prompt
    assert "Elektroniker für Automatisierungstechnik" in prompt


# --- Mock mode -------------------------------------------------------------


def test_generate_cv_profile_statement_mock_mode_is_honest(client, db, make_user):
    make_user(email="cvps2@example.com", password="Password123!")
    login(client, "cvps2@example.com", "Password123!")
    job = make_job(db)
    _, application = start_application(client, db, job)

    resp = client.post(f"/applications/{application.id}/cv-profile-statement", follow_redirects=True)
    assert resp.status_code == 200
    assert b"isn&#39;t available" in resp.data or b"isn't available" in resp.data

    statement = CvProfileStatement.query.filter_by(application_id=application.id).first()
    assert statement is not None
    assert statement.provider == "mock"


def test_regenerates_when_ui_locale_changes(client, db, make_user, monkeypatch):
    """i18n pass 3: the CV profile statement now follows the UI language
    (it used to hardcode German unconditionally - see DECISIONS.md), so a
    statement cached under one locale must not be served as-is once the
    session's locale differs, same as match narrative's own locale-cache
    test in test_match_routes.py."""
    make_user(email="cvps-locale@example.com", password="Password123!")
    login(client, "cvps-locale@example.com", "Password123!")
    job = make_job(db)
    _, application = start_application(client, db, job)

    fake = FakeProvider("A grounded, honest CV summary.")
    monkeypatch.setattr(cv_profile_statement_module, "get_provider", lambda: fake)

    client.post("/set-locale", data={"lang": "en", "next": f"/applications/{application.id}"})
    resp = client.post(f"/applications/{application.id}/cv-profile-statement", follow_redirects=True)
    assert resp.status_code == 200
    # generate + validate = 2 calls for the first generation
    assert fake.calls == 2

    statement = CvProfileStatement.query.filter_by(application_id=application.id).first()
    assert statement.generated_locale == "en"

    # Same locale again: cached, no new AI calls at all.
    resp = client.post(f"/applications/{application.id}/cv-profile-statement", follow_redirects=True)
    assert resp.status_code == 200
    assert fake.calls == 2

    # Switch locale: must regenerate (another generate+validate pair),
    # even though nothing about the profile or job changed.
    client.post("/set-locale", data={"lang": "de", "next": f"/applications/{application.id}"})
    resp = client.post(f"/applications/{application.id}/cv-profile-statement", follow_redirects=True)
    assert resp.status_code == 200
    assert fake.calls == 4

    db.session.refresh(statement)
    assert statement.generated_locale == "de"


def test_generate_button_visible_before_any_statement_exists(client, db, make_user):
    make_user(email="cvps3@example.com", password="Password123!")
    login(client, "cvps3@example.com", "Password123!")
    job = make_job(db)
    _, application = start_application(client, db, job)

    resp = client.get(f"/applications/{application.id}")
    assert b"Generate CV profile statement" in resp.data


# --- Real provider path: generation + caching -------------------------------


def test_generate_cv_profile_statement_uses_real_provider_and_caches(app, db, make_user, monkeypatch):
    user = make_user(email="cvps4@example.com")
    job = make_job(db)
    application = make_application(db, user, job)

    fake = FakeProvider("Motivierter Kandidat mit Interesse an Elektrotechnik.")
    monkeypatch.setattr(cv_profile_statement_module, "get_provider", lambda: fake)
    result1 = cv_profile_statement_module.generate_cv_profile_statement(user, application)
    assert "Motivierter Kandidat" in result1.statement_text

    other = FakeProvider("A completely different statement.")
    monkeypatch.setattr(cv_profile_statement_module, "get_provider", lambda: other)
    result2 = cv_profile_statement_module.generate_cv_profile_statement(user, application)
    assert "Motivierter Kandidat" in result2.statement_text  # cached, not regenerated
    assert other.calls == 0

    assert CvProfileStatement.query.filter_by(application_id=application.id).count() == 1


def test_cv_profile_statement_is_per_application(app, db, make_user, monkeypatch):
    user = make_user(email="cvps5@example.com")
    job1 = make_job(db, dedup_key="cvps-test-1")
    job2 = make_job(db, dedup_key="cvps-test-2")
    app1 = make_application(db, user, job1)
    app2 = make_application(db, user, job2)

    monkeypatch.setattr(cv_profile_statement_module, "get_provider", lambda: FakeProvider("Statement for job 1."))
    cv_profile_statement_module.generate_cv_profile_statement(user, app1)

    assert cv_profile_statement_module.get_cv_profile_statement(app2) is None


# --- Staleness on profile edit ----------------------------------------------


def test_staleness_recompute_on_profile_edit(app, db, make_user, monkeypatch):
    user = make_user(email="cvps6@example.com")
    job = make_job(db)
    application = make_application(db, user, job)

    monkeypatch.setattr(cv_profile_statement_module, "get_provider", lambda: FakeProvider("Original statement."))
    first = cv_profile_statement_module.generate_cv_profile_statement(user, application)
    assert "Original statement." in first.statement_text
    first_snapshot = first.profile_updated_at_snapshot

    time.sleep(0.01)  # onupdate=utcnow needs a real, later timestamp to register as changed
    user.profile.city = "Berlin"
    db.session.commit()

    monkeypatch.setattr(
        cv_profile_statement_module, "get_provider", lambda: FakeProvider("Updated statement after profile edit.")
    )
    second = cv_profile_statement_module.generate_cv_profile_statement(user, application)

    assert "Updated statement after profile edit." in second.statement_text
    assert second.profile_updated_at_snapshot != first_snapshot
    assert CvProfileStatement.query.filter_by(application_id=application.id).count() == 1


# --- Fabrication guard (validation pass) ------------------------------------


def test_fabricated_response_gets_corrected_by_validation_pass(app, db, make_user, monkeypatch):
    """Same guard cover letter generation already relies on
    (app/ai/cover_letter.py's validate_cover_letter): a second AI pass
    checks the generated text against the real facts and can replace it -
    not just a system-prompt instruction alone."""
    user = make_user(email="cvps7@example.com")
    job = make_job(db, title="Elektroniker")

    fabricated = "Bewirbt sich mit einem Meistertitel und 10 Jahren Erfahrung als Elektroniker."
    corrected = "CORRECTED:\nMotivierter Kandidat mit Interesse an der Ausbildung als Elektroniker."
    sequenced = SequencedFakeProvider([fabricated, corrected])
    monkeypatch.setattr(cv_profile_statement_module, "get_provider", lambda: sequenced)

    result = cv_profile_statement_module.generate_cv_profile_statement(user, make_application(db, user, job))

    assert sequenced.calls == 2  # both the generation and the validation pass ran
    assert "Meistertitel" not in result.statement_text
    assert "Motivierter Kandidat mit Interesse an der Ausbildung als Elektroniker." in result.statement_text


def test_valid_response_passes_through_unchanged(app, db, make_user, monkeypatch):
    user = make_user(email="cvps8@example.com")
    job = make_job(db, title="Mechatroniker")

    generation_text = "Interessiert an der Ausbildung als Mechatroniker."
    validation_text = "VALID: no issues found."
    sequenced = SequencedFakeProvider([generation_text, validation_text])
    monkeypatch.setattr(cv_profile_statement_module, "get_provider", lambda: sequenced)

    result = cv_profile_statement_module.generate_cv_profile_statement(user, make_application(db, user, job))

    assert sequenced.calls == 2
    assert result.statement_text == generation_text


# --- Strengths surfacing: read-only, zero new AI calls ----------------------


def test_strengths_surfacing_renders_real_matched_skills(client, db, make_user):
    make_user(email="cvps9@example.com", password="Password123!")
    login(client, "cvps9@example.com", "Password123!")
    from app.models.user import User

    user = User.query.filter_by(email="cvps9@example.com").first()
    db.session.add(Skill(profile_id=user.profile.id, name="Löten"))
    db.session.commit()

    job = make_job(db, title="Elektroniker", skills=["Löten"])
    _, application = start_application(client, db, job)

    resp = client.get(f"/applications/{application.id}")
    assert resp.status_code == 200
    assert b"Skills this posting values that you already have" in resp.data
    assert b"L\xc3\xb6ten" in resp.data  # "Löten", UTF-8 encoded


def test_strengths_surfacing_makes_zero_new_ai_calls(client, db, make_user, monkeypatch):
    make_user(email="cvps10@example.com", password="Password123!")
    login(client, "cvps10@example.com", "Password123!")
    job = make_job(db)
    _, application = start_application(client, db, job)

    def _explode():
        raise AssertionError("get_provider() should never be called just to render the detail page")

    monkeypatch.setattr(matching_module, "get_provider", _explode)

    resp = client.get(f"/applications/{application.id}")
    assert resp.status_code == 200  # would have raised via _explode() if get_or_compute_match touched AI


# --- Untouched surfaces ------------------------------------------------------


def test_pdf_package_module_untouched_by_generation(app, db, make_user, monkeypatch):
    user = make_user(email="cvps11@example.com")
    job = make_job(db)
    application = make_application(db, user, job)

    def _explode(*args, **kwargs):
        raise AssertionError("build_application_pdf should never be called by CV profile statement generation")

    monkeypatch.setattr(pdf_package_module, "build_application_pdf", _explode)
    monkeypatch.setattr(cv_profile_statement_module, "get_provider", lambda: FakeProvider("Statement text."))

    cv_profile_statement_module.generate_cv_profile_statement(user, application)  # would raise if it touched pdf_package


def test_uploaded_cv_document_untouched_by_generation(app, db, make_user, monkeypatch):
    from app.models import Document

    user = make_user(email="cvps12@example.com")
    job = make_job(db)
    application = make_application(db, user, job)

    cv_doc = Document(
        user_id=user.id, doc_type="cv", original_filename="cv.pdf", stored_filename="stored-cv.pdf",
        storage_path="uploads/stored-cv.pdf", mime_type="application/pdf", file_size=1234,
    )
    db.session.add(cv_doc)
    db.session.commit()
    before = {c.name: getattr(cv_doc, c.name) for c in Document.__table__.columns}

    monkeypatch.setattr(cv_profile_statement_module, "get_provider", lambda: FakeProvider("Statement text."))
    cv_profile_statement_module.generate_cv_profile_statement(user, application)

    db.session.refresh(cv_doc)
    after = {c.name: getattr(cv_doc, c.name) for c in Document.__table__.columns}
    assert before == after
