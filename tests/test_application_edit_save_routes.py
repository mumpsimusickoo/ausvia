"""Screens pass 2 (Application Detail, 2026-08-27): the three save routes
the schema pass flagged as missing (InterviewPrep/CvProfileStatement/
GmailMessage.reply_suggestion all got edited_at columns with no route to
ever set them). Mirrors save_cover_letter/save_email's exact mechanism -
these tests are the counterpart to that pattern's own existing test
coverage, for the three new call sites.
"""
from app.ai import interview_prep as interview_prep_module
from app.ai import reply_ai
from app.ai.cv_profile_statement import generate_cv_profile_statement
from app.ai.provider import AIProvider, AIResponse
from app.models.ai import InterviewPrep, CvProfileStatement
from app.models.integration import GmailMessage
from tests.conftest import login
from tests.test_applications import make_job, start_application


class FakeProvider(AIProvider):
    provider_name = "fake"

    def __init__(self, text):
        self._text = text

    def complete(self, system_prompt, user_prompt, max_tokens=1024):
        return AIResponse(text=self._text, model="fake-model", provider=self.provider_name, input_tokens=5, output_tokens=5)


def test_save_interview_prep_sets_edited_at_on_existing_row(client, db, make_user, monkeypatch):
    make_user(email="save1@example.com", password="Password123!")
    login(client, "save1@example.com", "Password123!")
    job = make_job(db, dedup_key="save-prep")
    _, application = start_application(client, db, job)

    monkeypatch.setattr(interview_prep_module, "get_provider", lambda: FakeProvider("Tell me about PLC."))
    interview_prep_module.generate_interview_prep(application.user, application)
    prep = InterviewPrep.query.filter_by(application_id=application.id).first()
    assert prep.edited_at is None  # generation is not an edit

    resp = client.post(
        f"/applications/{application.id}/interview-prep/save",
        data={"prep_text": "My own rewritten prep notes."},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    db.session.refresh(prep)
    assert prep.prep_text == "My own rewritten prep notes."
    assert prep.edited_at is not None


def test_save_interview_prep_creates_a_fresh_row_without_edited_at(client, db, make_user):
    """No prior generation at all - the fresh-row branch. edited_at stays
    unset (there's nothing to be "edited" relative to)."""
    make_user(email="save2@example.com", password="Password123!")
    login(client, "save2@example.com", "Password123!")
    job = make_job(db, dedup_key="save-prep-fresh")
    _, application = start_application(client, db, job)

    resp = client.post(
        f"/applications/{application.id}/interview-prep/save",
        data={"prep_text": "Written from scratch."},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    prep = InterviewPrep.query.filter_by(application_id=application.id).first()
    assert prep is not None
    assert prep.prep_text == "Written from scratch."
    assert prep.edited_at is None


def test_save_cv_profile_statement_sets_edited_at_on_existing_row(client, db, make_user, monkeypatch):
    make_user(email="save3@example.com", password="Password123!")
    login(client, "save3@example.com", "Password123!")
    job = make_job(db, dedup_key="save-cv")
    _, application = start_application(client, db, job)

    generate_cv_profile_statement(application.user, application)  # mock mode
    statement = CvProfileStatement.query.filter_by(application_id=application.id).first()
    assert statement.edited_at is None

    resp = client.post(
        f"/applications/{application.id}/cv-profile-statement/save",
        data={"statement_text": "My own rewritten statement."},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    db.session.refresh(statement)
    assert statement.statement_text == "My own rewritten statement."
    assert statement.edited_at is not None


def test_save_reply_suggestion_sets_edited_at_on_existing_message(client, db, make_user, monkeypatch):
    make_user(email="save4@example.com", password="Password123!")
    login(client, "save4@example.com", "Password123!")
    job = make_job(db, dedup_key="save-reply")
    _, application = start_application(client, db, job)
    application.contact_email = "hr@example.de"
    db.session.commit()
    message = GmailMessage(application_id=application.id, gmail_message_id="save-reply-1", body_text="Bitte um Rueckruf.")
    db.session.add(message)
    db.session.commit()

    monkeypatch.setattr(reply_ai, "get_provider", lambda: FakeProvider("Vielen Dank fuer Ihre Nachricht."))
    reply_ai.generate_reply_suggestion(application.user, application, message)
    assert message.reply_suggestion_edited_at is None

    resp = client.post(
        f"/applications/{application.id}/messages/{message.id}/save-reply",
        data={"ai_suggested_reply": "My own rewritten reply."},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    db.session.refresh(message)
    assert message.ai_suggested_reply == "My own rewritten reply."
    assert message.reply_suggestion_edited_at is not None


def test_save_routes_reject_another_users_application(client, db, make_user):
    """_owned_application_or_404 already covers this app-wide - one
    spot-check on the new routes rather than re-proving the whole
    ownership mechanism."""
    make_user(email="owner@example.com", password="Password123!")
    make_user(email="intruder@example.com", password="Password123!")
    login(client, "owner@example.com", "Password123!")
    job = make_job(db, dedup_key="save-ownership")
    _, application = start_application(client, db, job)
    client.get("/auth/logout")

    login(client, "intruder@example.com", "Password123!")
    resp = client.post(
        f"/applications/{application.id}/interview-prep/save",
        data={"prep_text": "Should not be allowed."},
        follow_redirects=True,
    )
    assert resp.status_code == 404
