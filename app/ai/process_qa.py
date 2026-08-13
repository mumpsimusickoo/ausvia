"""Grounded AI answers to a fixed set of common Ausbildung process/
terminology questions (Phase 9). Deliberately built as a constrained,
typed-question picker rather than open free-text chat: this app has no
chat-style UI anywhere today, and introducing one is a bigger design
decision than a single feature pass should make unilaterally (see this
phase's report for the flagged recommendation either way). The fixed
question set lives in app/models/ai.py's PROCESS_QA_QUESTIONS, shared
between the route (to validate a question_key) and the template (to render
the picker).

Same staleness/caching pattern as JobMatch/CompanyInsight, keyed per (user,
question) - one question ("Should I mention unrelated work experience?")
is grounded in the candidate's own profile, not just general domain
knowledge, so answers aren't safely shareable across users even though most
of the other questions are pure domain knowledge. No deterministic core -
even the general-knowledge questions benefit from natural phrasing a
template can't easily provide - so mock mode declines honestly, same
pattern as app/companies/insights.py.
"""
from app.extensions import db
from app.ai.facts import format_candidate_facts
from app.ai.prompts.process_qa import build_process_qa_prompt
from app.ai.provider_factory import get_provider
from app.ai.usage import record_usage
from app.models.ai import ProcessQAAnswer, PROCESS_QA_QUESTIONS
from app.models.user import utcnow

NOT_CONFIGURED_TEXT = (
    "AI answers aren't available because no AI provider is configured "
    "(AI_PROVIDER=mock)."
)


def get_process_qa_answer(user, question_key):
    return ProcessQAAnswer.query.filter_by(user_id=user.id, question_key=question_key).first()


def generate_process_qa_answer(user, question_key):
    if question_key not in PROCESS_QA_QUESTIONS:
        raise ValueError(f"Unknown process Q&A question key: {question_key!r}")

    profile = user.profile
    profile_updated_at = profile.updated_at if profile else None

    existing = get_process_qa_answer(user, question_key)
    if existing and existing.answer_text and existing.profile_updated_at_snapshot == profile_updated_at:
        return existing

    answer = existing or ProcessQAAnswer(user_id=user.id, question_key=question_key)

    provider = get_provider()
    if provider.provider_name == "mock":
        answer.answer_text = NOT_CONFIGURED_TEXT
        answer.provider = "mock"
    else:
        question_text = PROCESS_QA_QUESTIONS[question_key]
        candidate_facts_text = format_candidate_facts(profile)
        system, prompt = build_process_qa_prompt(question_text, candidate_facts_text)
        response = provider.complete(system, prompt, max_tokens=300)
        record_usage(user.id, "process_qa", response)
        answer.answer_text = response.text
        answer.provider = response.provider

    answer.profile_updated_at_snapshot = profile_updated_at
    answer.generated_at = utcnow()
    if not existing:
        db.session.add(answer)
    db.session.commit()
    return answer
