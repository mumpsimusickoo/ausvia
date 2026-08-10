"""
Generates a customized cover letter (Anschreiben) per job posting.
Uses a template with placeholders filled from the posting + your profile.
"""
from datetime import date

DEFAULT_TEMPLATE = """{your_name}
{your_address}
{your_email} | {your_phone}

{company}
{company_address}

{city}, {date}

Bewerbung als {job_title}

Sehr geehrte Damen und Herren,

mit großem Interesse habe ich Ihre Ausschreibung für die Ausbildung als {job_title} bei {company} gefunden. Da ich {study_field} studiere/studiert habe, passt diese Ausbildung sehr gut zu meinem bisherigen Werdegang und meinen Interessen im Bereich {field_keywords}.

{custom_paragraph}

Ich bin ein motivierter und lernbereiter Mensch, der gerne im Team arbeitet und praktische Herausforderungen sucht. Meine bisherigen Kenntnisse aus dem Studium möchte ich gerne in der Praxis vertiefen und freue mich darauf, bei {company} einen wichtigen Beitrag zu leisten.

Meine vollständigen Bewerbungsunterlagen (Lebenslauf, Zeugnisse und beglaubigte Übersetzungen) finden Sie im Anhang.

Über die Möglichkeit eines persönlichen Kennenlernens würde ich mich sehr freuen.

Mit freundlichen Grüßen
{your_name}
"""


def generate_custom_paragraph(company, job_title, company_blurb=None):
    """
    Builds one paragraph tailored to the company. If a short blurb about the
    company (e.g. scraped from their site or the job posting text) is available,
    it's woven in. Otherwise falls back to a generic but role-specific line.
    """
    if company_blurb:
        return (
            f"Besonders spannend finde ich, dass {company} {company_blurb.strip()} "
            f"Genau in diesem Umfeld möchte ich meine praktischen Fähigkeiten als "
            f"{job_title} einbringen und weiterentwickeln."
        )
    return (
        f"Besonders reizt mich an {company} die Möglichkeit, technisches Wissen direkt "
        f"in der Praxis anzuwenden und mich in einem professionellen Umfeld als "
        f"{job_title} weiterzuentwickeln."
    )


def build_cover_letter(profile, posting, company_blurb=None, template=None):
    """
    profile: dict with your_name, your_address, your_email, your_phone,
             study_field, field_keywords, city
    posting: dict from jobsearch.simplify_posting()
    company_blurb: optional short description of the company (plain text)
    """
    template = template or DEFAULT_TEMPLATE
    custom_paragraph = generate_custom_paragraph(
        posting["company"], posting["title"], company_blurb
    )

    return template.format(
        your_name=profile["your_name"],
        your_address=profile.get("your_address", ""),
        your_email=profile.get("your_email", ""),
        your_phone=profile.get("your_phone", ""),
        company=posting["company"] or "",
        company_address=posting.get("location", "") or "",
        city=profile.get("city", ""),
        date=date.today().strftime("%d.%m.%Y"),
        job_title=posting["title"] or "",
        study_field=profile.get("study_field", ""),
        field_keywords=profile.get("field_keywords", ""),
        custom_paragraph=custom_paragraph,
    )
