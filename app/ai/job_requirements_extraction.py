"""
AI-assisted structured extraction of skills/language requirements from an
Arbeitsagentur job description (job-description extraction pass), chained
from app/jobs/ingest.py's enrich_job_detail() via a background task
(app/tasks/runner.py::submit_task) - never run inline during a request.

Deliberately conservative: the deterministic section-isolation step
(app/jobs/requirements_section.py) narrows what the AI is shown to a
posting's actual requirements section when one is confidently found; the
AI's own output is then validated so every extracted skill must appear,
case-insensitively, in the text it was actually given - a response naming
a skill absent from the source text is rejected outright, not partially
trusted. That grounding check, not the prompt's own instructions, is the
load-bearing anti-hallucination guarantee here.

Job.language_requirements is deliberately NOT written by this pass, even
though the AI is asked to report explicit language mentions (and that
detection is validated/tested the same way skills are). The existing
{"language", "level"} shape has no way to represent "explicitly required,
level unspecified" safely under the current _score_language(): an entry
with no CEFR-comparable level contributes zero points for *every*
candidate, including a native speaker, which is worse than leaving the
category skipped entirely (see the investigation this was built from).
Populating it without also changing that scoring branch - explicitly not
done in this pass - would make matching worse, not better. Detection
stays built and tested so turning this on later is a small, isolated
change once that scoring question is separately resolved.
"""
import json
import logging

from app.extensions import db
from app.ai.prompts.job_requirements_extraction import build_extraction_prompt
from app.ai.provider import AIProviderError
from app.ai.provider_factory import get_provider
from app.ai.usage import record_usage
from app.jobs.requirements_section import extract_requirements_section
from app.models.ai import JobMatch
from app.models.job import Job
from app.utils.logging import log_event

logger = logging.getLogger(__name__)

MAX_SKILLS = 15
MAX_LANGUAGES = 5


def _validate_and_ground(raw_text, source_text):
    """Parses the AI's JSON response and strictly validates it structurally.
    Returns (skills, languages) - plain lists of strings, filtered to only
    entries actually present (case-insensitively) in source_text - or None
    if the response is structurally malformed (not JSON, wrong shape, wrong
    types), which is a different, harder failure than "found nothing"."""
    if not isinstance(raw_text, str):
        return None
    try:
        data = json.loads(raw_text.strip())
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    if "skills" not in data or "languages" not in data:
        return None

    skills = data["skills"]
    languages = data["languages"]
    if not isinstance(skills, list) or not isinstance(languages, list):
        return None
    if not all(isinstance(s, str) for s in skills):
        return None
    if not all(isinstance(l, str) for l in languages):
        return None

    source_lower = source_text.lower()

    grounded_skills = []
    for skill in skills[:MAX_SKILLS]:
        skill = skill.strip()
        if skill and skill.lower() in source_lower and skill not in grounded_skills:
            grounded_skills.append(skill)

    grounded_languages = []
    for language in languages[:MAX_LANGUAGES]:
        language = language.strip()
        if language and language.lower() in source_lower and language not in grounded_languages:
            grounded_languages.append(language)

    return grounded_skills, grounded_languages


def extract_job_requirements(job_id, user_id):
    """Runs at most once per canonical Job - gated on job.skills is None,
    mirroring enrich_job_detail()'s own idempotency pattern (an empty list
    means "ran, found nothing safely usable", distinct from None, "never
    attempted" - both are falsy but not conflated here). Always leaves the
    Job in a valid state: either genuinely untouched (AI unavailable,
    provider error, or a malformed response - none of these count as a
    completed attempt) or with a validated, source-grounded skills list.

    Called from app/jobs/routes.py's detail() route via submit_task(), not
    inline - job_id/user_id are passed as plain values (not the ORM
    objects) since this runs in a worker thread with its own app context,
    per submit_task()'s own contract.
    """
    job = db.session.get(Job, job_id)
    if job is None:
        return "Job not found."
    if job.skills is not None:
        return "Already extracted."
    if not job.description:
        return "No description to extract from."

    provider = get_provider()
    if provider.provider_name == "mock":
        # Declines honestly, same as every other AI feature - job.skills
        # stays None (not []) so a later real extraction isn't permanently
        # blocked by this check alone. In practice nothing re-triggers it
        # today (enrich_job_detail() only fires once per job), so this is
        # a known v1 limitation, not a full fix - see the written report.
        return "Mock mode - no AI provider configured, nothing extracted."

    section_text, found = extract_requirements_section(job.description)
    source_text = section_text if found else job.description

    system, prompt = build_extraction_prompt(source_text)
    try:
        response = provider.complete(system, prompt, max_tokens=400)
    except AIProviderError as e:
        log_event(
            "job_source",
            f"Requirements extraction failed for job {job.id}: {e}",
            level="warning", user_id=user_id,
        )
        return f"Extraction failed: {e}"

    record_usage(user_id, "job_requirements_extraction", response)

    validated = _validate_and_ground(response.text, source_text)
    if validated is None:
        log_event(
            "job_source",
            f"Requirements extraction for job {job.id} returned a malformed response - fields left untouched.",
            level="warning", user_id=user_id,
        )
        return "Extraction response was malformed - fields left untouched."

    skills, languages = validated
    job.skills = skills
    # languages intentionally not persisted to job.language_requirements -
    # see module docstring.
    db.session.commit()

    JobMatch.query.filter_by(job_id=job.id).delete()
    db.session.commit()

    return f"Extracted {len(skills)} skill(s); {len(languages)} language mention(s) detected (not persisted)."
