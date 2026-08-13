from app.ai import profile_coaching
from app.ai.provider import AIProvider, AIResponse
from app.models.ai import ProfileCoaching
from tests.conftest import login


class FakeProvider(AIProvider):
    provider_name = "fake"

    def __init__(self, text):
        self._text = text

    def complete(self, system_prompt, user_prompt, max_tokens=1024):
        return AIResponse(text=self._text, model="fake-model", provider=self.provider_name, input_tokens=8, output_tokens=8)


def test_generate_coaching_mock_mode_is_honest(client, db, make_user):
    make_user(email="coach1@example.com", password="Password123!")
    login(client, "coach1@example.com", "Password123!")

    resp = client.post("/profile/coaching", follow_redirects=True)
    assert resp.status_code == 200
    assert b"isn&#39;t available" in resp.data or b"isn't available" in resp.data

    coaching = ProfileCoaching.query.first()
    assert coaching is not None
    assert coaching.provider == "mock"


def test_generate_coaching_uses_real_provider_and_caches(app, db, make_user, monkeypatch):
    user = make_user(email="coach2@example.com")
    monkeypatch.setattr(profile_coaching, "get_provider", lambda: FakeProvider("Your PLC experience is a real strength."))

    result1 = profile_coaching.generate_profile_coaching(user)
    assert result1.summary_text == "Your PLC experience is a real strength."
    assert result1.provider == "fake"

    # calling again without a profile change should return the cached row,
    # not call the provider a second time
    monkeypatch.setattr(profile_coaching, "get_provider", lambda: FakeProvider("A different review."))
    result2 = profile_coaching.generate_profile_coaching(user)
    assert result2.summary_text == "Your PLC experience is a real strength."

    assert ProfileCoaching.query.filter_by(user_id=user.id).count() == 1


def test_coaching_regenerates_after_profile_change(app, db, make_user, monkeypatch):
    user = make_user(email="coach3@example.com")
    monkeypatch.setattr(profile_coaching, "get_provider", lambda: FakeProvider("First review."))
    profile_coaching.generate_profile_coaching(user)

    user.profile.city = "Berlin"
    db.session.commit()

    monkeypatch.setattr(profile_coaching, "get_provider", lambda: FakeProvider("Second review."))
    result = profile_coaching.generate_profile_coaching(user)
    assert result.summary_text == "Second review."


def test_coaching_is_per_user_not_shared(app, db, make_user, monkeypatch):
    user1 = make_user(email="coach4a@example.com")
    user2 = make_user(email="coach4b@example.com")
    monkeypatch.setattr(profile_coaching, "get_provider", lambda: FakeProvider("Review for user 1."))
    profile_coaching.generate_profile_coaching(user1)

    assert profile_coaching.get_profile_coaching(user2) is None


def test_coaching_button_shown_on_profile_page(client, db, make_user):
    make_user(email="coach5@example.com", password="Password123!")
    login(client, "coach5@example.com", "Password123!")

    resp = client.get("/profile/")
    assert b"Get AI feedback on my profile" in resp.data
