from app.applications import routes as app_routes
from app.integrations import gmail_oauth
from app.models import Job, Application, GeneratedEmail
from app.models.integration import GmailMessage
from tests.conftest import login
from tests.test_gmail_reply_tracking import FakeGmailService, make_message_payload


def start_application(client, db, user, contact_email="hr@firma.de"):
    job = Job(title="Elektroniker", dedup_key="gmail-route-test")
    db.session.add(job)
    db.session.commit()
    client.post(f"/applications/start/{job.id}")
    application = Application.query.filter_by(user_id=user.id, job_id=job.id).first()
    application.contact_email = contact_email
    db.session.commit()
    return application


def test_check_replies_requires_gmail_connected(client, db, make_user):
    user = make_user(email="gr1@example.com", password="Password123!")
    login(client, "gr1@example.com", "Password123!")
    application = start_application(client, db, user)

    resp = client.post(f"/applications/{application.id}/check-replies", follow_redirects=True)
    assert resp.status_code == 200
    assert b"Connect your Gmail account first" in resp.data


def test_check_replies_creates_messages_when_connected(client, db, make_user, monkeypatch):
    user = make_user(email="gr2@example.com", password="Password123!")
    login(client, "gr2@example.com", "Password123!")
    application = start_application(client, db, user)

    payloads = {"m1": make_message_payload("m1", "t1", "hr@firma.de", "Re: Bewerbung", "<a@firma.de>", "Hallo!")}
    fake_service = FakeGmailService([{"id": "m1"}], payloads)
    monkeypatch.setattr(app_routes.gmail_oauth, "get_gmail_service", lambda user: fake_service)

    resp = client.post(f"/applications/{application.id}/check-replies", follow_redirects=True)
    assert resp.status_code == 200
    assert b"1 new message" in resp.data
    assert GmailMessage.query.filter_by(application_id=application.id).count() == 1


def test_message_routes_are_owned_per_application(client, db, make_user):
    owner = make_user(email="gr3owner@example.com", password="Password123!")
    other = make_user(email="gr3other@example.com", password="Password123!")

    login(client, "gr3owner@example.com", "Password123!")
    application = start_application(client, db, owner)
    message = GmailMessage(application_id=application.id, gmail_message_id="m1", from_address="hr@firma.de")
    db.session.add(message)
    db.session.commit()
    client.get("/auth/logout")

    login(client, "gr3other@example.com", "Password123!")
    resp = client.post(f"/applications/{application.id}/messages/{message.id}/classify")
    assert resp.status_code == 404
    resp = client.post(f"/applications/{application.id}/messages/{message.id}/suggest-reply")
    assert resp.status_code == 404
    resp = client.post(f"/applications/{application.id}/messages/{message.id}/create-reply-draft")
    assert resp.status_code == 404


def test_create_reply_draft_requires_text(client, db, make_user):
    user = make_user(email="gr4@example.com", password="Password123!")
    login(client, "gr4@example.com", "Password123!")
    application = start_application(client, db, user)
    message = GmailMessage(application_id=application.id, gmail_message_id="m1", from_address="hr@firma.de")
    db.session.add(message)
    db.session.commit()

    resp = client.post(
        f"/applications/{application.id}/messages/{message.id}/create-reply-draft",
        data={},
        follow_redirects=True,
    )
    assert b"Write or generate a reply first" in resp.data


def test_create_reply_draft_success(client, db, make_user, monkeypatch):
    user = make_user(email="gr5@example.com", password="Password123!")
    login(client, "gr5@example.com", "Password123!")
    application = start_application(client, db, user)
    message = GmailMessage(
        application_id=application.id, gmail_message_id="m1",
        from_address="hr@firma.de", subject="Bewerbung", gmail_thread_id="t1", rfc_message_id="<a@firma.de>",
    )
    db.session.add(message)
    db.session.commit()

    created = {}

    class FakeDraftsService:
        def users(self):
            return self

        def drafts(self):
            return self

        def create(self, userId, body):
            created["body"] = body
            return self

        def execute(self):
            return {"id": "draft1"}

    monkeypatch.setattr(app_routes.gmail_oauth, "get_gmail_service", lambda user: FakeDraftsService())

    resp = client.post(
        f"/applications/{application.id}/messages/{message.id}/create-reply-draft",
        data={"reply_text": "Gerne, hier ist meine Antwort."},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Reply draft created" in resp.data
    assert created["body"]["message"]["threadId"] == "t1"
    assert any(e.event_type == "reply_draft_created" for e in application.events)


def test_application_gmail_draft_requires_connection(client, db, make_user):
    user = make_user(email="gr6@example.com", password="Password123!")
    login(client, "gr6@example.com", "Password123!")
    application = start_application(client, db, user)
    application.status = "ready"
    application.package_storage_path = "/tmp/fake.pdf"
    db.session.add(GeneratedEmail(application_id=application.id, subject="s", body="b", source="template"))
    db.session.commit()

    resp = client.post(f"/applications/{application.id}/gmail-draft", follow_redirects=True)
    assert b"Connect your Gmail account first" in resp.data
