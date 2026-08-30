import pytest

from app import create_app
from app.extensions import db as _db
from app.models import User, CandidateProfile, Job


@pytest.fixture
def rate_limited_client(monkeypatch, tmp_path):
    """Flask-Limiter reads RATELIMIT_ENABLED once, at init_app() time - so
    mutating app.config afterward (on the shared `app` fixture) has no
    effect. This builds a fresh app with the flag already set to True
    *before* create_app() runs, specifically to prove the Phase 5 rate
    limits actually work. Every other test keeps using the shared `app`
    fixture with rate limiting disabled, per config.py's TestingConfig."""
    from config import TestingConfig

    monkeypatch.setattr(TestingConfig, "RATELIMIT_ENABLED", True)
    application = create_app("testing")
    application.config["UPLOAD_DIR"] = str(tmp_path)
    application.config["GENERATED_DIR"] = str(tmp_path)

    with application.app_context():
        _db.create_all()
        yield application.test_client()
        _db.session.remove()
        _db.drop_all()


def test_ai_narrative_route_is_rate_limited(rate_limited_client):
    client = rate_limited_client

    user = User(email="rl1@example.com", role="user", plan="trial")
    user.set_password("Password123!")
    _db.session.add(user)
    _db.session.flush()
    _db.session.add(CandidateProfile(user_id=user.id, contact_email=user.email))
    job = Job(title="Elektroniker", dedup_key="rate-limit-test")
    _db.session.add(job)
    _db.session.commit()

    client.post("/auth/login", data={"email": "rl1@example.com", "password": "Password123!"})

    statuses = [client.post(f"/jobs/{job.id}/narrative").status_code for _ in range(32)]
    assert 429 in statuses, f"expected a 429 within 32 requests against a 30/hour limit, got: {statuses}"


def test_manual_import_extraction_is_rate_limited(rate_limited_client, monkeypatch):
    """Manual import extraction pass (2026-08-30): same 30/hour/IP
    protection as every other AI-calling route, but this feature never
    surfaces a 429 to the user (see app/ai/manual_import_extraction.py's
    own catch of RateLimitExceeded) - it degrades to the raw-title/raw-
    text baseline instead, so the actual observable proof here is that
    the real provider is never called more than 30 times, not an HTTP
    status code."""
    from app.ai.provider import AIProvider, AIResponse
    from app.jobs.manual_import import FetchFailed

    client = rate_limited_client

    user = User(email="rl2@example.com", role="user", plan="trial")
    user.set_password("Password123!")
    _db.session.add(user)
    _db.session.flush()
    _db.session.add(CandidateProfile(user_id=user.id, contact_email=user.email))
    _db.session.commit()
    client.post("/auth/login", data={"email": "rl2@example.com", "password": "Password123!"})

    real_calls = []

    class CountingFakeProvider(AIProvider):
        provider_name = "fake"

        def complete(self, system_prompt, user_prompt, max_tokens=1024):
            real_calls.append(1)
            return AIResponse(
                text='{"title": null, "company_name": null, "location": null, "start_date": null, "exclude_line_numbers": []}',
                model="fake-model", provider="fake", input_tokens=5, output_tokens=5,
            )

    monkeypatch.setattr("app.ai.manual_import_extraction.get_provider", lambda: CountingFakeProvider())

    for i in range(32):
        url = f"https://ratelimit-manual-import.example/{i}"

        def fake_fetch(u, _title=f"Title {i}"):
            return {"page_title": _title, "text": "Some page text.\nMore text.\nEven more.\n"}

        monkeypatch.setattr("app.jobs.routes.fetch_and_extract_text", fake_fetch)
        resp = client.post("/jobs/import/fetch", data={"urls": url})
        assert resp.status_code in (200, 302)  # never a 429 - always degrades gracefully

    assert len(real_calls) <= 30, f"expected the real provider to be called at most 30 times, got {len(real_calls)}"
