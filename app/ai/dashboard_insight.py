"""Cross-application AI synthesis (Screens pass 3, Dashboard, 2026-08-27) -
the first Intelligence surface that aggregates across a user's whole
application set rather than one job/application/reply. Same
staleness/caching pattern as JobMatch/CompanyInsight/ProfileCoaching, with
one addition: application_count_snapshot alongside profile_updated_at_snapshot,
since the input set here is "all of a user's applications" - a newly
started or deleted application can make a cached synthesis stale even when
the profile hasn't changed. Count, not a hash of every application's full
state (status, gaps, etc.), is a deliberate, cheap approximation: exact
enough to catch the common case (an application added or removed) without
tracking a fingerprint of every field that could invalidate it - a
regenerate button already covers a status change that doesn't touch the
count, the same way "click Regenerate" is already how every other
Intelligence surface handles no-auto-invalidation drift.

No deterministic core, same reasoning as app/ai/profile_coaching.py -
mock mode declines honestly rather than faking a synthesis.
"""
from app.extensions import db
from app.ai.facts import format_candidate_facts, format_applications_summary
from app.ai.prompts.dashboard_insight import build_dashboard_insight_prompt
from app.ai.provider_factory import get_provider
from app.ai.usage import record_usage
from app.models.ai import DashboardInsight
from app.models.user import utcnow

NOT_CONFIGURED_TEXT = (
    "AI cross-application insights aren't available because no AI provider is "
    "configured (AI_PROVIDER=mock). Your applications and profile above are "
    "real; this would only be an AI-spotted pattern layered on top."
)

# Fewer than this, there's nothing meaningful to compare - a "pattern" across
# one or two applications isn't a pattern, it's just describing them. Matches
# the honest-emptiness stance the prompt itself is instructed to take, but
# short-circuits before spending a call on a set too small to say anything
# real about.
MIN_APPLICATIONS_FOR_INSIGHT = 2


def get_dashboard_insight(user):
    return DashboardInsight.query.filter_by(user_id=user.id).first()


def generate_dashboard_insight(user, applications, match_by_job_id=None):
    profile = user.profile
    profile_updated_at = profile.updated_at if profile else None
    application_count = len(applications)

    existing = get_dashboard_insight(user)
    if (
        existing
        and existing.summary_text
        and existing.profile_updated_at_snapshot == profile_updated_at
        and existing.application_count_snapshot == application_count
    ):
        return existing

    insight = existing or DashboardInsight(user_id=user.id)

    provider = get_provider()
    if provider.provider_name == "mock":
        insight.summary_text = NOT_CONFIGURED_TEXT
        insight.provider = "mock"
    else:
        candidate_facts_text = format_candidate_facts(profile)
        applications_summary_text = format_applications_summary(applications, match_by_job_id)
        system, prompt = build_dashboard_insight_prompt(candidate_facts_text, applications_summary_text)
        response = provider.complete(system, prompt, max_tokens=250)
        record_usage(user.id, "dashboard_insight", response)
        insight.summary_text = response.text
        insight.provider = response.provider

    insight.profile_updated_at_snapshot = profile_updated_at
    insight.application_count_snapshot = application_count
    insight.generated_at = utcnow()
    if not existing:
        db.session.add(insight)
    db.session.commit()
    return insight
