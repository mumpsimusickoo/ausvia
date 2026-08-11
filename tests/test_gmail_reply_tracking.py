import base64

from app.integrations.gmail_reply_tracking import check_for_replies
from app.models import Job, Application
from app.models.integration import GmailMessage
from tests.conftest import login


def make_message_payload(msg_id, thread_id, from_addr, subject, rfc_id, body):
    encoded_body = base64.urlsafe_b64encode(body.encode()).decode()
    return {
        "id": msg_id,
        "threadId": thread_id,
        "internalDate": "1691700000000",
        "snippet": body[:50],
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "From", "value": from_addr},
                {"name": "Subject", "value": subject},
                {"name": "Message-ID", "value": rfc_id},
            ],
            "body": {"data": encoded_body},
        },
    }


class FakeMessagesResource:
    def __init__(self, refs, payloads):
        self._refs = refs
        self._payloads = payloads

    def list(self, userId, q, maxResults=25):
        return self

    def get(self, userId, id, format):
        return _Executable(self._payloads[id])

    def execute(self):
        return {"messages": self._refs}


class _Executable:
    def __init__(self, value):
        self._value = value

    def execute(self):
        return self._value


class FakeGmailService:
    def __init__(self, refs, payloads):
        self._messages = FakeMessagesResource(refs, payloads)

    def users(self):
        return self

    def messages(self):
        return self._messages


class ExplodingService:
    """Raises if any method is called - used to prove check_for_replies
    short-circuits before hitting the API when there's nothing to search for."""

    def users(self):
        raise AssertionError("Gmail API should not have been called")


def make_application(db, user, contact_email="hr@firma.de"):
    job = Job(title="Elektroniker", dedup_key="reply-test")
    db.session.add(job)
    db.session.commit()
    app_row = Application(user_id=user.id, job_id=job.id, contact_email=contact_email, status="sent")
    db.session.add(app_row)
    db.session.commit()
    return app_row


def test_no_contact_email_short_circuits(app, db, make_user):
    user = make_user(email="r1@example.com")
    application = make_application(db, user, contact_email=None)
    result = check_for_replies(user, application, ExplodingService())
    assert result == []


def test_detects_new_replies_and_extracts_body(app, db, make_user):
    user = make_user(email="r2@example.com")
    application = make_application(db, user)

    refs = [{"id": "m1"}]
    payloads = {
        "m1": make_message_payload(
            "m1", "t1", "hr@firma.de", "Re: Bewerbung", "<abc@firma.de>",
            "Wir laden Sie zum Vorstellungsgespraech ein.",
        )
    }
    service = FakeGmailService(refs, payloads)

    new_messages = check_for_replies(user, application, service)
    assert len(new_messages) == 1
    msg = new_messages[0]
    assert msg.gmail_message_id == "m1"
    assert msg.gmail_thread_id == "t1"
    assert msg.rfc_message_id == "<abc@firma.de>"
    assert msg.from_address == "hr@firma.de"
    assert "Vorstellungsgespraech" in msg.body_text

    assert any(e.event_type == "reply_detected" for e in application.events)


def test_reingesting_does_not_duplicate(app, db, make_user):
    user = make_user(email="r3@example.com")
    application = make_application(db, user)

    refs = [{"id": "m1"}]
    payloads = {"m1": make_message_payload("m1", "t1", "hr@firma.de", "Re: Bewerbung", "<abc@firma.de>", "Hello.")}
    service = FakeGmailService(refs, payloads)

    check_for_replies(user, application, service)
    second_result = check_for_replies(user, application, service)

    assert second_result == []
    assert GmailMessage.query.filter_by(application_id=application.id).count() == 1
