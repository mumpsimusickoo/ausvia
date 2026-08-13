"""AI plain-language summary of a job posting's original text (Phase 9),
grounded only in the posting's real stored description - same
untrusted-external-text treatment as the rest of app/ai/prompts/. Same
staleness/caching pattern as JobMatch/CompanyInsight, keyed per (user, job).

Deliberately personalized per candidate rather than shared across users the
way Job's own fields are: this pass chose to calibrate the summary to the
candidate's own stated German level (profile.languages), since AUSVIA's
whole audience is international candidates with hugely varying German
levels (A1-C2, tracked per spec) - a "plain language" explainer that
doesn't account for the reader's actual comprehension level is much less
useful than one that does. The tradeoff is losing the ability to share one
explainer across every candidate looking at the same posting; given the
personalization is the point of the feature, that tradeoff is the right
one here.

No deterministic core - simplifying dense German text is inherently a
language task - so mock mode declines honestly, same pattern as
app/companies/insights.py.
"""
from app.extensions import db
from app.ai.prompts.job_explainer import build_job_explainer_prompt
from app.ai.provider_factory import get_provider
from app.ai.usage import record_usage
from app.models.ai import JobExplainer
from app.models.user import utcnow

NOT_CONFIGURED_TEXT = (
    "AI plain-language summaries aren't available because no AI provider is "
    "configured (AI_PROVIDER=mock). The posting's original text is shown "
    "below in full; this would only be an AI simplification layered on top."
)


def _candidate_german_level(profile):
    if not profile:
        return None
    german = next(
        (l for l in profile.languages if l.name.strip().lower() in ("german", "deutsch")),
        None,
    )
    return german.level if german else None


def get_job_explainer(user, job):
    return JobExplainer.query.filter_by(user_id=user.id, job_id=job.id).first()


def generate_job_explainer(user, job):
    profile = user.profile
    profile_updated_at = profile.updated_at if profile else None

    existing = get_job_explainer(user, job)
    if existing and existing.explainer_text and existing.profile_updated_at_snapshot == profile_updated_at:
        return existing

    explainer = existing or JobExplainer(user_id=user.id, job_id=job.id)

    provider = get_provider()
    if provider.provider_name == "mock":
        explainer.explainer_text = NOT_CONFIGURED_TEXT
        explainer.provider = "mock"
    else:
        german_level = _candidate_german_level(profile)
        system, prompt = build_job_explainer_prompt(job.description or "", german_level)
        response = provider.complete(system, prompt, max_tokens=500)
        record_usage(user.id, "job_explainer", response)
        explainer.explainer_text = response.text
        explainer.provider = response.provider

    explainer.profile_updated_at_snapshot = profile_updated_at
    explainer.generated_at = utcnow()
    if not existing:
        db.session.add(explainer)
    db.session.commit()
    return explainer
