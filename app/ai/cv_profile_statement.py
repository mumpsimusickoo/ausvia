"""AI-generated short CV profile statement ("Kurzprofil") for one
application - option A from the CV-tailoring investigation. Grounded in
the candidate's real profile and the job's real stored facts, same
staleness/caching pattern as InterviewPrep (keyed per application, since
that's the natural lookup on the page it's shown on, and an Application is
already unique per (user, job)). Purely informational: never inserted into
app/applications/pdf_package.py or the submitted package, and never
modifies the user's uploaded CV document - the user copies this text into
their own separately maintained CV, same as interview prep and the
follow-up email.

Unlike interview prep (a private study aid, never submitted anywhere),
this text is meant to be copied into a real, submitted document - so it
gets the same two-pass generate-then-validate treatment as
app/ai/cover_letter.py, not just the system prompt's instruction alone.
"""
from flask_babel import lazy_gettext as _l

from app.extensions import db
from app.ai.facts import format_candidate_facts, format_job_facts
from app.ai.prompts.cv_profile_statement import build_generation_prompt, build_validation_prompt
from app.ai.provider_factory import get_provider
from app.ai.usage import record_usage
from app.i18n import get_locale
from app.models.ai import CvProfileStatement
from app.models.user import utcnow

# i18n pass 3: this is a deterministic app status message, not AI-generated
# content, so it follows the UI language like everything else pass 2
# translated - str() at the assignment site resolves the LazyString to a
# plain string within the active request's locale (a bare LazyString can't
# bind to a SQLite column - see DECISIONS.md's i18n pass 2 entry for the
# same bug found and fixed in app/ai/reply_ai.py).
NOT_CONFIGURED_TEXT = _l(
    "AI CV profile statement generation isn't available because no AI "
    "provider is configured (AI_PROVIDER=mock). The profile and job details "
    "on this page are real; this would only be an AI-generated summary "
    "layered on top."
)


def get_cv_profile_statement(application):
    return CvProfileStatement.query.filter_by(application_id=application.id).first()


def generate_statement_text(user, job, locale):
    """Returns (text, provider_name) - the raw AI generation, before
    validation. Mirrors app/ai/cover_letter.py's generate_cover_letter()."""
    provider = get_provider()
    system, prompt = build_generation_prompt(format_candidate_facts(user.profile), format_job_facts(job), locale)
    response = provider.complete(system, prompt, max_tokens=400)
    record_usage(user.id, "cv_profile_statement_generation", response)
    return response.text.strip(), response.provider


def validate_statement_text(user, job, statement_text, locale):
    """Returns the final text to store: unchanged if the validation pass
    finds no issues, corrected if it does. Mirrors
    app/ai/cover_letter.py's validate_cover_letter()'s AI-path parsing -
    the same guard against a fabricated/ungrounded response other AI
    features rely on, not something novel to this feature."""
    provider = get_provider()
    system, prompt = build_validation_prompt(
        format_candidate_facts(user.profile), format_job_facts(job), statement_text, locale
    )
    response = provider.complete(system, prompt, max_tokens=700)
    record_usage(user.id, "cv_profile_statement_validation", response)

    text = response.text.strip()
    if text.startswith("CORRECTED:"):
        return text[len("CORRECTED:"):].strip()
    return statement_text


def generate_cv_profile_statement(user, application):
    profile = user.profile
    profile_updated_at = profile.updated_at if profile else None
    locale = get_locale()

    existing = get_cv_profile_statement(application)
    if (
        existing and existing.statement_text
        and existing.profile_updated_at_snapshot == profile_updated_at
        and existing.generated_locale == locale
    ):
        return existing

    statement = existing or CvProfileStatement(application_id=application.id)

    provider = get_provider()
    if provider.provider_name == "mock":
        statement.statement_text = str(NOT_CONFIGURED_TEXT)
        statement.provider = "mock"
    else:
        raw_text, provider_name = generate_statement_text(user, application.job, locale)
        statement.statement_text = validate_statement_text(user, application.job, raw_text, locale)
        statement.provider = provider_name

    statement.profile_updated_at_snapshot = profile_updated_at
    statement.generated_locale = locale
    statement.generated_at = utcnow()
    if not existing:
        db.session.add(statement)
    db.session.commit()
    return statement
