from datetime import datetime

from app.ai import followup_email
from app.ai.provider import AIProvider, AIResponse
from app.models import Application, Job
from app.models.application import FollowUpEmail
from tests.conftest import login


class FakeProvider(AIProvider):
    provider_name = "fake"

    def __init__(self, text):
        self._text = text

    def complete(self, system_prompt, user_prompt, max_tokens=1024):
        return AIResponse(text=self._text, model="fake-model", provider=self.provider_name, input_tokens=8, output_tokens=8)


def make_job(db, **overrides):
    kwargs = dict(dedup_key="followup-test", employment_type="Ausbildung", title="Elektroniker")
    kwargs.update(overrides)
    job = Job(**kwargs)
    db.session.add(job)
    db.session.commit()
    return job


def make_application(db, user, job, status="sent", sent_at=None):
    application = Application(user_id=user.id, job_id=job.id, status=status, sent_at=sent_at)
    db.session.add(application)
    db.session.commit()
    return application


def test_followup_email_not_offered_before_sent(client, db, make_user):
    from tests.test_applications import start_application

    make_user(email="fu1@example.com", password="Password123!")
    login(client, "fu1@example.com", "Password123!")
    job = make_job(db)
    _, application = start_application(client, db, job)
    assert application.status == "preparing"

    resp = client.get(f"/applications/{application.id}")
    assert b"Draft a follow-up" not in resp.data
    assert b"Follow-up email" not in resp.data

    resp2 = client.post(f"/applications/{application.id}/generate-followup-email", follow_redirects=True)
    assert b"only available once" in resp2.data
    assert FollowUpEmail.query.filter_by(application_id=application.id).first() is None


def test_followup_email_mock_mode_gives_real_deterministic_text_not_a_decline(client, db, make_user):
    """Unlike the other 4 Wave 1 features, follow-up email has a genuine
    deterministic template fallback - mock mode must produce a real, usable
    email, not an "AI isn't available" apology."""
    make_user(email="fu2@example.com", password="Password123!")
    login(client, "fu2@example.com", "Password123!")
    from app.models import User

    user = User.query.filter_by(email="fu2@example.com").first()
    user.profile.first_name = "Karim"
    user.profile.last_name = "Boulaid"
    db.session.commit()

    job = make_job(db, title="Elektroniker für Automatisierungstechnik")
    application = make_application(db, user, job, status="sent", sent_at=datetime(2026, 7, 1))

    resp = client.post(f"/applications/{application.id}/generate-followup-email", follow_redirects=True)
    assert resp.status_code == 200
    assert b"isn&#39;t available" not in resp.data
    assert b"Elektroniker" in resp.data
    assert b"01.07.2026" in resp.data
    assert b"Karim Boulaid" in resp.data

    followup = FollowUpEmail.query.filter_by(application_id=application.id).first()
    assert followup is not None
    assert followup.source == "template"
    assert followup.provider is None


def test_followup_email_uses_real_provider(app, db, make_user, monkeypatch):
    user = make_user(email="fu3@example.com")
    job = make_job(db)
    application = make_application(db, user, job, status="follow_up", sent_at=datetime(2026, 6, 1))

    monkeypatch.setattr(
        followup_email, "get_provider",
        lambda: FakeProvider("SUBJECT: Nachfrage\nBODY:\nSehr geehrte Damen und Herren,\n\nfreundliche Nachfrage.\n\nMfG"),
    )

    subject, body, source, provider = followup_email.generate_followup_email(user, application)
    assert source == "ai"
    assert provider == "fake"
    assert subject == "Nachfrage"
    assert "freundliche Nachfrage" in body


def test_followup_email_regeneration_overwrites_not_caches(app, db, make_user, monkeypatch):
    """Unlike JobMatch/CompanyInsight-style features, follow-up email always
    regenerates fresh - same behavior as the original application email."""
    user = make_user(email="fu4@example.com")
    job = make_job(db)
    application = make_application(db, user, job, status="sent")

    monkeypatch.setattr(followup_email, "get_provider", lambda: FakeProvider("SUBJECT: First\nBODY:\nFirst body."))
    subject1, body1, _, _ = followup_email.generate_followup_email(user, application)
    assert subject1 == "First"

    monkeypatch.setattr(followup_email, "get_provider", lambda: FakeProvider("SUBJECT: Second\nBODY:\nSecond body."))
    subject2, body2, _, _ = followup_email.generate_followup_email(user, application)
    assert subject2 == "Second"  # not cached - genuinely regenerated


def test_save_followup_email_edit(client, db, make_user):
    make_user(email="fu5@example.com", password="Password123!")
    login(client, "fu5@example.com", "Password123!")
    from app.models import User

    user = User.query.filter_by(email="fu5@example.com").first()
    job = make_job(db)
    application = make_application(db, user, job, status="sent")

    client.post(f"/applications/{application.id}/generate-followup-email")
    resp = client.post(
        f"/applications/{application.id}/followup-email",
        data={"subject": "Edited subject", "body": "Edited body."},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    followup = FollowUpEmail.query.filter_by(application_id=application.id).first()
    assert followup.subject == "Edited subject"
    assert followup.body == "Edited body."
