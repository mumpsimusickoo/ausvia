"""Unit tests for app/mail.py (real password reset email delivery via
Resend, 2026-08-30 pass - see DECISIONS.md). Covers graceful degradation
(unconfigured key, a real ResendError, an unexpected exception) and
locale-correct content. Route-level behavior (generic message, rate
limiting) lives in tests/test_auth.py and tests/test_rate_limiting.py.
"""
from resend.exceptions import ResendError

from app.mail import FROM_ADDRESS, send_password_reset_email
from app.models.system_log import SystemLog

RESET_LINK = "https://ausvia.org/auth/reset-password/fake-token-for-testing"


class _FakeEmails:
    """Stand-in for resend.Emails - records calls, or raises whatever
    the test configures, without ever making a real network call."""

    def __init__(self, raise_error=None):
        self.calls = []
        self._raise_error = raise_error

    def send(self, params):
        self.calls.append(params)
        if self._raise_error:
            raise self._raise_error
        return {"id": "fake-email-id"}


def test_unconfigured_key_does_not_attempt_a_send(app, db, make_user, monkeypatch):
    user = make_user(email="reset-nokey@example.com")
    app.config["RESEND_API_KEY"] = None

    fake_emails = _FakeEmails()
    monkeypatch.setattr("resend.Emails.send", fake_emails.send)

    with app.test_request_context("/"):
        send_password_reset_email(user, RESET_LINK)

    assert fake_emails.calls == []
    log = SystemLog.query.order_by(SystemLog.id.desc()).first()
    assert log.category == "auth"
    assert "RESEND_API_KEY not configured" in log.message
    assert log.level == "warning"


def test_configured_key_sends_with_correct_fields(app, db, make_user, monkeypatch):
    user = make_user(email="reset-ok@example.com")
    app.config["RESEND_API_KEY"] = "test-key-not-real"

    fake_emails = _FakeEmails()
    monkeypatch.setattr("resend.Emails.send", fake_emails.send)

    with app.test_request_context("/"):
        send_password_reset_email(user, RESET_LINK)

    assert len(fake_emails.calls) == 1
    call = fake_emails.calls[0]
    assert call["from"] == FROM_ADDRESS
    assert call["to"] == user.email
    assert RESET_LINK in call["html"]
    assert RESET_LINK in call["text"]
    assert call["subject"]


def test_resend_error_is_caught_and_logged_not_raised(app, db, make_user, monkeypatch):
    user = make_user(email="reset-resenderror@example.com")
    app.config["RESEND_API_KEY"] = "test-key-not-real"

    fake_emails = _FakeEmails(raise_error=ResendError(
        code=401, error_type="authentication_error", message="API key is invalid",
        suggested_action="Check your API key",
    ))
    monkeypatch.setattr("resend.Emails.send", fake_emails.send)

    with app.test_request_context("/"):
        send_password_reset_email(user, RESET_LINK)  # must not raise

    log = SystemLog.query.order_by(SystemLog.id.desc()).first()
    assert log.category == "auth"
    assert "failed to send" in log.message
    assert log.level == "warning"


def test_unexpected_exception_is_caught_and_logged_not_raised(app, db, make_user, monkeypatch):
    user = make_user(email="reset-unexpected@example.com")
    app.config["RESEND_API_KEY"] = "test-key-not-real"

    fake_emails = _FakeEmails(raise_error=ConnectionError("network unreachable"))
    monkeypatch.setattr("resend.Emails.send", fake_emails.send)

    with app.test_request_context("/"):
        send_password_reset_email(user, RESET_LINK)  # must not raise

    log = SystemLog.query.order_by(SystemLog.id.desc()).first()
    assert "failed to send" in log.message


def test_email_content_uses_the_account_locale_not_the_request_locale(app, db, make_user, monkeypatch):
    # The requester's browser (an anonymous, logged-out visitor) may not
    # even be the account owner - the account's own stored User.locale is
    # the correct signal for what language the actual recipient reads,
    # not whatever the current request happens to resolve to.
    user_de = make_user(email="reset-de@example.com")
    user_de.locale = "de"
    db.session.commit()

    fake_emails = _FakeEmails()
    monkeypatch.setattr("resend.Emails.send", fake_emails.send)
    app.config["RESEND_API_KEY"] = "test-key-not-real"

    with app.test_request_context("/"):
        send_password_reset_email(user_de, RESET_LINK)

    call = fake_emails.calls[0]
    assert "Passwort" in call["subject"]
    assert "Hallo" in call["html"]


def test_email_content_defaults_to_english_locale(app, db, make_user, monkeypatch):
    user_en = make_user(email="reset-en@example.com")
    assert user_en.locale == "en"

    fake_emails = _FakeEmails()
    monkeypatch.setattr("resend.Emails.send", fake_emails.send)
    app.config["RESEND_API_KEY"] = "test-key-not-real"

    with app.test_request_context("/"):
        send_password_reset_email(user_en, RESET_LINK)

    call = fake_emails.calls[0]
    assert "password" in call["subject"].lower()
    assert "Hi," in call["html"]
