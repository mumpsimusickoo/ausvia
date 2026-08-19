"""
Structured, deterministic candidate-job matching engine (spec section 16/17).
The score and gap analysis are always computed here in plain Python from the
candidate profile and job data actually on file - never guessed by an LLM.
AI (see app/ai/prompts) only ever adds narrative explanation on top of these
already-computed facts, never invents the numbers.
"""
import re
from dataclasses import dataclass, field

from app.models.profile import CEFR_LEVELS

CEFR_RANK = {level: i for i, level in enumerate(CEFR_LEVELS)}

# category weight when both sides have usable data; redistributed proportionally
# among only the categories that could actually be evaluated for a given job
CATEGORY_WEIGHTS = {
    "skills": 30,
    "language": 25,
    "education": 20,
    "location": 15,
    "start_date": 10,
}

RECOMMENDATION_THRESHOLDS = (
    (80, "strong_candidate"),
    (60, "possible_candidate"),
    (40, "significant_gaps"),
)

# Job attribute names that actually feed compute_match() below - distinct
# from CATEGORY_WEIGHTS' category labels (e.g. "language"/"education" name
# categories, not the job.language_requirements/job.education_requirements
# attributes compute_match() actually reads). Used by callers that mutate a
# Job outside the normal enrichment/extraction paths (e.g. dedupe's
# merge_missing_fields()) to decide whether a change could have affected an
# already-cached JobMatch, without hardcoding this list at each call site.
SCORE_RELEVANT_JOB_FIELDS = frozenset({
    "skills", "language_requirements", "education_requirements", "federal_state", "start_date",
})


@dataclass
class GapItem:
    label: str
    status: str  # "matched" | "preferred_missing" | "required_missing" | "unknown"
    note: str | None = None


@dataclass
class MatchResult:
    score: int | None
    strengths: list[str] = field(default_factory=list)
    gaps: list[GapItem] = field(default_factory=list)
    recommendation: str = "insufficient_data"
    skipped_categories: list[str] = field(default_factory=list)
    # per-category 0-100 score for categories that had usable data on both
    # sides; a skipped category is simply absent here, not zero (zero would
    # falsely read as "bad fit" rather than "not evaluated")
    category_scores: dict = field(default_factory=dict)


def _tokenize(text):
    return set(re.findall(r"[a-zA-ZäöüÄÖÜß]+", (text or "").lower()))


def _score_skills(profile, job):
    job_skills = [s.strip() for s in (job.skills or []) if s and s.strip()]
    if not job_skills:
        return None, [], []

    candidate_skill_names = [s.name.strip().lower() for s in profile.skills]
    strengths, gaps = [], []
    matched = 0
    for skill in job_skills:
        skill_lower = skill.lower()
        hit = any(
            skill_lower in cand or cand in skill_lower for cand in candidate_skill_names
        )
        if hit:
            matched += 1
            strengths.append(skill)
        else:
            gaps.append(GapItem(label=skill, status="preferred_missing"))

    ratio = matched / len(job_skills)
    return ratio, strengths, gaps


def _score_language(profile, job):
    requirements = job.language_requirements or []
    if not requirements:
        return None, [], []

    candidate_langs = {lang.name.strip().lower(): lang.level for lang in profile.languages}
    strengths, gaps = [], []
    points = 0
    for req in requirements:
        language = (req.get("language") or "").strip()
        required_level = (req.get("level") or "").strip()
        if not language:
            continue
        candidate_level = candidate_langs.get(language.lower())

        if candidate_level is None:
            gaps.append(GapItem(label=f"{language} ({required_level})", status="required_missing"))
            continue

        required_rank = CEFR_RANK.get(required_level)
        candidate_rank = CEFR_RANK.get(candidate_level)
        if required_rank is None or candidate_rank is None:
            gaps.append(GapItem(label=f"{language} ({required_level})", status="unknown"))
            continue

        if candidate_rank >= required_rank:
            points += 1
            strengths.append(f"{language} {candidate_level} (required: {required_level})")
        else:
            gaps.append(
                GapItem(
                    label=f"{language} {required_level} preferred",
                    status="preferred_missing",
                    note=f"candidate has {candidate_level}",
                )
            )

    return points / len(requirements), strengths, gaps


