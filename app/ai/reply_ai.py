"""Orchestrates AI classification and reply-drafting for detected Gmail
replies (spec sections 31/32). Mock mode never fakes a classification or a
contextual reply - unlike cover letters, there's no reliable non-AI way to
meaningfully respond to arbitrary incoming text, so mock mode is honest
about that rather than guessing."""
from flask_babel import lazy_gettext as _l, gettext as _

from app.ai.facts import format_candidate_facts
from app.ai.provider import AIProviderError
from app.ai.provider_factory import get_provider
from app.ai.prompts.email_classification import build_classification_prompt
from app.ai.prompts.reply_suggestion import build_reply_prompt
from app.ai.usage import record_usage
from app.extensions import db
from app.models.integration import REPLY_INTENTS

NOT_CONFIGURED_NOTE = _l("AI classification isn't available (no AI provider is configured).")
NOT_CONFIGURED_REPLY = (
    "AI-drafted replies aren't available because no AI provider is configured "
    "(AI_PROVIDER=mock). You can still write your own reply directly in Gmail."
)


def classify_reply(user, application, message):
    provider = get_provider()
    if provider.provider_name == "mock":
        message.classified_intent = None
        message.classification_confidence = None
        # str(): NOT_CONFIGURED_NOTE is a lazy_gettext LazyString (correct -
        # it's a module-level constant, resolved fresh per request) but
        # sqlite3's DBAPI can't bind a LazyString directly to a column
        # (found via a real test failure: "Error binding parameter 3: type
        # 'LazyString' is not supported") - resolving it to a plain str
        # here, still within the active request's locale, fixes that.
        message.classification_notes = str(NOT_CONFIGURED_NOTE)
        message.classification_provider = "mock"
        db.session.commit()
        return message

    system, prompt = build_classification_prompt(application, message)
    try:
        response = provider.complete(system, prompt, max_tokens=200)
    except AIProviderError as e:
        message.classification_notes = _("Classification failed: %(error)s", error=e)
        message.classification_provider = provider.provider_name
        db.session.commit()
        return message

    record_usage(user.id, "reply_classification", response)
    intent, confidence, notes = _parse_classification(response.text)

    message.classified_intent = intent
    message.classification_confidence = confidence
    message.classification_notes = notes
    message.classification_provider = response.provider
    db.session.commit()
    return message


def _parse_classification(text):
    intent, confidence, notes = None, None, None
    for line in text.strip().splitlines():
        if line.upper().startswith("INTENT:"):
            candidate = line.split(":", 1)[1].strip().lower()
            intent = candidate if candidate in REPLY_INTENTS else "unclear"
        elif line.upper().startswith("CONFIDENCE:"):
            candidate = line.split(":", 1)[1].strip().lower()
            confidence = candidate if candidate in ("high", "medium", "low") else "low"
        elif line.upper().startswith("NOTES:"):
            notes = line.split(":", 1)[1].strip()
    return intent or "unclear", confidence or "low", notes


def generate_reply_suggestion(user, application, message):
    provider = get_provider()
    if provider.provider_name == "mock":
        message.ai_suggested_reply = NOT_CONFIGURED_REPLY
        message.ai_suggested_reply_provider = "mock"
        db.session.commit()
        return message.ai_suggested_reply

    application_context = (
        f"Position: {application.job.title}\n"
        f"Company: {application.job.company_name or 'not specified'}\n"
        f"Application status: {application.status}"
    )
    company_message = message.body_text or message.snippet or "(no content available)"

    system, prompt = build_reply_prompt(format_candidate_facts(user.profile), application_context, company_message)
    response = provider.complete(system, prompt, max_tokens=600)
    record_usage(user.id, "reply_suggestion", response)

    message.ai_suggested_reply = response.text.strip()
    message.ai_suggested_reply_provider = response.provider
    db.session.commit()
    return message.ai_suggested_reply
