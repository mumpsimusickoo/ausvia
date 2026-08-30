import io

from pdfmerge import text_to_pdf_bytes

from app.models import Application, ApplicationDocument, GeneratedDocument, Document, Job
from tests.conftest import login

# a hand-crafted minimal "%PDF..." byte string passes the upload magic-byte
# check but isn't structurally parseable - the PDF merge step needs a real one.
VALID_PDF = text_to_pdf_bytes("Test document content for the application package.")


def make_job(db, **overrides):
    kwargs = dict(dedup_key="app-test", employment_type="Ausbildung", title="Elektroniker")
    kwargs.update(overrides)
    job = Job(**kwargs)
    db.session.add(job)
    db.session.commit()
    return job


def start_application(client, db, job):
    resp = client.post(f"/applications/start/{job.id}", follow_redirects=True)
    application = Application.query.filter_by(job_id=job.id).first()
    return resp, application


def test_start_application_creates_preparing_status(client, db, make_user):
    make_user(email="a1@example.com", password="Password123!")
    login(client, "a1@example.com", "Password123!")
    job = make_job(db)

    resp, application = start_application(client, db, job)
    assert resp.status_code == 200
    assert application is not None
    assert application.status == "preparing"
    assert len(application.events) == 1


def test_starting_application_seeds_contact_info_from_job(client, db, make_user):
    # Contact-info follow-up pass (2026-08-30): confirms the secondary
    # consequence of the manual-import/Arbeitsagentur contact-extraction
    # fixes is actually resolved too, not just the generated-content
    # salutation - Application.contact_email is the real address the
    # Gmail draft/reply flow uses (app/applications/routes.py), seeded
    # once at Application creation from whatever the Job row already has.
    make_user(email="a-contact-seed@example.com", password="Password123!")
    login(client, "a-contact-seed@example.com", "Password123!")
    job = make_job(db, contact_person="Frau Julia Weber", contact_email="bewerbung@example.de")

    resp, application = start_application(client, db, job)
    assert resp.status_code == 200
    assert application.contact_person == "Frau Julia Weber"
    assert application.contact_email == "bewerbung@example.de"


def test_starting_twice_does_not_duplicate(client, db, make_user):
    make_user(email="a2@example.com", password="Password123!")
    login(client, "a2@example.com", "Password123!")
    job = make_job(db)

    client.post(f"/applications/start/{job.id}")
    client.post(f"/applications/start/{job.id}")
    assert Application.query.filter_by(job_id=job.id).count() == 1


def test_generate_cover_letter_uses_template_fallback(client, db, make_user):
    make_user(email="a3@example.com", password="Password123!")
    login(client, "a3@example.com", "Password123!")
    job = make_job(db, title="Mechatroniker")
    _, application = start_application(client, db, job)

    resp = client.post(f"/applications/{application.id}/generate-cover-letter", follow_redirects=True)
    assert resp.status_code == 200

    letter = GeneratedDocument.query.filter_by(application_id=application.id).first()
    assert letter is not None
    assert letter.source == "template"
    assert "Mechatroniker" in letter.content


def test_approve_requires_cover_letter_and_documents(client, db, make_user):
    make_user(email="a4@example.com", password="Password123!")
    login(client, "a4@example.com", "Password123!")
    job = make_job(db)
    _, application = start_application(client, db, job)

    resp = client.post(f"/applications/{application.id}/approve", follow_redirects=True)
    assert b"Generate or write a cover letter" in resp.data
    db.session.refresh(application)
    assert application.status == "preparing"


def test_full_flow_generate_select_approve_download(client, db, make_user):
    make_user(email="a5@example.com", password="Password123!")
    login(client, "a5@example.com", "Password123!")
    job = make_job(db, title="Elektroniker für Automatisierungstechnik")
    _, application = start_application(client, db, job)

    client.post(f"/applications/{application.id}/generate-cover-letter")

    upload_resp = client.post(
        "/documents/upload",
        data={"doc_type": "cv", "file": (io.BytesIO(VALID_PDF), "cv.pdf")},
        content_type="multipart/form-data",
    )
    doc = Document.query.filter_by(original_filename="cv.pdf").first()
    assert doc is not None

    client.post(f"/applications/{application.id}/documents", data={"document_ids": [str(doc.id)]})

    resp = client.post(f"/applications/{application.id}/approve", follow_redirects=True)
    assert resp.status_code == 200

    db.session.refresh(application)
    assert application.status == "ready"
    assert application.package_storage_path
    import os

    assert os.path.exists(application.package_storage_path)

    resp = client.get(f"/applications/{application.id}/download")
    assert resp.status_code == 200
    assert resp.headers["Content-Type"] == "application/pdf"