def _score_education(profile, job):
    if not job.education_requirements:
        return None, [], []

    job_tokens = _tokenize(job.education_requirements) | _tokenize(job.title)
    if not job_tokens:
        return None, [], []

    best_overlap = 0
    best_entry = None
    for entry in profile.education_entries:
        entry_tokens = _tokenize(entry.degree) | _tokenize(entry.field)
        overlap = len(entry_tokens & job_tokens)
        if overlap > best_overlap:
            best_overlap = overlap
            best_entry = entry

    if best_entry and best_overlap > 0:
        label = " / ".join(p for p in [best_entry.degree, best_entry.field] if p)
        return 1.0, [f"Education background aligns: {label}"], []

    return 0.0, [], [
        GapItem(
            label="Education / field of study",
            status="unknown",
            note="Could not confirm alignment automatically - review manually.",
        )
    ]


def _score_location(profile, job):
    preference = profile.preference
    if not preference or not preference.locations:
        return 1.0, ["Open to opportunities Germany-wide"], []

    job_places = {p.lower() for p in [job.location, job.federal_state] if p}
    preferred_places = {p.strip().lower() for p in preference.locations if p.strip()}

    if job_places & preferred_places:
        return 1.0, [f"Location matches preference ({job.location or job.federal_state})"], []

    if preference.open_to_relocation:
        return 0.5, [], [
            GapItem(
                label="Location",
                status="preferred_missing",
                note=f"{job.location or 'This location'} is outside stated preferences, but candidate is open to relocation.",
            )
        ]

    return 0.0, [], [
        GapItem(
            label="Location",
            status="required_missing",
            note=f"{job.location or 'This location'} is outside stated preferences and candidate is not open to relocation.",
        )
    ]


def _score_start_date(profile, job):
    preference = profile.preference
    if not preference or not preference.desired_start_date or not job.start_date:
        return None, [], []

    wanted = re.search(r"\d{4}", preference.desired_start_date)
    actual = re.search(r"\d{4}", job.start_date)
    if not wanted or not actual:
        return None, [], []

    if wanted.group() == actual.group():
        return 1.0, [f"Start date matches ({job.start_date})"], []
    return 0.0, [], [
        GapItem(
            label="Start date",
            status="preferred_missing",
            note=f"Job starts {job.start_date}, candidate prefers {preference.desired_start_date}.",
        )
    ]


def compute_match(profile, job):
    if profile is None:
        return MatchResult(score=None, recommendation="insufficient_data")

    scorers = {
        "skills": _score_skills,
        "language": _score_language,
        "education": _score_education,
        "location": _score_location,
        "start_date": _score_start_date,
    }

    strengths, gaps, skipped = [], [], []
    category_scores = {}
    earned = 0.0
    possible = 0

    for category, scorer in scorers.items():
        ratio, cat_strengths, cat_gaps = scorer(profile, job)
        if ratio is None:
            skipped.append(category)
            continue
        weight = CATEGORY_WEIGHTS[category]
        possible += weight
        earned += ratio * weight
        category_scores[category] = round(100 * ratio)
        strengths.extend(cat_strengths)
        gaps.extend(cat_gaps)

    if possible == 0:
        return MatchResult(
            score=None, strengths=strengths, gaps=gaps,
            recommendation="insufficient_data", skipped_categories=skipped,
            category_scores=category_scores,
        )

    score = round(100 * earned / possible)
    recommendation = "weak_match"
    for threshold, label in RECOMMENDATION_THRESHOLDS:
        if score >= threshold:
            recommendation = label
            break

    return MatchResult(
        score=score, strengths=strengths, gaps=gaps,
        recommendation=recommendation, skipped_categories=skipped,
        category_scores=category_scores,
    )
