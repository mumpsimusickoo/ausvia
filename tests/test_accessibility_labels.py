"""Regression tests for QA Phase 7 findings W6 (unlabeled form fields) and
W7 (validation errors not programmatically associated with their field)."""
import io
import re

from tests.conftest import login
from pdfmerge import text_to_pdf_bytes


def _label_for_ids(html):
    return set(re.findall(r'<label[^>]*\bfor="([^"]+)"', html))


def _element_ids(html):
    return set(re.findall(r'\bid="([^"]+)"', html))


def test_document_upload_fields_have_associated_labels(client, db, make_user):
    make_user(email="a11y1@example.com", password="Password123!")
    login(client, "a11y1@example.com", "Password123!")

    resp = client.get("/documents/")
    html = resp.get_data(as_text=True)

    label_fors = _label_for_ids(html)
    ids = _element_ids(html)
    for expected in ("upload-doc-type", "upload-file", "upload-description"):
        assert expected in label_fors, f"no <label for={expected!r}> found"
        assert expected in ids, f"no element with id={expected!r} found"


def test_application_detail_generated_content_fields_have_associated_labels(client, db, make_user):
    from tests.test_applications import make_job, start_application

    make_user(email="a11y2@example.com", password="Password123!")
    login(client, "a11y2@example.com", "Password123!")
    job = make_job(db)
    _, application = start_application(client, db, job)

    client.post(f"/applications/{application.id}/generate-cover-letter")
    client.post(f"/applications/{application.id}/generate-email")

    resp = client.get(f"/applications/{application.id}")
    html = resp.get_data(as_text=True)

    label_fors = _label_for_ids(html)
    ids = _element_ids(html)
    assert "cover-letter-content" in label_fors
    assert "cover-letter-content" in ids
    assert "email-body" in label_fors
    assert "email-body" in ids


def test_registration_validation_error_is_aria_linked_to_its_field(client, db):
    resp = client.post(
        "/auth/register",
        data={
            "access_code": "not-a-valid-format",
            "email": "not-an-email",
            "password": "short",
            "confirm_password": "different",
        },
        follow_redirects=True,
    )
    html = resp.get_data(as_text=True)

    # every field with a rendered error must carry aria-invalid + point its
    # aria-describedby at a container that actually exists in the page
    described_by_ids = re.findall(r'aria-describedby="([^"]+)"', html)
    assert described_by_ids, "expected at least one aria-describedby on an invalid field"
    for described_id in described_by_ids:
        assert f'id="{described_id}"' in html, f"aria-describedby target #{described_id} does not exist in the page"
    assert 'aria-invalid="true"' in html
