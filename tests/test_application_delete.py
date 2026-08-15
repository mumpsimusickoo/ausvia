"""Tests for application deletion (app/applications/routes.py::delete).

Status-based confirmation: "preparing"/"ready" (nothing sent to anyone
yet - see LOW_RISK_DELETE_STATUSES) delete with just a normal POST;
anything past that represents real correspondence history and requires a
typed "DELETE" confirmation, enforced server-side (not just decorative
client-side JS - a direct POST without it must fail exactly the same way
a browser submission without typing it would).
"""
import io

from pdfmerge import text_to_pdf_bytes

from app.models import Application, ApplicationDocument, ApplicationEvent, Document, GeneratedDocument, GeneratedEmail, Job
from app.models.ai import InterviewPrep, JobMatch
from app.models.integration import GmailMessage
from tests.conftest import login

VALID_PDF = text_to_pdf_bytes("Test document content for the application package.")


def make_job(db, **overrides):
    kwargs = dict(dedup_key="del-test", employment_type="Ausbildung", title="Elektroniker")
    kwargs.update(overrides)
    job = Job(**kwargs)
    db.session.add(job)
    db.session.commit()
    return job


def start_application(client, db, job):
    resp = client.post(f"/applications/start/{job.id}", follow_redirects=True)
    application = Application.query.filter_by(job_id=job.id).first()
    return resp, application


def test_preparing_application_deletes_with_plain_post(client, db, make_user):
    make_user(email="del1@example.com", password="Password123!")
    login(client, "del1@example.com", "Password123!")
    job = make_job(db)
    _, application = start_application(client, db, job)
    assert application.status == "preparing"

    resp = client.post(f"/applications/{application.id}/delete", follow_redirects=True)
    assert resp.status_code == 200
    assert Application.query.count() == 0


def test_sent_application_rejects_delete_without_confirmation_text(client, db, make_user):
    make_user(email="del2@example.com", password="Password123!")
    login(client, "del2@example.com", "Password123!")
    job = make_job(db)
    _, application = start_application(client, db, job)
    application.status = "sent"
    db.session.commit()

    resp = client.post(f"/applications/{application.id}/delete", follow_redirects=True)
    assert resp.status_code == 200
    assert b"type DELETE" in resp.data or b"DELETE" in resp.data
    # Not deleted - the confirmation gate actually blocked it.
    assert Application.query.count() == 1


def test_sent_application_rejects_wrong_confirmation_text(client, db, make_user):
    make_user(email="del3@example.com", password="Password123!")
    login(client, "del3@example.com", "Password123!")
    job = make_job(db)
    _, application = start_application(client, db, job)
    application.status = "sent"
    db.session.commit()

    resp = client.post(
        f"/applications/{application.id}/delete", data={"confirm_text": "delete pls"}, follow_redirects=True
    )
    assert resp.status_code == 200
    assert Application.query.count() == 1


def test_sent_application_deletes_with_correct_confirmation_text(client, db, make_user):
    make_user(email="del4@example.com", password="Password123!")
    login(client, "del4@example.com", "Password123!")
    job = make_job(db)
    _, application = start_application(client, db, job)
    application.status = "sent"
    db.session.commit()

    resp = client.post(
        f"/applications/{application.id}/delete", data={"confirm_text": "DELETE"}, follow_redirects=True
    )
    assert resp.status_code == 200
    assert Application.query.count() == 0


def test_confirmation_text_is_case_insensitive(client, db, make_user):
    make_user(email="del5@example.com", password="Password123!")
    login(client, "del5@example.com", "Password123!")
    job = make_job(db)
    _, application = start_application(client, db, job)
    application.status = "interview"
    db.session.commit()

    resp = client.post(
        f"/applications/{application.id}/delete", data={"confirm_text": "delete"}, follow_redirects=True
    )
    assert Application.query.count() == 0


def test_every_status_past_preparing_and_ready_requires_confirmation(client, db, make_user):
    make_user(email="del6@example.com", password="Password123!")
    login(client, "del6@example.com", "Password123!")

    protected_statuses = ["sent", "follow_up", "interview", "offer", "accepted", "rejected", "withdrawn", "expired"]
    for i, status in enumerate(protected_statuses):
        job = make_job(db, dedup_key=f"del-test-{i}", title=f"Job {i}")
        _, application = start_application(client, db, job)
        application.status = status
        db.session.commit()

        resp = client.post(f"/applications/{application.id}/delete", follow_redirects=True)
        assert Application.query.filter_by(id=application.id).first() is not None, (
            f"status={status} should have required confirmation but deleted anyway"
        )


