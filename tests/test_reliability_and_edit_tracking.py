"""Schema pass, 2026-08-26: reliability field + edit tracking on the AI-backed
models behind the Intelligence component (see DECISIONS.md's 2026-08-26
entries). Both are nullable-by-design, unwired-by-design for every surface
except the one (GmailMessage.classification_confidence) that already had a
real self-report mechanism before this pass. These tests assert the honest
default (None, not an invented value) and, where a real generator/cache path
already exists, that it doesn't accidentally start setting either field -
that would silently contradict the documented decision that these are
unpopulated for now.
"""
from app.ai import interview_prep, reply_ai
from app.ai.cv_profile_statement import generate_cv_profile_statement
from app.ai.provider import AIProvider, AIResponse
from app.companies.insights import generate_company_insight
from app.jobs.matching import generate_improvement_tips, generate_narrative
from app.ai.profile_coaching import generate_profile_coaching
from app.extensions import db as _db
from app.models import Application, Company, Job
from app.models.ai import CvProfileStatement, InterviewPrep, JobMatch
from app.models.application import GeneratedDocument, GeneratedEmail
from app.models.integration import GmailMessage
from app.models.user import utcnow


class FakeProvider(AIProvider):
    provider_name = "fake"

    def __init__(self, text):
        self._text = text

    def complete(self, system_prompt, user_prompt, max_tokens=1024):
        return AIResponse(text=self._text, model="fake-model", provider=self.provider_name, input_tokens=5, output_tokens=5)


def make_job(db, **overrides):
    kwargs = dict(dedup_key="reliability-test", employment_type="Ausbildung", title="Elektroniker")
    kwargs.update(overrides)
    job = Job(**kwargs)
    db.session.add(job)
    db.session.commit()
    return job


# --- Reliability: defaults and non-population -----------------------------

def test_job_match_reliability_columns_default_null(app, db, make_user, monkeypatch):
    user = make_user(email="rel1@example.com")
    job = make_job(db, skills=["PLC"])
    match = JobMatch(user_id=user.id, job_id=job.id)
    db.session.add(match)
    db.session.commit()
    assert match.narrative_reliability is None
    assert match.improvement_tips_reliability is None

    monkeypatch.setattr("app.jobs.matching.get_provider", lambda: FakeProvider("Great fit."))
    generate_narrative(user, job, match)
    generate_improvement_tips(user, job, match)

    # Neither generator sources a reliability value today - see
    # DECISIONS.md. They must not silently start inventing one.
    assert match.narrative_reliability is None
    assert match.improvement_tips_reliability is None


def test_company_insight_reliability_defaults_null_in_mock_mode(app, db, make_user):
    user = make_user(email="rel2@example.com")
    company = Company(name="Beispiel GmbH", normalized_name="beispiel")
    db.session.add(company)
    db.session.commit()

    insight = generate_company_insight(user, company, jobs=[])
    assert insight.reliability is None


def test_profile_coaching_reliability_defaults_null_in_mock_mode(app, db, make_user):
    user = make_user(email="rel3@example.com")
    coaching = generate_profile_coaching(user)
    assert coaching.reliability is None


def test_generated_document_and_email_reliability_default_null(app, db, make_user):
    """generate_cover_letter()/generate_email() (app/ai/cover_letter.py,
    app/ai/email_gen.py) return plain (text, source, provider) tuples - the
    reliability column lives on the persisted row the route builds from
    that tuple, so the relevant assertion is the column's own default."""
    user = make_user(email="rel4@example.com")
    job = make_job(db)
    application = Application(user_id=user.id, job_id=job.id)
    db.session.add(application)
    db.session.commit()

    letter = GeneratedDocument(application_id=application.id, content="...", source="template")
    email = GeneratedEmail(application_id=application.id, subject="s", body="b", source="template")
    db.session.add_all([letter, email])
    db.session.commit()

    assert letter.reliability is None
    assert email.reliability is None


