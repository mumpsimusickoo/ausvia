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
    match.category_scores = result.category_scores
    match.profile_updated_at_snapshot = profile_updated_at
    match.computed_at = utcnow()
    # a stale narrative could misrepresent a changed profile/job - clear it on recompute
    match.narrative_text = None
    match.improvement_tips_text = None

    db.session.commit()
    return match


def get_or_compute_matches(user, jobs):
    """Batched sibling of get_or_compute_match(), for the search results page
    (Screens pass 4, 2026-08-28) - sorting search results by score requires
    every result scored before the sort happens, not lazily per card.

    get_or_compute_match() does one SELECT plus one commit per job - fine for
    a single card, measured at ~34ms/job cold on this app's real dev data
    when called in a loop (~1.7s for 50 jobs). compute_match() itself is not
    the cost (~0.24ms/job, negligible even at hundreds of jobs) - the N+1
    query/commit pattern is. This does one SELECT for every already-cached
    match in the batch and one commit at the end, regardless of batch size -
    measured at ~4.4ms/job cold, ~0.19ms/job warm on the same data (a ~8x
    and ~26x improvement respectively). See DECISIONS.md for the full
    numbers and the compute-on-search decision they informed.

    Returns {job.id: JobMatch}. Same staleness contract as
    get_or_compute_match() (profile_updated_at_snapshot) - this changes how
    efficiently the batch is fetched/recomputed, not when a score goes
    stale."""
    if not jobs:
        return {}

    profile = user.profile
    profile_updated_at = profile.updated_at if profile else None

    existing_by_job_id = {
        m.job_id: m
        for m in JobMatch.query.filter_by(user_id=user.id).filter(JobMatch.job_id.in_([j.id for j in jobs])).all()
    }

    result_by_job_id = {}
    for job in jobs:
        match = existing_by_job_id.get(job.id)
        if match and match.profile_updated_at_snapshot == profile_updated_at:
            result_by_job_id[job.id] = match
            continue

        computed = compute_match(profile, job)
        if match is None:
            match = JobMatch(user_id=user.id, job_id=job.id)
            db.session.add(match)

        match.score = computed.score
        match.strengths = computed.strengths
        match.gaps = [{"label": g.label, "status": g.status, "note": g.note} for g in computed.gaps]
        match.recommendation = computed.recommendation
        match.skipped_categories = computed.skipped_categories
        match.category_scores = computed.category_scores
        match.profile_updated_at_snapshot = profile_updated_at
        match.computed_at = utcnow()
        match.narrative_text = None
        match.improvement_tips_text = None
        result_by_job_id[job.id] = match

    db.session.commit()
    return result_by_job_id


# recommendation -> short label for the search results card. Mirrors
# app/ai/matching.py's RECOMMENDATION_THRESHOLDS labels, not a re-derivation
# from the raw score - the score->recommendation mapping already happened
# once in compute_match(), this just names it for display.
MATCH_LABELS = {
    "strong_candidate": "Strong match",
    "possible_candidate": "Good match",
    "significant_gaps": "Some gaps",
    "weak_match": "Weak match",
    "insufficient_data": "Not scored",
}


def match_label(recommendation):
    return MATCH_LABELS.get(recommendation, "Not scored")


_CATEGORY_DISPLAY_NAMES = {
    "skills": "skills", "language": "language", "education": "education",
    "location": "location", "start_date": "start date",
}


def summarize_match_line(job_match):
    """One-line strengths/gaps summary for a search result card - mirrors
    the bundle's own construction exactly ("Alle Fähigkeiten erfüllt" / "All
    skills met", "Sprache und Ort erfüllt" / "Language and location met"):
    name which *categories* were fully satisfied, not raw strength strings
    (those mix formats across categories - a skill name, a language
    proficiency sentence, an "Education background aligns: X" sentence -
    and read poorly concatenated). Built from category_scores, the same
    per-category numbers match_band() already renders, not a new analysis.
    Deterministic string formatting only, no AI call. Returns None when
    there's nothing to summarize (no profile, or no category was evaluated
    at all)."""
    if job_match is None or job_match.score is None:
        return None

    category_scores = job_match.category_scores or {}
    gaps = job_match.gaps or []
    if not category_scores and not gaps:
        return None

    fully_met = [cat for cat, score in category_scores.items() if score == 100]
    parts = []
    if fully_met and len(fully_met) == len(category_scores):
        parts.append("All requirements met")
    elif fully_met:
        names = [_CATEGORY_DISPLAY_NAMES.get(c, c) for c in fully_met]
        parts.append(f"{' and '.join(names).capitalize()} met")
    if gaps:
        gap_notes = [g.get("note") or g.get("label") for g in gaps[:2]]
        parts.append(", ".join(n for n in gap_notes if n))

    return " · ".join(p for p in parts if p)


def _match_result_from_cached(job_match):
    from app.ai.matching import GapItem, MatchResult

    gaps = [GapItem(**g) for g in (job_match.gaps or [])]
    return MatchResult(
        score=job_match.score,
        strengths=job_match.strengths or [],
        gaps=gaps,
        recommendation=job_match.recommendation,
        skipped_categories=job_match.skipped_categories or [],
        category_scores=job_match.category_scores or {},
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
