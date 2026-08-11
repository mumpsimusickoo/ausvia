"""Application email generation (spec section 22) - AI path + template fallback."""
from app.ai.facts import format_candidate_facts, format_job_facts
from app.ai.provider_factory import get_provider
from app.ai.prompts.email import build_email_prompt
from app.ai.salutation import build_salutation
from app.ai.usage import record_usage


def render_template_email(profile, job, attachment_summary):
    salutation = build_salutation(job.contact_person)
    name = profile.full_name or "[Name not set in profile]"
    subject = f"Bewerbung um einen Ausbildungsplatz als {job.title}"
    body = (
        f"{salutation},\n\n"
        f"anbei sende ich Ihnen meine Bewerbungsunterlagen für die Ausbildung als {job.title} "
        f"bei {job.company_name or 'Ihrem Unternehmen'}.\n\n"
        f"Beigefügt finden Sie: {attachment_summary}.\n\n"
        f"Für Rückfragen stehe ich Ihnen gerne zur Verfügung.\n\n"
        f"Mit freundlichen Grüßen\n{name}"
    )
    return subject, body


def generate_email(user, job, attachment_summary):
    """Returns (subject, body, source, provider_name)."""
    provider = get_provider()

    if provider.provider_name == "mock":
        subject, body = render_template_email(user.profile, job, attachment_summary)
        return subject, body, "template", None

    system, prompt = build_email_prompt(
        format_candidate_facts(user.profile),
        format_job_facts(job),
        build_salutation(job.contact_person),
        attachment_summary,
    )
    response = provider.complete(system, prompt, max_tokens=500)
    record_usage(user.id, "email_generation", response)

    subject, body = _parse_email_response(response.text)
    if not subject:
        subject = f"Bewerbung um einen Ausbildungsplatz als {job.title}"
    return subject, body, "ai", response.provider


def _parse_email_response(text):
    subject = ""
    body = text
    if "SUBJECT:" in text and "BODY:" in text:
        _, rest = text.split("SUBJECT:", 1)
        subject_part, body_part = rest.split("BODY:", 1)
        subject = subject_part.strip()
        body = body_part.strip()
    return subject, body
