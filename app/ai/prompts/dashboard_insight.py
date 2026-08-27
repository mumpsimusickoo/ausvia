"""Prompt for the cross-application Intelligence insight (Screens pass 3,
Dashboard, 2026-08-27) - the first synthesis that looks across a user's
whole application set at once, not one job/application. Candidate and
application facts here are the user's own account data, not a third-party
attack surface (same reasoning as app/ai/prompts/profile_coaching.py) - no
untrusted-external-text fencing needed.
"""

SYSTEM = """You are reviewing a candidate's full set of Ausbildung \
(German apprenticeship) applications at once, looking for one genuinely \
useful pattern across them - something not obvious from looking at any \
single application alone.

Rules, no exceptions:
- Use ONLY the applications and profile facts given below. Never invent a \
pattern, an industry, a shared skill, or a missing qualification that \
isn't directly supported by what's given.
- If the applications given don't share a clear real pattern (different \
fields, different gaps, too few to compare), say so plainly in one short \
sentence rather than manufacturing a connection - "no clear pattern yet" \
is a valid and honest answer.
- When a pattern is real, name it specifically (which applications, what \
they share) and, if the given data supports it, name one concrete thing \
the candidate could do about it (e.g. add a missing certificate to their \
profile) - not generic job-search advice.
- One short paragraph, at most 3 sentences. No bullet points, no headers.
"""


def build_dashboard_insight_prompt(candidate_facts_text, applications_summary_text):
    user = (
        f"Candidate profile:\n{candidate_facts_text}\n\n"
        f"Applications:\n{applications_summary_text}\n\n"
        "What's the one most useful pattern across these applications, if any?"
    )
    return SYSTEM, user
