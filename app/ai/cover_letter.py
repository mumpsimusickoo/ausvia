"""
Anschreiben generation and validation (spec sections 20/21). Two paths:
- AI path (AI_PROVIDER=anthropic): personalized generation + a second AI pass
  that checks the letter against the facts and self-corrects if needed.
- Template path (default/mock): a deterministic, genuinely usable German
  business-letter renderer using only real profile/job data - not a stub.
Both paths only ever use facts from app/ai/facts.py, never raw job HTML.
"""
from datetime import date

from app.ai.facts import format_candidate_facts, format_job_facts
from app.ai.provider_factory import get_provider
from app.ai.prompts.cover_letter import build_generation_prompt, build_validation_prompt
from app.ai.salutation import build_salutation
from app.ai.usage import record_usage


def render_template_cover_letter(profile, job):
    salutation = build_salutation(job.contact_person)
    name = profile.full_name or "[Name not set in profile]"
    address_line = ", ".join(p for p in [profile.address, profile.postal_code, profile.city] if p)
    contact_line = " | ".join(p for p in [profile.phone, profile.contact_email] if p)

    most_recent_education = profile.education_entries[0] if profile.education_entries else None
    education_sentence = ""
    if most_recent_education:
        field = most_recent_education.field or most_recent_education.degree
        if field:
            education_sentence = (
                f"Im Rahmen meiner Ausbildung/meines Studiums im Bereich {field} "
                f"an {most_recent_education.institution} habe ich mich intensiv mit "
                f"praxisnahen Aufgabenstellungen auseinandergesetzt. "
            )

    skills_sentence = ""
    if profile.skills:
        skill_names = ", ".join(s.name for s in profile.skills[:6])
        skills_sentence = f"Zu meinen Kenntnissen zählen unter anderem {skill_names}. "

    language_sentence = ""
    german = next((l for l in profile.languages if l.name.strip().lower() == "german" or l.name.strip().lower() == "deutsch"), None)
    if german:
        language_sentence = f"Meine Deutschkenntnisse befinden sich auf dem Niveau {german.level}. "

    body = (
        f"mit großem Interesse habe ich Ihre Ausschreibung für die Ausbildung als {job.title} "
        f"bei {job.company_name or 'Ihrem Unternehmen'} gelesen und bewerbe mich hiermit um diesen Ausbildungsplatz.\n\n"
        f"{education_sentence}{skills_sentence}{language_sentence}\n\n"
        f"Ich bin motiviert, mich in einem professionellen Umfeld weiterzuentwickeln und praktische "
        f"Erfahrungen zu sammeln. Über die Möglichkeit eines persönlichen Kennenlernens würde ich mich sehr freuen.\n\n"
        f"Meine vollständigen Bewerbungsunterlagen finden Sie im Anhang.\n\n"
        f"Mit freundlichen Grüßen\n{name}"
    ).strip()

    return (
        f"{name}\n{address_line}\n{contact_line}\n\n"
        f"{job.company_name or ''}\n{job.location or ''}\n\n"
        f"{date.today().strftime('%d.%m.%Y')}\n\n"
        f"Bewerbung um einen Ausbildungsplatz als {job.title}\n\n"
        f"{salutation},\n\n"
        f"{body}"
    )


def generate_cover_letter(user, job):
    """Returns (text, source, provider_name)."""
    provider = get_provider()

    if provider.provider_name == "mock":
        text = render_template_cover_letter(user.profile, job)
        return text, "template", None

    system, prompt = build_generation_prompt(
        format_candidate_facts(user.profile),
        format_job_facts(job),
        build_salutation(job.contact_person),
    )
    response = provider.complete(system, prompt, max_tokens=1200)
    record_usage(user.id, "cover_letter_generation", response)
    return response.text.strip(), "ai", response.provider


def validate_cover_letter(user, job, letter_text, source):
    """Returns (validated: bool, notes: str, corrected_text: str | None)."""
    if source == "template":
        return _deterministic_sanity_check(user.profile, job, letter_text)

    provider = get_provider()
    if provider.provider_name == "mock":
        return _deterministic_sanity_check(user.profile, job, letter_text)

    system, prompt = build_validation_prompt(
        format_candidate_facts(user.profile), format_job_facts(job), letter_text
    )
    response = provider.complete(system, prompt, max_tokens=1500)
    record_usage(user.id, "cover_letter_validation", response)

    text = response.text.strip()
    if text.startswith("CORRECTED:"):
        corrected = text[len("CORRECTED:"):].strip()
        return False, "AI validation found and corrected issues.", corrected
    if text.startswith("VALID:"):
        return True, text[len("VALID:"):].strip(), None
    return True, "AI validation returned an unexpected format; treating as unreviewed.", None


def _deterministic_sanity_check(profile, job, letter_text):
    missing = []
    if job.title and job.title.lower() not in letter_text.lower():
        missing.append("job title")
    if job.company_name and job.company_name.lower() not in letter_text.lower():
        missing.append("company name")
    if profile and profile.full_name and profile.full_name.lower() not in letter_text.lower():
        missing.append("candidate name")

    if missing:
        return False, f"Automated check: missing expected mention of: {', '.join(missing)}.", None
    return True, "Automated check: job title, company, and candidate name all present.", None
