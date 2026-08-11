from app.ai import reply_ai
from app.ai.provider import AIProvider, AIResponse
from app.models import Job, Application
from app.models.integration import GmailMessage


class FakeProvider(AIProvider):
    provider_name = "fake"

    def __init__(self, text):
        self._text = text

    def complete(self, system_prompt, user_prompt, max_tokens=1024):
        return AIResponse(text=self._text, model="fake-model", provider=self.provider_name, input_tokens=5, output_tokens=5)


def make_message(db, user):
    job = Job(title="Elektroniker", dedup_key="reply-ai-test")
    db.session.add(job)
    db.session.commit()
    application = Application(user_id=user.id, job_id=job.id, contact_email="hr@firma.de", status="sent")
    db.session.add(application)
    db.session.commit()
    message = GmailMessage(
        application_id=application.id, gmail_message_id="m1",
        from_address="hr@firma.de", subject="Re: Bewerbung", body_text="Koennen Sie naechste Woche?",
    )
    db.session.add(message)
    db.session.commit()
    return application, message


def test_classify_reply_mock_mode_is_honest_not_fake(app, db, make_user):
    user = make_user(email="ra1@example.com")
    application, message = make_message(db, user)

    reply_ai.classify_reply(user, application, message)

    assert message.classified_intent is None
    assert message.classification_confidence is None
    assert "isn't available" in message.classification_notes
    assert message.classification_provider == "mock"


def test_classify_reply_parses_ai_response(app, db, make_user, monkeypatch):
    user = make_user(email="ra2@example.com")
    application, message = make_message(db, user)

    fake_text = "INTENT: interview_invitation\nCONFIDENCE: high\nNOTES: They want to schedule a call."
    monkeypatch.setattr(reply_ai, "get_provider", lambda: FakeProvider(fake_text))

    reply_ai.classify_reply(user, application, message)

    assert message.classified_intent == "interview_invitation"
    assert message.classification_confidence == "high"
    assert message.classification_notes == "They want to schedule a call."
    assert message.classification_provider == "fake"


def test_classify_reply_falls_back_to_unclear_on_malformed_response(app, db, make_user, monkeypatch):
    user = make_user(email="ra3@example.com")
    application, message = make_message(db, user)

    monkeypatch.setattr(reply_ai, "get_provider", lambda: FakeProvider("not the expected format at all"))

    reply_ai.classify_reply(user, application, message)

    assert message.classified_intent == "unclear"
    assert message.classification_confidence == "low"


def test_generate_reply_suggestion_mock_mode_is_honest(app, db, make_user):
    user = make_user(email="ra4@example.com")
    application, message = make_message(db, user)

    text = reply_ai.generate_reply_suggestion(user, application, message)

    assert "aren't available" in text
    assert message.ai_suggested_reply_provider == "mock"


def test_generate_reply_suggestion_with_ai_provider(app, db, make_user, monkeypatch):
    user = make_user(email="ra5@example.com")
    application, message = make_message(db, user)

    monkeypatch.setattr(reply_ai, "get_provider", lambda: FakeProvider("Vielen Dank, gerne naechste Woche Dienstag."))

    text = reply_ai.generate_reply_suggestion(user, application, message)

    assert text == "Vielen Dank, gerne naechste Woche Dienstag."
    assert message.ai_suggested_reply_provider == "fake"
