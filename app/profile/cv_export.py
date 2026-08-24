"""Renders the candidate's stored profile data into a real, standalone CV
PDF (design-audit decision, 2026-08-24). Genuinely new capability, not an
extension of app/applications/pdf_package.py: that module only concatenates
already-existing PDF pages together, whereas this builds fresh formatted
content from structured data via reportlab's platypus flowables (the same
library already used for cover-letter rendering in the top-level
pdfmerge.py, just aimed at Profile/Education/Experience/Skill/Language
instead of AI-generated text).

Deliberately NOT an AI feature: no provider call, no generated wording -
every line comes straight from a stored field, and a field that's empty is
simply omitted rather than invented or filled with placeholder text. This
is also deliberately profile-scoped, not application-scoped - it does not
read or write app.models.ai.CvProfileStatement (the per-application
"Kurzprofil" summary), which stays exactly what it already was.
"""
import io
import re
import unicodedata

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer

from app.models.user import utcnow


def _date_range(start, end):
    def fmt(d):
        return d.strftime("%m/%Y") if d else None

    start_s, end_s = fmt(start), fmt(end)
    if start_s and end_s:
        return f"{start_s} – {end_s}"
    if start_s:
        return f"{start_s} – present"
    return end_s or ""


def _styles():
    base = getSampleStyleSheet()
    return {
        "name": ParagraphStyle(
            "CVName", parent=base["Title"], fontSize=22, leading=26, alignment=TA_CENTER,
        ),
        "contact": ParagraphStyle(
            "CVContact", parent=base["Normal"], fontSize=9.5, leading=13,
            alignment=TA_CENTER, textColor=colors.HexColor("#475569"),
        ),
        "section": ParagraphStyle(
            "CVSection", parent=base["Heading2"], fontSize=13, leading=16,
            spaceBefore=14, spaceAfter=6, textColor=colors.HexColor("#0f7379"),
        ),
        "entry_title": ParagraphStyle(
            "CVEntryTitle", parent=base["Normal"], fontSize=11, leading=14, fontName="Helvetica-Bold",
        ),
        "entry_meta": ParagraphStyle(
            "CVEntryMeta", parent=base["Normal"], fontSize=9.5, leading=13,
            textColor=colors.HexColor("#64748b"), spaceAfter=2,
        ),
        "body": ParagraphStyle(
            "CVBody", parent=base["Normal"], fontSize=9.5, leading=13.5, spaceBefore=2, spaceAfter=6,
        ),
        "footer": ParagraphStyle(
            "CVFooter", parent=base["Normal"], fontSize=8, leading=11,
            alignment=TA_CENTER, textColor=colors.HexColor("#94a3b8"),
        ),
    }


def _contact_line(profile):
    parts = []
    address_bits = [
        profile.address,
        " ".join(p for p in [profile.postal_code, profile.city] if p) or None,
        profile.country,
    ]
    address_line = ", ".join(p for p in address_bits if p)
    if address_line:
        parts.append(address_line)
    if profile.phone:
        parts.append(profile.phone)
    if profile.contact_email:
        parts.append(profile.contact_email)
    if profile.nationality:
        parts.append(profile.nationality)
    return " · ".join(parts)


def build_cv_pdf(profile):
    """Returns PDF bytes for one CandidateProfile. Renders only fields that
    are actually populated - nothing is invented, nothing is AI-generated."""
    styles = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=22 * mm, rightMargin=22 * mm, topMargin=20 * mm, bottomMargin=20 * mm,
    )

    story = [Paragraph(profile.full_name or "Lebenslauf", styles["name"])]

    contact_line = _contact_line(profile)
    if contact_line:
        story.append(Paragraph(contact_line, styles["contact"]))

    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#e2e8f0"), thickness=1))

    if profile.education_entries:
        story.append(Paragraph("Education", styles["section"]))
        for edu in profile.education_entries:
            title = " · ".join(p for p in [edu.degree, edu.field] if p) or edu.institution
            story.append(Paragraph(title, styles["entry_title"]))
            meta_bits = []
            if edu.degree or edu.field:
                meta_bits.append(edu.institution)
            if edu.country:
                meta_bits.append(edu.country)
            meta_line = " — ".join(p for p in [", ".join(meta_bits), _date_range(edu.start_date, edu.end_date)] if p)
            if meta_line:
                story.append(Paragraph(meta_line, styles["entry_meta"]))
            if edu.description:
                story.append(Paragraph(edu.description.replace("\n", "<br/>"), styles["body"]))

    if profile.experience_entries:
        story.append(Paragraph("Experience", styles["section"]))
        for exp in profile.experience_entries:
            story.append(Paragraph(exp.role or exp.company, styles["entry_title"]))
            meta_bits = [exp.company] if exp.role else []
            meta_line = " — ".join(p for p in [", ".join(meta_bits), _date_range(exp.start_date, exp.end_date)] if p)
            if meta_line:
                story.append(Paragraph(meta_line, styles["entry_meta"]))
            if exp.responsibilities:
                story.append(Paragraph(exp.responsibilities.replace("\n", "<br/>"), styles["body"]))
            if exp.achievements:
                story.append(Paragraph(exp.achievements.replace("\n", "<br/>"), styles["body"]))

    if profile.skills:
        story.append(Paragraph("Skills", styles["section"]))
        skill_line = ", ".join(
            f"{s.name} ({s.proficiency})" if s.proficiency else s.name for s in profile.skills
        )
        story.append(Paragraph(skill_line, styles["body"]))

    if profile.languages:
        story.append(Paragraph("Languages", styles["section"]))
        lang_line = ", ".join(
            f"{lang.name} ({lang.level})" if lang.level else lang.name for lang in profile.languages
        )
        story.append(Paragraph(lang_line, styles["body"]))

    story.append(Spacer(1, 16))
    story.append(Paragraph(
        f"Generated by AUSVIA from the candidate's own profile data · {utcnow().strftime('%d.%m.%Y')}",
        styles["footer"],
    ))

    doc.build(story)
    buf.seek(0)
    return buf.read()


def safe_cv_filename(full_name):
    def clean(value):
        value = value or "Kandidat"
        value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
        value = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")
        return value[:60] or "Kandidat"

    return f"Lebenslauf_{clean(full_name)}.pdf"
