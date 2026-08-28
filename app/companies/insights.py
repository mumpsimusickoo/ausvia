"""
Caches the optional AI "why this company might fit you" synthesis
(CompanyInsight), same staleness/caching pattern as app/jobs/matching.py's
JobMatch: recompute only when the candidate profile has changed since the
last generation. There is no deterministic core here (unlike match
scoring) - interpreting a company's real facts against a profile is
inherently a language task, so mock mode declines honestly instead of
faking a synthesis, same honesty pattern as app/ai/reply_ai.py.
"""
from flask_babel import lazy_gettext as _l

from app.extensions import db
from app.ai.facts import format_candidate_facts
from app.ai.prompts.company import build_company_fit_prompt
from app.ai.provider_factory import get_provider
from app.ai.usage import record_usage
from app.i18n import get_locale
from app.models.ai import CompanyInsight
from app.models.user import utcnow

# i18n pass 3: deterministic app status message, follows the UI language -
# see the identical NOT_CONFIGURED_TEXT note in app/ai/cv_profile_statement.py.
NOT_CONFIGURED_TEXT = _l(
    "AI company insights aren't available because no AI provider is configured "
    "(AI_PROVIDER=mock). The company details above are real; this note would "
    "only be an AI interpretation layered on top, not new information."
)


def get_company_insight(user, company):
    return CompanyInsight.query.filter_by(user_id=user.id, company_id=company.id).first()


def generate_company_insight(user, company, jobs):
    profile = user.profile
    profile_updated_at = profile.updated_at if profile else None
    locale = get_locale()

    existing = get_company_insight(user, company)
    if (
        existing and existing.summary_text
        and existing.profile_updated_at_snapshot == profile_updated_at
        and existing.generated_locale == locale
    ):
        return existing

    insight = existing or CompanyInsight(user_id=user.id, company_id=company.id)

    provider = get_provider()
    if provider.provider_name == "mock":
        insight.summary_text = str(NOT_CONFIGURED_TEXT)
        insight.provider = "mock"
    else:
        candidate_facts_text = format_candidate_facts(profile)
        system, prompt = build_company_fit_prompt(profile, company, jobs, candidate_facts_text, locale)
        response = provider.complete(system, prompt, max_tokens=300)
        record_usage(user.id, "company_insight", response)
        insight.summary_text = response.text
        insight.provider = response.provider

    insight.profile_updated_at_snapshot = profile_updated_at
    insight.generated_locale = locale
    insight.generated_at = utcnow()
    if not existing:
        db.session.add(insight)
    db.session.commit()
    return insight
