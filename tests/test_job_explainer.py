from app.ai import job_explainer
from app.ai.provider import AIProvider, AIResponse
from app.models import Job, Language
from app.models.ai import JobExplainer
from tests.conftest import login


class FakeProvider(AIProvider):
    provider_name = "fake"

    def __init__(self, text):
        self._text = text
        self.last_prompt = None

    def complete(self, system_prompt, user_prompt, max_tokens=1024):
        self.last_prompt = user_prompt
        return AIResponse(text=self._text, model="fake-model", provider=self.provider_name, input_tokens=8, output_tokens=8)


def make_job(db, **overrides):
    kwargs = dict(dedup_key="explainer-test", employment_type="Ausbildung", title="Elektroniker", description="Wir suchen einen motivierten Auszubildenden.")
    kwargs.update(overrides)
    job = Job(**kwargs)
    db.session.add(job)
    db.session.commit()
    return job


def test_generate_explainer_mock_mode_is_honest(client, db, make_user):
    make_user(email="exp1@example.com", password="Password123!")
    login(client, "exp1@example.com", "Password123!")
    job = make_job(db)

    resp = client.post(f"/jobs/{job.id}/explain", follow_redirects=True)
    assert resp.status_code == 200
    assert b"aren&#39;t available" in resp.data or b"aren't available" in resp.data

    explainer = JobExplainer.query.filter_by(job_id=job.id).first()
    assert explainer is not None
    assert explainer.provider == "mock"


def test_generate_explainer_uses_real_provider_and_caches(app, db, make_user, monkeypatch):
    user = make_user(email="exp2@example.com")
    job = make_job(db)
    monkeypatch.setattr(job_explainer, "get_provider", lambda: FakeProvider("Plain summary."))

    result1 = job_explainer.generate_job_explainer(user, job)
    assert result1.explainer_text == "Plain summary."

    monkeypatch.setattr(job_explainer, "get_provider", lambda: FakeProvider("A different summary."))
    result2 = job_explainer.generate_job_explainer(user, job)
    assert result2.explainer_text == "Plain summary."  # cached

    assert JobExplainer.query.filter_by(user_id=user.id, job_id=job.id).count() == 1


def test_explainer_prompt_includes_candidate_german_level(app, db, make_user, monkeypatch):
    user = make_user(email="exp3@example.com")
    db.session.add(Language(profile_id=user.profile.id, name="German", level="A2"))
    db.session.commit()
    job = make_job(db)

    fake = FakeProvider("Simplified summary.")
    monkeypatch.setattr(job_explainer, "get_provider", lambda: fake)

    job_explainer.generate_job_explainer(user, job)
    assert "A2" in fake.last_prompt


def test_explainer_prompt_omits_german_level_when_unknown(app, db, make_user, monkeypatch):
    user = make_user(email="exp4@example.com")
    job = make_job(db)

    fake = FakeProvider("Summary without level context.")
    monkeypatch.setattr(job_explainer, "get_provider", lambda: fake)

    job_explainer.generate_job_explainer(user, job)
    assert "Candidate's stated German level" not in fake.last_prompt


def test_explainer_is_per_user_not_shared(app, db, make_user, monkeypatch):
    user1 = make_user(email="exp5a@example.com")
    user2 = make_user(email="exp5b@example.com")
    job = make_job(db)

    monkeypatch.setattr(job_explainer, "get_provider", lambda: FakeProvider("Summary for user 1."))
    job_explainer.generate_job_explainer(user1, job)

    assert job_explainer.get_job_explainer(user2, job) is None