def test_reply_classification_confidence_unaffected_by_new_column(app, db, make_user, monkeypatch):
    """classification_confidence is the one surface with a real self-report
    mechanism already - confirms adding reply_suggestion_reliability next to
    it on the same table didn't disturb that existing behavior."""
    user = make_user(email="rel5@example.com")
    job = make_job(db, dedup_key="reliability-test-2")
    application = Application(user_id=user.id, job_id=job.id, status="sent")
    db.session.add(application)
    db.session.commit()
    message = GmailMessage(application_id=application.id, gmail_message_id="rel-m1", body_text="Bitte um Rueckruf.")
    db.session.add(message)
    db.session.commit()

    monkeypatch.setattr(reply_ai, "get_provider", lambda: FakeProvider("INTENT: unclear\nCONFIDENCE: medium\nNOTES: Ambiguous."))
    reply_ai.classify_reply(user, application, message)
    assert message.classification_confidence == "medium"


def test_reply_suggestion_reliability_defaults_null(app, db, make_user, monkeypatch):
    user = make_user(email="rel6@example.com")
    job = make_job(db, dedup_key="reliability-test-3")
    application = Application(user_id=user.id, job_id=job.id, status="sent")
    db.session.add(application)
    db.session.commit()
    message = GmailMessage(application_id=application.id, gmail_message_id="rel-m2", body_text="Wann koennen Sie starten?")
    db.session.add(message)
    db.session.commit()

    reply_ai.generate_reply_suggestion(user, application, message)  # mock mode
    assert message.reply_suggestion_reliability is None

    monkeypatch.setattr(reply_ai, "get_provider", lambda: FakeProvider("Gerne ab dem 1. September."))
    reply_ai.generate_reply_suggestion(user, application, message)
    assert message.reply_suggestion_reliability is None


# --- Edit tracking: same mechanism as GeneratedDocument/GeneratedEmail ----

def test_interview_prep_edited_at_defaults_null_and_generation_never_sets_it(app, db, make_user, monkeypatch):
    user = make_user(email="edit1@example.com")
    job = make_job(db, dedup_key="edit-test-1")
    application = Application(user_id=user.id, job_id=job.id)
    db.session.add(application)
    db.session.commit()

    monkeypatch.setattr(interview_prep, "get_provider", lambda: FakeProvider("1. Tell me about PLC."))
    prep = interview_prep.generate_interview_prep(user, application)
    assert prep.edited_at is None  # AI generation is not an edit

    prep.edited_at = utcnow()  # what a future save route will do
    db.session.commit()
    assert _db.session.get(InterviewPrep, prep.id).edited_at is not None


def test_cv_profile_statement_edited_at_defaults_null_and_generation_never_sets_it(app, db, make_user):
    user = make_user(email="edit2@example.com")
    job = make_job(db, dedup_key="edit-test-2")
    application = Application(user_id=user.id, job_id=job.id)
    db.session.add(application)
    db.session.commit()

    statement = generate_cv_profile_statement(user, application)  # mock mode
    assert statement.edited_at is None

    statement.edited_at = utcnow()
    db.session.commit()
    assert _db.session.get(CvProfileStatement, statement.id).edited_at is not None


def test_reply_suggestion_edited_at_defaults_null_and_generation_never_sets_it(app, db, make_user, monkeypatch):
    user = make_user(email="edit3@example.com")
    job = make_job(db, dedup_key="edit-test-3")
    application = Application(user_id=user.id, job_id=job.id, status="sent")
    db.session.add(application)
    db.session.commit()
    message = GmailMessage(application_id=application.id, gmail_message_id="edit-m1", body_text="Danke fuer Ihre Bewerbung.")
    db.session.add(message)
    db.session.commit()

    monkeypatch.setattr(reply_ai, "get_provider", lambda: FakeProvider("Vielen Dank fuer die Rueckmeldung."))
    reply_ai.generate_reply_suggestion(user, application, message)
    assert message.reply_suggestion_edited_at is None

    message.reply_suggestion_edited_at = utcnow()
    db.session.commit()
    assert _db.session.get(GmailMessage, message.id).reply_suggestion_edited_at is not None
