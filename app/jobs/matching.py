"""
Orchestrates the deterministic matching engine (app/ai/matching.py) with
caching (spec section 37: don't recompute stable analyses unnecessarily) and
optional AI narrative generation on top.
"""
from app.extensions import db
from app.ai.matching import compute_match
from app.ai.provider_factory import get_provider
from app.ai.prompts.narrative import build_match_narrative_prompt, build_improvement_tips_prompt
from app.ai.usage import record_usage
from app.models.ai import JobMatch
from app.models.user import utcnow


def get_or_compute_match(user, job):
    """Returns a persisted JobMatch, recomputing if missing or stale (profile
    edited since the cached computation)."""
    profile = user.profile
    profile_updated_at = profile.updated_at if profile else None

    existing = JobMatch.query.filter_by(user_id=user.id, job_id=job.id).first()
    if existing and existing.profile_updated_at_snapshot == profile_updated_at:
        return existing

    result = compute_match(profile, job)

    if existing:
        match = existing
    else:
        match = JobMatch(user_id=user.id, job_id=job.id)
        db.session.add(match)

    match.score = result.score
    match.strengths = result.strengths
    match.gaps = [{"label": g.label, "status": g.status, "note": g.note} for g in result.gaps]
    match.recommendation = result.recommendation
    match.skipped_categories = result.skipped_categories
    match.profile_updated_at_snapshot = profile_updated_at
    match.computed_at = utcnow()
    # a stale narrative could misrepresent a changed profile/job - clear it on recompute
    match.narrative_text = None
    match.improvement_tips_text = None

    db.session.commit()
    return match


def _match_result_from_cached(job_match):
    from app.ai.matching import GapItem, MatchResult

    gaps = [GapItem(**g) for g in (job_match.gaps or [])]
    return MatchResult(
        score=job_match.score,
        strengths=job_match.strengths or [],
        gaps=gaps,
        recommendation=job_match.recommendation,
        skipped_categories=job_match.skipped_categories or [],
    )


def generate_narrative(user, job, job_match):
    if job_match.narrative_text:
        return job_match.narrative_text

    provider = get_provider()
    system, prompt = build_match_narrative_prompt(user.profile, job, _match_result_from_cached(job_match))
    response = provider.complete(system, prompt, max_tokens=400)

    if provider.provider_name != "mock":
        record_usage(user.id, "match_narrative", response)

    job_match.narrative_text = response.text
    job_match.narrative_provider = response.provider
    job_match.narrative_generated_at = utcnow()
    db.session.commit()
    return response.text


def generate_improvement_tips(user, job, job_match):
    if job_match.improvement_tips_text:
        return job_match.improvement_tips_text

    provider = get_provider()
    system, prompt = build_improvement_tips_prompt(user.profile, job, _match_result_from_cached(job_match))
    response = provider.complete(system, prompt, max_tokens=400)

    if provider.provider_name != "mock":
        record_usage(user.id, "improvement_tips", response)

    job_match.improvement_tips_text = response.text
    job_match.improvement_tips_provider = response.provider
    job_match.improvement_tips_generated_at = utcnow()
    db.session.commit()
    return response.text