def test_approve_fails_gracefully_on_corrupt_pdf_not_500(client, db, make_user):
    # passes the upload magic-byte sniff (starts with %PDF) but has no real
    # PDF structure - regression test for a bug found via live smoke testing
    # where this crashed the approve route with a raw 500.
    make_user(email="a9@example.com", password="Password123!")
    login(client, "a9@example.com", "Password123!")
    job = make_job(db)
    _, application = start_application(client, db, job)
    client.post(f"/applications/{application.id}/generate-cover-letter")

    corrupt_pdf = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>"
    client.post(
        "/documents/upload",
        data={"doc_type": "cv", "file": (io.BytesIO(corrupt_pdf), "corrupt.pdf")},
        content_type="multipart/form-data",
    )
    doc = Document.query.filter_by(original_filename="corrupt.pdf").first()
    client.post(f"/applications/{application.id}/documents", data={"document_ids": [str(doc.id)]})

    resp = client.post(f"/applications/{application.id}/approve", follow_redirects=True)
    assert resp.status_code == 200
    assert b"corrupted or unreadable" in resp.data
    db.session.refresh(application)
    assert application.status == "preparing"
    assert application.package_storage_path is None


def test_deleting_selected_document_does_not_crash_generate_email_or_approve(client, db, make_user):
    """Regression test for QA Phase 7 finding B1: deleting a document that's
    still selected on an application orphaned its ApplicationDocument row
    and crashed generate-email/approve with a raw 500 the next time either
    read sd.document. Fixed via Document.application_documents cascade
    (app/models/document.py) + SQLite FK enforcement (app/__init__.py)."""
    make_user(email="a10@example.com", password="Password123!")
    login(client, "a10@example.com", "Password123!")
    job = make_job(db)
    _, application = start_application(client, db, job)
    client.post(f"/applications/{application.id}/generate-cover-letter")

    client.post(
        "/documents/upload",
        data={"doc_type": "cv", "file": (io.BytesIO(VALID_PDF), "will_be_deleted.pdf")},
        content_type="multipart/form-data",
    )
    doc = Document.query.filter_by(original_filename="will_be_deleted.pdf").first()
    client.post(f"/applications/{application.id}/documents", data={"document_ids": [str(doc.id)]})
    assert ApplicationDocument.query.filter_by(application_id=application.id, document_id=doc.id).count() == 1

    client.post(f"/documents/{doc.id}/delete")

    # the selection must be cleaned up, not left dangling
    assert ApplicationDocument.query.filter_by(document_id=doc.id).count() == 0

    resp = client.post(f"/applications/{application.id}/generate-email", follow_redirects=True)
    assert resp.status_code == 200

    resp2 = client.post(f"/applications/{application.id}/approve", follow_redirects=True)
    assert resp2.status_code == 200
    # no documents remain selected - an honest rejection, not a crash
    assert b"Select at least one document" in resp2.data


def test_mark_sent_requires_ready_status(client, db, make_user):
    make_user(email="a6@example.com", password="Password123!")
    login(client, "a6@example.com", "Password123!")
    job = make_job(db)
    _, application = start_application(client, db, job)

    resp = client.post(f"/applications/{application.id}/mark-sent", follow_redirects=True)
    assert b"Approve the application" in resp.data
    db.session.refresh(application)
    assert application.status == "preparing"


def test_application_is_owned_per_user(client, db, make_user):
    owner = make_user(email="a7owner@example.com", password="Password123!")
    other = make_user(email="a7other@example.com", password="Password123!")
    job = make_job(db)

    login(client, "a7owner@example.com", "Password123!")
    _, application = start_application(client, db, job)
    client.get("/auth/logout")

    login(client, "a7other@example.com", "Password123!")
    resp = client.get(f"/applications/{application.id}")
    assert resp.status_code == 404

    resp = client.post(f"/applications/{application.id}/generate-cover-letter")
    assert resp.status_code == 404


def test_status_update_logs_timeline_event(client, db, make_user):
    make_user(email="a8@example.com", password="Password123!")
    login(client, "a8@example.com", "Password123!")
    job = make_job(db)
    _, application = start_application(client, db, job)

    resp = client.post(
        f"/applications/{application.id}/status",
        data={"status": "withdrawn", "notes": "Changed my mind"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    db.session.refresh(application)
    assert application.status == "withdrawn"
    assert application.notes == "Changed my mind"
    assert any("withdrawn" in e.description for e in application.events)
