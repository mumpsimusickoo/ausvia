"""Direct tests for app/applications/pdf_package.py - the actual PDF
assembly logic (as opposed to tests/test_applications.py's route-level
coverage, which only checks that a package file exists and downloads with
the right content-type, never its actual page count or extractable text).

Written as real, dedicated evidence for the Phase 8 pypdf 4.3.1 -> 6.15.0
upgrade (D6/2.5 decision) - exercises all three page-source code paths
(generated cover letter, a real uploaded PDF, and an uploaded image
converted to a PDF page) and inspects the assembled output with pypdf
itself, not just "no exception was raised."
"""
import io
import os

from PIL import Image
from pypdf import PdfReader

from app.applications.pdf_package import build_application_pdf, image_to_pdf_bytes, safe_package_filename
from pdfmerge import text_to_pdf_bytes


def _make_real_pdf(tmp_path, name, text):
    """A real, structurally valid single-page PDF via the same renderer the
    app itself uses for the cover letter - not a hand-crafted %PDF stub."""
    path = tmp_path / name
    path.write_bytes(text_to_pdf_bytes(text))
    return str(path)


def _make_real_png(tmp_path, name, size=(300, 200), color=(40, 60, 120)):
    path = tmp_path / name
    Image.new("RGB", size, color).save(path, format="PNG")
    return str(path)


def test_build_application_pdf_assembles_all_three_page_sources_correctly(tmp_path):
    cv_path = _make_real_pdf(tmp_path, "cv.pdf", "Karim Boulaid\nCurriculum Vitae\n\nISET Sfax, Automatisme et Informatique Industrielle.")
    diploma_image_path = _make_real_png(tmp_path, "diploma.png")
    output_path = str(tmp_path / "package" / "output.pdf")

    cover_letter_text = (
        "Sehr geehrte Damen und Herren,\n\n"
        "mit großem Interesse bewerbe ich mich um die Ausbildung als Elektroniker.\n\n"
        "Mit freundlichen Grüßen\nKarim Boulaid"
    )

    build_application_pdf(
        cover_letter_text,
        documents=[(cv_path, "application/pdf"), (diploma_image_path, "image/png")],
        output_path=output_path,
    )

    assert os.path.exists(output_path)
    with open(output_path, "rb") as f:
        assert f.read(5) == b"%PDF-"

    reader = PdfReader(output_path)
    # 1 cover letter page + 1 CV page + 1 converted image page
    assert len(reader.pages) == 3

    cover_page_text = reader.pages[0].extract_text()
    assert "Ausbildung als Elektroniker" in cover_page_text

    cv_page_text = reader.pages[1].extract_text()
    assert "Karim Boulaid" in cv_page_text
    assert "Curriculum Vitae" in cv_page_text

    # page 3 is a rendered image with no extractable text - just confirm it's
    # a real page with real (A4) dimensions, not a blank/corrupt stub
    image_page = reader.pages[2]
    assert float(image_page.mediabox.width) > 0
    assert float(image_page.mediabox.height) > 0


def test_build_application_pdf_with_multiple_pdf_documents_preserves_order(tmp_path):
    cv_path = _make_real_pdf(tmp_path, "cv.pdf", "CV content.")
    diploma_path = _make_real_pdf(tmp_path, "diploma.pdf", "Diploma content.")
    translation_path = _make_real_pdf(tmp_path, "translation.pdf", "Translation content.")
    output_path = str(tmp_path / "output.pdf")

    build_application_pdf(
        "Cover letter content.",
        documents=[
            (cv_path, "application/pdf"),
            (diploma_path, "application/pdf"),
            (translation_path, "application/pdf"),
        ],
        output_path=output_path,
    )

    reader = PdfReader(output_path)
    assert len(reader.pages) == 4  # cover letter + 3 documents
    texts = [p.extract_text() for p in reader.pages]
    assert "Cover letter content." in texts[0]
    assert "CV content." in texts[1]
    assert "Diploma content." in texts[2]
    assert "Translation content." in texts[3]


def test_build_application_pdf_with_no_extra_documents_is_just_the_cover_letter(tmp_path):
    output_path = str(tmp_path / "output.pdf")
    build_application_pdf("Solo cover letter.", documents=[], output_path=output_path)

    reader = PdfReader(output_path)
    assert len(reader.pages) == 1
    assert "Solo cover letter." in reader.pages[0].extract_text()


def test_image_to_pdf_bytes_produces_a_valid_single_page_a4_pdf(tmp_path):
    png_path = _make_real_png(tmp_path, "photo.png", size=(1200, 800))
    pdf_bytes = image_to_pdf_bytes(png_path)

    assert pdf_bytes[:5] == b"%PDF-"
    reader = PdfReader(io.BytesIO(pdf_bytes))
    assert len(reader.pages) == 1
    # A4 in points, per reportlab.lib.pagesizes.A4
    assert round(float(reader.pages[0].mediabox.width)) == 595
    assert round(float(reader.pages[0].mediabox.height)) == 842


def test_safe_package_filename_unaffected_by_pypdf_version():
    name = safe_package_filename("Karim Boulaid", "Siemens AG", "Elektroniker für Automatisierungstechnik")
    assert name == "Bewerbung_Karim_Boulaid_Siemens_AG_Elektroniker_fur_Automatisierungstechnik.pdf"
