import io

from app.models.document import Document
from tests.conftest import login

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
