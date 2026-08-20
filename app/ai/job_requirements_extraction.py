"""
AI-assisted structured extraction of skills/language requirements and
application contact info from an Arbeitsagentur job description
(job-description extraction pass), chained from app/jobs/ingest.py's
enrich_job_detail() via a background task (app/tasks/runner.py::
submit_task) - never run inline during a request.

Contact-info extraction (contact-extraction pass) was added as one
extended call rather than a second, separate AI call: it fires off the
exact same trigger as skills extraction already does (enrich_job_detail()
succeeding, via the same background task), reads the same job description,
and the response-validation shape it needs (parse JSON, ground every
value against the text the AI was actually shown) is identical in kind to
what skills/languages already required - a second call would mean a
second real API cost and a second failure-isolation path for no benefit
over extending the one already here.

Deliberately conservative: the deterministic section-isolation step
(app/jobs/requirements_section.py) narrows what the AI is shown - the
requirements section for skills/languages, a separate, independently
isolated contact/application section for contact_person/contact_email -
to a posting's actual relevant text when one is confidently found, so the
AI never even sees curriculum/duties/marketing text for either purpose.
The AI's own output is then validated so every extracted value must
appear, case-insensitively, in the specific text block it was shown for
that purpose - a response naming a skill or contact detail absent from
that text is rejected outright, not partially trusted. That grounding
check, not the prompt's own instructions, is the load-bearing
anti-hallucination guarantee here, for skills/languages and for
contact_person/contact_email alike. contact_email additionally gets a
basic format sanity check (must contain "@", look roughly email-shaped) -
a cheap extra safety net alongside grounding, not a replacement for it:
a well-formed-looking string can still be rejected for not grounding, and
a grounded string can still be rejected for not looking like an email.

job.contact_person/job.contact_email are only ever filled when currently
empty - same "fill only if empty" discipline app/jobs/dedupe.py's
merge_missing_fields() already uses, so a value the user already typed in
manually is never silently overwritten by an extraction result.

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
import re

from app.extensions import db
from app.ai.prompts.job_requirements_extraction import build_extraction_prompt
from app.ai.provider import AIProviderError
from app.ai.provider_factory import get_provider
from app.ai.usage import record_usage
from app.jobs.requirements_section import extract_contact_section, extract_requirements_section
from app.models.ai import JobMatch
from app.models.job import Job
from app.utils.logging import log_event

logger = logging.getLogger(__name__)

MAX_SKILLS = 15
MAX_LANGUAGES = 5

# Cheap extra safety net for contact_email, alongside (not instead of) the
# grounding check - deliberately simple ("looks roughly like an email"),
# not full RFC 5322 validation, which isn't the point here.
EMAIL_SHAPE_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _grounded_contact_value(value, contact_text_lower):
    """Returns the stripped value if it's a non-empty string that appears
    (case-insensitively) as a literal substring of the contact-section
    text the AI was actually shown for this purpose - None otherwise.
    Unlike skills/languages, contact_person/contact_email are OPTIONAL
    keys in the response schema (see _validate_and_ground): a missing key,
    or a value that fails to ground, is simply treated as "not found",
    never as making the whole response malformed - most postings won't
    state a specific contact person, and that's the correct, expected
    result, not a failure."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value:
        return None
    if value.lower() not in contact_text_lower:
        return None
    return value


def _validate_and_ground(raw_text, source_text, contact_text):
    """Parses the AI's JSON response and strictly validates it structurally.
    Returns (skills, languages, contact_person, contact_email) - skills/
    languages are plain lists of strings grounded against source_text
    (unchanged behavior); contact_person/contact_email are each either a
    grounded string (grounded against contact_text, the separately
    isolated application/contact section - see module docstring for why
    this is a different text block than source_text) or None. Returns
    None (not a tuple) if the response is structurally malformed for
    skills/languages specifically (not JSON, wrong shape, wrong types) -
    a different, harder failure than "found nothing". contact_person/
    contact_email being absent, null, or the wrong type never counts as
    malformed on their own - they're optional."""
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

    contact_text_lower = contact_text.lower()

    contact_person = _grounded_contact_value(data.get("contact_person"), contact_text_lower)

    contact_email = _grounded_contact_value(data.get("contact_email"), contact_text_lower)
    if contact_email and not EMAIL_SHAPE_RE.match(contact_email):
        contact_email = None  # grounded, but doesn't look like an email - discard anyway

    return grounded_skills, grounded_languages, contact_person, contact_email


def extract_job_requirements(job_id, user_id):
    """Runs at most once per canonical Job - gated on job.skills is None,
    mirroring enrich_job_detail()'s own idempotency pattern (an empty list
    means "ran, found nothing safely usable", distinct from None, "never
    attempted" - both are falsy but not conflated here). Always leaves the
    Job in a valid state: either genuinely untouched (AI unavailable,
    provider error, or a malformed response - none of these count as a
    completed attempt) or with a validated, source-grounded skills list
    and (when found and not already manually set) contact_person/
    contact_email.

    The same job.skills-is-None gate governs contact extraction too, since
    both run in one combined call - a job whose skills were already
    extracted before this feature existed won't be retroactively
    backfilled with contact info by a later view. Same known v1
    limitation as skills extraction's own (see the comment below): nothing
    re-triggers this today, enrich_job_detail() only fires once per job.

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

    contact_section_text, contact_found = extract_contact_section(job.description)
    # Deliberately NOT falling back to the full description here the way
    # source_text does above - that fallback exists so skills extraction
    # still has *something* to read when no section was isolated, but the
    # full description can contain curriculum/marketing text (exactly what
    # the isolators exist to keep out of view). A static placeholder keeps
    # that guarantee intact for contact extraction too: nothing to ground
    # against means contact_person/contact_email correctly come back None.
    contact_text = contact_section_text if contact_found else "(no distinct application/contact section identified)"

    system, prompt = build_extraction_prompt(source_text, contact_text)
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

    validated = _validate_and_ground(response.text, source_text, contact_text)
    if validated is None:
        log_event(
            "job_source",
            f"Requirements extraction for job {job.id} returned a malformed response - fields left untouched.",
            level="warning", user_id=user_id,
        )
        return "Extraction response was malformed - fields left untouched."

    skills, languages, contact_person, contact_email = validated
    job.skills = skills
    # languages intentionally not persisted to job.language_requirements -
    # see module docstring.

    filled = []
    if contact_person and not job.contact_person:
        job.contact_person = contact_person
        filled.append("contact person")
    if contact_email and not job.contact_email:
        job.contact_email = contact_email
        filled.append("contact email")

    db.session.commit()

    # contact_person/contact_email are never score-relevant (app/ai/
    # matching.py's compute_match() doesn't read either), so filling them
    # doesn't need to invalidate any cached JobMatch - only job.skills
    # being set does, exactly as before.
    JobMatch.query.filter_by(job_id=job.id).delete()
    db.session.commit()

    contact_note = f"; {', '.join(filled)} filled" if filled else ""
    return (
        f"Extracted {len(skills)} skill(s); {len(languages)} language mention(s) "
        f"detected (not persisted){contact_note}."
    )
