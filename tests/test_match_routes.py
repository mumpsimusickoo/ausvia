from app.ai.provider import AIProvider, AIProviderError, AIResponse
from app.jobs import matching as matching_module
from app.models import Skill, Job
from app.models.ai import JobMatch
from tests.conftest import login


class FakeProvider(AIProvider):
    provider_name = "fake"

    def __init__(self, text="A grounded, factual explanation.", raise_error=None):
        self._text = text
        self._raise_error = raise_error

    def complete(self, system_prompt, user_prompt, max_tokens=1024):
        if self._raise_error:
            raise self._raise_error
        return AIResponse(text=self._text, model="fake-model", provider=self.provider_name, input_tokens=10, output_tokens=5)


def make_job(db, **overrides):
    kwargs = dict(dedup_key="route-test-key", employment_type="Ausbildung", title="Elektroniker")
    kwargs.update(overrides)
    job = Job(**kwargs)
    db.session.add(job)
    db.session.commit()
    return job


def test_detail_page_shows_deterministic_match_without_ai_call(client, db, make_user, monkeypatch):
    make_user(email="detail@example.com", password="Password123!")
    login(client, "detail@example.com", "Password123!")
    job = make_job(db, skills=["PLC"])

    def boom(*a, **kw):
        raise AssertionError("AI provider should not be called just to view the detail page")

    monkeypatch.setattr(matching_module, "get_provider", boom)

    resp = client.get(f"/jobs/{job.id}")
    assert resp.status_code == 200


def test_generate_narrative_with_mocked_provider(client, db, make_user, monkeypatch):
    make_user(email="narrator@example.com", password="Password123!")
    login(client, "narrator@example.com", "Password123!")
    job = make_job(db, skills=["PLC"])

    monkeypatch.setattr(matching_module, "get_provider", lambda: FakeProvider("Great fit for your PLC background."))

    resp = client.post(f"/jobs/{job.id}/narrative", follow_redirects=True)
    assert resp.status_code == 200
    assert b"Great fit for your PLC background." in resp.data

    match = JobMatch.query.filter_by(job_id=job.id).first()
    assert match.narrative_text == "Great fit for your PLC background."
    assert match.narrative_provider == "fake"


def test_narrative_generation_failure_does_not_crash(client, db, make_user, monkeypatch):
    make_user(email="failer@example.com", password="Password123!")
    login(client, "failer@example.com", "Password123!")
    job = make_job(db, skills=["PLC"])

    monkeypatch.setattr(
        matching_module, "get_provider", lambda: FakeProvider(raise_error=AIProviderError("provider down"))
    )

    resp = client.post(f"/jobs/{job.id}/narrative", follow_redirects=True)
    assert resp.status_code == 200
    assert b"provider down" in resp.data

    match = JobMatch.query.filter_by(job_id=job.id).first()
    assert match.narrative_text is None


def test_match_recomputes_when_profile_changes(app, db, make_user):
    user = make_user(email="stale@example.com", password="Password123!")
    job = make_job(db, skills=["PLC", "STEP7"])

    from app.jobs.matching import get_or_compute_match

    first = get_or_compute_match(user, job)
    first_score = first.score

    db.session.add(Skill(profile_id=user.profile.id, name="PLC"))
    db.session.add(Skill(profile_id=user.profile.id, name="STEP7"))
    user.profile.first_name = "Updated"  # bumps profile.updated_at via onupdate
    db.session.commit()

    second = get_or_compute_match(user, job)
    assert second.id == first.id  # same cache row, updated in place
    assert second.score != first_score
    assert second.score == 100
