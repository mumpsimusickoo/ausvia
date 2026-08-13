from app.ai import interview_prep
from app.ai.provider import AIProvider, AIResponse
from app.models import Application, Job
from app.models.ai import InterviewPrep
from tests.conftest import login


class FakeProvider(AIProvider):
    provider_name = "fake"

    def __init__(self, text):
        self._text = text

    def complete(self, system_prompt, user_prompt, max_tokens=1024):
        return AIResponse(text=self._text, model="fake-model", provider=self.provider_name, input_tokens=8, output_tokens=8)


def make_job(db, **overrides):
    kwargs = dict(dedup_key="prep-test", employment_type="Ausbildung", title="Elektroniker")
    kwargs.update(overrides)
    job = Job(**kwargs)
    db.session.add(job)
    db.session.commit()
    return job


def start_application(client, db, job):
    resp = client.post(f"/applications/start/{job.id}", follow_redirects=True)
    application = Application.query.filter_by(job_id=job.id).first()
    return resp, application


def test_generate_interview_prep_mock_mode_is_honest(client, db, make_user):
    make_user(email="prep1@example.com", password="Password123!")
    login(client, "prep1@example.com", "Password123!")
    job = make_job(db)
    _, application = start_application(client, db, job)

    resp = client.post(f"/applications/{application.id}/interview-prep", follow_redirects=True)
    assert resp.status_code == 200
    assert b"isn&#39;t available" in resp.data or b"isn't available" in resp.data

    prep = InterviewPrep.query.filter_by(application_id=application.id).first()
    assert prep is not None
    assert prep.provider == "mock"


def test_interview_prep_available_before_interview_status(client, db, make_user):
    """Explicitly not gated to "interview" status - a candidate may want to
    prepare earlier, per the product instruction."""
    make_user(email="prep2@example.com", password="Password123!")
    login(client, "prep2@example.com", "Password123!")
    job = make_job(db)
    _, application = start_application(client, db, job)
    assert application.status == "preparing"

    resp = client.get(f"/applications/{application.id}")
    assert b"Generate interview prep" in resp.data


def test_generate_interview_prep_uses_real_provider_and_caches(app, db, make_user, monkeypatch):
    user = make_user(email="prep3@example.com")
    job = make_job(db)
    application = Application(user_id=user.id, job_id=job.id)
    db.session.add(application)
    db.session.commit()

    monkeypatch.setattr(interview_prep, "get_provider", lambda: FakeProvider("1. Tell me about your PLC project.\nMention the automation line you worked on."))
    result1 = interview_prep.generate_interview_prep(user, application)
    assert "PLC project" in result1.prep_text

    monkeypatch.setattr(interview_prep, "get_provider", lambda: FakeProvider("A different set of questions."))
    result2 = interview_prep.generate_interview_prep(user, application)
    assert "PLC project" in result2.prep_text  # cached, not regenerated

    assert InterviewPrep.query.filter_by(application_id=application.id).count() == 1


def test_interview_prep_is_per_application(app, db, make_user, monkeypatch):
    user = make_user(email="prep4@example.com")
    job1 = make_job(db, dedup_key="prep-test-1")
    job2 = make_job(db, dedup_key="prep-test-2")
    app1 = Application(user_id=user.id, job_id=job1.id)
    app2 = Application(user_id=user.id, job_id=job2.id)
    db.session.add_all([app1, app2])
    db.session.commit()

    monkeypatch.setattr(interview_prep, "get_provider", lambda: FakeProvider("Questions for job 1."))
    interview_prep.generate_interview_prep(user, app1)

    assert interview_prep.get_interview_prep(app2) is None
