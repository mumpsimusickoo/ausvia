"""
Assembles the final application PDF package (spec sections 23/24): generated
cover letter first, then the user's selected documents in their chosen order.
Extends pdfmerge.py's text-to-PDF rendering (kept as-is) with support for
image documents (JPG/PNG), since the document library allows those alongside
PDFs. Original uploaded files are never modified - only read.
"""
import io
import os
import re
import unicodedata

from PIL import Image
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4

from pdfmerge import text_to_pdf_bytes

IMAGE_MIME_TYPES = {"image/jpeg", "image/png"}


def image_to_pdf_bytes(image_path):
    """Renders a JPG/PNG as a single A4 PDF page, fit within the page with margins."""
    margin = 20 * 72 / 25.4  # ~20mm in points
    page_w, page_h = A4
    max_w, max_h = page_w - 2 * margin, page_h - 2 * margin

    img = Image.open(image_path)
    img_w, img_h = img.size
    scale = min(max_w / img_w, max_h / img_h, 1.0)
    draw_w, draw_h = img_w * scale, img_h * scale
    x = (page_w - draw_w) / 2
    y = (page_h - draw_h) / 2

    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.drawImage(image_path, x, y, width=draw_w, height=draw_h, preserveAspectRatio=True, mask="auto")
    c.showPage()
    c.save()
    buf.seek(0)
    return buf.read()


def build_application_pdf(cover_letter_text, documents, output_path):
    """documents: list of (absolute_file_path, mime_type) in package order."""
    writer = PdfWriter()

    cover_bytes = text_to_pdf_bytes(cover_letter_text)
    for page in PdfReader(io.BytesIO(cover_bytes)).pages:
        writer.add_page(page)

    for path, mime_type in documents:
        if mime_type in IMAGE_MIME_TYPES:
            page_bytes = image_to_pdf_bytes(path)
            for page in PdfReader(io.BytesIO(page_bytes)).pages:
                writer.add_page(page)
        else:
            for page in PdfReader(path).pages:
                writer.add_page(page)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "wb") as f:
        writer.write(f)

    return output_path


def safe_package_filename(candidate_name, company_name, job_title):
    """Bewerbung_Name_Company_Title.pdf - sanitized, ASCII-safe, length-capped."""
    def clean(value):
        value = value or "Unbekannt"
        value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
        value = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")
        return value[:40] or "Unbekannt"

    return f"Bewerbung_{clean(candidate_name)}_{clean(company_name)}_{clean(job_title)}.pdf"
