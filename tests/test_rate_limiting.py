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
