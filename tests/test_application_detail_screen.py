"""Screens pass 2 (Application Detail, 2026-08-27): route-level context
additions (tab counts, next-step card, PDF package info, the one
reliability badge that actually populates) and the honest-absence edge
cases the task called out as the real risk area for this screen.
"""
from app.extensions import db
from app.models import ApplicationDocument, Document
from app.models.integration import GmailConnection, GmailMessage
from tests.conftest import login
from tests.test_applications import make_job, start_application


def make_document(user, **overrides):
    kwargs = dict(
        user_id=user.id, original_filename="test.pdf", stored_filename="stored-test.pdf",
        storage_path="x/test.pdf", doc_type="cv", mime_type="application/pdf", file_size=1024,
    )
    kwargs.update(overrides)
    doc = Document(**kwargs)
    db.session.add(doc)
    db.session.commit()
    return doc


def test_documents_tab_count_reflects_selected_documents(client, db, make_user):
    user = make_user(email="ad1@example.com", password="Password123!")
    login(client, "ad1@example.com", "Password123!")
    job = make_job(db, dedup_key="ad-docs")
    _, application = start_application(client, db, job)
    doc = make_document(user)
    db.session.add(ApplicationDocument(application_id=application.id, document_id=doc.id))
    db.session.commit()

    resp = client.get(f"/applications/{application.id}")
    assert b"Documents" in resp.data
    assert b">1<" in resp.data  # the tab's count badge


def test_replies_tab_count_reflects_gmail_messages(client, db, make_user):
    make_user(email="ad2@example.com", password="Password123!")
    login(client, "ad2@example.com", "Password123!")
    job = make_job(db, dedup_key="ad-replies")
    _, application = start_application(client, db, job)
    db.session.add(GmailMessage(application_id=application.id, gmail_message_id="ad-r1"))
    db.session.add(GmailMessage(application_id=application.id, gmail_message_id="ad-r2"))
    db.session.commit()

    resp = client.get(f"/applications/{application.id}")
    assert b">2<" in resp.data


def test_classification_confidence_renders_a_real_reliability_badge(client, db, make_user):
    """The one reliability badge in the app with real data to show today -
    unlike every other Intelligence surface (still null by design, see the
    schema pass)."""
    user = make_user(email="ad3@example.com", password="Password123!")
    login(client, "ad3@example.com", "Password123!")
    db.session.add(GmailConnection(user_id=user.id, google_email="ad3@example.com"))
    job = make_job(db, dedup_key="ad-confidence")
    _, application = start_application(client, db, job)
    application.contact_email = "hr@example.de"
    db.session.add(GmailMessage(
        application_id=application.id, gmail_message_id="ad-c1", from_address="hr@example.de",
        classified_intent="interview_invitation", classification_confidence="high",
    ))
    db.session.commit()

    resp = client.get(f"/applications/{application.id}")
    assert b"RELIABILITY HIGH" in resp.data


def test_next_step_shows_a_real_reason_when_one_exists(client, db, make_user):
    make_user(email="ad4@example.com", password="Password123!")
    login(client, "ad4@example.com", "Password123!")
    job = make_job(db, dedup_key="ad-nextstep")
    _, application = start_application(client, db, job)
    application.status = "ready"
    db.session.commit()

    resp = client.get(f"/applications/{application.id}")
    assert b"Approved but not yet sent" in resp.data


def test_next_step_honest_fallback_when_nothing_urgent(client, db, make_user):
    make_user(email="ad5@example.com", password="Password123!")
    login(client, "ad5@example.com", "Password123!")
    job = make_job(db, dedup_key="ad-nextstep-none")
    _, application = start_application(client, db, job)
    application.status = "interview"  # not stalled, no imminent dates, cover letter/email not required here
    db.session.commit()
    # Give it a cover letter + email so the "not finished yet" reason doesn't fire.
    from app.models import GeneratedDocument, GeneratedEmail
    db.session.add(GeneratedDocument(application_id=application.id, content="x", source="manual"))
    db.session.add(GeneratedEmail(application_id=application.id, subject="x", body="x", source="manual"))
    db.session.commit()

    resp = client.get(f"/applications/{application.id}")
    assert b"Nothing time-sensitive right now." in resp.data


def test_pdf_package_shows_honest_not_built_yet_before_approval(client, db, make_user):
    make_user(email="ad6@example.com", password="Password123!")
    login(client, "ad6@example.com", "Password123!")
    job = make_job(db, dedup_key="ad-package")
    _, application = start_application(client, db, job)

    resp = client.get(f"/applications/{application.id}")
    assert b"Not built yet - approve the application to generate it." in resp.data


def test_contained_documents_rail_shows_empty_state_with_zero_documents(client, db, make_user):
    make_user(email="ad7@example.com", password="Password123!")
    login(client, "ad7@example.com", "Password123!")
    job = make_job(db, dedup_key="ad-zero-docs")
    _, application = start_application(client, db, job)

    resp = client.get(f"/applications/{application.id}")
    assert b"No documents selected yet." in resp.data