def test_ready_status_deletes_without_confirmation_text(client, db, make_user):
    make_user(email="del7@example.com", password="Password123!")
    login(client, "del7@example.com", "Password123!")
    job = make_job(db)
    _, application = start_application(client, db, job)
    application.status = "ready"
    db.session.commit()

    resp = client.post(f"/applications/{application.id}/delete", follow_redirects=True)
    assert Application.query.count() == 0


def test_delete_removes_dependent_rows_without_orphaning(client, db, make_user):
    make_user(email="del8@example.com", password="Password123!")
    login(client, "del8@example.com", "Password123!")
    job = make_job(db)
    _, application = start_application(client, db, job)

    application.log_event("note", "A manual event for this application.")
    db.session.add(GeneratedDocument(application_id=application.id, content="Cover letter text.", source="template"))
    db.session.add(GeneratedEmail(application_id=application.id, subject="s", body="b", source="template"))
    db.session.add(GmailMessage(
        application_id=application.id, gmail_message_id="msg-1", from_address="hr@firma.de", subject="Re:",
    ))
    db.session.add(InterviewPrep(application_id=application.id, prep_text="Likely questions..."))
    doc = Document(
        user_id=application.user_id, doc_type="cv", original_filename="cv.pdf", stored_filename="x.pdf",
        storage_path="x/x.pdf", mime_type="application/pdf", file_size=10,
    )
    db.session.add(doc)
    db.session.flush()
    db.session.add(ApplicationDocument(application_id=application.id, document_id=doc.id))
    db.session.commit()

    application_id = application.id

    resp = client.post(f"/applications/{application_id}/delete", follow_redirects=True)
    assert resp.status_code == 200

    assert Application.query.filter_by(id=application_id).first() is None
    assert ApplicationEvent.query.filter_by(application_id=application_id).count() == 0
    assert GeneratedDocument.query.filter_by(application_id=application_id).count() == 0
    assert GeneratedEmail.query.filter_by(application_id=application_id).count() == 0
    assert GmailMessage.query.filter_by(application_id=application_id).count() == 0
    assert InterviewPrep.query.filter_by(application_id=application_id).count() == 0
    assert ApplicationDocument.query.filter_by(application_id=application_id).count() == 0
    # The document itself (owned separately by the user, just referenced
    # by the application) must survive - only the join row is cleaned up.
    assert Document.query.filter_by(id=doc.id).count() == 1


def test_delete_does_not_touch_job_match(client, db, make_user):
    # JobMatch is keyed by (user_id, job_id), not application_id - it
    # represents fit against the job itself and must survive the
    # application being deleted.
    from app.jobs.matching import get_or_compute_match

    make_user(email="del9@example.com", password="Password123!")
    login(client, "del9@example.com", "Password123!")
    job = make_job(db)
    resp, application = start_application(client, db, job)

    user = application.user
    match = get_or_compute_match(user, job)
    match_id = match.id

    client.post(f"/applications/{application.id}/delete", follow_redirects=True)

    assert JobMatch.query.filter_by(id=match_id).first() is not None


def test_user_cannot_delete_another_users_application(client, db, make_user):
    owner = make_user(email="del10a@example.com", password="Password123!")
    other = make_user(email="del10b@example.com", password="Password123!")

    login(client, "del10a@example.com", "Password123!")
    job = make_job(db)
    _, application = start_application(client, db, job)
    client.get("/auth/logout")

    login(client, "del10b@example.com", "Password123!")
    resp = client.post(f"/applications/{application.id}/delete", follow_redirects=True)
    assert resp.status_code == 404
    assert Application.query.filter_by(id=application.id).first() is not None


def test_delete_removes_package_file_from_disk(client, db, make_user, tmp_path):
    make_user(email="del11@example.com", password="Password123!")
    login(client, "del11@example.com", "Password123!")
    job = make_job(db)
    _, application = start_application(client, db, job)

    package_path = tmp_path / "package.pdf"
    package_path.write_bytes(b"%PDF-fake")
    application.package_storage_path = str(package_path)
    application.package_filename = "package.pdf"
    db.session.commit()

    client.post(f"/applications/{application.id}/delete", follow_redirects=True)

    assert not package_path.exists()


def test_delete_button_visible_on_detail_page(client, db, make_user):
    make_user(email="del12@example.com", password="Password123!")
    login(client, "del12@example.com", "Password123!")
    job = make_job(db)
    _, application = start_application(client, db, job)

    resp = client.get(f"/applications/{application.id}")
    assert b"Delete this application" in resp.data
    assert b"Delete application" in resp.data
