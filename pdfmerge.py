"""
Turns the generated cover letter text into a PDF page, then merges it with
the CV, diploma, and translated papers into a single application PDF.
"""
import io
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from pypdf import PdfReader, PdfWriter


def text_to_pdf_bytes(text):
    """Render plain text (paragraphs separated by blank lines) as a clean A4 PDF page."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=25 * mm, rightMargin=25 * mm,
        topMargin=25 * mm, bottomMargin=25 * mm,
    )
    styles = getSampleStyleSheet()
    body_style = ParagraphStyle(
        "Body", parent=styles["Normal"], fontSize=11, leading=16, spaceAfter=10
    )

    story = []
    for para in text.strip().split("\n\n"):
        # preserve single line breaks within a paragraph (e.g. address block)
        safe = para.replace("\n", "<br/>")
        story.append(Paragraph(safe, body_style))
        story.append(Spacer(1, 4))

    doc.build(story)
    buf.seek(0)
    return buf.read()


def merge_application_pdf(cover_letter_text, cv_path, diploma_path, translations_paths, output_path):
    """
    Builds the final single PDF: cover letter (generated) + CV + diploma + translated papers.
    translations_paths: list of file paths (can be empty).
    """
    writer = PdfWriter()

    # 1. Cover letter (generated in-memory)
    cover_pdf_bytes = text_to_pdf_bytes(cover_letter_text)
    cover_reader = PdfReader(io.BytesIO(cover_pdf_bytes))
    for page in cover_reader.pages:
        writer.add_page(page)

    # 2. CV
    for page in PdfReader(cv_path).pages:
        writer.add_page(page)

    # 3. Diploma
    for page in PdfReader(diploma_path).pages:
        writer.add_page(page)

    # 4. Translated papers (any number)
    for path in translations_paths:
        for page in PdfReader(path).pages:
            writer.add_page(page)

    with open(output_path, "wb") as f:
        writer.write(f)

    return output_path
