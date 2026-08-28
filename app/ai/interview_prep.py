"""AI-generated likely interview questions + talking points for one
application (Phase 9), grounded in the candidate's real profile and the
job/company's real stored facts. Available at any application status, not
gated to "Interview" only - a candidate may reasonably want to prepare
earlier. Same staleness/caching pattern as JobMatch/CompanyInsight (keyed
per application here, since that's the natural lookup on the page it's
shown on, and an Application is already unique per (user, job)). No
deterministic core - generating plausible interview questions is inherently
a language task - so mock mode declines honestly, same pattern as
app/companies/insights.py.
"""
from flask_babel import lazy_gettext as _l

from app.extensions import db
from app.ai.facts import format_candidate_facts, format_job_facts
from app.ai.prompts.interview_prep import build_interview_prep_prompt
from app.ai.provider_factory import get_provider
from app.ai.usage import record_usage
from app.i18n import get_locale
from app.models.ai import InterviewPrep
from app.models.user import utcnow

# i18n pass 3: deterministic app status message, follows the UI language -
# see the identical NOT_CONFIGURED_TEXT note in app/ai/cv_profile_statement.py.
NOT_CONFIGURED_TEXT = _l(
    "AI interview prep isn't available because no AI provider is configured "
    "(AI_PROVIDER=mock). The job and company details on this page are real; "
    "this would only be an AI-generated study aid layered on top."
)


def get_interview_prep(application):
    return InterviewPrep.query.filter_by(application_id=application.id).first()


def generate_interview_prep(user, application):
    profile = user.profile
    profile_updated_at = profile.updated_at if profile else None
    locale = get_locale()

    existing = get_interview_prep(application)
    if (
        existing and existing.prep_text
        and existing.profile_updated_at_snapshot == profile_updated_at
        and existing.generated_locale == locale
    ):
        return existing

    prep = existing or InterviewPrep(application_id=application.id)

    provider = get_provider()
    if provider.provider_name == "mock":
        prep.prep_text = str(NOT_CONFIGURED_TEXT)
        prep.provider = "mock"
    else:
        candidate_facts_text = format_candidate_facts(profile)
        job_facts_text = format_job_facts(application.job)
        system, prompt = build_interview_prep_prompt(candidate_facts_text, job_facts_text, locale)
        response = provider.complete(system, prompt, max_tokens=700)
        record_usage(user.id, "interview_prep", response)
        prep.prep_text = response.text
        prep.provider = response.provider

    prep.profile_updated_at_snapshot = profile_updated_at
    prep.generated_locale = locale
    prep.generated_at = utcnow()
    if not existing:
        db.session.add(prep)
    db.session.commit()
    return prep
