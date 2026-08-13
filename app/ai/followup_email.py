"""Follow-up email drafting (Phase 9) for an application sitting in Sent or
Follow-up status - user-triggered, same shape as app/ai/email_gen.py's
original application email: an AI path plus a genuine deterministic
template fallback (unlike the profile-coaching/interview-prep/job-explainer/
process-qa features in this same phase, drafting a short formulaic
follow-up email is exactly the kind of task the existing cover-letter/email
template fallbacks already prove is doable deterministically - not
inherently a language-interpretation task the way reviewing a profile or
generating interview questions is). Always regenerates on request (no
staleness cache) - matches GeneratedEmail's own "regenerating overwrites it"
behavior, not JobMatch/CompanyInsight's cache-until-profile-changes pattern.
"""
from app.ai.email_gen import _parse_email_response
from app.ai.facts import format_candidate_facts, format_job_facts
from app.ai.prompts.followup_email import build_followup_email_prompt
from app.ai.provider_factory import get_provider
from app.ai.salutation import build_salutation
from app.ai.usage import record_usage


def render_template_followup_email(profile, application):
    job = application.job
    salutation = build_salutation(job.contact_person)
    name = profile.full_name or "[Name not set in profile]"
    sent_date_text = application.sent_at.strftime("%d.%m.%Y") if application.sent_at else "kürzlich"
    subject = f"Nachfrage zu meiner Bewerbung als {job.title}"
    body = (
        f"{salutation},\n\n"
        f"ich habe mich am {sent_date_text} um die Ausbildung als {job.title} bei "
        f"{job.company_name or 'Ihrem Unternehmen'} beworben und wollte freundlich nachfragen, "
        f"ob es bereits Neuigkeiten zu meiner Bewerbung gibt.\n\n"
        f"Für Rückfragen stehe ich Ihnen jederzeit gerne zur Verfügung.\n\n"
        f"Mit freundlichen Grüßen\n{name}"
    )
    return subject, body


def generate_followup_email(user, application):
    """Returns (subject, body, source, provider_name)."""
    provider = get_provider()

    if provider.provider_name == "mock":
        subject, body = render_template_followup_email(user.profile, application)
        return subject, body, "template", None

    sent_date_text = application.sent_at.strftime("%d.%m.%Y") if application.sent_at else "recently"
    system, prompt = build_followup_email_prompt(
        format_candidate_facts(user.profile),
        format_job_facts(application.job),
        build_salutation(application.job.contact_person),
        sent_date_text,
    )
    response = provider.complete(system, prompt, max_tokens=400)
    record_usage(user.id, "followup_email_generation", response)

    subject, body = _parse_email_response(response.text)
    if not subject:
        subject = f"Nachfrage zu meiner Bewerbung als {application.job.title}"
    return subject, body, "ai", response.provider
