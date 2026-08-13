"""Standalone AI review of the whole candidate profile (Phase 9), independent
of any one job posting - distinct from app/jobs/matching.py's job-specific
improvement tips. Same staleness/caching pattern as JobMatch/CompanyInsight:
recompute only when the profile has changed since the last generation.
There's no deterministic core here - reviewing a career narrative is
inherently a language task - so mock mode declines honestly instead of
faking a review, same pattern as app/companies/insights.py.
"""
from app.extensions import db
from app.ai.facts import format_candidate_facts
from app.ai.prompts.profile_coaching import build_profile_coaching_prompt
from app.ai.provider_factory import get_provider
from app.ai.usage import record_usage
from app.models.ai import ProfileCoaching
from app.models.user import utcnow

NOT_CONFIGURED_TEXT = (
    "AI profile coaching isn't available because no AI provider is configured "
    "(AI_PROVIDER=mock). Your profile data itself is real and complete as shown "
    "above; this would only be an AI review layered on top, not new information."
)


def get_profile_coaching(user):
    return ProfileCoaching.query.filter_by(user_id=user.id).first()


def generate_profile_coaching(user):
    profile = user.profile
    profile_updated_at = profile.updated_at if profile else None

    existing = get_profile_coaching(user)
    if existing and existing.summary_text and existing.profile_updated_at_snapshot == profile_updated_at:
        return existing

    coaching = existing or ProfileCoaching(user_id=user.id)

    provider = get_provider()
    if provider.provider_name == "mock":
        coaching.summary_text = NOT_CONFIGURED_TEXT
        coaching.provider = "mock"
    else:
        candidate_facts_text = format_candidate_facts(profile)
        system, prompt = build_profile_coaching_prompt(candidate_facts_text)
        response = provider.complete(system, prompt, max_tokens=500)
        record_usage(user.id, "profile_coaching", response)
        coaching.summary_text = response.text
        coaching.provider = response.provider

    coaching.profile_updated_at_snapshot = profile_updated_at
    coaching.generated_at = utcnow()
    if not existing:
        db.session.add(coaching)
    db.session.commit()
    return coaching
