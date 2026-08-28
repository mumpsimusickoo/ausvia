import io

from app.models.application import Application, ApplicationDocument
from app.models.document import Document
from app.models.job import Job
from tests.conftest import login
from pdfmerge import text_to_pdf_bytes

VALID_PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>"


def test_upload_valid_pdf(client, db, make_user):
    make_user(email="d1@example.com", password="Password123!")
    login(client, "d1@example.com", "Password123!")

    resp = client.post(
        "/documents/upload",
        data={
            "doc_type": "cv",
            "description": "My CV",
            "file": (io.BytesIO(VALID_PDF), "cv.pdf"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert b"cv.pdf" in resp.data
    doc = Document.query.filter_by(original_filename="cv.pdf").first()
    assert doc is not None
    assert doc.mime_type == "application/pdf"


def test_upload_rejects_content_mismatch(client, db, make_user):
    make_user(email="d2@example.com", password="Password123!")
    login(client, "d2@example.com", "Password123!")

    resp = client.post(
        "/documents/upload",
        data={
            "doc_type": "other",
            "file": (io.BytesIO(b"this is not a pdf"), "fake.pdf"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert b"doesn" in resp.data  # "doesn't match its extension"
    assert Document.query.filter_by(original_filename="fake.pdf").first() is None


def test_upload_rejects_disallowed_extension(client, db, make_user):
    make_user(email="d3@example.com", password="Password123!")
    login(client, "d3@example.com", "Password123!")

    resp = client.post(
        "/documents/upload",
        data={
            "doc_type": "other",
            "file": (io.BytesIO(b"MZ\x90\x00fake exe"), "malware.exe"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert b"Unsupported file type" in resp.data
    assert Document.query.filter_by(original_filename="malware.exe").first() is None


def test_user_cannot_access_another_users_document(client, db, make_user):
    make_user(email="owner2@example.com", password="Password123!")
    login(client, "owner2@example.com", "Password123!")
    client.post(
        "/documents/upload",
        data={"doc_type": "cv", "file": (io.BytesIO(VALID_PDF), "owner_cv.pdf")},
        content_type="multipart/form-data",
    )
    doc = Document.query.filter_by(original_filename="owner_cv.pdf").first()
    client.get("/auth/logout")

    make_user(email="intruder2@example.com", password="Password123!")
    login(client, "intruder2@example.com", "Password123!")

    resp = client.get(f"/documents/{doc.id}/download")
    assert resp.status_code == 404

    resp = client.post(f"/documents/{doc.id}/delete")
    assert resp.status_code == 404

    # document must still exist and be unmodified
    still_there = db.session.get(Document, doc.id)
    assert still_there is not None


def test_upload_pdf_stores_ai_suggestion_when_mismatched(client, db, make_user):
    make_user(email="d5@example.com", password="Password123!")
    login(client, "d5@example.com", "Password123!")

    cv_pdf = text_to_pdf_bytes("LEBENSLAUF\n\nBerufserfahrung: Praktikum bei Elektro Hoffmann GmbH")
    resp = client.post(
        "/documents/upload",
        data={"doc_type": "other", "file": (io.BytesIO(cv_pdf), "mystery.pdf")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert b"might be a" in resp.data
    doc = Document.query.filter_by(original_filename="mystery.pdf").first()
    assert doc.doc_type == "other"  # never auto-applied
    assert doc.ai_suggested_doc_type == "cv"


def test_apply_suggested_type_updates_doc_type(client, db, make_user):
    make_user(email="d6@example.com", password="Password123!")
    login(client, "d6@example.com", "Password123!")

    cv_pdf = text_to_pdf_bytes("LEBENSLAUF\n\nBerufserfahrung: ...")
    client.post(
        "/documents/upload",
        data={"doc_type": "other", "file": (io.BytesIO(cv_pdf), "mystery2.pdf")},
        content_type="multipart/form-data",
    )
    doc = Document.query.filter_by(original_filename="mystery2.pdf").first()
    assert doc.ai_suggested_doc_type == "cv"

    client.post(f"/documents/{doc.id}/apply-suggested-type")
    db.session.refresh(doc)
    assert doc.doc_type == "cv"
    assert doc.ai_suggested_doc_type is None


def test_dismiss_suggested_type_clears_suggestion_without_changing_type(client, db, make_user):
    make_user(email="d7@example.com", password="Password123!")
    login(client, "d7@example.com", "Password123!")

    cv_pdf = text_to_pdf_bytes("LEBENSLAUF\n\nBerufserfahrung: ...")
    client.post(
        "/documents/upload",
        data={"doc_type": "other", "file": (io.BytesIO(cv_pdf), "mystery3.pdf")},
        content_type="multipart/form-data",
    )
    doc = Document.query.filter_by(original_filename="mystery3.pdf").first()

    client.post(f"/documents/{doc.id}/dismiss-suggested-type")
    db.session.refresh(doc)
    assert doc.doc_type == "other"
    assert doc.ai_suggested_doc_type is None


def test_set_primary_cv_unsets_previous_primary(client, db, make_user):
    make_user(email="d4@example.com", password="Password123!")
    login(client, "d4@example.com", "Password123!")

    client.post(
        "/documents/upload",
        data={"doc_type": "cv", "file": (io.BytesIO(VALID_PDF), "cv1.pdf")},
        content_type="multipart/form-data",
    )
    client.post(
        "/documents/upload",
        data={"doc_type": "cv", "file": (io.BytesIO(VALID_PDF), "cv2.pdf")},
        content_type="multipart/form-data",
    )
    doc1 = Document.query.filter_by(original_filename="cv1.pdf").first()
    doc2 = Document.query.filter_by(original_filename="cv2.pdf").first()

    client.post(f"/documents/{doc1.id}/set-primary/cv")
    client.post(f"/documents/{doc2.id}/set-primary/cv")

    db.session.refresh(doc1)
    db.session.refresh(doc2)
    assert doc1.is_primary_cv is False
    assert doc2.is_primary_cv is True


def test_empty_state_shown_when_no_documents(client, db, make_user):
    make_user(email="d8@example.com", password="Password123!")
    login(client, "d8@example.com", "Password123!")

    resp = client.get("/documents/")
    assert b"No documents yet" in resp.data


def test_document_not_used_in_any_application(client, db, make_user):
    make_user(email="d9@example.com", password="Password123!")
    login(client, "d9@example.com", "Password123!")
    client.post(
        "/documents/upload",
        data={"doc_type": "cv", "file": (io.BytesIO(VALID_PDF), "unused.pdf")},
        content_type="multipart/form-data",
    )

    resp = client.get("/documents/")
    assert b"Not used in any application" in resp.data


def test_document_used_in_applications_count(client, db, make_user):
    # Screens pass 5 (Documents, 2026-08-28): "Used in N applications" is a
    # query over the existing ApplicationDocument join, not new plumbing.
    user = make_user(email="d10@example.com", password="Password123!")
    login(client, "d10@example.com", "Password123!")

    doc = Document(
        user_id=user.id, doc_type="cv", original_filename="used.pdf",
        stored_filename="used-stored.pdf", storage_path="x/used-stored.pdf",
        mime_type="application/pdf", file_size=1000,
    )
    db.session.add(doc)
    db.session.commit()

    job = Job(title="Elektroniker", employment_type="Ausbildung", dedup_key="doc-usage-test")
    db.session.add(job)
    db.session.commit()
    application = Application(user_id=user.id, job_id=job.id, status="preparing")
    db.session.add(application)
    db.session.commit()
    db.session.add(ApplicationDocument(application_id=application.id, document_id=doc.id, order_index=0))
    db.session.commit()

    resp = client.get("/documents/")
    assert b"Used in 1 application" in resp.data
    assert b"Not used in any application" not in resp.data
